"""상장 후보 전체의 기업개황(업종코드·시장구분)을 천천히 조사해 캐시에 쌓는다.

    backend/.venv/bin/python -m app.survey_industry --delay 0.5 --limit 1000

- 이미 조사한(캐시가 신선한) 기업은 건너뛰므로 여러 번 나눠 돌려도 된다. 실패한 기업은 캐시에 없으니 다음 실행에서 다시 시도한다.
- 연결이 연속으로 끊기거나 호출 한도(020)가 나오면 DART를 더 두드리지 않고 바로 멈춘다.
"""
import argparse
import asyncio

import httpx

from . import company_cache
from .corp_codes import load_listed_corps
from .dart import DartError

SAVE_EVERY = 50


async def run_survey(
    client,
    corps: list[dict],
    *,
    delay: float,
    limit: int | None,
    max_consecutive_failures: int = 5,
    fetch=company_cache.fetch_overview,
    sleep=asyncio.sleep,
) -> dict:
    cache = company_cache.load_cache()
    todo = [c for c in corps if not company_cache.is_fresh(cache.get(c["corp_code"]))]
    skipped = len(corps) - len(todo)
    if limit is not None:
        todo = todo[:limit]

    done = failed = consecutive = 0
    stopped_reason = None
    for c in todo:
        try:
            cache[c["corp_code"]] = await fetch(client, c["corp_code"])
            done += 1
            consecutive = 0
        except DartError as e:
            failed += 1
            if e.status == "020":  # 호출 한도 초과
                stopped_reason = "DART 호출 한도 초과(020)"
                break
            if e.status == "network":
                consecutive += 1
                if consecutive >= max_consecutive_failures:
                    stopped_reason = f"연결 실패 {consecutive}회 연속 — DART가 막았을 수 있어 중단"
                    break
        if done and done % SAVE_EVERY == 0:
            company_cache.save_cache(cache)
        await sleep(delay)
    company_cache.save_cache(cache)
    return {"total": len(corps), "already_done": skipped, "fetched": done,
            "failed": failed, "remaining": len(todo) - done - failed, "stopped": stopped_reason}


async def _main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--delay", type=float, default=0.5, help="호출 사이 간격(초)")
    parser.add_argument("--limit", type=int, default=None, help="이번 실행에서 조회할 최대 기업 수")
    args = parser.parse_args()
    async with httpx.AsyncClient() as client:
        corps = await load_listed_corps(client)
        print(await run_survey(client, corps, delay=args.delay, limit=args.limit))


if __name__ == "__main__":
    asyncio.run(_main())
