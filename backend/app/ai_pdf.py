"""8-D: 올린 PDF에서 서술 추출 (docs/spec.md F4 1~4장, "PDF 원문 인용 규칙").

AI 호출 3개 (모두 해석용 모델, 2026-11-03 결정)
- extract_position: 업계 위치(점유율 문장·표 행, 경쟁사 이름) · 주요 고객 비중 · 회사가 밝힌 위험 요인
- extract_mda: IV. 이사의 경영진단 및 분석의견 요약 (사업보고서만, 반기·분기보고서는 이 항목을 기재하지 않는다)
- extract_focus: 연구개발 · 투자·신규 시설 · 신사업 (+ 반기/3분기 PDF가 있으면 "바뀐 점")

규칙
- 넘길 글은 pdf_select(A안)로 고른다. 인용 확인은 넘긴 부분이 아니라 섹션 전체 글로 한다(띄어쓰기·줄바꿈·표 칸만 무시)
- 인용이 PDF에 없으면 버린다. 인용이 하나도 남지 않은 항목은 버린다. 남은 인용에 쪽 번호와 보고서 이름·공시뷰어 링크를 코드가 붙인다
- 요약 문장의 숫자는 그 항목의 인용이나 넘겨준 계산 결과에 있는 숫자만 허용한다(문장 단위로 버린다)
- 경쟁사 이름은 남은 인용 안에 있는 것만. 고객 비중은 인용 안의 % 숫자를 코드가 읽고, 여러 고객을 합친 비중은 판정에 쓰지 않는다
"""
import re
from dataclasses import dataclass

import httpx

from . import ai_prompts as P
from . import db
from .ai_facts import Facts
from .ai_tasks import Outcome, _failed, _usage, ask
from .ai_verify import numbers_in, unknown_numbers
from .fin_collect import DART_VIEWER
from .llm import LlmError
from .pdf_select import CALL_LIMIT, Picked, Rule, pick_many
from .report_models import ReportPdf

NO_PDF = "PDF 없이 만든 리포트입니다. 새로 만들면 표시됩니다"
NOT_FOUND = "사업보고서에서 이 항목을 찾지 못했습니다"
MIN_QUOTE = 15
KIND_NAMES = {"annual": "사업보고서", "half": "반기보고서", "q3": "3분기보고서"}
INTERIM_NAMES = {"half": "반기", "q3": "3분기"}
AGGREGATE = re.compile(r"(상위|주요)?\s*\d+\s*(대|개|곳)\s*(주요\s*)?(매출처|고객|거래처)")
PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
MAX = {"position": 3, "customers": 3, "risks": 5, "mda": 3, "focus": 3, "changes": 2, "business": 3}
NOT_FILED_MARK = "기재하지아니"  # 반기·분기보고서의 IV ("기업공시서식 작성기준에 따라 … 기재하지 아니하였습니다")

# ───────── 호출별로 넘길 섹션과 고르는 규칙 (앞일수록 먼저 자리를 받는다)
POSITION_RULES = [
    ("other_info", Rule(priority=(("점유율",), ("경쟁", "시장", "업계", "산업")), keep_tables=("점유율",),
                        keywords=("점유율", "경쟁", "시장", "업계", "고객", "매출처", "위험"))),
    ("sales_orders", Rule(priority=(("매출처", "고객"), ("판매",)), keep_tables=("매출처", "고객"), keywords=("매출처", "고객", "비중"))),
    ("business_overview", Rule(keywords=("시장", "경쟁", "점유율"))),
    ("risk_derivatives", Rule(keywords=("위험", "리스크", "불확실", "영향"))),
    ("mda", Rule(limit=4_000, exclude=("예측정보", "부외거래"), keywords=("위험", "리스크", "불확실", "우려", "변동성"))),
]
MDA_RULE = Rule(priority=(("개요",), ("재무상태", "영업실적"), ("유동성", "자금조달"), ("그밖에", "투자의사결정")),
                exclude=("예측정보", "부외거래"), keywords=("증가", "감소", "개선", "계획", "전략", "투자", "수요", "전망"))
