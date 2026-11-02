"""환율·기준금리 수집: 한국은행 ECOS Open API (docs/spec.md 1장). 최근 1년 일별 값."""
from datetime import date, timedelta

import httpx

from .config import get_ecos_api_key

BASE_URL = "https://ecos.bok.or.kr/api/StatisticSearch"
SOURCE_URL = "https://ecos.bok.or.kr"
TIMEOUT = 15
MAX_ROWS = 1000

# key, 이름, 통계표 코드, 항목 코드, 단위
SERIES = (
    ("usd_krw", "원/달러 환율(매매기준율)", "731Y001", "0000001", "원"),
    ("base_rate", "한국은행 기준금리", "722Y001", "0101000", "%"),
)


class EcosError(Exception):
    """환율·금리 수집 단계 실패. 메시지에 키(URL)를 넣지 않는다."""


def parse_rows(rows: list[dict]) -> list[dict]:
    """ECOS 행 → [{"date": "2026-11-02", "value": 1337.2}] (날짜순). 숫자가 아닌 값은 뺀다."""
    points = []
    for row in rows:
        t = str(row.get("TIME", ""))
        try:
            value = float(row["DATA_VALUE"])
            day = date(int(t[:4]), int(t[4:6]), int(t[6:8]))
        except (KeyError, TypeError, ValueError):
            continue
        points.append({"date": day.isoformat(), "value": value})
    return sorted(points, key=lambda p: p["date"])


async def fetch_series(client: httpx.AsyncClient, stat_code: str, item_code: str, start: date, end: date) -> list[dict]:
    try:
        key = get_ecos_api_key()
    except RuntimeError as e:  # .env에 키가 없음
        raise EcosError(str(e)) from None
    url = f"{BASE_URL}/{key}/json/kr/1/{MAX_ROWS}/{stat_code}/D/{start:%Y%m%d}/{end:%Y%m%d}/{item_code}"
    try:
        resp = await client.get(url, timeout=TIMEOUT)
        data = resp.json()
    except httpx.HTTPError as e:  # 예외 문자열에는 키가 담긴 URL이 있을 수 있어 종류만 남긴다
        raise EcosError(f"한국은행 ECOS에 연결하지 못했습니다 ({type(e).__name__})") from None
    except ValueError:
        raise EcosError(f"한국은행 ECOS 응답을 읽지 못했습니다 (HTTP {resp.status_code})") from None
    if isinstance(data, dict) and "StatisticSearch" in data:
        return parse_rows(data["StatisticSearch"].get("row", []))
    code = str((data.get("RESULT") or {}).get("CODE")) if isinstance(data, dict) else ""
    if code == "INFO-200":  # 해당 기간 데이터 없음
        return []
    if code in ("INFO-100", "INFO-300"):
        raise EcosError("한국은행 ECOS 인증키를 확인해 주세요 (backend/.env의 ECOS_API_KEY)")
    if code == "ERROR-602":
        raise EcosError("한국은행 ECOS 호출 한도를 넘었습니다. 잠시 뒤 다시 시도해 주세요")
    raise EcosError(f"한국은행 ECOS 조회에 실패했습니다 (코드 {code or 'HTTP ' + str(resp.status_code)})")


async def fetch_macro(client: httpx.AsyncClient, today: date | None = None) -> list[dict]:
    """환율·기준금리 최근 1년. 시리즈마다 {key, label, unit, stat_code, source_url, points}."""
    end = today or date.today()
    start = end - timedelta(days=365)
    out = []
    for key, label, stat_code, item_code, unit in SERIES:  # 하나씩 순서대로 부른다
        points = await fetch_series(client, stat_code, item_code, start, end)
        out.append({"key": key, "label": label, "unit": unit, "stat_code": stat_code, "source_url": SOURCE_URL,
                    "start": start.isoformat(), "end": end.isoformat(), "points": points})
    return out
