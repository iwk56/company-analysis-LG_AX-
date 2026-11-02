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


LOOKUP_BATCH = 10  # 개황은 이름 순서대로 10곳씩만 조회해 상장기업 10곳이 모이면 멈춘다


async def _listed_matches(client: httpx.AsyncClient, hits: list[dict]) -> tuple[list[dict], dict, int]:
    """이름이 맞는 기업 중 현재 상장(유가증권·코스닥)인 곳만 최대 10곳.

    고유번호 파일에는 상장폐지 기업도 종목코드가 남아 있어 개황의 시장구분으로 걸러야 한다.
    반환: (상장기업, 개황 캐시, 조회에 실패한 기업 수)
    """
    cache = company_cache.load_cache()
    listed, lookup_failed = [], 0
    for i in range(0, len(hits), LOOKUP_BATCH):
        chunk = hits[i : i + LOOKUP_BATCH]
        stale = [c["corp_code"] for c in chunk if not company_cache.is_fresh(cache.get(c["corp_code"]))]
        results = await asyncio.gather(
            *(company_cache.fetch_overview(client, code) for code in stale), return_exceptions=True
        )
        for code, res in zip(stale, results):
            if isinstance(res, DartError):  # 한 곳이 실패해도 나머지는 보여준다
                lookup_failed += 1
            elif isinstance(res, BaseException):
                raise res
            else:
                cache[code] = res
        if stale:
            company_cache.save_cache(cache)
        listed += [c for c in chunk if company_cache.is_listed(cache.get(c["corp_code"]))]
        if len(listed) >= MAX_RESULTS:
            break
    return listed[:MAX_RESULTS], cache, lookup_failed


@app.get("/api/companies/search")
async def search_companies(q: str = Query(..., description="기업명 (2글자 이상)")):
    q = q.strip()
    if len(q) < MIN_QUERY_LENGTH:
        raise HTTPException(status_code=400, detail="2글자 이상 입력해 주세요")
    try:
        async with httpx.AsyncClient() as client:
            hits = search_listed(await load_listed_corps(client), q)
            corps, cache, lookup_failed = await _listed_matches(client, hits)
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
    warning = f"{lookup_failed}곳은 DART 조회에 실패해 결과에서 빠졌을 수 있습니다" if lookup_failed else None
    return {"query": q, "count": len(items), "message": message, "warning": warning, "items": items}
