"""리포트 생성·진행 상태·목록·상세·삭제 API (docs/spec.md F3, F7)."""
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import company_cache, report_store
from .enrich import TASKS, AlreadyRunning, enrich_report
from .corp_codes import load_listed_corps
from .dart import DartError
from .db import get_session
from .industry import is_financial
from .jobs import collect_news, manager
from .news import NewsError
from .ksic import industry_name
from .report_models import Report

router = APIRouter(prefix="/api/reports", tags=["reports"])


MAX_COMPETITORS = 4
MAX_COMMENT_LENGTH = 1000
SECTION_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")  # 섹션이 늘어도 키 모양만 맞으면 저장된다


class CreateReport(BaseModel):
    corp_code: str
    competitors: list[str] = []  # 경쟁사 고유번호 1~4곳


async def _validate_company(corp_code: str) -> dict:
    """생성할 수 있는 기업인지 확인하고 저장할 기업 정보를 돌려준다 (상장·금융업이 아닌 기업만)."""
    try:
        async with httpx.AsyncClient() as client:
            corps = await load_listed_corps(client)
            corp = next((c for c in corps if c["corp_code"] == corp_code), None)
            if corp is None:
                raise HTTPException(status_code=400, detail="상장기업 목록에서 찾을 수 없는 기업입니다. 검색 결과에서 선택해 주세요")
            cache = company_cache.load_cache()
            entry = cache.get(corp_code)
            if not company_cache.is_fresh(entry):
                entry = cache[corp_code] = await company_cache.fetch_overview(client, corp_code)
                company_cache.save_cache(cache)
    except DartError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except RuntimeError as e:  # DART_API_KEY 없음
        raise HTTPException(status_code=500, detail=str(e))
    if not company_cache.is_listed(entry):
        raise HTTPException(status_code=400, detail="현재 상장(유가증권·코스닥) 기업이 아니어서 리포트를 만들 수 없습니다")
    financial = is_financial(corp_code, entry["induty_code"])
    if financial:
        raise HTTPException(status_code=400, detail="금융업은 이 도구의 재무비율 기준과 맞지 않아 리포트를 만들 수 없습니다")
    return {"corp_code": corp_code, "corp_name": corp["corp_name"], "stock_code": corp["stock_code"],
            "industry_code": entry["induty_code"], "industry_name": industry_name(entry["induty_code"]),
            "is_financial": financial}


@router.post("", status_code=202)
async def create_report(body: CreateReport):
    """리포트 생성 작업을 시작한다. 진행 상태는 GET /api/reports/jobs/{job_id}로 확인한다."""
    corp_code = body.corp_code.strip()
    codes = list(dict.fromkeys(c.strip() for c in body.competitors))  # 중복 제거, 순서 유지
    if not codes:
        raise HTTPException(status_code=400, detail="경쟁사를 1곳 이상 선택해 주세요")
    if len(codes) > MAX_COMPETITORS:
        raise HTTPException(status_code=400, detail="최대 4곳까지 선택할 수 있습니다")
    if corp_code in codes:
        raise HTTPException(status_code=400, detail="분석 기업 자신은 경쟁사로 선택할 수 없습니다")
    running = manager.find_running(corp_code)  # 같은 기업이 이미 만들어지는 중이면 그 작업을 알려준다
    if running:
        return running.to_dict()
    company = await _validate_company(corp_code)
    competitors = []
    for code in codes:
        try:
            competitors.append(await _validate_company(code))
        except HTTPException as e:
            raise HTTPException(status_code=e.status_code, detail=f"경쟁사 선택 오류({code}): {e.detail}")
    return manager.start(company, competitors).to_dict()


@router.post("/jobs/{job_id}/retry", status_code=202)
async def retry_job(job_id: str):
    """실패한 생성 작업을 같은 입력으로 처음부터 다시 시작한다."""
    job = manager.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다 (서버를 다시 켠 경우 사라집니다)")
    if job.status != "failed":
        raise HTTPException(status_code=400, detail="실패한 작업만 다시 시도할 수 있습니다")
    return manager.retry(job).to_dict()


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = manager.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다 (서버를 다시 켠 경우 사라집니다)")
    return job.to_dict()


@router.get("")
def list_reports(q: str | None = Query(None, description="기업명 일부"), session: Session = Depends(get_session)):
    items = report_store.list_reports(session, q)
    return {"count": len(items), "items": items}


@router.get("/{report_id}")
def get_report(report_id: int, session: Session = Depends(get_session)):
    report = report_store.get_report(session, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")
    # 아직 만들지 않은 AI 작업 (기능이 나중에 생겨 기존 리포트에 없는 것 포함). 화면이 [AI 해석 만들기]를 보여주는 데 쓴다
    report["ai_pending"] = [k for k in TASKS if k not in report["enrichments"]]
    return report


class CommentBody(BaseModel):
    content: str = ""


@router.put("/{report_id}/comments/{section_key}")
def put_comment(report_id: int, section_key: str, body: CommentBody, session: Session = Depends(get_session)):
    """섹션 코멘트를 저장·수정한다. 빈 내용이면 삭제한다 (spec F6)."""
    if not SECTION_KEY.match(section_key):
        raise HTTPException(status_code=400, detail="올바르지 않은 섹션 이름입니다")
    if len(body.content) > MAX_COMMENT_LENGTH:
        raise HTTPException(status_code=400, detail=f"코멘트는 {MAX_COMMENT_LENGTH:,}자까지 쓸 수 있습니다")
    result = report_store.set_comment(session, report_id, section_key, body.content)
    if result is False:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")
    return {"section_key": section_key, "comment": result}


@router.post("/{report_id}/ai")
async def run_ai(report_id: int, session: Session = Depends(get_session)):
    """공시 확인·AI 작업 중 아직 없거나 실패한 것만 실행한다 (이미 만든 해석은 다시 만들지 않는다). 끝나면 결과 전체를 돌려준다."""
    if session.get(Report, report_id) is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")
    try:
        await enrich_report(report_id, manager.dart_lock())
    except AlreadyRunning:
        raise HTTPException(status_code=409, detail="이 리포트의 AI 해석을 이미 만드는 중입니다. 잠시 뒤 다시 확인해 주세요")
    session.expire_all()
    return {"enrichments": report_store.get_report(session, report_id)["enrichments"]}


@router.post("/{report_id}/articles/refresh")
async def refresh_articles(report_id: int, session: Session = Depends(get_session)):
    """[다시 불러오기]: 보관 기간(21일)이 지나 지운 기사를 네이버에서 새로 받는다. 끝나면 기사 목록을 돌려준다."""
    detail = report_store.get_report(session, report_id)  # 보관 기간이 지난 기사는 여기서 지워진다
    if detail is None:
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")
    if detail["articles"] is None:
        raise HTTPException(status_code=409, detail="기사 수집 기능이 생기기 전에 만든 리포트입니다. 리포트를 다시 만들어 주세요")
    if not detail["articles"]["expired"]:
        raise HTTPException(status_code=409, detail="기사 보관 기간이 아직 지나지 않았습니다")
    try:
        async with httpx.AsyncClient() as client:
            news = await collect_news(client, detail["company"]["corp_name"])
    except NewsError as e:
        raise HTTPException(status_code=502, detail=str(e))
    report_store.replace_articles(session, report_id, news)
    session.expire_all()
    return {"articles": report_store.get_report(session, report_id)["articles"]}


@router.delete("/{report_id}")
def delete_report(report_id: int, session: Session = Depends(get_session)):
    if not report_store.delete_report(session, report_id):
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")
    return {"deleted": report_id}
