"""리포트 생성 작업: 서버 메모리에서 단계별로 진행하고, 끝까지 성공했을 때만 DB에 저장한다.

서버를 다시 켜면 진행 중이던 작업은 사라진다(MVP). 실패 단계 표시는 이 작업 상태에 담기고, 단계별 [다시 시도]는 Phase 8.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field

import httpx

from . import db
from .calc import analyze
from .dart import DartError
from .fin_collect import NoFinancialsError, collect_company, to_year_list
from .fin_fetch import FinancialsFetcher
from .recent_results import collect_recent
from .report_store import save_report

log = logging.getLogger("uvicorn.error")

STEPS = (("collect", "재무 수집"), ("recent", "최근 실적 수집"), ("calc", "계산"), ("save", "저장"))
MAX_KEPT_JOBS = 50


def new_fetcher(client: httpx.AsyncClient) -> FinancialsFetcher:  # 테스트에서 바꿀 수 있게 따로 둔다
    return FinancialsFetcher(client)


@dataclass
class Job:
    id: str
    corp_code: str
    corp_name: str
    status: str = "running"  # running | done | failed
    steps: list[dict] = field(default_factory=lambda: [{"key": k, "label": l, "status": "pending"} for k, l in STEPS])
    report_id: int | None = None
    error: dict | None = None  # {"step": 단계 키, "step_label": 단계 이름, "message": 안내}

    def to_dict(self) -> dict:
        return {"job_id": self.id, "corp_code": self.corp_code, "corp_name": self.corp_name, "status": self.status,
                "steps": self.steps, "report_id": self.report_id, "error": self.error}


class StepFailed(Exception):
    def __init__(self, message: str):
        self.message = message


class JobManager:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._tasks: set[asyncio.Task] = set()
        self._lock: asyncio.Lock | None = None
        self._lock_loop = None

    def _dart_lock(self) -> asyncio.Lock:
        """DART 호출 구간은 한 번에 한 작업만 (동시·대량 호출로 막힌 적이 있어 겹치지 않게 한다)."""
        loop = asyncio.get_running_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock, self._lock_loop = asyncio.Lock(), loop
        return self._lock

    def find_running(self, corp_code: str) -> Job | None:
        return next((j for j in self.jobs.values() if j.corp_code == corp_code and j.status == "running"), None)

    def start(self, company: dict) -> Job:
        job = Job(id=uuid.uuid4().hex, corp_code=company["corp_code"], corp_name=company["corp_name"])
        self.jobs[job.id] = job
        for old in [j for j in self.jobs.values() if j.status != "running"][:-MAX_KEPT_JOBS]:
            del self.jobs[old.id]
        task = asyncio.create_task(self._run(job, company))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: Job, company: dict) -> None:
        current = STEPS[0][0]
        step = {s["key"]: s for s in job.steps}

        def begin(key: str):
            nonlocal current
            current = key
            step[key]["status"] = "running"

        try:
            async with httpx.AsyncClient() as client, self._dart_lock():
                fetcher = new_fetcher(client)
                begin("collect")
                res = await collect_company(fetcher, job.corp_code)
                step["collect"]["status"] = "done"
                begin("recent")
                recent, recent_reason = await collect_recent(fetcher, res)
                step["recent"]["status"] = "done"
            begin("calc")
            analysis = analyze(to_year_list(res))
            step["calc"]["status"] = "done"
            begin("save")
            with db.SessionLocal() as session:
                try:
                    job.report_id = save_report(session, company, res, analysis, recent, recent_reason)
                except Exception:
                    session.rollback()
                    raise
            step["save"]["status"] = "done"
            job.status = "done"
        except (DartError, NoFinancialsError) as e:
            self._fail(job, current, str(e))
        except Exception:
            log.exception("리포트 생성 중 예상하지 못한 오류 (%s)", job.corp_name)
            self._fail(job, current, "예상하지 못한 오류가 발생했습니다. 서버 로그를 확인해 주세요")

    @staticmethod
    def _fail(job: Job, key: str, message: str) -> None:
        for s in job.steps:
            if s["key"] == key:
                s["status"] = "failed"
        label = dict(STEPS)[key]
        job.status = "failed"
        job.error = {"step": key, "step_label": label, "message": message}


manager = JobManager()