_RND = ("연구", "개발", "조직", "실적", "특허")
_INV = ("투자", "신설", "증설", "설비", "공장", "신규")
_NEW = ("신규", "신사업", "진출", "미래", "성장")
FOCUS_ANNUAL = [
    ("contracts_rnd", Rule(limit=10_000, priority=(("연구개발",),), keywords=_RND)),
    ("materials_facilities", Rule(limit=6_000, priority=(("생산설비", "설비", "투자"),), keywords=_INV)),
    ("business_overview", Rule(limit=3_000, keywords=_NEW)),
    ("other_info", Rule(limit=6_000, priority=(("신규사업", "신사업"), ("회사의현황", "영업개황")), keywords=_NEW)),
]
FOCUS_INTERIM = [
    ("contracts_rnd", Rule(limit=4_000, priority=(("연구개발",),), keywords=_RND)),
    ("materials_facilities", Rule(limit=3_000, priority=(("생산설비", "설비", "투자"),), keywords=_INV)),
    ("other_info", Rule(limit=3_000, priority=(("신규사업", "신사업"), ("회사의현황", "영업개황")), keywords=_NEW)),
]
FOCUS_ANNUAL_LIMIT, FOCUS_INTERIM_LIMIT = 20_000, 10_000  # 합쳐서 호출 상한 30,000자
OVERVIEW_RULES = [("business_overview", Rule(limit=6_000)), ("products", Rule(limit=4_000, keywords=("주요 제품", "매출", "비율")))]
BUSINESS_RULES = [  # 7-B 외부 환경의 "사업의 내용" (예전 DART 원문 길이와 같게)
    ("business_overview", Rule(limit=1_500)),
    ("materials_facilities", Rule(limit=2_000, keywords=_INV)),
    ("other_info", Rule(limit=8_000, priority=(("업계", "산업"), ("시장", "경쟁", "점유율")), keep_tables=("점유율",),
                        keywords=("점유율", "경쟁", "시장", "업계", "수요", "산업"))),
]


@dataclass
class Doc:
    slot: str  # annual | interim
    kind: str
    year: int
    label: str  # 예: 2025 사업보고서
    url: str | None  # DART 공시뷰어 원문 (PDF 파일은 링크하지 않음)
    sections: dict[str, dict]  # 찾은 섹션만 (키 → {key, label, pages: [{page, text}], ...})


def _doc_url(report: dict, row: ReportPdf) -> str | None:
    if row.split_method == "dart_xml":  # DART 원문에서 만든 섹션: 접수번호로 그 공시를 바로 연다
        m = next((re.search(r"접수번호 (\d{14})", c.get("message") or "") for c in row.checks or []), None)
        if m:
            return DART_VIEWER.format(m.group(1))
    if row.slot == "annual":
        src = next((s for s in report["sources"] if s["kind"] == "annual_report" and s["year"] == row.period_end.year), None)
        return src["url"] if src else None
    rr = report.get("recent_results")
    if rr and rr["year"] == row.period_end.year and rr["report_name"] == INTERIM_NAMES.get(row.kind) and rr.get("rcept_no"):
        return DART_VIEWER.format(rr["rcept_no"])
    return None


def load_docs(report: dict) -> dict[str, Doc]:
    """리포트에 저장된 PDF 섹션 (사업보고서 'annual', 반기/3분기 'interim'). PDF 없이 만든 리포트면 빈 dict."""
    db.ensure_init()
    with db.SessionLocal() as s:
        rows = s.query(ReportPdf).filter_by(report_id=report["id"]).all()
    out = {}
    for r in rows:
        year = r.period_end.year
        out[r.slot] = Doc(r.slot, r.kind, year, f"{year} {KIND_NAMES.get(r.kind, '보고서')}", _doc_url(report, r),
                          {x["key"]: x for x in r.sections if x.get("found") and x.get("pages")})
    return out


# ───────── 넘길 글 만들기
def _picks(doc: Doc, rules: list[tuple[str, Rule]], limit: int) -> list[Picked]:
    return pick_many([(doc.sections[k], rule) for k, rule in rules if k in doc.sections], limit)


def _sources(doc: Doc, picks: list[Picked], prefix: str = "") -> dict[str, str]:
    return {f"{prefix}{doc.label} · {p.label}" + (" (일부만 사용)" if p.partial else ""): p.text for p in picks}


def _inputs(doc: Doc, picks: list[Picked]) -> list[dict]:
    return [{"doc": doc.label, **p.meta()} for p in picks]


def pdf_text(docs: dict[str, Doc], rules: list[tuple[str, Rule]], limit: int) -> tuple[str | None, list[dict]]:
    """사업보고서 PDF에서 규칙대로 고른 글 한 덩어리 (1장 주력 사업·7-B 외부 환경 입력). PDF가 없으면 (None, [])."""
    doc = docs.get("annual")
    if doc is None:
        return None, []
    picks = _picks(doc, rules, limit)
    text = "\n\n".join(f"<{p.label}{' (일부)' if p.partial else ''}>\n{p.text}" for p in picks)
    return (text or None), _inputs(doc, picks)


