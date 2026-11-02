"""기업개황 캐시: 조회한 기업의 업종코드·시장구분을 파일에 저장해 두고 재사용한다.

검색, 전체 업종코드 조사(survey_industry.py), Phase 5 경쟁사 추천이 같은 파일을 쓴다."""
import json
import time

import httpx

from .config import DATA_DIR
from .dart import fetch_company

CACHE_FILE = DATA_DIR / "company_cache.json"
CACHE_TTL_SECONDS = 90 * 24 * 3600  # 업종코드·시장구분은 드물게 바뀌어 90일마다 새로 조회


def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    return json.loads(CACHE_FILE.read_text(encoding="utf-8"))


def save_cache(cache: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def is_fresh(entry: dict | None) -> bool:
    return bool(entry) and time.time() - entry["fetched_at"] < CACHE_TTL_SECONDS


async def fetch_overview(client: httpx.AsyncClient, corp_code: str) -> dict:
    data = await fetch_company(client, corp_code)
    return {
        "induty_code": (data.get("induty_code") or "").strip() or None,
        "corp_cls": data.get("corp_cls"),  # Y 유가증권, K 코스닥, N 코넥스, E 기타(상장폐지 등)
        "fetched_at": time.time(),
    }

LISTED_CLS = ("Y", "K")  # 유가증권·코스닥만 상장기업으로 본다 (코넥스 N, 기타 E 제외)


def is_listed(entry: dict | None) -> bool:
    return bool(entry) and entry.get("corp_cls") in LISTED_CLS
