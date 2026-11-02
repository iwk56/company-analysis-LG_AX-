"""리포트 생성·진행 상태·목록·상세·삭제 API (docs/spec.md F3, F7)."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import company_cache, report_store
from .corp_codes import load_listed_corps
from .dart import DartError
from .db import get_session
from .industry import is_financial
from .jobs import manager
from .ksic import industry_name

router = APIRouter(prefix="/api/reports", tags=["reports"])


class CreateReport(BaseModel):
    corp_code: str


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
    running = manager.find_running(body.corp_code.strip())  # 같은 기업이 이미 만들어지는 중이면 그 작업을 알려준다
    if running:
        return running.to_dict()
    company = await _validate_company(body.corp_code.strip())
    return manager.start(company).to_dict()


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
    return report


@router.delete("/{report_id}")
def delete_report(report_id: int, session: Session = Depends(get_session)):
    if not report_store.delete_report(session, report_id):
        raise HTTPException(status_code=404, detail="리포트를 찾을 수 없습니다")
    return {"deleted": report_id}