# ───────── 인용 확인과 쪽 번호
def _squash(s: str | None) -> str:
    return re.sub(r"[\s|]+", "", s or "")


class Corpus:
    """인용을 찾을 섹션 전체 글. 쪽 경계를 기억해 인용이 시작하는 쪽을 돌려준다."""

    def __init__(self, parts: list[tuple[Doc, dict]]):
        self.parts = []
        for doc, sec in parts:
            joined, starts = "", []
            for c in sec["pages"]:
                starts.append((len(joined), c["page"]))
                joined += _squash(c["text"])
            self.parts.append((doc, sec, joined, starts))

    def find(self, quote) -> dict | None:
        if not isinstance(quote, str):
            return None
        q = _squash(quote)
        if len(q) < MIN_QUOTE:
            return None
        for doc, sec, joined, starts in self.parts:
            i = joined.find(q)
            if i >= 0:
                page = [p for start, p in starts if start <= i][-1]
                # DART 원문(2026-11-04 기본)에는 쪽 번호가 없어 섹션 이름으로 출처를 단다. PDF면 예전처럼 쪽 번호
                cite = f"{doc.label} p.{page}" if page else f"{doc.label} {sec['label']}"
                return {"text": re.sub(r"\s+", " ", quote).strip(), "page": page, "doc": doc.label, "slot": doc.slot,
                        "section": sec["key"], "section_label": sec["label"], "cite": cite, "url": doc.url}
        return None

    def quotes(self, raw, limit: int, where: str, dropped: list[str]) -> list[dict]:
        out, seen = [], set()
        for i, q in enumerate(raw if isinstance(raw, list) else []):
            found = self.find(q)
            if found is None:
                dropped.append(f"{where} 인용 {i + 1}: PDF 원문에서 찾지 못함")
                continue
            key = _squash(found["text"])
            if key not in seen and len(out) < limit:
                seen.add(key)
                out.append(found)
        return out


def _quote_numbers(quotes: list[dict]) -> set[str]:
    out: set[str] = set()
    for q in quotes:
        out |= numbers_in(q["text"])
    return out


def _sentences(text, allowed: set[str], where: str, dropped: list[str]) -> str | None:
    """문장마다 숫자를 확인해 넘겨주지 않은 숫자가 든 문장만 버린다."""
    if not isinstance(text, str) or not text.strip():
        return None
    kept = []
    for s in re.split(r"(?<=[.다])\s+", text.strip()):
        bad = unknown_numbers(s, allowed)
        if bad:
            dropped.append(f"{where}: 자료에 없는 숫자 {', '.join(sorted(bad))}")
        elif s.strip():
            kept.append(s.strip())
    return " ".join(kept) or None


def _summary_item(raw, corpus: Corpus, extra_allowed: set[str], limit: int, where: str, dropped: list[str]) -> dict | None:
    """{"summary", "quotes"} 한 항목. 인용이 하나도 남지 않으면 버린다."""
    if not isinstance(raw, dict):
        return None
    quotes = corpus.quotes(raw.get("quotes"), limit, where, dropped)
    if not quotes:
        if raw.get("summary") or raw.get("quotes"):
            dropped.append(f"{where}: 원문에서 찾은 인용이 없어 버림")
        return None
    summary = _sentences(raw.get("summary"), extra_allowed | _quote_numbers(quotes), f"{where} 요약", dropped)
    return {"summary": summary, "quotes": quotes}


def _finish(content: dict, dropped: list[str], r, has_any: bool, empty_message: str) -> Outcome:
    if not has_any:
        return _usage(Outcome("empty", content, message=empty_message, warnings=dropped), r)
    return _usage(Outcome("ok", content, warnings=dropped), r)


# ───────── 호출 ⓐ 업계 위치 · 주요 고객 · 위험 요인
def customer_scope(quote: str, ai_scope) -> str:
    """여러 고객을 합친 비중이면 aggregate (AI가 single이라고 해도 인용에 '10대 매출처' 같은 말이 있으면 합계로 본다)."""
    if AGGREGATE.search(quote) or ai_scope == "aggregate":
        return "aggregate"
    return "single" if ai_scope == "single" else "unknown"


