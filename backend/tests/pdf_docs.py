"""AI 흐름 테스트용 PDF 글: 가짜 응답(app/ai_fixtures/extract_*.json)의 인용 문장을 실제 사업보고서와 같은 목차 구조에 담는다.
가짜 응답의 인용이 이 글에서 검증을 통과하므로, 고정 응답 파일과 테스트가 항상 맞는다."""
import json

from app import llm
from app.pdf_reader import PdfDoc


def _fx(task: str) -> dict:
    return json.loads((llm.FIXTURE_DIR / f"{task}.json").read_text(encoding="utf-8"))


def sk_like_doc() -> PdfDoc:
    pos, mda, focus = _fx("extract_position"), _fx("extract_mda"), _fx("extract_focus")
    biz = _fx("extract_business")  # 사업 구조 (2026-11-04)
    bq = lambda k: "\n".join(biz[k]["quotes"])  # noqa: E731
    risks = [r["quote"] for r in pos["risks"]]
    cover = ("사 업 보 고 서\n(제 78기)\n2025년 01월 01일 부터\n사업연도\n2025년 12월 31일 까지\n"
             "회 사 명 : 에스케이하이닉스 주식회사\n대 표 이 사 : 곽 노 정")
    pages = [
        "목 차\nII. 사업의 내용 ........ 1",
        cover,
        "II. 사업의 내용\n1. 사업의 개요\n당사는 메모리 반도체를 만드는 글로벌 반도체 기업입니다.\n"
        "2. 주요 제품 및 서비스\n가. 주요 제품 등의 현황\n반도체 부문 DRAM, NAND Flash 등\n" + bq("products") + "\n"
        "3. 원재료 및 생산설비\n가. 투자계획\n" + focus["investment"]["quotes"][0] + "\n나. 원재료\n" + bq("materials")
        + "\n다. 생산능력 및 가동률\n" + bq("production"),
        "4. 매출 및 수주상황\n가. 매출에 관한 사항\n당사는 주요 고객사들과 공급 물량 및 가격을 결정하고 있습니다.\n"
        + bq("sales_mix") + "\n나. 수주상황\n" + bq("orders") + "\n다. 부문 정보\n" + bq("segments") + "\n"
        "5. 위험관리 및 파생거래\n가. 시장위험\n" + "\n".join(risks[:2]),
        "6. 주요계약 및 연구개발활동\n가. 연구개발활동\n" + "\n".join(focus["rnd"]["quotes"]) + "\n"
        "7. 기타 참고사항\n가. 업계의 현황\n" + pos["position"]["quotes"][2] + "\n나. 회사의 현황\n(2) 시장점유율\n"
        "구분 2025년 3분기 2025년 2분기 2025년 1분기 2024년 2023년\n" + "\n".join(pos["position"]["quotes"][:2]) + "\n"
        + focus["new_business"]["quotes"][0],
        "III. 재무에 관한 사항\n1. 요약재무정보",
        "IV. 이사의 경영진단 및 분석의견\n1. 예측정보에 대한 주의사항\n본 자료는 미래에 대한 예측정보를 포함하고 있습니다.\n2. 개요\n"
        + "\n".join(mda["quotes"][:2]) + "\n6. 그 밖에 투자의사결정에 필요한 사항\n" + mda["quotes"][2],
        "V. 회계감사인의 감사의견 등\n적정",
    ]
    return PdfDoc(pages, [])


def sk_like_interim_doc() -> PdfDoc:
    focus = _fx("extract_focus")
    cover = ("반 기 보 고 서\n(제 79 기)\n2026년 01월 01일 부터\n사업연도\n2026년 06월 30일 까지\n"
             "회 사 명 : 에스케이하이닉스 주식회사")
    pages = [
        "목 차",
        cover,
        "II. 사업의 내용\n1. 사업의 개요\n개요\n6. 주요계약 및 연구개발활동\n다. 연구개발 실적\n"
        + focus["changes"]["rnd"]["quotes"][0] + "\n7. 기타 참고사항\n가. 업계의 현황\n수요가 늘고 있습니다.",
        "III. 재무에 관한 사항",
    ]
    return PdfDoc(pages, [])
