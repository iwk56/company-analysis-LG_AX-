"""기사 수집: NAVER API HUB 뉴스 검색 (docs/spec.md 1장). 제목·요약문·링크·날짜만 받고, 본문은 받지 않는다.

2026-11-03부터 회사명 하나 대신 **취업 준비생 공통 질문 검색어 6개**(사업·투자·전략·협력·인사·우려)로 정확도순 5건씩 받는다.
받은 기사를 고르거나 묶지 않고(약관상 가공 금지) 검색어마다 **받은 순서·내용 그대로** 보여 준다. 사업과 상관없는 기사가
덜 나오게 하는 것은 "무엇을 검색할지"를 정하는 것으로만 한다. 기간 필터·중복 제거·자르기는 하지 않는다.

NAVER 검색 API 약관(검색 API 특약 2.2~2.4)에 따라
- 제목·요약문은 받은 그대로 저장한다(검색어 강조 <b>와 HTML 문자 포함, 화면이 안전하게 표시한다)
- 서버 보관은 이력 조회 목적으로 수집 후 21일까지만 하고, 지나면 지운다(report_store.purge_expired_articles)
- 기사 데이터는 AI에 넣지 않는다(화면의 참고 목록으로만 쓴다)
"""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from .config import get_naver_credentials

NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
DISPLAY = 30  # 최신순으로 받는 건수 (예전 방식: 회사명 하나)
TOPIC_DISPLAY = 5  # 주제별 검색어마다 받는 건수
TOPIC_SORT = "sim"  # 주제별은 정확도순: 최신순이면 증시 마감 기사처럼 회사명만 스친 기사가 앞에 온다 (2026-11-04)
# (화면 제목, 검색어 틀). 주제를 구체화해 겹침을 줄이되 검색결과는 손대지 않는다.
TOPICS = (("사업 현황", "{name} 주요 사업 제품 매출"), ("투자·증설", "{name} 투자 증설 공장"),
          ("전략·신사업", "{name} 신사업 전략 전환"), ("협력·고객", "{name} 공급 계약 협력 고객"),
          ("경영진·조직", "{name} 대표이사 인사 임원"), ("리스크·우려", "{name} 리스크 지연 차질 우려"))
# 2026-11-05 이전에 저장된 기사의 주제 검색어. 기존 보관 중인 기사 그룹을 유지한다.
LEGACY_TOPICS = (("사업 현황", "{name} 사업"), ("투자·증설", "{name} 투자"), ("전략·신사업", "{name} 전략"),
                 ("협력·고객", "{name} 협력"), ("경영진·조직", "{name} 인사"), ("리스크·우려", "{name} 우려"))
# 2026-11-04 방향 전환(회사 이해용): 취준생 질문 말투 대신 짧은 주제 이름. 검색어는 그대로(라벨은 화면에서 검색어로 다시 맞추므로 예전 기사도 새 이름으로 보인다)
# 업종에 상관없이 취업 준비생이 묻는 공통 질문 6개 (2026-11-04, 4개 업종 미리보기로 고름).
# 뺀 것: "실적"·"업황"(주가 기사 위주), "출시"·"채용"(업종·시기에 따라 비거나 엉뚱함).
# "-계열사명"으로 빼는 검색은 네이버 API에서 오히려 엉뚱하고 오래된 기사가 나와 쓰지 않는다(같은 이름으로 시작하는 계열사 기사는 섞일 수 있음)


def topic_queries(corp_name: str) -> list[tuple[str, str]]:
    """[(화면 제목, 검색어)]"""
    return [(label, tpl.format(name=corp_name)) for label, tpl in TOPICS]


def legacy_topic_queries(corp_name: str) -> list[tuple[str, str]]:
    """기존 저장 기사에 사용된 검색어와 화면 제목."""
    return [(label, tpl.format(name=corp_name)) for label, tpl in LEGACY_TOPICS]


def topic_label(query: str, corp_name: str) -> str | None:
    queries = topic_queries(corp_name) + legacy_topic_queries(corp_name)
    return next((label for label, q in queries if q == query), None)
RETENTION_DAYS = 21  # 약관상 서버 보관 최대 기간 (이력 조회 목적)
KST = timezone(timedelta(hours=9))
TIMEOUT = 15


class NewsError(Exception):
    """기사 수집 단계 실패. 메시지는 화면에 그대로 보여주므로 키 값은 절대 넣지 않는다."""


def parse_items(items: list[dict]) -> list[dict]:
    """응답 항목 → 기사 목록. 순서와 내용은 받은 그대로이고, 링크나 날짜가 없어 보여줄 수 없는 항목만 뺀다."""
    rows: list[dict] = []
    for it in items:
        link = (it.get("originallink") or it.get("link") or "").strip()  # 언론사 원문 우선
        try:
            published = parsedate_to_datetime(it.get("pubDate", "")).astimezone(KST).replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
        if not link:
            continue
        rows.append({"title": it.get("title") or "", "summary": it.get("description") or "", "link": link, "published_at": published})
    return rows


def is_expired(collected_at: datetime, now: datetime) -> bool:
    """수집 후 21일이 지났는가 (둘 다 한국 시간, 시간대 정보 없음)."""
    return now >= collected_at + timedelta(days=RETENTION_DAYS)


def now_kst() -> datetime:
    return datetime.now(KST).replace(tzinfo=None, microsecond=0)


def _error_message(resp: httpx.Response) -> str:
    if resp.status_code == 401:
        return "NAVER API HUB 인증에 실패했습니다. backend/.env의 NAVER_CLIENT_ID·NAVER_CLIENT_SECRET과 API 권한을 확인해 주세요"
    if resp.status_code == 429:
        return "NAVER API HUB 하루 호출 한도를 넘었습니다. 내일 다시 시도해 주세요"
    return f"기사 검색에 실패했습니다 (HTTP {resp.status_code})"


async def fetch_news(client: httpx.AsyncClient, query: str, display: int = DISPLAY, sort: str = "date") -> list[dict]:
    """검색어로 기사 display건을 받은 그대로 가져온다(sort: date 최신순 | sim 정확도순). 기사가 없으면 빈 목록."""
    try:
        cid, secret = get_naver_credentials()
    except RuntimeError as e:  # .env에 키가 없음
        raise NewsError(str(e)) from None
    try:
        resp = await client.get(NEWS_URL, params={"query": query, "display": display, "sort": sort}, timeout=TIMEOUT,
                                headers={"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret})
    except httpx.HTTPError as e:
        raise NewsError(f"NAVER API HUB에 연결하지 못했습니다 ({type(e).__name__})") from None
    if resp.status_code != 200:
        raise NewsError(_error_message(resp))
    try:
        items = resp.json().get("items", [])
    except ValueError:
        raise NewsError("NAVER API HUB 응답을 읽지 못했습니다") from None
    return parse_items(items)
