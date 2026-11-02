"""OpenDART 호출. 오류 메시지에 인증키(URL)가 섞이지 않도록 예외를 직접 만들어 던진다."""
import asyncio

import httpx

from .config import DART_BASE_URL, get_dart_api_key


class DartError(Exception):
    def __init__(self, status: str, message: str):
        super().__init__(f"DART 오류 {status}: {message}")
        self.status = status
        self.message = message


async def _get(client: httpx.AsyncClient, path: str, params: dict, retries: int = 3) -> httpx.Response:
    for attempt in range(retries):
        try:
            resp = await client.get(
                f"{DART_BASE_URL}/{path}",
                params={"crtfc_key": get_dart_api_key(), **params},
                timeout=30,
            )
            resp.raise_for_status()
            return resp
        except httpx.HTTPError as e:
            if attempt < retries - 1:
                await asyncio.sleep(0.5 * (attempt + 1))
                continue
            # httpx 예외 문자열에는 키가 담긴 URL이 들어갈 수 있어 종류만 남긴다
            raise DartError("network", f"DART 연결 실패 ({type(e).__name__})") from None


async def fetch_corp_code_zip(client: httpx.AsyncClient) -> bytes:
    resp = await _get(client, "corpCode.xml", {})
    if not resp.content.startswith(b"PK"):  # 오류 시 zip이 아닌 XML/JSON이 온다
        raise DartError("corpCode", "고유번호 파일을 받지 못했습니다 (키 또는 호출 한도 확인)")
    return resp.content


async def fetch_company(client: httpx.AsyncClient, corp_code: str) -> dict:
    data = (await _get(client, "company.json", {"corp_code": corp_code})).json()
    if data.get("status") != "000":
        raise DartError(data.get("status", "?"), data.get("message", ""))
    return data
