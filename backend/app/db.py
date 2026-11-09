"""SQLite 연결 (SQLAlchemy 동기). Phase 9에서 Supabase(PostgreSQL)로 바꿀 때 이 파일의 주소만 바꾼다."""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import DATA_DIR

DB_URL = f"sqlite:///{DATA_DIR / 'report.db'}"

engine = None
SessionLocal: sessionmaker | None = None


def init(url: str = DB_URL) -> None:
    """엔진을 만들고 테이블을 만든다(이미 있으면 그대로 둔다)."""
    global engine, SessionLocal
    from .report_models import Base

    if url.startswith("sqlite:///"):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _foreign_keys_on(dbapi_conn, _record):  # SQLite는 기본이 꺼져 있어 리포트를 지울 때 딸린 행도 지우려면 켜야 한다
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    _add_missing_columns()
    SessionLocal = sessionmaker(engine, expire_on_commit=False)


# 이미 있는 DB에 나중에 더한 열 (create_all은 있는 테이블에 열을 더하지 않는다). (테이블, 열, SQL 타입)
_LATER_COLUMNS = (("articles", "topic", "VARCHAR"),
                  ("financial_years", "gross_profit", "BIGINT"),
                  ("financial_years", "sga", "BIGINT"),
                  ("financial_years", "finance_income", "BIGINT"),
                  ("financial_years", "finance_costs", "BIGINT"),
                  ("financial_years", "pretax_income", "BIGINT"),
                  ("financial_years", "income_tax", "BIGINT"),
                  ("financial_years", "capex_ppe", "BIGINT"),
                  ("financial_years", "capex_intangible", "BIGINT"),
                  ("financial_years", "dividends_paid", "BIGINT"),
                  ("financial_years", "buyback", "BIGINT"),
                  ("financial_years", "borrowing_in", "BIGINT"),
                  ("financial_years", "borrowing_out", "BIGINT"),
                  ("financial_years", "tax_paid", "BIGINT"),
                  ("financial_years", "cash_end", "BIGINT"))


def _add_missing_columns() -> None:
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table, col, sql_type in _LATER_COLUMNS:
            if table in insp.get_table_names() and col not in {c["name"] for c in insp.get_columns(table)}:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {sql_type}"))


def ensure_init() -> None:
    if SessionLocal is None:
        init()


def get_session():
    ensure_init()
    with SessionLocal() as session:
        yield session
