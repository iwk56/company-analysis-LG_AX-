"""경쟁사 자동 선정 (2026-11-04, 산업·경쟁 탭). 실무 기준(같은 제품 → 같은 고객 → 비슷한 사업 구조)을 먼저 보고, 이름·규모는 마지막에 본다.

1) 후보 (코드):
   ① 같은 제품: 한국거래소 KIND에 등록된 '주요제품' 단어가 분석 기업과 겹치는 상장 일반기업(업종코드가 달라도 들어온다, 예: 삼성전자)
   ② 같은 업종: 업종코드 앞 3자리(중분류, 예: 261 반도체 제조)가 같은 상장 일반기업
   ①을 먼저(겹친 단어 많은 순), 그다음 ②를 시가총액 큰 순으로 최대 20곳. 금융업·스팩·분석 기업 자신은 뺀다.
2) AI(값싼 모델)가 후보마다 주요제품·업종·시가총액을 보고 ①같은 제품 ②같은 고객 ③비슷한 사업 구조 순으로 판단해 최대 6곳 고른다.
   회사 이름의 느낌이나 시가총액은 판단 근거로 쓰지 않는다. 후보 밖 국내 상장 직접 경쟁사는 이름으로 최대 3곳 더할 수 있다.
   이름은 코드가 상장기업 목록과 정확히 맞춰 보고, 없는 이름·금융업은 버린다.
3) AI가 실패하면 제품 단어가 겹치는 회사 → 같은 세부 업종 → 시가총액 순으로 6곳. 비교 숫자는 모두 DART·주식시세에서 코드가 계산한다.
"""
import json
import logging
from datetime import date, timedelta
from urllib.parse import unquote

import httpx

from . import ai_prompts as P
from . import company_cache, kind_products
from .ai_tasks import ask
from .config import DATA_DIR, get_data_go_kr_key
from .corp_codes import SPAC_KEYWORDS
from .industry import is_financial
from .ksic import industry_name
from .llm import LlmError
from .stocks import URL as STOCK_URL

log = logging.getLogger("uvicorn.error")
CAPS_DIR = DATA_DIR / "market_caps"
MAX_PEERS = 6  # 2026-11-04 사용자 요청: 국내 경쟁사 최대 6곳
MAX_CANDIDATES = 20  # AI에 보여 줄 후보 수 (제품이 겹치는 곳 먼저, 그다음 같은 업종 시가총액 순)
MAX_PRODUCT_MATCHES = 10  # 후보 중 '같은 제품' 몫
LOOKBACK_DAYS = 7  # 주말·휴일이면 하루씩 앞으로
BASIS = {"product": "같은 제품", "customer": "같은 고객", "structure": "비슷한 사업 구조"}  # AI가 고른 근거 → 화면 표시


async def market_caps(client: httpx.AsyncClient, today: date | None = None) -> dict[str, int]:
    """종목코드 → 시가총액(원), 가장 최근 거래일 하루치. 하루치를 파일로 저장해 같은 날 다시 부르지 않는다. 실패하면 빈 dict."""
    today = today or date.today()
    try:
        key = unquote(get_data_go_kr_key())
    except RuntimeError:
        return {}
    for back in range(1, LOOKBACK_DAYS + 1):
        day = today - timedelta(days=back)
        path = CAPS_DIR / f"{day:%Y%m%d}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        params = {"serviceKey": key, "numOfRows": 4000, "pageNo": 1, "resultType": "json", "basDt": day.strftime("%Y%m%d")}
        try:
            resp = await client.get(STOCK_URL, params=params, timeout=60)
            items = ((resp.json()["response"].get("body") or {}).get("items") or {})
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            log.warning("시가총액 조회 실패 (%s)", type(e).__name__)
            return {}
        items = items.get("item") if isinstance(items, dict) else []
        if isinstance(items, dict):
            items = [items]
        caps = {}
        for it in items or []:
            code, cap = str(it.get("srtnCd", "")).strip(), str(it.get("mrktTotAmt", "")).replace(",", "")
            if code and cap.isdigit():
                caps[code] = int(cap)
        if caps:
            CAPS_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(caps), encoding="utf-8")
            return caps
    return {}


