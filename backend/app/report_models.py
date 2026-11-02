"""리포트 저장 테이블 (docs/spec.md 4장). AI 작성 내용·시세·기사 등은 해당 Phase에서 추가한다.

금액은 DART 원문 그대로 원 단위 정수로 저장하고, 억 원 변환은 보여줄 때 한다.
"""
from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    corp_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    corp_name: Mapped[str] = mapped_column(String)
    stock_code: Mapped[str] = mapped_column(String)
    industry_code: Mapped[str | None] = mapped_column(String)
    industry_name: Mapped[str | None] = mapped_column(String)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    corp_code: Mapped[str] = mapped_column(ForeignKey("companies.corp_code"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    base_year: Mapped[int] = mapped_column(Integer)  # 기준 사업연도(5년 추이의 마지막 해)
    data_as_of: Mapped[date] = mapped_column(Date)  # 데이터 기준일: 최근 실적 기간 끝, 없으면 기준 사업연도 말
    basis: Mapped[str] = mapped_column(String)  # 연결 | 별도
    year_count: Mapped[int] = mapped_column(Integer)
    interest_basis: Mapped[str | None] = mapped_column(String)  # 이자보상배율 분모: 이자비용 | 금융비용
    competitors: Mapped[list] = mapped_column(JSON, default=list)  # 경쟁사는 Phase 5부터
    notes: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    recent_reason: Mapped[str | None] = mapped_column(String)  # 최근 실적 박스가 없을 때 사유

    company: Mapped[Company] = relationship()
    financial_years: Mapped[list["FinancialYear"]] = relationship(
        cascade="all, delete-orphan", order_by="FinancialYear.year")
    recent: Mapped["RecentResult | None"] = relationship(cascade="all, delete-orphan", uselist=False)
    results: Mapped[list["CalcResult"]] = relationship(cascade="all, delete-orphan")
    sources: Mapped[list["Source"]] = relationship(cascade="all, delete-orphan", order_by="Source.id")
    comments: Mapped[list["Comment"]] = relationship(cascade="all, delete-orphan")
    article_search: Mapped["ArticleSearch | None"] = relationship(cascade="all, delete-orphan", uselist=False)
    macro_series: Mapped[list["MacroSeries"]] = relationship(cascade="all, delete-orphan", order_by="MacroSeries.id")
    enrichments: Mapped[list["Enrichment"]] = relationship(cascade="all, delete-orphan", order_by="Enrichment.id")


def _report_fk() -> Mapped[int]:
    return mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)


def _amount() -> Mapped[int | None]:
    return mapped_column(BigInteger, nullable=True)


class FinancialYear(Base):
    """원자료: 연도별 표준 항목 17개(없으면 NULL)."""
    __tablename__ = "financial_years"
    __table_args__ = (UniqueConstraint("report_id", "year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = _report_fk()
    year: Mapped[int] = mapped_column(Integer)
    rcept_no: Mapped[str | None] = mapped_column(String)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list)  # 매칭하지 못한 표준 항목
    revenue = _amount()
    operating_income = _amount()
    net_income = _amount()
    net_income_parent = _amount()
    total_assets = _amount()
    total_liabilities = _amount()
    total_equity = _amount()
    equity_parent = _amount()
    current_assets = _amount()
    current_liabilities = _amount()
    receivables = _amount()
    inventory = _amount()
    cost_of_sales = _amount()
    interest_expense = _amount()
    cfo = _amount()
    cfi = _amount()
    cff = _amount()


class RecentResult(Base):
    """원자료: 최근 반기/3분기 누적 손익(당기·전년 동기)."""
    __tablename__ = "recent_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), unique=True)
    report_name: Mapped[str] = mapped_column(String)  # 반기 | 3분기
    year: Mapped[int] = mapped_column(Integer)
    reprt_code: Mapped[str] = mapped_column(String)
    rcept_no: Mapped[str] = mapped_column(String)
    basis: Mapped[str] = mapped_column(String)
    period_current: Mapped[str] = mapped_column(String)
    period_prior: Mapped[str] = mapped_column(String)
    current: Mapped[dict] = mapped_column(JSON)  # 항목 → 원
    prior: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[list] = mapped_column(JSON, default=list)


class CalcResult(Base):
    """계산 결과: 섹션별 JSON (ratios, dupont, cashflow, signals, recent_changes)."""
    __tablename__ = "calc_results"
    __table_args__ = (UniqueConstraint("report_id", "section"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = _report_fk()
    section: Mapped[str] = mapped_column(String)
    content: Mapped[dict] = mapped_column(JSON)


class Source(Base):
    """출처: 수치별 DART 공시 원문 링크."""
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = _report_fk()
    kind: Mapped[str] = mapped_column(String)  # annual_report | interim_report
    year: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String)
    rcept_no: Mapped[str] = mapped_column(String)
    url: Mapped[str] = mapped_column(String)


class Comment(Base):
    """내 코멘트: 리포트별·섹션별 1개. 섹션 키는 문자열로만 저장해 섹션이 늘어도 테이블을 바꾸지 않는다."""
    __tablename__ = "comments"
    __table_args__ = (UniqueConstraint("report_id", "section_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = _report_fk()
    section_key: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ArticleSearch(Base):
    """원자료: 기사 검색 기록. 행이 없는 리포트는 기사 수집 기능이 생기기 전에 만든 리포트이고, 행은 있는데 기사가 0건이면 '최근 3개월 기사 없음'이다."""
    __tablename__ = "article_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), unique=True)
    query: Mapped[str] = mapped_column(String)
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)

    articles: Mapped[list["Article"]] = relationship(cascade="all, delete-orphan", order_by="Article.id")


class Article(Base):
    """원자료: 기사 제목·요약문·링크·날짜 (최신순으로 넣는다)."""
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("article_searches.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(String)
    link: Mapped[str] = mapped_column(String)
    published_at: Mapped[datetime] = mapped_column(DateTime)


class MacroSeries(Base):
    """원자료: 환율·기준금리 시계열(ECOS). 행이 없는 리포트는 수집 기능이 생기기 전에 만든 리포트."""
    __tablename__ = "macro_series"
    __table_args__ = (UniqueConstraint("report_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = _report_fk()
    key: Mapped[str] = mapped_column(String)  # usd_krw | base_rate
    label: Mapped[str] = mapped_column(String)
    unit: Mapped[str] = mapped_column(String)
    stat_code: Mapped[str] = mapped_column(String)
    source_url: Mapped[str] = mapped_column(String)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    points: Mapped[list] = mapped_column(JSON)  # [{"date": "2026-11-02", "value": 1337.2}]


class Enrichment(Base):
    """공시 확인·AI 작업 결과: 작업 키(employees, extract_*, write_*)마다 1행. 한 번 만든 해석은 다시 만들지 않고 저장본을 쓴다.

    status: ok | empty(원문에 자료 없음·검증 못 함) | failed(다시 시도 가능). by: code | ai.
    """
    __tablename__ = "enrichments"
    __table_args__ = (UniqueConstraint("report_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = _report_fk()
    key: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    by: Mapped[str] = mapped_column(String)
    model: Mapped[str | None] = mapped_column(String)
    content: Mapped[dict | None] = mapped_column(JSON)
    message: Mapped[str | None] = mapped_column(String)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime)
