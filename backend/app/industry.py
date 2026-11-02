"""금융업 판별 규칙 — 규칙과 예외 목록은 이 파일에서만 고친다.

규칙 (DART 업종코드는 3~5자리가 섞여 있어 앞 2자리로 판단한다)
1. 업종코드가 KSIC 64~66(금융 및 보험업 계열)이면 금융업
2. 단, 64992(지주회사)는 기본적으로 일반기업 (LG·SK·CJ 같은 비금융 지주사 분석을 위해)
3. 상장 금융지주사는 FINANCIAL_HOLDING_CORP_CODES(고유번호)로 직접 관리해 업종코드와 상관없이 금융업으로 본다
   — 기업명에 "금융"이 들었는지로는 판별하지 않는다
"""

FINANCIAL_PREFIXES = ("64", "65", "66")
HOLDING_COMPANY_CODE = "64992"

# 금융업으로 취급할 상장 금융지주사 (고유번호: 기업명) — 2026-11-02 확정
FINANCIAL_HOLDING_CORP_CODES: dict[str, str] = {
    "00688996": "KB금융",
    "00382199": "신한지주",
    "00547583": "하나금융지주",
    "01350869": "우리금융지주",  # 현재 법인(316140). 00375302(053000)는 옛 법인, 상장폐지
    "00858364": "BNK금융지주",
    "00878915": "iM금융지주",  # 구 DGB금융지주
    "00980122": "JB금융지주",
    "00860332": "메리츠금융지주",
    "00432102": "한국금융지주",
}


def is_financial(corp_code: str, induty_code: str | None) -> bool | None:
    """금융업이면 True, 일반기업이면 False, 업종코드를 모르면 None."""
    if corp_code in FINANCIAL_HOLDING_CORP_CODES:
        return True
    if not induty_code:
        return None
    if induty_code == HOLDING_COMPANY_CODE:
        return False
    return induty_code.startswith(FINANCIAL_PREFIXES)
