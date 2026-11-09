"""AI가 돌려준 값을 코드가 확인한다 (docs/spec.md 0장 규칙 1·2).

- 추출: AI가 인용한 원문이 실제 원문 안에 있는지, 값이 그 인용 안에 있는지 확인하고, 단위 환산은 코드가 한다.
- 해석: 문장 속 숫자가 AI에게 넘긴 자료에 있던 숫자인지 확인한다. 없던 숫자가 나오면 그 문장은 버린다.
"""
import re

UNIT_WON = {"원": 1, "천원": 1_000, "백만원": 1_000_000, "억원": 100_000_000, "조원": 1_000_000_000_000}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _squash(s: str) -> str:
    return re.sub(r"[\s|]+", "", s)


def quote_in_source(quote: str | None, source: str) -> bool:
    """인용이 원문에 그대로(공백·표 칸 구분선 차이만 무시하고) 들어 있는지."""
    return bool(quote) and len(_squash(quote)) >= 4 and _squash(quote) in _squash(source)


def value_in_quote(value_text: str | None, quote: str | None) -> bool:
    return bool(value_text) and bool(quote) and _squash(value_text) in _squash(quote)


def parse_amount(value_text: str | None, unit: str | None) -> int | None:
    """'923,703' + '백만원' → 923703000000 (원). 괄호·△·- 앞붙임은 음수. 읽을 수 없거나 단위를 모르면 None."""
    if not value_text or unit not in UNIT_WON:
        return None
    s = value_text.strip().replace(" ", "")
    negative = (s.startswith("(") and s.endswith(")")) or s.startswith(("△", "-", "▲"))
    s = s.strip("()△▲-").replace(",", "")
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    amount = round(float(s) * UNIT_WON[unit])
    return -amount if negative else amount


def verified_amount(value_text: str | None, unit: str | None, quote: str | None, source: str) -> int | None:
    """인용이 원문에 있고, 값이 인용 안에 있고, 단위가 하나로 읽힐 때만 원 단위 금액을 돌려준다."""
    if not quote_in_source(quote, source) or not value_in_quote(value_text, quote):
        return None
    return parse_amount(value_text, unit)


def unit_in_quote(unit: str | None, quote: str | None) -> bool:
    """AI가 말한 단위가 인용(표 머리의 '(단위 : 백만원)' 등) 안에 있는지. 단위를 잘못 읽으면 금액이 천 배씩 달라진다."""
    if not unit or not quote:
        return False
    return unit in _squash(quote).replace("단위:", "")


def numbers_in(text: str) -> set[str]:
    """문장 속 숫자 토큰(쉼표 제거, 소수점 뒤 불필요한 0 유지). '46.8%' → '46.8'."""
    return {m.group().replace(",", "").rstrip(".") for m in _NUMBER.finditer(text)}


# 기간 표시는 '자료에 없는 숫자'로 보지 않는다 (2026-11-04: "2026년 반기" 같은 문장이 버려지던 문제)
# 연도(1990~2099 뒤에 년·.월·-월), 월(1~12 뒤에 월), 분기(1~4 뒤에 분기)만. 금액·비율은 그대로 확인한다
_PERIOD = re.compile(
    r"(?<![\d.,])(?:"
    r"(?:19[9]\d|20\d\d)\.(?:0[1-9]|1[0-2])(?!\d)"  # 2026.01 (연.월)
    r"|(?:19[9]\d|20\d\d)(?=\s*년|-\d{1,2}(?!\d))"  # 2026년, 2026-06
    r"|(?:1[0-2]|0?[1-9])(?=\s*월|\s*~\s*(?:1[0-2]|0?[1-9])\s*월)"  # 6월, 1~6월의 1
    r"|[1-4](?=\s*분기)"  # 3분기
    r"|(?<=월)(?:3[01]|[12]\d|0?[1-9])(?=\s*일)|(?<=월 )(?:3[01]|[12]\d|0?[1-9])(?=\s*일)"  # 12월 31일의 31
    r")|(?<=\d{4}\.\d{2}~)(?:0[1-9]|1[0-2])(?!\d)"  # 2026.01~06의 06
)


def period_numbers(text: str) -> set[str]:
    return {m.group() for m in _PERIOD.finditer(text)}


def unknown_numbers(text: str, allowed: set[str]) -> set[str]:
    """text에 있는데 allowed에 없는 숫자 (연도·월·분기 같은 기간 표시는 뺀다)."""
    return numbers_in(text) - allowed - period_numbers(text)