async def extract_position(client: httpx.AsyncClient, docs: dict[str, Doc]) -> Outcome:
    doc = docs.get("annual")
    if doc is None:
        return Outcome("empty", message=NO_PDF)
    picks = _picks(doc, POSITION_RULES, CALL_LIMIT)
    if not picks:
        return Outcome("empty", message=NOT_FOUND)
    try:
        r = await ask(client, "extract_position", "write", P.user_message(P.EXTRACT_POSITION, _sources(doc, picks)))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data, []
    corpus = Corpus([(doc, doc.sections[p.key]) for p in picks])

    position = None
    raw = d.get("position") if isinstance(d.get("position"), dict) else {}
    quotes = corpus.quotes(raw.get("quotes"), MAX["position"], "업계 위치", dropped)
    shares = market_shares(raw.get("market_shares"), corpus, dropped)
    if quotes or shares:
        # 2026-11-04: '보고서에 나온 경쟁사'는 화면에서 뺐다(경쟁사는 비교 기업 자동 선정에서 보여 줌). 점유율은 숫자로 따로 둔다
        allowed = _quote_numbers(quotes) | {v for m in shares for v in numbers_in(m["quote"]["text"] + " " + " ".join(m["periods"]))}
        position = {"summary": _sentences(raw.get("summary"), allowed, "업계 위치 요약", dropped),
                    "quotes": quotes, "market_shares": shares}
    elif raw.get("quotes"):
        dropped.append("업계 위치: 원문에서 찾은 인용이 없어 버림")

    customers = []
    for i, c in enumerate(d.get("customers") if isinstance(d.get("customers"), list) else []):
        if not isinstance(c, dict) or len(customers) >= MAX["customers"]:
            continue
        found = corpus.find(c.get("quote"))
        if found is None:
            dropped.append(f"주요 고객 {i + 1}: PDF 원문에서 찾지 못함")
            continue
        share = None
        m = PERCENT.search(c.get("share") or "") if isinstance(c.get("share"), str) else None
        if m and _squash(c["share"]) in _squash(found["text"]):
            share = float(m.group(1)) / 100
        elif c.get("share"):
            dropped.append(f"주요 고객 {i + 1}: 비중 표기가 인용 안에 없음")
        customers.append({"quote": found, "share": share, "share_text": c.get("share") if share is not None else None,
                          "scope": customer_scope(found["text"], c.get("scope"))})

    risks = []
    for i, x in enumerate(d.get("risks") if isinstance(d.get("risks"), list) else []):
        if not isinstance(x, dict) or len(risks) >= MAX["risks"]:
            continue
        found = corpus.find(x.get("quote"))
        if found is None:
            dropped.append(f"위험 요인 {i + 1}: PDF 원문에서 찾지 못함")
            continue
        risks.append({"quote": found, "plain": _sentences(x.get("plain"), numbers_in(found["text"]), f"위험 요인 {i + 1}", dropped)})

    content = {"position": position, "customers": customers, "risks": risks, "inputs": _inputs(doc, picks)}
    return _finish(content, dropped, r, bool(position or customers or risks),
                   "사업보고서에서 업계 위치·주요 고객·위험 요인 문장을 원문과 대조하지 못했습니다 (언급이 없거나 AI가 옮긴 문장이 원문과 달랐습니다)")


def market_shares(raw, corpus: Corpus, dropped: list[str]) -> list[dict]:
    """시장점유율 행: 행 인용이 원문에 있고, 값이 모두 그 인용 안에 순서대로 있고, 기간 이름이 원문에 있을 때만 남긴다.
    share는 첫 기간(원문 표의 맨 앞 칸) 값을 0~1로. 나머지 몫(1 - share)은 화면에서 코드가 계산한다."""
    out = []
    for i, m in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(m, dict) or len(out) >= 4:
            continue
        where = f"시장점유율 {i + 1}"
        found = corpus.find(m.get("quote"))
        values = [v for v in m.get("values") or [] if isinstance(v, str)]
        periods = [p for p in m.get("periods") or [] if isinstance(p, str)]
        product = str(m.get("product") or "").strip()
        if found is None or not values or not product:
            dropped.append(f"{where}: 원문에서 행을 찾지 못했거나 값이 없음")
            continue
        q = _squash(found["text"])
        at, ok = 0, True
        for v in values:
            j = q.find(_squash(v), at)
            if j < 0 or not PERCENT.search(v):
                ok = False
                break
            at = j + len(_squash(v))
        if not ok or _squash(product) not in q:
            dropped.append(f"{where}: 값 또는 제품 이름이 인용 안에 없음")
            continue
        texts = [_squash(t) for _d, _s, t, _st in corpus.parts]
        if len(periods) != len(values) or not all(any(_squash(p) in t for t in texts) for p in periods):
            periods = []  # 기간을 원문에서 확인하지 못하면 기간 없이 값만 보여 준다
        shares = [float(PERCENT.search(v).group(1)) / 100 for v in values]
        source = m.get("source") if isinstance(m.get("source"), str) and any(_squash(m["source"]) in t for t in texts) else None
        out.append({"product": product, "periods": periods, "values": values, "shares": shares, "share": shares[0],
                    "quote": found, "source": source})
    return out