def candidates(target: dict, corps: list[dict], cache: dict, caps: dict[str, int], products: dict[str, dict] | None = None) -> list[dict]:
    """후보 목록. 각 항목에 market_cap·induty_code·products·shared(겹친 제품 단어)·match를 붙인다.
    products: 종목코드 → {"products", "sector"} (KIND). 없으면 업종코드만으로 고른다."""
    products = products or {}
    code = (cache.get(target["corp_code"]) or {}).get("induty_code") or target.get("industry_code") or ""
    mine = kind_products.keywords((products.get(target.get("stock_code") or "") or {}).get("products", ""))

    usable = []
    for c in corps:
        e = cache.get(c["corp_code"])
        if (c["corp_code"] == target["corp_code"] or not company_cache.is_listed(e) or any(k in c["corp_name"] for k in SPAC_KEYWORDS)
                or is_financial(c["corp_code"], e.get("induty_code"))):
            continue
        prod = (products.get(c.get("stock_code") or "") or {}).get("products", "")
        usable.append({**c, "induty_code": e.get("induty_code") or "", "market_cap": caps.get(c.get("stock_code") or ""),
                       "products": prod, "shared": sorted(kind_products.overlap(mine, kind_products.keywords(prod))) if mine else []})

    def label(x: dict) -> str:
        parts = []
        if x["shared"]:
            parts.append("같은 제품 단어(" + ", ".join(x["shared"][:3]) + ")")
        if code and x["induty_code"] == code:
            parts.append("같은 업종")
        elif code and x["induty_code"][:3] == code[:3]:
            parts.append("비슷한 업종")
        return " · ".join(parts)

    # 제품 단어가 겹쳐도 업종 대분류(앞 2자리, 예: 26 전자부품·컴퓨터·통신장비)가 다르면 단어 2개 이상 겹칠 때만 후보로 둔다
    # (등록된 주요제품이 짧고 오래돼 '컴퓨터' 한 단어로 엉뚱한 회사가 걸리는 것을 막는다)
    def related(x: dict) -> bool:
        return bool(x["shared"]) and (len(x["shared"]) >= 2 or (bool(code) and x["induty_code"][:2] == code[:2]))
    by_product = sorted([x for x in usable if related(x)], key=lambda x: (-len(x["shared"]), -(x["market_cap"] or 0)))[:MAX_PRODUCT_MATCHES]
    taken = {x["corp_code"] for x in by_product}
    # 같은 업종: 앞 3자리(중분류)가 같은 곳을 시가총액 순으로. 세부 코드(예: 2612)에는 LED·태양광이 섞여 있어 세부 코드를 우선하지 않는다
    same = (lambda x: x["induty_code"][:3] == code[:3]) if len(code) > 3 else (lambda x: x["induty_code"] == code)
    by_industry = sorted([x for x in usable if code and same(x) and x["corp_code"] not in taken], key=lambda x: -(x["market_cap"] or 0))
    return [dict(x, match=label(x)) for x in by_product + by_industry]


def fallback_order(cands: list[dict], code: str) -> list[dict]:
    """AI가 실패했을 때: 제품 단어가 겹치는 곳 → 같은 세부 업종 → 시가총액 순."""
    return sorted(cands, key=lambda x: (-len(x["shared"]), x["induty_code"] != code, -(x["market_cap"] or 0)))  # 후보에 든 것만 정렬


def _cap_text(won: int | None) -> str:
    return f"{won / 1e12:,.1f}조 원" if won else "시세 없음"


async def suggest(client: httpx.AsyncClient, target: dict, corps: list[dict], today: date | None = None) -> list[dict]:
    """[{corp_code, corp_name, stock_code, reason, picked_by}] 최대 6곳. 고를 수 없으면 빈 목록."""
    cache = company_cache.load_cache()
    caps = await market_caps(client, today)
    products = await kind_products.load(client)
    cands = candidates(target, corps, cache, caps, products)[:MAX_CANDIDATES]
    code = (cache.get(target["corp_code"]) or {}).get("induty_code") or target.get("industry_code") or ""
    fallback = [{"corp_code": c["corp_code"], "corp_name": c["corp_name"], "stock_code": c["stock_code"],
                 "reason": f"{c['match'] or '같은 업종'} · 시가총액 {_cap_text(c['market_cap'])}", "picked_by": "industry"}
                for c in fallback_order(cands, code)[:MAX_PEERS]]
    mine = (products.get(target.get("stock_code") or "") or {}).get("products") or "자료 없음"
    lines = [f"- {c['corp_name']} | 주요제품: {c['products'] or '자료 없음'} | 업종: {industry_name(c['induty_code']) or c['induty_code']}"
             f" | 시가총액 {_cap_text(c['market_cap'])}" for c in cands]
    user = P.user_message(P.PICK_PEERS, {
        "분석 기업": f"{target['corp_name']} | 주요제품: {mine} | 업종: {target.get('industry_name') or '모름'}"
                  f" | 시가총액 {_cap_text(caps.get(target.get('stock_code') or ''))}",
        "후보 (같은 제품 단어가 겹치는 곳 먼저, 그다음 같은 업종 시가총액 순)": "\n".join(lines) or "없음",
    })
    try:
        r = await ask(client, "pick_peers", "extract", user)
    except LlmError as e:
        log.warning("경쟁사 고르기 AI 실패, 시가총액 순으로 정함: %s", e.message)
        return fallback
    log.info("경쟁사 고르기 AI 응답 (%s, 토큰 %s/%s): %s", getattr(r, "model", None), getattr(r, "input_tokens", 0), getattr(r, "output_tokens", 0),
             [p.get("name") for p in ((r.data.get("peers") if isinstance(r.data, dict) else None) or []) if isinstance(p, dict)])
    by_name = {c["corp_name"].replace(" ", ""): c for c in corps}
    out, seen = [], {target["corp_code"]}
    for p in (r.data.get("peers") if isinstance(r.data, dict) else None) or []:
        if not isinstance(p, dict) or len(out) >= MAX_PEERS:
            continue
        c = by_name.get(str(p.get("name") or "").replace(" ", ""))
        e = cache.get(c["corp_code"]) if c else None
        if (not c or c["corp_code"] in seen or not company_cache.is_listed(e) or is_financial(c["corp_code"], (e or {}).get("induty_code"))
                or any(k in c["corp_name"] for k in SPAC_KEYWORDS)):
            continue
        seen.add(c["corp_code"])
        reason = str(p.get("reason") or "").strip()[:80]
        tags = [BASIS[b] for b in (p.get("basis") or []) if b in BASIS]
        text = " · ".join(dict.fromkeys(tags)) + (" — " if tags and reason else "") + reason
        out.append({"corp_code": c["corp_code"], "corp_name": c["corp_name"], "stock_code": c["stock_code"],
                    "reason": text or "AI가 고른 비교 기업", "picked_by": "ai"})
    if not out:
        log.warning("경쟁사 고르기 AI가 쓸 수 있는 회사를 돌려주지 않아 시가총액 순으로 정함")
    return out or fallback
