"""주가·시가총액 수집: 공공데이터포털 금융위원회_주식시세정보 V2 (docs/spec.md 1장·5장, Phase 5-B).

기업마다 최근 1년 일별 시세를 한 번에 받는다(1건, 최대 400행). 보통주 종목코드 기준이라 시가총액도 보통주만이다.
수정주가가 아니므로 액면분할 등은 반영되지 않는다. 상장주식수가 하루 사이 크게 바뀐 날을 코드가 찾아 안내한다.
"""
from datetime import date, timedelta
from urllib.parse import unquote

import httpx

from .config import get_data_go_kr_key

URL = "https://apis.data.go.kr/1160100/GetStockSecuritiesInfoService_V2/getStockPriceInfo_V2"
SOURCE_URL = "https://www.data.go.kr/data/15094808/openapi.do"
SOURCE_LABEL = "공공데이터포털 금융위원회_주식시세정보"
TIMEOUT = 30
MAX_ROWS = 400  # 1년 거래일(약 245일)보다 넉넉하게
SPLIT_RATIO = 2.0  # 상장주식수가 하루 사이 2배 이상 늘거나 절반 이하로 줄면 액면분할·병합 등으로 본다
SHORT_HISTORY_DAYS = 10  # 첫 거래일이 기간 시작보다 이만큼 늦으면 '조회 기간 중 상장'으로 본다


class StockError(Exception):
    """주가 수집 단계 실패. 메시지에 키(URL)를 넣지 않는다."""


def _int(v) -> int | None:
    try:
        return int(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_items(items: list[dict], stock_code: str) -> list[dict]:
    """응답 행 → [{"date", "close", "shares", "market_cap"}] (날짜순). 종목코드가 정확히 같은 행만(부분 일치 검색이라)."""
    out = {}
    for it in items:
        if str(it.get("srtnCd", "")).strip() != stock_code:
            continue
        d = str(it.get("basDt", ""))
        close, shares, cap = _int(it.get("clpr")), _int(it.get("lstgStCnt")), _int(it.get("mrktTotAmt"))
        if len(d) != 8 or not close:
            continue
        out[d] = {"date": f"{d[:4]}-{d[4:6]}-{d[6:8]}", "close": close, "shares": shares, "market_cap": cap}
    return [out[k] for k in sorted(out)]


async def fetch_prices(client: httpx.AsyncClient, stock_code: str, start: date, end: date) -> list[dict]:
    """start 이상 end 이하 일별 시세. 자료가 없으면 빈 목록."""
    try:
        key = unquote(get_data_go_kr_key())
    except RuntimeError as e:
        raise StockError(str(e)) from None
    params = {"serviceKey": key, "numOfRows": MAX_ROWS, "pageNo": 1, "resultType": "json", "likeSrtnCd": stock_code,
              "beginBasDt": start.strftime("%Y%m%d"), "endBasDt": (end + timedelta(days=1)).strftime("%Y%m%d")}  # endBasDt는 '미만'
    try:
        resp = await client.get(URL, params=params, timeout=TIMEOUT)
    except httpx.HTTPError as e:  # 예외 문자열에는 키가 담긴 URL이 있을 수 있어 종류만 남긴다
        raise StockError(f"공공데이터포털에 연결하지 못했습니다 ({type(e).__name__})") from None
    text = resp.text
    if "SERVICE_KEY_IS_NOT_REGISTERED" in text:
        raise StockError("공공데이터포털 인증키를 확인해 주세요 (금융위원회_주식시세정보 활용신청·backend/.env의 DATA_GO_KR_KEY)")
    if "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in text:
        raise StockError("공공데이터포털 하루 호출 한도를 넘었습니다. 내일 다시 시도해 주세요")
    try:
        body = resp.json()["response"]
    except (ValueError, KeyError, TypeError):
        raise StockError(f"공공데이터포털 응답을 읽지 못했습니다 (HTTP {resp.status_code})") from None
    code = str((body.get("header") or {}).get("resultCode"))
    if code != "00":
        raise StockError(f"공공데이터포털 주식시세 조회에 실패했습니다 (코드 {code})")
    items = ((body.get("body") or {}).get("items") or {})
    items = items.get("item") if isinstance(items, dict) else []
    if isinstance(items, dict):  # 1건이면 목록이 아니라 객체로 오는 경우가 있다
        items = [items]
    return parse_items(items or [], stock_code)


def build_series(company: dict, rows: list[dict], start: date, end: date, is_target: bool) -> dict:
    """한 기업의 시계열과 지수(기준일 = 100), 최신 시가총액, 안내 문구. 계산은 모두 여기서 한다."""
    out = {"corp_code": company["corp_code"], "corp_name": company["corp_name"], "stock_code": company["stock_code"],
           "is_target": is_target, "start": start.isoformat(), "end": end.isoformat(), "base_date": None, "points": [], "notes": []}
    if not rows:
        out["notes"].append("조회 기간의 시세가 없습니다")
        return out
    base = rows[0]  # 기간 시작(생성일 1년 전) 이후 첫 거래일
    out["base_date"] = base["date"]
    out["points"] = [{**r, "index": round(r["close"] / base["close"] * 100, 2)} for r in rows]
    if date.fromisoformat(base["date"]) - start > timedelta(days=SHORT_HISTORY_DAYS):
        out["notes"].append(f"조회 기간 중 첫 거래일({base['date']})을 기준(=100)으로 했습니다 (상장 1년 미만이거나 거래가 없던 기간이 있음)")
    for prev, cur in zip(rows, rows[1:]):
        if prev["shares"] and cur["shares"]:
            ratio = cur["shares"] / prev["shares"]
            if ratio >= SPLIT_RATIO or ratio <= 1 / SPLIT_RATIO:
                out["notes"].append(f"{cur['date']}에 상장주식수가 크게 바뀌어(액면분할·병합 등) 그 앞뒤 주가 흐름이 왜곡됐을 수 있습니다")
    return out


def latest_market(series: dict | None) -> dict | None:
    """가장 최근 거래일의 시가총액(보통주). 없으면 None."""
    pts = (series or {}).get("points") or []
    last = next((p for p in reversed(pts) if p.get("market_cap")), None)
    return {"market_cap": last["market_cap"], "as_of": last["date"]} if last else None


async def fetch_stocks(client: httpx.AsyncClient, companies: list[tuple[dict, bool]], today: date | None = None) -> list[dict]:
    """(기업, 분석 기업 여부) 목록 → 기업별 시계열. 하나씩 순서대로 부른다(리포트당 최대 5건)."""
    end = today or date.today()
    start = end - timedelta(days=365)
    out = []
    for company, is_target in companies:
        rows = await fetch_prices(client, company["stock_code"], start, end) if company.get("stock_code") else []
        out.append(build_series(company, rows, start, end, is_target))
    return out
