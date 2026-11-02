import asyncio

from app import company_cache, survey_industry
from app.dart import DartError

CORPS = [{"corp_code": str(i), "corp_name": f"c{i}", "stock_code": "1"} for i in range(6)]


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(company_cache, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(company_cache, "DATA_DIR", tmp_path)


def _run(**kw):
    async def nosleep(_): pass
    return asyncio.run(survey_industry.run_survey(None, CORPS, delay=0, sleep=nosleep, **kw))


def test_skips_already_surveyed_and_retries_failures(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    calls, failed_once = [], []

    async def fetch(_, code):
        calls.append(code)
        if code == "2" and not failed_once:
            failed_once.append(1)
            raise DartError("013", "no data")
        return {"induty_code": "264", "corp_cls": "Y", "fetched_at": 9e12}

    first = _run(limit=None, fetch=fetch)
    assert first["fetched"] == 5 and first["failed"] == 1
    calls.clear()
    second = _run(limit=None, fetch=fetch)
    assert calls == ["2"] and second["already_done"] == 5 and second["fetched"] == 1


def test_stops_after_consecutive_network_failures(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    async def fetch(_, code):
        raise DartError("network", "x")

    r = _run(limit=None, fetch=fetch, max_consecutive_failures=3)
    assert r["failed"] == 3 and r["stopped"] and r["remaining"] == 3


def test_stops_on_rate_limit(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    async def fetch(_, code):
        raise DartError("020", "limit")

    assert "020" in _run(limit=None, fetch=fetch)["stopped"]
