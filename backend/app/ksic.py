"""한국표준산업분류(KSIC) 10차 표에서 업종코드 → 업종명을 찾는다.

표는 xlsx를 압축 푼 폴더(backend/data/ksic/ksic_10_*)에서 XML을 직접 읽는다.
DART 업종코드는 2~5자리가 섞여 있어 표의 중분류(2)~세세분류(5) 코드를 모두 담는다.
표가 없으면 빈 표로 동작하고 호출하는 쪽에서 업종코드만 보여준다.
"""
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR

KSIC_DIR = DATA_DIR / "ksic"
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
# 시트의 (코드 열, 항목명 열): 중분류, 소분류, 세분류, 세세분류
_LEVEL_COLUMNS = (("C", "D"), ("E", "F"), ("G", "H"), ("I", "J"))


def parse_table(folder: Path) -> dict[str, str]:
    shared = [
        "".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
        for si in ET.parse(folder / "xl/sharedStrings.xml").getroot().findall("m:si", _NS)
    ]
    table: dict[str, str] = {}
    for row in ET.parse(folder / "xl/worksheets/sheet1.xml").getroot().findall(".//m:row", _NS):
        cells = {}
        for c in row.findall("m:c", _NS):
            v = c.find("m:v", _NS)
            if v is not None:
                col = re.match(r"[A-Z]+", c.get("r")).group()
                cells[col] = shared[int(v.text)] if c.get("t") == "s" else v.text
        for code_col, name_col in _LEVEL_COLUMNS:
            code, name = cells.get(code_col), cells.get(name_col)
            if code and name and re.fullmatch(r"\d{2,5}", code.strip()):
                table[code.strip()] = name.strip()
    return table


@lru_cache(maxsize=1)
def load_table() -> dict[str, str]:
    folders = sorted(KSIC_DIR.glob("ksic_10_*")) if KSIC_DIR.exists() else []
    return parse_table(folders[0]) if folders else {}


def industry_name(code: str | None) -> str | None:
    return load_table().get(code) if code else None