# ───────── 호출 ⓑ 경영진단
async def extract_mda(client: httpx.AsyncClient, docs: dict[str, Doc], facts: Facts) -> Outcome:
    doc = docs.get("annual")
    if doc is None:
        return Outcome("empty", message=NO_PDF)
    sec = doc.sections.get("mda")
    if sec is None:
        return Outcome("empty", message=NOT_FOUND)
    if NOT_FILED_MARK in _squash("".join(c["text"] for c in sec["pages"])) and sec.get("chars", 0) < 1_000:
        return Outcome("empty", message="보고서에 경영진단이 기재되어 있지 않습니다")
    picks = pick_many([(sec, MDA_RULE)])
    ref = "\n".join(facts.blocks[k] for k in ("trend", "recent_results") if facts.blocks.get(k))
    try:
        r = await ask(client, "extract_mda", "write",
                      P.user_message(P.EXTRACT_MDA, {**_sources(doc, picks), "참고: 코드 계산 결과": ref}))
    except LlmError as e:
        return _failed(e)
    dropped: list[str] = []
    item = _summary_item(r.data, Corpus([(doc, sec)]), facts.allowed, MAX["mda"], "경영진단", dropped)
    content = {**(item or {"summary": None, "quotes": []}), "inputs": _inputs(doc, picks)}
    return _finish(content, dropped, r, item is not None,
                   "경영진단 요약의 인용을 원문과 대조하지 못해 사용하지 않았습니다")


# ───────── 호출 ⓒ 연구개발 · 투자 · 신사업 (+ 최근 보고서에서 바뀐 점)
FOCUS_KEYS = (("rnd", "연구개발"), ("investment", "투자·신규 시설"), ("new_business", "신사업"))


async def extract_focus(client: httpx.AsyncClient, docs: dict[str, Doc], facts: Facts) -> Outcome:
    doc = docs.get("annual")
    if doc is None:
        return Outcome("empty", message=NO_PDF)
    picks = _picks(doc, FOCUS_ANNUAL, FOCUS_ANNUAL_LIMIT)
    if not picks:
        return Outcome("empty", message=NOT_FOUND)
    interim = docs.get("interim")
    ipicks = _picks(interim, FOCUS_INTERIM, FOCUS_INTERIM_LIMIT) if interim else []
    sources = {**_sources(doc, picks), **(_sources(interim, ipicks, "최근 보고서 · ") if ipicks else {})}
    request = (f"최근 보고서 있음: '{interim.label}' 자료로 changes를 작성하세요." if ipicks
               else "최근 보고서 없음: changes는 null로 두세요.")
    try:
        r = await ask(client, "extract_focus", "write", P.user_message(P.EXTRACT_FOCUS, sources, request))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data, []
    corpus = Corpus([(doc, doc.sections[p.key]) for p in picks])
    content: dict = {k: _summary_item(d.get(k), corpus, facts.allowed, MAX["focus"], name, dropped) for k, name in FOCUS_KEYS}
    changes = None
    if ipicks and isinstance(d.get("changes"), dict):
        icorpus = Corpus([(interim, interim.sections[p.key]) for p in ipicks])
        changes = {}
        for k, name in FOCUS_KEYS:
            raw = d["changes"].get(k)
            if isinstance(raw, dict):
                item = _summary_item({"summary": raw.get("text"), "quotes": raw.get("quotes")}, icorpus, facts.allowed,
                                     MAX["changes"], f"{name} 바뀐 점", dropped)
                if item:
                    changes[k] = {"text": item["summary"], "quotes": item["quotes"]}
        changes = changes or None
    content.update({"changes": changes, "interim_label": interim.label if interim else None,
                    "inputs": _inputs(doc, picks) + (_inputs(interim, ipicks) if ipicks else [])})
    has_any = any(content[k] for k, _ in FOCUS_KEYS)
    return _finish(content, dropped, r, has_any, "연구개발·투자·신사업 요약의 인용을 원문과 대조하지 못해 사용하지 않았습니다")


