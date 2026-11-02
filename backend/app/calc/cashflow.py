"""현금흐름 패턴 — docs/spec.md 3장 '현금흐름 패턴'. 영업·투자·재무의 부호 조합 8가지."""
from .models import NO_DATA, YearFinancials

PATTERNS = {
    ("+", "-", "-"): "우량형",
    ("+", "-", "+"): "성장형",
    ("+", "+", "-"): "구조조정형",
    ("+", "+", "+"): "현금축적형",
    ("-", "-", "+"): "신생·위험형",
    ("-", "+", "+"): "위험형",
    ("-", "+", "-"): "쇠퇴형",
    ("-", "-", "-"): "현금소진형",
}


def classify_cashflow(cur: YearFinancials) -> tuple[str | None, str | None]:
    """(패턴 이름, 판정 못 한 사유). 정확히 0인 항목은 spec 표에 없는 경우라 판정하지 않는다."""
    flows = (cur.cfo, cur.cfi, cur.cff)
    if any(v is None for v in flows):
        return None, NO_DATA
    if any(v == 0 for v in flows):
        return None, "현금흐름이 정확히 0인 항목이 있어 패턴 판정 불가"
    return PATTERNS[tuple("+" if v > 0 else "-" for v in flows)], None
