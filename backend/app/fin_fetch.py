"""OpenDART 단일회사 전체 재무제표(fnlttSinglAcntAll) 수집. 응답은 디스크에 저장해 같은 요청을 다시 보내지 않는다.

호출은 실제로 DART에 나가는 건만 세어 0.5초 간격을 둔다(저장본을 읽을 때는 간격 없음).
"""
import asyncio
import json
import time
from datetime import date

import httpx

from .config import DATA_DIR
from .dart import DartError, _get

RAW_DIR = DATA_DIR / "dart_raw"
ANNUAL_REPORT = "11011"  # 사업보고서
CALL_INTERVAL_SECONDS = 0.5


class FinancialsFetcher:
    def __init__(self, client: httpx.AsyncClient, raw_dir=RAW_DIR, interval: float = CALL_INTERVAL_SECONDS,
                 sleep=asyncio.sleep, today: date | None = None):
        self.client, self.raw_dir, self.interval, self._sleep = client, raw_dir, interval, sleep
        self.today = today or date.today()
        self._last_call: float | None = None
        self.calls_made = 0  # 실제로 DART에 보낸 호출 수

    def _path(self, corp_code: str, year: int, fs_div: str):
        return self.raw_dir / f"{corp_code}_{year}_{ANNUAL_REPORT}_{fs_div}.json"

    async def fetch(self, corp_code: str, year: int, fs_div: str) -> dict:
        """{status, message, list} 그대로. 저장본이 있으면 DART를 부르지 않는다."""
        path = self._path(corp_code, year, fs_div)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        if self._last_call is not None:
            wait = self.interval - (time.monotonic() - self._last_call)
            if wait > 0:
                await self._sleep(wait)
        self._last_call = time.monotonic()
        self.calls_made += 1
        resp = await _get(self.client, "fnlttSinglAcntAll.json", {
            "corp_code": corp_code, "bsns_year": str(year), "reprt_code": ANNUAL_REPORT, "fs_div": fs_div})
        try:
            data = resp.json()
        except ValueError:
            raise DartError("json", "재무제표 응답을 읽지 못했습니다") from None
        status = data.get("status")
        if status not in ("000", "013"):  # 013 = 조회된 데이터 없음
            raise DartError(status or "?", data.get("message", ""))
        # 데이터 없음(013)은 아직 제출 전일 수 있는 최근 연도는 저장하지 않는다
        if status == "000" or year <= self.today.year - 2:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return data
