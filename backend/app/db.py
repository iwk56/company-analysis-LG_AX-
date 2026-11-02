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
    SessionLocal = sessionmaker(engine, expire_on_commit=False)


def ensure_init() -> None:
    if SessionLocal is None:
        init()


def get_session():
    ensure_init()
    with SessionLocal() as session:
        yield session
