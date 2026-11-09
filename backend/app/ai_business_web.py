"""사업보고서에 없는 지역별 매출·판매 경로 자료를 공식 DART 웹 검색으로 보완한다."""
from urllib.parse import urlsplit

import httpx

from . import ai_prompts as P
from . import company_cache
from .ai_tasks import Outcome
from .config import web_news_enabled
from .dart import DartError
from .llm import LlmError, call_web_json, _strip_utm

TOPICS = ("region", "channel")
MAX_ITEMS = 2


def missing_topics(business: dict | None, segments: dict | None) -> tuple[str, ...]:
    """이미 PDF나 재무제표 주석에서 확인한 내용은 웹 검색 대상에서 뺀다."""
    sales_mix = (business or {}).get("sales_mix") or {}
    quotes = sales_mix.get("quotes") or []
    text = " ".join(
        [str(sales_mix.get("summary") or "")]
        + [str(q.get("text") or "") for q in quotes if isinstance(q, dict)]
    ).replace(" ", "")
    negative = ("제시되지않", "기재되지않", "자료없", "확인할수없", "확인되지않")
    has_disclosure = not any(marker in text for marker in negative)
    has_region = bool((segments or {}).get("overseas_share") is not None) or (
        has_disclosure and any(word in text for word in ("지역별매출", "국내매출", "해외매출", "수출매출"))
    )
    has_channel = has_disclosure and any(
        word in text for word in ("직판", "직접판매", "대리점", "온라인판매", "도매", "소매", "판매경로")
    )
    return tuple(topic for topic, found in (("region", has_region), ("channel", has_channel)) if not found)


def _homepage_domain(homepage: str | None) -> str | None:
    if not homepage:
        return None
    try:
        parsed = urlsplit(homepage if "://" in homepage else f"https://{homepage}")
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or "." not in host:
        return None
    return host[4:] if host.startswith("www.") else host


def _official_source_url(url: str, homepage_domain: str | None) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        return False
    if host in ("dart.fss.or.kr", "opendart.fss.or.kr") or host.endswith((".dart.fss.or.kr", ".opendart.fss.or.kr")):
        return True
    return bool(homepage_domain and (host == homepage_domain or host.endswith(f".{homepage_domain}")))


async def _official_homepage(client: httpx.AsyncClient, corp_code: str) -> tuple[str | None, str | None]:
    cache = company_cache.load_cache()
    entry = cache.get(corp_code)
    if entry and "homepage" in entry:
        return _homepage_domain(entry["homepage"]), None
    try:
        entry = await company_cache.fetch_overview(client, corp_code)
    except (DartError, RuntimeError) as error:
        return None, f"회사 공식 홈페이지 주소를 확인하지 못했습니다. DART 주소만 검색합니다 ({error})"
    cache[corp_code] = entry
    company_cache.save_cache(cache)
    domain = _homepage_domain(entry.get("homepage"))
    return domain, None if domain else "회사 공식 홈페이지 주소가 없어 DART 주소만 검색합니다"


async def find_business_info(client: httpx.AsyncClient, report: dict, topics: tuple[str, ...]) -> Outcome:
    if not web_news_enabled():
        return Outcome("empty", message="웹 검색이 꺼져 있습니다 (WEB_NEWS=0)")
    if not topics:
        return Outcome("empty", message="PDF·재무제표에서 확인되어 웹 검색을 건너뛰었습니다")

    company = report["company"]
    year = report["base_year"]
    name = company["corp_name"]
    homepage_domain, domain_warning = await _official_homepage(client, company["corp_code"])
    queries = []
    if "region" in topics:
        queries.append(f"site:dart.fss.or.kr {name} {year} 사업보고서 지역별 매출 국내 해외")
        if homepage_domain:
            queries.append(f"site:{homepage_domain} {name} {year} 지역별 매출 IR")
    if "channel" in topics:
        queries.append(f"site:dart.fss.or.kr {name} {year} 사업보고서 판매 경로 판매방법 직판")
        if homepage_domain:
            queries.append(f"site:{homepage_domain} {name} {year} 판매 경로 매출 IR")
    parts = {
        "분석 기업": f"{name} (고유번호: {company['corp_code']}), 기준 사업연도 {year}",
        "회사 공식 홈페이지 도메인": homepage_domain or "확인되지 않음",
        "보완이 필요한 항목": ", ".join(topics),
        "검색 범위": "해당 기업의 해당 사업연도 DART 사업보고서 또는 공식 홈페이지 IR만. 필요한 항목의 공개 자료",
        "추천 검색어": "\n".join(queries),
    }
    try:
        result = await call_web_json(
            client, "business_web", P.WEB_DART_RULES,
            P.user_message(P.WEB_BUSINESS_INFO, parts),
        )
    except LlmError as error:
        return Outcome("failed", message=error.message)

    items, warnings = [], [domain_warning] if domain_warning else []
    seen_topics = set()
    raw_items = result.data.get("items")
    for i, item in enumerate(raw_items if isinstance(raw_items, list) else []):
        if not isinstance(item, dict):
            continue
        topic = item.get("topic")
        claim = str(item.get("claim") or "").strip()
        title = str(item.get("title") or "").strip()
        url = _strip_utm(str(item.get("url") or ""))
        if topic not in TOPICS or topic in seen_topics:
            warnings.append(f"항목 {i + 1}: 알 수 없는 주제이거나 중복이라 제외했습니다")
            continue
        if type(item.get("year")) is not int or item["year"] != year:
            warnings.append(f"항목 {i + 1}: 기준 사업연도가 달라 제외했습니다")
            continue
        if not claim or len(claim) > 500 or not title or len(title) > 200:
            warnings.append(f"항목 {i + 1}: 내용 또는 공시 제목이 비어 있거나 너무 길어 제외했습니다")
            continue
        if not _official_source_url(url, homepage_domain) or url not in result.cited:
            warnings.append(f"항목 {i + 1}: 실제 검색한 공식 DART·회사 홈페이지 주소가 아니라 제외했습니다")
            continue
        seen_topics.add(topic)
        items.append({"topic": topic, "year": year, "claim": claim, "title": title, "url": url})
        if len(items) >= MAX_ITEMS:
            break

    content = {"items": items, "searches": result.searches}
    if not items:
        warnings.append(
            f"응답 키 {sorted(result.data)[:5]}, 항목 "
            f"{len(raw_items) if isinstance(raw_items, list) else '없음'}개, 인용 주소 {len(result.cited)}개"
        )
        topic_labels = {"region": "지역별 매출", "channel": "판매 경로별 매출"}
        requested = "·".join(topic_labels[topic] for topic in topics if topic in topic_labels)
        return Outcome(
            "empty", content,
            f"{year}년 {requested}의 공식 자료를 찾지 못했습니다 (검색 {result.searches}번)",
            model=result.model, input_tokens=result.input_tokens, output_tokens=result.output_tokens, warnings=warnings,
        )

    return Outcome(
        "ok", content, model=result.model, input_tokens=result.input_tokens,
        output_tokens=result.output_tokens, warnings=warnings,
    )
