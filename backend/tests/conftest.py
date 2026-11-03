"""테스트 공통: 외부 시세 API를 실수로 부르지 않게 공공데이터포털 키를 비운다 (키가 없으면 fetch_prices가 호출 전에 멈춘다).
7-B 공시 목록(DART list.json)도 테스트가 따로 가짜를 넣지 않으면 부르지 못하게 막는다."""
import pytest

from app import enrich


@pytest.fixture(autouse=True)
def _no_live_stock_calls(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)


@pytest.fixture(autouse=True)
def _no_live_disclosure_calls(monkeypatch):
    async def blocked(*_args, **_kwargs):
        raise RuntimeError("테스트에서는 DART 공시 목록을 부르지 않습니다")

    monkeypatch.setattr(enrich, "fetch_disclosures", blocked)
