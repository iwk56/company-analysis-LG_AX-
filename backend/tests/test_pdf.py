"""Phase 8-C: PDF 읽기·섹션 나누기·확인 규칙·올릴 보고서 안내·올리기 API (DART를 부르지 않는다).

테스트용 PDF는 tests/fixtures/pdf/ (가상 회사 "테스트전자", make_pdfs.py로 만듦). 실제 사업보고서 PDF는 쓰지 않는다.
"""
from pathlib import Path

import pytest

from app import pdf_api, pdf_uploads
from app.pdf_check import UNREADABLE, compare_revenue, find_summary_revenue, verify
from app.pdf_reader import PdfDoc, extract, split_sections
from tests.test_reports import client  # noqa: F401 (리포트 API와 같은 임시 DB·가짜 기업 목록)

PDF_DIR = Path(__file__).parent / "fixtures" / "pdf"
NAME = "테스트전자(주)"  # 기업개황 정식 회사명 모양


def load(name: str) -> PdfDoc:
    return extract((PDF_DIR / name).read_bytes())


def cover_doc(title="사 업 보 고 서", start="2025년 01월 01일", end="2025년 12월 31일", company="테스트전자 주식회사", body=()):
    """목차 1쪽 + 표지 + 본문 쪽 (글자만으로 확인 규칙을 본다)."""
    toc = "목 차\n사 업 보 고 서 .................. 1\nII. 사업의 내용 .................. 2"
    cover = f"{title}\n(제 78기)\n{start} 부터\n사업연도\n{end} 까지\n회 사 명 : {company}\n대 표 이 사 : 홍 길 동"
    return PdfDoc([toc, cover, *body], [])


# ───────── 섹션 나누기
EXPECTED_RANGES = {"business_overview": (3, 3), "products": (3, 3), "materials_facilities": (3, 4), "sales_orders": (4, 4),
                   "risk_derivatives": (4, 4), "contracts_rnd": (5, 5), "other_info": (5, 5), "mda": (7, 7)}


def ranges(sections):
    return {s["key"]: (s["page_start"], s["page_end"]) for s in sections}


def test_split_by_bookmarks_gives_page_ranges_and_text():
    method, sections = split_sections(load("annual_ok.pdf"))
    assert method == "bookmarks" and ranges(sections) == EXPECTED_RANGES and all(s["found"] for s in sections)
    by = {s["key"]: s for s in sections}
    # II-2 주요 제품 표는 II-1이 아니라 II-2에 남고, II-3은 다음 쪽까지 이어진다
    assert by["business_overview"]["pages"] == [{"page": 3, "text": "1. 사업의 개요\n당사는 가상의 전자부품 회사입니다."}]
    assert [c["page"] for c in by["materials_facilities"]["pages"]] == [3, 4]
    assert "전자공시시스템" not in by["materials_facilities"]["pages"][-1]["text"]  # 꼬리말은 뺀다
    assert by["other_info"]["title"] == "7. 기타 참고사항" and not by["other_info"]["over_limit"]


def test_split_without_bookmarks_finds_headings_and_skips_toc_and_table_rows():
    doc = load("annual_no_outline.pdf")
    assert doc.outline == []
    method, sections = split_sections(doc)
    assert method == "headings" and ranges(sections) == EXPECTED_RANGES
    mda = next(s for s in sections if s["key"] == "mda")
    assert "V. 영업이익 표 안의 줄" in mda["pages"][0]["text"]  # 쪽 첫 줄이 아닌 로마 숫자 줄은 장 제목이 아니다


def test_bookmark_pointing_to_previous_page_uses_heading_on_next_page():
    # LG 2025 사업보고서: II-3 책갈피는 55쪽인데 제목은 56쪽 첫 줄 → 55쪽은 II-2에 남아야 한다
    pages = ["II. 사업의 내용\n1. 사업의 개요\n개요", "2. 주요 제품 및 서비스\n제품 설명", "요금제 표 계속",
             "3. 원재료 및 생산설비\n원재료 없음", "III. 재무에 관한 사항"]
    outline = [(1, "II. 사업의 내용", 1), (2, "1. 사업의 개요", 1), (2, "2. 주요 제품 및 서비스", 2),
               (2, "3. 원재료 및 생산설비", 3), (1, "III. 재무에 관한 사항", 5)]
    _, sections = split_sections(PdfDoc(pages, outline))
    by = ranges(sections)
    assert by["products"] == (2, 3) and by["materials_facilities"] == (4, 4)
    assert next(s for s in sections if s["key"] == "products")["pages"][-1] == {"page": 3, "text": "요금제 표 계속"}


def test_split_reports_missing_sections_without_failing():
    method, sections = split_sections(PdfDoc(["목 차", "표지 사업연도", "III. 재무에 관한 사항\n숫자"], []))
    assert method == "headings" and not any(s["found"] for s in sections)
    assert all(s["page_start"] is None and s["chars"] == 0 for s in sections)


