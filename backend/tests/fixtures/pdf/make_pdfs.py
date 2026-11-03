"""테스트용 작은 PDF를 만든다 (가상 회사 "테스트전자", 실제 사업보고서 PDF는 저장소에 넣지 않는다).

DART PDF와 같은 모양: 1쪽 목차(점선 줄), 2쪽 표지(글자 사이 띄어쓰기), II장 하위 목차, III-1 요약재무정보, IV·V장, 꼬리말.
다시 만들 때만 실행한다: backend/.venv/bin/pip install -r requirements-dev.txt 후
    backend/.venv/bin/python tests/fixtures/pdf/make_pdfs.py
"""
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

FONT = "HYSMyeongJo-Medium"  # reportlab 내장 한글 CID 글꼴 (글꼴 파일을 넣지 않는다)
OUT = Path(__file__).parent
pdfmetrics.registerFont(UnicodeCIDFont(FONT))

TOC = ["목 차", "사 업 보 고 서 ........................................ 1", "II. 사업의 내용 ................................... 2",
       "1. 사업의 개요 .................................... 2", "III. 재무에 관한 사항 ............................. 5",
       "IV. 이사의 경영진단 및 분석의견 ................... 6"]


def body_pages(revenue: str) -> list[list[str]]:
    """표지 다음 쪽들. (제목 줄, 책갈피 깊이)는 아래 OUTLINE과 맞춘다."""
    return [
        ["II. 사업의 내용", "1. 사업의 개요", "당사는 가상의 전자부품 회사입니다.", "2. 주요 제품 및 서비스",
         "가. 주요 제품 등의 현황", "부품 1,234,567(100%)", "3. 원재료 및 생산설비", "원재료는 웨이퍼입니다."],
        ["설비투자는 공장 증설입니다.", "4. 매출 및 수주상황", "주요 고객 A사 비중 35%입니다.", "5. 위험관리 및 파생거래",
         "환율 위험을 관리합니다."],
        ["6. 주요계약 및 연구개발활동", "연구개발비는 매출의 10%입니다.", "7. 기타 참고사항", "경쟁사 B사와 점유율 1위를 다툽니다."],
        ["III. 재무에 관한 사항", "1. 요약재무정보", "가. 요약연결재무정보", "(단위: 백만원)", "구분 제78기 제77기",
         "I. 유동자산 500 400", f"매출액 {revenue} 1,000,000", "영업이익 100,000 90,000"],
        ["IV. 이사의 경영진단 및 분석의견", "1. 예측정보에 대한 주의사항", "회사는 수요 회복을 예상합니다.",
         "V. 영업이익 표 안의 줄"],  # 표 안의 로마 숫자 줄은 장 제목이 아니다
        ["V. 회계감사인의 감사의견 등", "적정 의견입니다."],
    ]


# (제목, 깊이, 쪽 번호) — 쪽 번호는 1쪽 목차, 2쪽 표지 기준
OUTLINE = [("사 업 보 고 서", 0, 2), ("II. 사업의 내용", 0, 3), ("1. 사업의 개요", 1, 3), ("2. 주요 제품 및 서비스", 1, 3),
           ("3. 원재료 및 생산설비", 1, 3), ("4. 매출 및 수주상황", 1, 4), ("5. 위험관리 및 파생거래", 1, 4),
           ("6. 주요계약 및 연구개발활동", 1, 5), ("7. 기타 참고사항", 1, 5), ("III. 재무에 관한 사항", 0, 6),
           ("1. 요약재무정보", 1, 6), ("IV. 이사의 경영진단 및 분석의견", 0, 7), ("V. 회계감사인의 감사의견 등", 0, 8)]


def write(c: canvas.Canvas, lines: list[str], page_no: int | None) -> None:
    c.setFont(FONT, 11)
    for i, line in enumerate(lines):
        c.drawString(60, 780 - 18 * i, line)
    if page_no is not None:
        c.drawString(60, 40, f"전자공시시스템 dart.fss.or.kr Page {page_no}")


def build(name: str, title: str = "사 업 보 고 서", start: str = "2025년 01월 01일", end: str = "2025년 12월 31일",
          company: str = "테스트전자 주식회사", revenue: str = "1,234,567", outline: bool = True) -> None:
    c = canvas.Canvas(str(OUT / name))
    c.setTitle(name)
    pages = [TOC, [title, "(제 78기)", "사업연도", f"{start} 부터", f"{end} 까지", "금융위원회", "한국거래소 귀중 2026년 3월 17일",
                   f"회      사      명 : {company}", "대   표    이   사 : 홍 길 동"]] + body_pages(revenue)
    for n, lines in enumerate(pages, start=1):
        for i, (_t, _level, page) in enumerate(OUTLINE):  # 책갈피마다 이름이 달라야 한다 (같은 이름이면 제목이 덮어써진다)
            if page == n:
                c.bookmarkPage(f"o{i}")
        write(c, lines, n - 1 if n >= 2 else None)
        c.showPage()
    if outline:
        for i, (title_, level, _page) in enumerate(OUTLINE):
            c.addOutlineEntry(title_, f"o{i}", level=level)
    c.save()


def build_scan(name: str) -> None:
    """글자 없이 도형만 있는 쪽 (스캔본·이미지 PDF 흉내)."""
    c = canvas.Canvas(str(OUT / name))
    for _ in range(3):
        c.rect(60, 200, 400, 500, fill=1)
        c.showPage()
    c.save()


if __name__ == "__main__":
    build("annual_ok.pdf")
    build("annual_no_outline.pdf", outline=False)
    build("interim_half.pdf", title="반 기 보 고 서", start="2026년 01월 01일", end="2026년 06월 30일", revenue="700,000")
    build_scan("scan.pdf")
    for p in sorted(OUT.glob("*.pdf")):
        print(p.name, p.stat().st_size)
