"""보고서 PDF 올리기 (docs/spec.md F2): 올릴 보고서 안내, 확인, 리포트를 만들 때까지 서버 메모리에 보관.

- PDF 원본은 저장하지 않는다. 확인을 통과한 PDF의 쪽별 글자와 책갈피만 메모리에 두었다가 생성 단계 "PDF 읽기"에서
  섹션으로 나눠 DB에 저장한다(spec 6장 정할 것 5). 서버를 다시 켜거나 2시간이 지나면 다시 올려야 한다(생성 작업과 같은 MVP 방식)
- 안내: DART 공시 목록(정기공시)에서 최근 사업보고서(기준 사업연도 N)와 N+1년의 최근 반기/3분기보고서를 찾는다. 같은 기업은 10분 동안 다시 부르지 않는다
"""
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import date

import httpx

from . import company_cache
from .dart import DartError, _get
from .fin_collect import DART_VIEWER
from .fin_fetch import ANNUAL_REPORT, HALF_REPORT, THIRD_QUARTER_REPORT, FinancialsFetcher
from .fin_mapping import RULES_BY_FIELD, find_row, parse_amount
from .pdf_check import ANNUAL, HALF, Q3, CheckResult, compare_revenue
from .pdf_reader import PdfDoc, split_sections

MAX_BYTES = 50 * 1024 * 1024  # 파일당 50MB
KEEP_SECONDS = 2 * 3600
MAX_KEPT = 20
GUIDE_TTL_SECONDS = 600
REPORT_NAME = re.compile(r"(사업보고서|반기보고서|분기보고서)\s*\((\d{4})\.(\d{2})\)")
NO_ANNUAL = "최근 2년 안에 제출된 사업보고서를 DART 공시 목록에서 찾지 못했습니다"


@dataclass
class Upload:
    id: str
    corp_code: str
    slot: str  # annual | interim
    file_name: str
    sha256: str
    size: int
    base_year: int
    doc: PdfDoc = field(repr=False)
    check: CheckResult = field(repr=False)
    revenue: dict | None = None
    created_at: float = field(default_factory=time.time)

    def summary(self) -> dict:
        """화면·생성 응답에 쓰는 확인 결과 (글자는 넣지 않는다)."""
        c = self.check.cover
        return {"upload_id": self.id, "slot": self.slot, "file_name": self.file_name, "size": self.size, "sha256": self.sha256,
                "page_count": len(self.doc.pages), "accepted": self.check.accepted, "reasons": self.check.reasons,
                "checks": self.check.checks, "kind": c.kind if c else None, "corrected": bool(c and c.corrected),
                "period_start": c.start.isoformat() if c and c.start else None,
                "period_end": c.end.isoformat() if c and c.end else None,
                "cover_page": c.page if c else None, "revenue": self.revenue}


class UploadStore:
    def __init__(self):
        self.items: dict[str, Upload] = {}

    def _prune(self) -> None:
        now = time.time()
        for k in [k for k, u in self.items.items() if now - u.created_at > KEEP_SECONDS]:
            del self.items[k]
        for k in list(self.items)[:-MAX_KEPT]:  # 오래된 것부터 지운다
            del self.items[k]

    def put(self, upload: Upload) -> Upload:
        self.items[upload.id] = upload
        self._prune()
        return upload

    def get(self, upload_id: str | None) -> Upload | None:
        self._prune()
        return self.items.get(upload_id or "")


store = UploadStore()


def new_id() -> str:
    return uuid.uuid4().hex


# ───────── 올릴 보고서 안내
_guides: dict[str, tuple[float, dict]] = {}


