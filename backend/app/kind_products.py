"""상장사 주요제품 (2026-11-04, 경쟁사 고르기용). 한국거래소 KIND 상장법인목록을 받아 종목코드 → 업종·주요제품.

- 출처: https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13 (EUC-KR HTML 표 한 개, 키 없음)
- 7일마다 한 번만 받아 data/kind_corps.json에 둔다. 받지 못하면 저장된 것을 쓰고, 그것도 없으면 빈 dict(주요제품 없이 고른다).
- 주요제품은 회사가 거래소에 등록한 짧은 설명이라 최신이 아닐 수 있다. AI 고르기의 참고 자료로만 쓰고 화면 숫자에는 쓰지 않는다.
"""
import html
import json
import logging
import re
import time

import httpx

from .config import DATA_DIR

log = logging.getLogger("uvicorn.error")
URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
PATH = DATA_DIR / "kind_corps.json"
MAX_AGE = 7 * 24 * 3600

_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def parse(page: str) -> dict[str, dict]:
    """KIND 표 → {종목코드(6자리): {"name", "sector", "products"}}. 머리글에서 열 위치를 찾는다(열 순서가 바뀌어도 동작)."""
    rows = [[html.unescape(_TAG.sub("", c)).strip() for c in _CELL.findall(r)] for r in _ROW.findall(page)]
    rows = [r for r in rows if r]
    if not rows:
        return {}
    head = rows[0]
    try:
        i_name, i_code = head.index("회사명"), head.index("종목코드")
    except ValueError:
        return {}
    i_sector = head.index("업종") if "업종" in head else None
    i_prod = head.index("주요제품") if "주요제품" in head else None
    out = {}
    for r in rows[1:]:
        if len(r) <= max(i_name, i_code):
            continue
        code = re.sub(r"\D", "", r[i_code]).zfill(6) if re.search(r"\d", r[i_code]) else r[i_code].strip()
        out[code] = {"name": r[i_name], "sector": r[i_sector] if i_sector is not None and i_sector < len(r) else "",
                     "products": r[i_prod] if i_prod is not None and i_prod < len(r) else ""}
    return out


def _saved() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


async def load(client: httpx.AsyncClient) -> dict[str, dict]:
    saved = _saved()
    if saved.get("items") and time.time() - saved.get("fetched_at", 0) < MAX_AGE:
        return saved["items"]
    try:
        resp = await client.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        items = parse(resp.content.decode("euc-kr", errors="replace"))
    except httpx.HTTPError as e:
        log.warning("KIND 상장법인목록(주요제품) 받기 실패 (%s), 저장된 목록을 씀", type(e).__name__)
        return saved.get("items") or {}
    if len(items) < 1000:  # 형식이 바뀌었거나 일부만 왔으면 저장하지 않는다
        log.warning("KIND 상장법인목록이 %d곳뿐이라 쓰지 않음", len(items))
        return saved.get("items") or items
    PATH.write_text(json.dumps({"fetched_at": time.time(), "items": items}, ensure_ascii=False), encoding="utf-8")
    return items


# ───────── 제품 키워드 겹침 (후보 넓히기·AI 실패 시 순서)
_STOP = {"등", "및", "외", "기타", "제조", "제품", "판매", "부품", "서비스", "사업", "용", "제조업", "도소매", "임대", "개발", "생산", "관련",
         # 거래 방식 단어(2026-11-04 실제 확인: SK하이닉스 등록값 "반도체,컴퓨터,통신기기 제조,도매"의 '도매'로 수산·의류 회사가 걸림)
         "도매", "소매", "무역", "수출입", "오파", "유통", "제작", "운영", "용역", "컨설팅", "수출", "수입", "가공"}


def keywords(products: str) -> set[str]:
    words = {w.strip().lower() for w in re.split(r"[,\s/·()\[\]、;:+&]+", products or "")}
    return {w for w in words if len(w) >= 2 and w not in _STOP}


def overlap(a: set[str], b: set[str]) -> set[str]:
    """같은 단어, 또는 3글자 이상 단어가 다른 쪽 단어 안에 들어 있으면(예: 낸드 ↔ 낸드플래시) 겹친 것으로 본다."""
    out = set()
    for x in a:
        for y in b:
            if x == y or (len(x) >= 3 and x in y) or (len(y) >= 3 and y in x):
                out.add(x)
    return out
