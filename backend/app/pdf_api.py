"""보고서 PDF 올리기 API (docs/spec.md F2): 올릴 보고서 안내, 올리기·확인."""
import asyncio
import hashlib

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from . import pdf_uploads
from .dart import DartError
from .jobs import manager, new_fetcher
from .pdf_check import verify
from .pdf_reader import PdfReadError, extract
from .pdf_uploads import MAX_BYTES, Upload, store
from .reports_api import _validate_company

router = APIRouter(prefix="/api/pdf", tags=["pdf"])

SLOTS = ("annual", "interim")


async def _guide(corp_code: str) -> dict:
    try:
        async with httpx.AsyncClient() as client, manager.dart_lock():
            return await pdf_uploads.fetch_guide(client, corp_code)
    except DartError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/guide")
async def get_guide(corp_code: str = Query(..., description="분석 기업 고유번호")):
    """올릴 보고서 안내: 기준 사업연도 N의 사업보고서와 N+1년의 최근 반기/3분기보고서 (이름·제출일·공시뷰어 링크)."""
    company = await _validate_company(corp_code.strip())
    return {"company": company, **await _guide(company["corp_code"])}


@router.post("/uploads")
async def upload_pdf(corp_code: str = Form(...), slot: str = Form(...), other_upload_id: str | None = Form(None),
                     file: UploadFile = File(...)):
    """PDF를 올리면 바로 확인한다. 확인 ①~④를 통과한 것만 보관하고 upload_id를 준다(거절이면 upload_id 없음).

    other_upload_id: 다른 칸에 이미 올린 PDF. 같은 파일이면 거절한다.
    """
    if slot not in SLOTS:
        raise HTTPException(status_code=400, detail="올바르지 않은 칸입니다")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="파일이 50MB를 넘습니다")
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일입니다")
    sha = hashlib.sha256(data).hexdigest()
    other = store.get(other_upload_id)
    if other and other.sha256 == sha:
        raise HTTPException(status_code=400, detail="같은 파일을 두 칸에 올렸습니다. 칸에 맞는 보고서를 올려 주세요")
    company = await _validate_company(corp_code.strip())
    guide = await _guide(company["corp_code"])
    if guide["base_year"] is None:
        raise HTTPException(status_code=400, detail=guide["message"])
    try:
        doc = await asyncio.to_thread(extract, data)  # 400쪽에 10초쯤 걸려 이벤트 루프를 막지 않게 한다
    except PdfReadError:
        raise HTTPException(status_code=400, detail="PDF 파일을 열지 못했습니다. DART 공시뷰어에서 받은 PDF를 올려 주세요")
    try:
        async with httpx.AsyncClient() as client, manager.dart_lock():
            name = await pdf_uploads.official_name(client, company["corp_code"])
            check = verify(doc, slot, name, guide["base_year"])
            revenue = None
            if check.accepted:
                year = guide["base_year"] + (0 if slot == "annual" else 1)
                revenue = await pdf_uploads.check_revenue(new_fetcher(client), company["corp_code"], doc, check.cover.kind, year)
    except DartError as e:
        raise HTTPException(status_code=502, detail=str(e))
    upload = Upload(id=pdf_uploads.new_id(), corp_code=company["corp_code"], slot=slot, file_name=file.filename or "report.pdf",
                    sha256=sha, size=len(data), base_year=guide["base_year"], doc=doc, check=check, revenue=revenue)
    if check.accepted:
        store.put(upload)
    out = upload.summary()
    if not check.accepted:
        out["upload_id"] = None
    return out