def _item(r: dict, kind: str, year: int) -> dict:
    d = r["rcept_dt"]
    return {"kind": kind, "year": year, "title": re.sub(r"\s+", " ", r["report_nm"]).strip(), "rcept_no": r["rcept_no"],
            "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "url": DART_VIEWER.format(r["rcept_no"])}


def parse_guide(rows: list[dict]) -> dict:
    """공시 목록(접수일 최신순) → {"base_year", "annual", "interim"}. 1분기보고서는 안내하지 않는다."""
    annual = interim = None
    for r in rows:
        m = REPORT_NAME.search(r.get("report_nm") or "")
        if m and m.group(1) == "사업보고서":
            annual = _item(r, ANNUAL, int(m.group(2)))
            break
    if annual is None:
        return {"base_year": None, "annual": None, "interim": None, "message": NO_ANNUAL}
    n = annual["year"]
    for r in rows:
        m = REPORT_NAME.search(r.get("report_nm") or "")
        if not m or int(m.group(2)) != n + 1:
            continue
        if m.group(1) == "반기보고서" and m.group(3) == "06":
            interim = _item(r, HALF, n + 1)
        elif m.group(1) == "분기보고서" and m.group(3) == "09":
            interim = _item(r, Q3, n + 1)
        if interim:
            break
    return {"base_year": n, "annual": annual, "interim": interim, "message": None}


async def fetch_guide(client: httpx.AsyncClient, corp_code: str, today: date | None = None) -> dict:
    hit = _guides.get(corp_code)
    if hit and time.time() - hit[0] < GUIDE_TTL_SECONDS:
        return hit[1]
    today = today or date.today()
    resp = await _get(client, "list.json", {"corp_code": corp_code, "bgn_de": f"{today.year - 2}0101",
                                            "end_de": today.strftime("%Y%m%d"), "pblntf_ty": "A",
                                            "last_reprt_at": "Y", "page_count": "100"})
    try:
        data = resp.json()
    except ValueError:
        raise DartError("json", "공시 목록 응답을 읽지 못했습니다") from None
    if data.get("status") == "013":
        rows = []
    elif data.get("status") != "000":
        raise DartError(data.get("status") or "?", data.get("message", ""))
    else:
        rows = data.get("list") or []
    guide = parse_guide(rows)
    _guides[corp_code] = (time.time(), guide)
    return guide


async def official_name(client: httpx.AsyncClient, corp_code: str) -> str:
    """DART 기업개황의 정식 회사명. 예전 캐시에는 없어서 없으면 기업개황을 다시 받는다."""
    cache = company_cache.load_cache()
    entry = cache.get(corp_code)
    if not company_cache.is_fresh(entry) or not entry.get("official_name"):
        entry = cache[corp_code] = await company_cache.fetch_overview(client, corp_code)
        company_cache.save_cache(cache)
    if not entry.get("official_name"):
        raise DartError("company", "기업개황에서 정식 회사명을 받지 못했습니다")
    return entry["official_name"]


# ───────── ⑤ 매출액 대조에 쓰는 DART 값
REPRT_CODES = {ANNUAL: ANNUAL_REPORT, HALF: HALF_REPORT, Q3: THIRD_QUARTER_REPORT}


async def dart_revenue(fetcher: FinancialsFetcher, corp_code: str, kind: str, year: int) -> tuple[float | None, bool]:
    """(매출액 원, 연결인지). 사업보고서는 당기, 반기·3분기는 당기 누적. 연결이 없으면 별도. 응답은 저장본을 쓴다."""
    for fs_div in ("CFS", "OFS"):
        data = await fetcher.fetch(corp_code, year, fs_div, REPRT_CODES[kind])
        if data.get("status") != "000":
            continue
        rows = [r for r in data["list"] if r.get("sj_div") in ("IS", "CIS")]
        m = find_row(rows, RULES_BY_FIELD["revenue"])
        if m is None:
            return None, fs_div == "CFS"
        col = "thstrm_amount" if kind == ANNUAL else "thstrm_add_amount"
        value = parse_amount(m.row.get(col))
        if value is None and kind != ANNUAL:
            value = parse_amount(m.row.get("thstrm_amount"))
        return value, fs_div == "CFS"
    return None, True


async def check_revenue(fetcher: FinancialsFetcher, corp_code: str, doc: PdfDoc, kind: str, year: int) -> dict:
    try:
        dart_won, consolidated = await dart_revenue(fetcher, corp_code, kind, year)
    except DartError:  # 경고만 하는 확인이라 DART 오류로 올리기를 막지 않는다
        dart_won, consolidated = None, True
    return compare_revenue(doc, dart_won, consolidated)


def to_record(upload: Upload) -> dict:
    """생성 단계 "PDF 읽기": 섹션으로 나눠 DB에 저장할 모양으로 만든다 (원본 파일은 없다)."""
    method, sections = split_sections(upload.doc)
    c = upload.check.cover
    return {"slot": upload.slot, "file_name": upload.file_name, "sha256": upload.sha256, "page_count": len(upload.doc.pages),
            "kind": c.kind, "corrected": c.corrected, "period_start": c.start, "period_end": c.end,
            "checks": upload.check.checks, "revenue_check": upload.revenue, "split_method": method, "sections": sections}
