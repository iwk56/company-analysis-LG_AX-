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