def test_long_section_is_kept_whole_and_marked_over_limit():
    long_text = "가" * 12_001
    _, sections = split_sections(PdfDoc(["II. 사업의 내용\n1. 사업의 개요\n" + long_text, "III. 재무에 관한 사항"], []))
    first = sections[0]
    assert first["found"] and first["over_limit"] and first["chars"] > 12_000


# ───────── 확인 규칙 ①~④
def test_correct_annual_report_is_accepted():
    r = verify(load("annual_ok.pdf"), "annual", NAME, 2025)
    assert r.accepted and r.reasons == [] and r.cover.page == 2 and r.cover.kind == "annual"
    assert r.cover.company == "테스트전자 주식회사" and not r.cover.corrected
    assert [c["key"] for c in r.checks] == ["readable", "kind", "company", "period"]


def test_wrong_kind_for_slot_is_rejected():
    r = verify(load("interim_half.pdf"), "annual", NAME, 2025)
    assert not r.accepted and r.reasons == ["사업보고서 칸에는 사업보고서를 올려 주세요 (이 PDF는 반기보고서입니다)"]
    assert next(c for c in r.checks if c["key"] == "period")["ok"] is None  # 종류가 틀리면 기간은 확인하지 않는다
    r = verify(load("annual_ok.pdf"), "interim", NAME, 2025)
    assert not r.accepted and "반기/3분기 칸에는" in r.reasons[0]
    r = verify(cover_doc("분 기 보 고 서", "2026년 01월 01일", "2026년 03월 31일"), "interim", NAME, 2025)
    assert r.reasons == ["1분기보고서는 받지 않습니다. 반기보고서 또는 3분기보고서를 올려 주세요"]


def test_interim_half_and_third_quarter_are_accepted():
    assert verify(load("interim_half.pdf"), "interim", NAME, 2025).accepted
    r = verify(cover_doc("분 기 보 고 서", "2026년 01월 01일", "2026년 09월 30일"), "interim", NAME, 2025)
    assert r.accepted and r.cover.kind == "q3"


def test_other_company_is_rejected_but_spacing_and_corporate_suffix_are_ignored():
    r = verify(load("annual_ok.pdf"), "annual", "엘지전자(주)", 2025)
    assert not r.accepted and r.reasons[0].startswith("다른 회사의 보고서입니다 (표지 회사명: 테스트전자 주식회사")
    assert verify(cover_doc(company="테스트 전자 (주)"), "annual", "테스트전자 주식회사", 2025).accepted
    assert verify(cover_doc(company="㈜테스트전자"), "annual", NAME, 2025).accepted


def test_other_year_is_rejected_with_expected_report():
    r = verify(load("annual_ok.pdf"), "annual", NAME, 2026)
    assert r.reasons == ["이 PDF는 2025 사업보고서입니다. 2026 사업보고서를 올려 주세요"]
    r = verify(load("interim_half.pdf"), "interim", NAME, 2026)
    assert r.reasons == ["이 PDF는 2026 반기보고서입니다. 2027 반기보고서 또는 3분기보고서를 올려 주세요"]
    r = verify(cover_doc(start="2025년 04월 01일", end="2026년 03월 31일"), "annual", NAME, 2025)
    assert "12월 결산 기업만" in r.reasons[0]


def test_scanned_pdf_is_rejected():
    r = verify(load("scan.pdf"), "annual", NAME, 2025)
    assert not r.readable and r.reasons == [UNREADABLE]


def test_missing_cover_and_corrected_report():
    r = verify(PdfDoc(["목 차 ....", "본문만 있고 표지 정보가 없는 쪽입니다", "II. 사업의 내용"], []), "annual", NAME, 2025)
    assert not r.accepted and "표지" in r.reasons[0]
    r = verify(cover_doc(title="[기재정정]사 업 보 고 서"), "annual", NAME, 2025)
    assert r.accepted and r.cover.corrected


# ───────── ⑤ 매출액 대조 (경고만)
def test_revenue_match_mismatch_and_not_found():
    doc = load("annual_ok.pdf")
    ok = compare_revenue(doc, 1_234_567_000_000, True)
    assert ok["status"] == "match" and ok["page"] == 6 and "재무 숫자 일치" in ok["message"]
    assert compare_revenue(doc, 1_234_567_400_000, True)["status"] == "match"  # 백만 원 단위 반올림 차이는 허용
    bad = compare_revenue(doc, 1_300_000_000_000, True)
    assert bad["status"] == "mismatch" and bad["message"].startswith("재무 숫자를 대조하지 못했습니다")
    assert compare_revenue(doc, None, True)["status"] == "not_found"
    assert compare_revenue(cover_doc(), 1, True)["status"] == "not_found"  # 요약재무정보가 없음


def test_summary_revenue_units_negative_and_separate_table():
    page = ("III. 재무에 관한 사항\n1. 요약재무정보\n가. 요약연결재무정보\n(단위: 천원)\n구분 제5기 제4기\n매출액 (1,500) 2,000\n"
            "나. 요약재무정보\n(단위: 백만원)\n구분 제5기 제4기\n영업수익 7,000 6,000")
    doc = PdfDoc(["목 차", page], [])
    assert find_summary_revenue(doc, True)[0] == -1_500_000
    assert find_summary_revenue(doc, False)[0] == 7_000_000_000  # 별도 기준이면 '요약재무정보' 표


