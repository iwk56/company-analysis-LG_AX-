"""OpenDART 고유번호 파일: 하루 1번만 내려받아 상장기업 목록으로 저장한다."""
import io
import json
import logging
import xml.etree.ElementTree as ET
import zipfile
from datetime import date

import httpx

from .config import DATA_DIR
from .dart import DartError, fetch_corp_code_zip

log = logging.getLogger(__name__)

LISTED_FILE = DATA_DIR / "listed_corps.json"


def parse_listed(zip_bytes: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        root = ET.fromstring(z.read(z.namelist()[0]))
    corps = []
    for item in root.iter("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        if not stock_code:  # 종목코드가 없으면 비상장
            continue
        corps.append(
            {
                "corp_code": (item.findtext("corp_code") or "").strip(),
                "corp_name": (item.findtext("corp_name") or "").strip(),
                "stock_code": stock_code,
            }
        )
    return corps


def _read_saved() -> dict | None:
    if not LISTED_FILE.exists():
        return None
    return json.loads(LISTED_FILE.read_text(encoding="utf-8"))


async def load_listed_corps(client: httpx.AsyncClient) -> list[dict]:
    saved = _read_saved()
    today = date.today().isoformat()
    if saved and saved["fetched_date"] == today:
        return saved["corps"]
    try:
        corps = parse_listed(await fetch_corp_code_zip(client))
    except DartError as e:
        if saved:  # 새로 못 받으면 어제까지 받아 둔 목록으로 계속
            log.warning("고유번호 파일 갱신 실패, 이전 파일 사용: %s", e)
            return saved["corps"]
        raise
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LISTED_FILE.write_text(
        json.dumps({"fetched_date": today, "corps": corps}, ensure_ascii=False),
        encoding="utf-8",
    )
    return corps


SPAC_KEYWORDS = ("스팩", "기업인수목적")  # 기업인수목적회사(스팩)는 분석 대상이 아니라 검색 결과에서 뺀다


def search_listed(corps: list[dict], query: str, limit: int | None = None) -> list[dict]:
    """이름이 일치 → 앞부분 일치 → 포함 순. 같은 순위 안에서는 이름이 짧은 순(삼성전자 같은 대표 기업이 앞에 오도록), 그다음 가나다순.

    이름에 "스팩" 또는 "기업인수목적"이 든 기업은 뺀다. 상장폐지 기업 걸러내기는 호출하는 쪽 몫.
    """
    q = query.strip().casefold()
    hits = []
    for c in corps:
        name = c["corp_name"].casefold()
        if q not in name or any(k in name for k in SPAC_KEYWORDS):
            continue
        rank = 0 if name == q else 1 if name.startswith(q) else 2
        hits.append((rank, len(name), c["corp_name"], c))
    hits.sort(key=lambda h: h[:3])
    return [h[3] for h in hits[:limit]]  # limit=None 이면 전체
