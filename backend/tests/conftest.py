"""테스트 공통: 외부 시세 API를 실수로 부르지 않게 공공데이터포털 키를 비운다 (키가 없으면 fetch_prices가 호출 전에 멈춘다)."""
import pytest


@pytest.fixture(autouse=True)
def _no_live_stock_calls(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)
