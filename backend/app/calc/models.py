"""계산 모듈의 입력·출력 형태. 입력은 표준 항목이고, DART 계정 이름 연결은 별도(복구 후)로 만든다.

금액 단위는 호출하는 쪽에서 통일하면 된다(비율 계산에는 영향 없음). 값이 없으면 None.
"""
from dataclasses import dataclass, field

NO_DATA = "자료 없음"
FIRST_YEAR = "해당 없음(전기 자료 없음)"
ZERO_DENOMINATOR = "해당 없음(분모 0)"
NEGATIVE_DENOMINATOR = "해당 없음(분모 음수)"
CAPITAL_IMPAIRED = "해당 없음(자본잠식)"
TURNED_PROFIT = "흑자전환"
TURNED_LOSS = "적자전환"
STILL_LOSS = "적자지속"


@dataclass(frozen=True)
class YearFinancials:
    year: int
    revenue: float | None = None  # 매출액
    operating_income: float | None = None  # 영업이익
    net_income: float | None = None  # 당기순이익
    net_income_parent: float | None = None  # 지배주주 순이익
    total_assets: float | None = None  # 자산총계
    total_liabilities: float | None = None  # 부채총계
    total_equity: float | None = None  # 자본총계
    equity_parent: float | None = None  # 지배주주 자본
    current_assets: float | None = None  # 유동자산
    current_liabilities: float | None = None  # 유동부채
    receivables: float | None = None  # 매출채권
    inventory: float | None = None  # 재고자산
    cost_of_sales: float | None = None  # 매출원가
    interest_expense: float | None = None  # 이자비용
    cfo: float | None = None  # 영업활동 현금흐름
    cfi: float | None = None  # 투자활동 현금흐름
    cff: float | None = None  # 재무활동 현금흐름
    # 2026-11-04 손익계산서 분석용
    gross_profit: float | None = None  # 매출총이익
    sga: float | None = None  # 판매비와관리비
    finance_income: float | None = None  # 금융수익
    finance_costs: float | None = None  # 금융비용
    pretax_income: float | None = None  # 법인세비용차감전순이익
    income_tax: float | None = None  # 법인세비용
    # 2026-11-04 현금흐름 분석용 (DART는 지출도 양수로 주는 경우가 많아 수집 때 절댓값으로 맞춘다)
    capex_ppe: float | None = None  # 유형자산의 취득
    capex_intangible: float | None = None  # 무형자산의 취득
    dividends_paid: float | None = None  # 배당금의 지급
    buyback: float | None = None  # 자기주식의 취득
    borrowing_in: float | None = None  # 차입금의 차입
    borrowing_out: float | None = None  # 차입금의 상환
    tax_paid: float | None = None  # 법인세의 납부
    cash_end: float | None = None  # 기말 현금및현금성자산


@dataclass(frozen=True)
class Metric:
    """비율 한 칸. 비율은 소수(0.153 = 15.3%), 회전율·이자보상배율은 배(회). 표시용 반올림은 화면에서 한다."""

    value: float | None
    na_reason: str | None = None  # value가 None일 때 화면에 보일 사유
    year_end_only: bool = False  # 평균 대신 기말 값만 쓴 경우(첫 연도)


@dataclass(frozen=True)
class Signal:
    level: str  # "양호" | "주의" | "위험"
    reason: str


@dataclass(frozen=True)
class DupontDriver:
    factor: str  # 순이익률 | 총자산회전율 | 재무레버리지
    changes: dict[str, float]  # 요소별 전년 대비 변화율


@dataclass(frozen=True)
class YearAnalysis:
    year: int
    ratios: dict[str, Metric]
    dupont: dict[str, Metric]
    dupont_driver: DupontDriver | None
    dupont_driver_na: str | None
    cashflow_pattern: str | None
    cashflow_na: str | None
    signals: dict[str, Signal | None] = field(default_factory=dict)