# ───────── 올릴 보고서 안내
ROWS = [  # 2026-11-03 SK하이닉스 정기공시 목록 모양 (최신순)
    {"report_nm": "반기보고서 (2026.06)", "rcept_no": "20260814003509", "rcept_dt": "20260814"},
    {"report_nm": "분기보고서 (2026.03)", "rcept_no": "20260515002287", "rcept_dt": "20260515"},
    {"report_nm": "사업보고서 (2025.12)", "rcept_no": "20260317000635", "rcept_dt": "20260317"},
    {"report_nm": "분기보고서 (2025.09)", "rcept_no": "20251114001805", "rcept_dt": "20251114"},
]


def test_guide_finds_latest_annual_and_next_year_half_or_third_quarter():
    g = pdf_uploads.parse_guide(ROWS)
    assert g["base_year"] == 2025 and g["annual"]["date"] == "2026-03-17" and g["annual"]["title"] == "사업보고서 (2025.12)"
    assert g["annual"]["url"].endswith("rcpNo=20260317000635")
    assert g["interim"]["kind"] == "half" and g["interim"]["date"] == "2026-08-14"
    q3 = pdf_uploads.parse_guide([{"report_nm": "분기보고서 (2026.09)", "rcept_no": "1", "rcept_dt": "20261114"}] + ROWS)
    assert q3["interim"]["kind"] == "q3"
    only_q1 = pdf_uploads.parse_guide(ROWS[1:])  # 1분기는 안내하지 않는다
    assert only_q1["interim"] is None
    assert pdf_uploads.parse_guide([])["annual"] is None


# ───────── 올리기 API
@pytest.fixture
def api(client, monkeypatch):  # noqa: F811
    async def fake_guide(_client, corp_code, today=None):
        return pdf_uploads.parse_guide(ROWS)

    async def fake_name(_client, corp_code):
        return NAME

    async def fake_revenue(fetcher, corp_code, kind, year):
        return (1_234_567_000_000 if kind == "annual" else 700_000_000_000), True

    monkeypatch.setattr(pdf_uploads, "fetch_guide", fake_guide)
    monkeypatch.setattr(pdf_uploads, "official_name", fake_name)
    monkeypatch.setattr(pdf_uploads, "dart_revenue", fake_revenue)
    return client


def upload(c, name, slot="annual", other=None, data=None):
    form = {"corp_code": "00164779", "slot": slot, **({"other_upload_id": other} if other else {})}
    return c.post("/api/pdf/uploads", data=form, files={"file": (name, data if data is not None else (PDF_DIR / name).read_bytes(),
                                                                 "application/pdf")})


def test_upload_confirms_pdf_and_keeps_it_for_report(api):
    r = upload(api, "annual_ok.pdf")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] and body["upload_id"] and body["page_count"] == 8 and body["kind"] == "annual"
    assert body["period_start"] == "2025-01-01" and body["revenue"]["status"] == "match"
    assert pdf_uploads.store.get(body["upload_id"]).sha256 == body["sha256"]
    half = upload(api, "interim_half.pdf", "interim", other=body["upload_id"]).json()
    assert half["accepted"] and half["revenue"]["status"] == "match" and half["kind"] == "half"


def test_upload_rejections_are_not_kept(api):
    before = len(pdf_uploads.store.items)
    wrong = upload(api, "interim_half.pdf").json()
    assert not wrong["accepted"] and wrong["upload_id"] is None and "사업보고서 칸에는" in wrong["reasons"][0]
    assert wrong["revenue"] is None  # 거절이면 숫자 대조를 하지 않는다
    scan = upload(api, "scan.pdf").json()
    assert scan["reasons"] == [UNREADABLE]
    assert len(pdf_uploads.store.items) == before


def test_same_file_in_both_slots_bad_file_and_size_limit(api, monkeypatch):
    first = upload(api, "annual_ok.pdf").json()
    r = upload(api, "annual_ok.pdf", "interim", other=first["upload_id"])
    assert r.status_code == 400 and "같은 파일" in r.json()["detail"]
    r = upload(api, "x.pdf", data=b"not a pdf")
    assert r.status_code == 400 and "PDF 파일을 열지 못했습니다" in r.json()["detail"]
    r = upload(api, "annual_ok.pdf", slot="other")
    assert r.status_code == 400
    monkeypatch.setattr(pdf_api, "MAX_BYTES", 100)
    r = upload(api, "annual_ok.pdf")
    assert r.status_code == 413 and "50MB" in r.json()["detail"]


def test_guide_api_and_company_rules(api):
    g = api.get("/api/pdf/guide", params={"corp_code": "00164779"}).json()
    assert g["base_year"] == 2025 and g["company"]["corp_name"] == "SK하이닉스" and g["interim"]["kind"] == "half"
    r = api.get("/api/pdf/guide", params={"corp_code": "00126256"})  # 금융업
    assert r.status_code == 400 and "금융업" in r.json()["detail"]