# ───────── 사업 구조 (2026-11-04): 제품·가격, 매출 구성, 생산·가동률, 원재료, 수주, 부문별 손익
BUSINESS_KEYS = (("products", "주요 제품·가격"), ("sales_mix", "매출 구성"), ("production", "생산능력·가동률"),
                 ("materials", "원재료"), ("orders", "수주 현황"), ("segments", "사업부문별 손익"))
STRUCTURE_RULES = [
    ("products", Rule(limit=4_000, keep_tables=("매출", "비율", "가격"), keywords=("제품", "가격", "매출", "비율", "수요"))),
    ("sales_orders", Rule(limit=6_000, keep_tables=("수출", "내수", "지역", "수주", "매출"),
                          keywords=("수출", "내수", "지역", "수주", "판매", "매출처"))),
    ("materials_facilities", Rule(limit=8_000, priority=(("생산능력", "생산실적", "가동률"), ("원재료",)),
                                  keep_tables=("생산", "가동", "원재료", "가격", "투입"),
                                  keywords=("생산능력", "생산실적", "가동률", "원재료", "가격", "매입"))),
    ("segment_note", Rule(limit=5_000, keep_tables=("부문", "영업이익", "매출", "고객", "수익"), keywords=("부문", "영업이익", "매출", "고객"))),
]
STRUCTURE_LIMIT = 22_000


async def extract_business(client: httpx.AsyncClient, docs: dict[str, Doc], facts: Facts) -> Outcome:
    """사업 구조 탭: 사업보고서 II-2·II-3·II-4와 연결재무제표 주석(영업부문)에서 항목 6개를 인용과 함께 뽑는다."""
    doc = docs.get("annual")
    if doc is None:
        return Outcome("empty", message=NO_PDF)
    picks = _picks(doc, STRUCTURE_RULES, STRUCTURE_LIMIT)
    if not picks:
        return Outcome("empty", message=NOT_FOUND)
    try:
        r = await ask(client, "extract_business", "write", P.user_message(P.EXTRACT_BUSINESS, _sources(doc, picks)))
    except LlmError as e:
        return _failed(e)
    d, dropped = r.data, []
    corpus = Corpus([(doc, doc.sections[p.key]) for p in picks])
    content: dict = {k: _summary_item(d.get(k), corpus, facts.allowed, MAX["business"], name, dropped) for k, name in BUSINESS_KEYS}
    content["inputs"] = _inputs(doc, picks)
    has_any = any(content[k] for k, _ in BUSINESS_KEYS)
    return _finish(content, dropped, r, has_any, "사업 구조 요약의 인용을 원문과 대조하지 못해 사용하지 않았습니다")


# ───────── SWOT·과제 호출에 넘길 검증된 결과 (근거 키 → 문단)
def pdf_basis(position: dict | None, mda: dict | None, focus: dict | None, label: str) -> dict[str, tuple[str, str]]:
    """{근거 키: (이름, 문단)} — 이미 인용 검증을 통과한 내용만. 이름은 새 장 이름을 쓴다."""
    out: dict[str, tuple[str, str]] = {}
    if position and position.get("position"):
        p = position["position"]
        lines = ([p["summary"]] if p.get("summary") else []) + [f"\"{q['text']}\" ({q['cite']})" for q in p["quotes"]]
        out["pdf:position"] = ("1장 업계 위치 (회사가 밝힌 내용)", "\n".join(lines))
    if position and position.get("risks"):
        lines = [f"{x['plain'] or x['quote']['text']} ({x['quote']['cite']})" for x in position["risks"]]
        out["pdf:risks"] = ("4장 회사가 밝힌 위험 요인", "\n".join(lines))
    if mda and mda.get("summary"):
        out["pdf:mda"] = ("2장 회사 스스로의 진단 (경영진의 설명)", mda["summary"])
    if focus:
        lines = [f"{name}: {focus[k]['summary']}" for k, name in FOCUS_KEYS if focus.get(k) and focus[k].get("summary")]
        if lines:
            out["pdf:focus"] = ("3장 회사가 힘쓰는 곳", "\n".join(lines))
    return {k: (f"{v[0]} · {label}", v[1]) for k, v in out.items()}
