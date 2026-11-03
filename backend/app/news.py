"""기사 수집: NAVER API HUB 뉴스 검색 (docs/spec.md 1장). 제목·요약문·링크·날짜만 받고, 본문은 받지 않는다.

회사명 하나로 날짜순 100건을 한 번에 받아 최근 3개월 안의 기사만 남기고, 같은 링크·같은 제목을 하나로 합친 뒤 최신 30건을 쓴다.

NAVER 검색 API 약관(검색 API 특약 2.2~2.4)에 따라
- 제목·요약문은 받은 그대로 저장한다(검색어 강조 <b>와 HTML 문자 포함, 화면이 안전하게 표시한다)
- 서버 보관은 이력 조회 목적으로 수집 후 21일까지만 하고, 지나면 지운다(report_store.purge_expired_articles)
- 기사 데이터는 AI에 넣지 않는다(화면의 참고 목록으로만 쓴다)
"""
import html
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from .config import get_naver_credentials

NEWS_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
FETCH_COUNT = 100  # 한 번에 받는 최대 건수(검색 API 상한)
MAX_ARTICLES = 30
MONTHS = 3
RETENTION_DAYS = 21  # 약관상 서버 보관 최대 기간 (이력 조회 목적)
KST = timezone(timedelta(hours=9))
TIMEOUT = 15
_TAG = re.compile(r"<[^>]+>")
_NOT_WORD = re.compile(r"[\W_]+")


class NewsError(Exception):
    """기사 수집 단계 실패. 메시지는 화면에 그대로 보여주므로 키 값은 절대 넣지 않는다."""


def months_ago(today: date, months: int) -> date:
    y, m = divmod(today.year * 12 + today.month - 1 - months, 12)
    m += 1
    for day in (today.day, 30, 29, 28):  # 말일이 없는 달이면 앞당긴다
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise AssertionError


def clean_text(text: str) -> str:
    """중복 판단용: 검색어 강조 태그(<b>)를 지우고 HTML 문자(&quot; 등)를 원래 글자로 바꾼다. 저장·표시에는 쓰지 않는다."""
    return " ".join(html.unescape(_TAG.sub("", text or "")).split())


def _title_key(title: str) -> str:
    return _NOT_WORD.sub("", title).lower()


def parse_items(items: list[dict], today: date, limit: int = MAX_ARTICLES) -> list[dict]:
    """응답 항목 → 기사 목록(최신순). 3개월 밖·날짜를 읽을 수 없는·링크가 없는 기사와 중복은 뺀다."""
    since = months_ago(today, MONTHS)
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    rows: list[dict] = []
    for it in items:
        title = it.get("title") or ""
        link = (it.get("originallink") or it.get("link") or "").strip()  # 언론사 원문 우선
        try:
            published = parsedate_to_datetime(it.get("pubDate", "")).astimezone(KST).replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
        key = _title_key(clean_text(title))
        if not key or not link or not (since <= published.date() <= today):
            continue
        if link in seen_links or key in seen_titles:
            continue
        seen_links.add(link)
        seen_titles.add(key)
        rows.append({"title": title, "summary": it.get("description") or "", "link": link, "published_at": published})
    rows.sort(key=lambda r: r["published_at"], reverse=True)
    return rows[:limit]


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


async def fetch_news(client: httpx.AsyncClient, query: str, today: date | None = None) -> list[dict]:
    """회사명으로 최근 3개월 기사를 최대 30건 가져온다. 기사가 없으면 빈 목록."""
    try:
        cid, secret = get_naver_credentials()
    except RuntimeError as e:  # .env에 키가 없음
        raise NewsError(str(e)) from None
    try:
        resp = await client.get(NEWS_URL, params={"query": query, "display": FETCH_COUNT, "sort": "date"}, timeout=TIMEOUT,
                                headers={"X-NCP-APIGW-API-KEY-ID": cid, "X-NCP-APIGW-API-KEY": secret})
    except httpx.HTTPError as e:
        raise NewsError(f"NAVER API HUB에 연결하지 못했습니다 ({type(e).__name__})") from None
    if resp.status_code != 200:
        raise NewsError(_error_message(resp))
    try:
        items = resp.json().get("items", [])
    except ValueError:
        raise NewsError("NAVER API HUB 응답을 읽지 못했습니다") from None
    return parse_items(items, today or datetime.now(KST).date())
