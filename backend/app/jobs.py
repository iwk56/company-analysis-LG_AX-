"""리포트 생성 작업: 서버 메모리에서 단계별로 진행하고, 끝까지 성공했을 때만 DB에 저장한다.

서버를 다시 켜면 진행 중이던 작업은 사라진다(MVP). 실패 단계 표시는 이 작업 상태에 담기고, [다시 시도]는 같은 입력으로 처음부터 다시 만든다(재무 응답은 저장본을 쓴다).
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field

import httpx

from . import db
from .calc import analyze
from .comparison import Excluded, build_comparison, build_entry
from .dart import DartError
from .fin_collect import NoFinancialsError, collect_company, to_year_list
from .fin_fetch import FinancialsFetcher
from .recent_results import collect_recent
from .report_store import save_report

log = logging.getLogger("uvicorn.error")

STEPS = (("collect", "재무 수집"), ("recent", "최근 실적 수집"), ("competitors", "경쟁사 재무 수집"), ("calc", "계산"), ("save", "저장"))
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
    company: dict = field(default_factory=dict, repr=False)  # 다시 시도할 때 쓰는 입력 (화면 응답에는 넣지 않음)
    competitors: list = field(default_factory=list, repr=False)

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

    def retry(self, failed: Job) -> Job:
        """실패한 작업과 같은 입력으로 처음부터 다시 만든다. 이미 같은 기업이 진행 중이면 그 작업을 돌려준다."""
        return self.find_running(failed.corp_code) or self.start(failed.company, failed.competitors)

    def start(self, company: dict, competitors: list[dict]) -> Job:
        job = Job(id=uuid.uuid4().hex, corp_code=company["corp_code"], corp_name=company["corp_name"],
                  company=company, competitors=competitors)
        self.jobs[job.id] = job
        for old in [j for j in self.jobs.values() if j.status != "running"][:-MAX_KEPT_JOBS]:
            del self.jobs[old.id]
        task = asyncio.create_task(self._run(job, company, competitors))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    async def _run(self, job: Job, company: dict, competitors: list[dict]) -> None:
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
                begin("competitors")
                collected = await self._collect_competitors(fetcher, competitors)  # 데이터가 없는 회사는 제외 사유와 함께 돌아온다
                step["competitors"]["status"] = "done"
            begin("calc")
            analysis = analyze(to_year_list(res))
            comparison = self._compare(company, res, analysis, collected)
            step["calc"]["status"] = "done"
            begin("save")
            with db.SessionLocal() as session:
                try:
                    job.report_id = save_report(session, company, res, analysis, recent, recent_reason,
                                              competitors=competitors, comparison=comparison)
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
    async def _collect_competitors(fetcher: FinancialsFetcher, competitors: list[dict]) -> list[tuple[dict, object]]:
        """경쟁사를 하나씩(순차) 수집한다. 재무제표가 없으면 그 회사만 제외하고, DART 오류는 단계 실패로 올린다."""
        out: list[tuple[dict, object]] = []
        for c in competitors:
            try:
                out.append((c, await collect_company(fetcher, c["corp_code"])))
            except NoFinancialsError:
                out.append((c, "데이터 부족으로 제외 (사업보고서 재무제표 없음)"))
        return out

    @staticmethod
    def _compare(company: dict, res, analysis, collected: list[tuple[dict, object]]) -> dict:
        base_year = res.latest_year
        target = build_entry(company, res, analysis, base_year, is_target=True)
        if not hasattr(target, "values"):  # 분석 기업은 위에서 매출액이 있는 연도를 찾았으므로 보통 여기에 오지 않는다
            raise NoFinancialsError(f"분석 기업의 {base_year} 매출액을 찾지 못해 비교할 수 없습니다")
        others = [Excluded(c["corp_code"], c["corp_name"], r) if isinstance(r, str)
                  else build_entry(c, r, analyze(to_year_list(r)), base_year) for c, r in collected]
        return build_comparison(base_year, target, others)

    @staticmethod
    def _fail(job: Job, key: str, message: str) -> None:
        for s in job.steps:
            if s["key"] == key:
                s["status"] = "failed"
        label = dict(STEPS)[key]
        job.status = "failed"
        job.error = {"step": key, "step_label": label, "message": message}


manager = JobManager()
