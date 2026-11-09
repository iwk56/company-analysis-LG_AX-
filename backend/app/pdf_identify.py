"""처음 화면에서 올린 사업보고서 PDF로 분석 기업을 찾는다 (2026-11-03 흐름 변경: 기업 검색 → PDF 먼저). 코드만 쓰고 AI는 쓰지 않는다.

1) 앞 40쪽에서 "종목코드는 '000660'" 같은 6자리 종목코드를 찾아 상장기업 목록과 맞춘다 (SK하이닉스 I-1에 있음)
2) 없으면 표지 회사명을 상장기업 목록 이름과 맞춘다. "주식회사"·"(주)"·띄어쓰기를 지우고,
   "에스케이"→"SK"처럼 한글로 적은 영문 그룹명도 바꿔 본다 (표지 "에스케이하이닉스 주식회사", 목록 "SK하이닉스")
찾은 기업이 맞는지는 그 뒤 기존 확인 ③(표지 회사명 = DART 기업개황 정식 회사명)이 다시 본다.
"""
import re

from .pdf_check import strip_company
from .pdf_reader import PdfDoc
from .corp_codes import SPAC_KEYWORDS

CODE_PAGES = 40
STOCK_CODE = re.compile(r"종목코드[^0-9\n]{0,12}(\d{6})")
# 표지에 한글로 적힌 영문 그룹명 → 상장기업 목록에 쓰인 모양
ALIASES = (("에스케이", "SK"), ("엘지", "LG"), ("케이티앤지", "KT&G"), ("케이티", "KT"), ("씨제이", "CJ"),
           ("지에스", "GS"), ("에이치디", "HD"), ("엘에스", "LS"), ("에스케이씨", "SKC"), ("디엘", "DL"), ("비지에프", "BGF"))


def stock_codes(doc: PdfDoc) -> list[str]:
    """앞 40쪽에 적힌 종목코드 (나온 순서, 중복 없이)."""
    found = []
    for page in doc.pages[:CODE_PAGES]:
        found += STOCK_CODE.findall(page)
    return list(dict.fromkeys(found))


def name_variants(cover_company: str) -> list[str]:
    base = strip_company(cover_company).casefold()
    out = [base]
    for kor, eng in ALIASES:
        if base.startswith(kor):
            out.append(eng.casefold() + base[len(kor):])
    return list(dict.fromkeys(out))


def find_company(corps: list[dict], doc: PdfDoc, cover_company: str | None) -> dict | None:
    """상장기업 목록에서 PDF의 기업을 찾는다. 못 찾으면 None."""
    usable = [c for c in corps if not any(k in c["corp_name"] for k in SPAC_KEYWORDS)]
    by_code = {c["stock_code"]: c for c in usable if c.get("stock_code")}
    for code in stock_codes(doc):
        if code in by_code:
            return by_code[code]
    if not cover_company:
        return None
    wanted = name_variants(cover_company)
    for name in wanted:
        hits = [c for c in usable if strip_company(c["corp_name"]).casefold() == name]
        if len(hits) == 1:
            return hits[0]
    return None
