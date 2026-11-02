import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query

from . import company_cache
from .ksic import industry_name
from .corp_codes import load_listed_corps, search_listed
from .dart import DartError
from .industry import is_financial
from .key_specs import startup_warnings

log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 서버를 켤 때 비어 있는 키 이름만 경고한다 (외부 호출은 하지 않는다)
    for warning in startup_warnings(os.environ):
        log.warning(warning)
    yield


app = FastAPI(title="기업분석 리포트 API", lifespan=lifespan)

MIN_QUERY_LENGTH = 2
MAX_RESULTS = 10


MAX_LOOKUPS_PER_SEARCH = 20  # 검색 1번에 DART로 나가는 기업개황 호출 상한 (캐시에 있는 기업은 세지 않음)
LOOKUP_INTERVAL_SECONDS = 0.5  # 호출 사이 간격. 동시에 몰아서 부르지 않는다
_sleep = asyncio.sleep  # 테스트에서 바꿀 수 있게 이름만 따로 둔다


async def _listed_matches(client: httpx.AsyncClient, hits: list[dict]) -> tuple[list[dict], dict, int, bool]:
    """이름이 맞는 기업 중 현재 상장(유가증권·코스닥)인 곳만 최대 10곳.

    고유번호 파일에는 상장폐지 기업도 종목코드가 남아 있어 개황의 시장구분으로 걸러야 한다.
    개황은 캐시에 없는 기업만 이름 순서대로 하나씩, 간격을 두고, 검색 1번에 최대 20건까지만 조회한다.
    연결이 끊기거나 호출 한도(020)가 나오면 더 부르지 않고 멈춘다.
    반환: (상장기업, 개황 캐시, 조회에 실패한 기업 수, 상한·중단 때문에 끝까지 못 본 여부)
    """
    cache = company_cache.load_cache()
    listed, lookup_failed, fetched, incomplete = [], 0, 0, False
    for c in hits:
        if len(listed) >= MAX_RESULTS:
            break
        code = c["corp_code"]
        if not company_cache.is_fresh(cache.get(code)):
            if fetched >= MAX_LOOKUPS_PER_SEARCH:
                incomplete = True
                break
            if fetched:
                await _sleep(LOOKUP_INTERVAL_SECONDS)
            fetched += 1
            try:
                cache[code] = await company_cache.fetch_overview(client, code)
            except DartError as e:
                lookup_failed += 1
                if e.status in ("network", "020"):  # 막혔거나 한도 초과면 계속 두드리지 않는다
                    incomplete = True
                    break
                continue
        if company_cache.is_listed(cache.get(code)):
            listed.append(c)
    if fetched:
        company_cache.save_cache(cache)
    return listed, cache, lookup_failed, incomplete


@app.get("/api/companies/search")
async def search_companies(q: str = Query(..., description="기업명 (2글자 이상)")):
    q = q.strip()
    if len(q) < MIN_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail="2글자 이상 입력해 주세요")
    try:
        async with httpx.AsyncClient() as client:
            hits = search_listed(await load_listed_corps(client), q)
            corps, cache, lookup_failed, incomplete = await _listed_matches(client, hits)
    except DartError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except RuntimeError as e:  # DART_API_KEY 없음
        raise HTTPException(status_code=500, detail=str(e))

    codes = {c["corp_code"]: cache[c["corp_code"]]["induty_code"] for c in corps}

    items = [
        {
            "corp_code": c["corp_code"],
            "corp_name": c["corp_name"],
            "stock_code": c["stock_code"],
            "industry_code": codes[c["corp_code"]],
            "industry_name": industry_name(codes[c["corp_code"]]),
            # 업종명을 못 찾으면(표에 없는 코드 등) 코드를 그대로 보여준다
            "industry_label": industry_name(codes[c["corp_code"]]) or codes[c["corp_code"]],
            "is_financial": is_financial(c["corp_code"], codes[c["corp_code"]]),
        }
        for c in corps
    ]
    message = None if items else "상장기업 중 일치하는 기업이 없습니다"
    warnings = []
    if lookup_failed:
        warnings.append(f"{lookup_failed}곳은 DART 조회에 실패해 결과에서 빠졌을 수 있습니다")
    if incomplete:
        warnings.append("DART 조회 상한(1회 검색당 20건) 또는 오류로 일부 기업을 확인하지 못했습니다. 검색어를 더 구체적으로 입력하거나 다시 검색해 주세요")
    warning = " / ".join(warnings) or None
    return {"query": q, "count": len(items), "message": message, "warning": warning, "items": items}
