import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

load_dotenv(BACKEND_DIR / ".env")

DART_BASE_URL = "https://opendart.fss.or.kr/api"
_runtime_live_ai_override: bool | None = None


def get_dart_api_key() -> str:
    key = os.environ.get("DART_API_KEY", "").strip()
    if not key:
        raise RuntimeError("backend/.env 에 DART_API_KEY 가 없습니다.")
    return key


def get_naver_credentials() -> tuple[str, str]:
    """NAVER API HUB 뉴스 검색용 (Client ID, Client Secret)."""
    cid = os.environ.get("NAVER_CLIENT_ID", "").strip()
    secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise RuntimeError("backend/.env 에 NAVER_CLIENT_ID, NAVER_CLIENT_SECRET 이 없습니다.")
    return cid, secret


def get_ecos_api_key() -> str:
    key = os.environ.get("ECOS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("backend/.env 에 ECOS_API_KEY 가 없습니다.")
    return key


def get_data_go_kr_key() -> str:
    """공공데이터포털 일반 인증키(Decoding 키). 인코딩된 키를 붙여넣었어도 한 번만 인코딩되도록 호출하는 쪽에서 unquote한다."""
    key = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not key:
        raise RuntimeError("backend/.env 에 DATA_GO_KR_KEY 가 없습니다.")
    return key


def get_llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "").strip().lower() or "openai"


def get_llm_model(kind: str) -> str:
    """kind: 'extract'(추출용 소형) | 'write'(해석용 중간급). 모델 이름은 코드에 고정하지 않고 .env에서 읽는다."""
    name = "OPENAI_MODEL_EXTRACT" if kind == "extract" else "OPENAI_MODEL_WRITE"
    model = os.environ.get(name, "").strip()
    if not model:
        raise RuntimeError(f"backend/.env 에 {name} 이 없습니다.")
    return model


def get_openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("backend/.env 에 OPENAI_API_KEY 가 없습니다.")
    return key


def web_news_enabled() -> bool:
    """웹 검색 작업을 켠다. 기본 켬, WEB_NEWS=0이면 검색 비용을 아끼기 위해 모두 끈다."""
    return os.environ.get("WEB_NEWS", "1").strip() != "0"


def live_ai_allowed() -> bool:
    """실제 AI 호출 허용 상태. 런타임 설정이 없으면 .env 값을 따른다."""
    if _runtime_live_ai_override is not None:
        return _runtime_live_ai_override
    return os.environ.get("LLM_ALLOW_LIVE", "").strip() == "1"


def set_runtime_live_ai(enabled: bool) -> None:
    """현재 서버 실행 중에만 적용되는 실제 AI 호출 허용 설정."""
    global _runtime_live_ai_override
    _runtime_live_ai_override = enabled
