import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

load_dotenv(BACKEND_DIR / ".env")

DART_BASE_URL = "https://opendart.fss.or.kr/api"


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
