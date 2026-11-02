"""기사·환율·금리 수집 (Phase 7-A). 네이버·ECOS를 부르지 않는다: 가짜 응답과 임시 SQLite 파일."""
import time
from datetime import date, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from app import company_cache, db, ecos, jobs, main, news, reports_api
from tests.test_reports import CORPS, OVERVIEW, FakeFetcher

TODAY = date(2026, 11, 2)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def item(title, link, pub, desc="요약", original=None):
    d = {"title": title, "link": link, "description": desc, "pubDate": pub}
    if original is not None:
        d["originallink"] = original
    return d


def mock_client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ───────────────────────── 기사 변환
def test_months_ago_handles_month_end():
    assert news.months_ago(date(2026, 11, 2), 3) == date(2026, 8, 2)
    assert news.months_ago(date(2026, 5, 31), 3) == date(2026, 2, 28)
    assert news.months_ago(date(2026, 1, 15), 3) == date(2025, 10, 15)


def test_clean_text_strips_tags_and_entities():
    assert news.clean_text("<b>SK하이닉스</b>, &quot;HBM&quot; 확대 &amp; 투자") == 'SK하이닉스, "HBM" 확대 & 투자'


def test_parse_items_filters_dedupes_and_sorts():
    items = [
        item("오래된 기사", "http://a/1", "Mon, 01 Jun 2026 09:00:00 +0900"),  # 3개월 밖
        item("<b>SK하이닉스</b> 실적", "http://a/2", "Sun, 01 Nov 2026 09:00:00 +0900", original="http://orig/2"),
        item("SK하이닉스 실적!", "http://a/3", "Sun, 01 Nov 2026 08:00:00 +0900"),  # 제목이 같은 기사(기호만 다름)
        item("다른 기사", "http://a/4", "Sat, 31 Oct 2026 10:00:00 +0900"),
        item("다른 기사 링크 중복", "http://a/4", "Fri, 30 Oct 2026 10:00:00 +0900"),  # 링크 중복
        item("날짜 없음", "http://a/5", ""),
        item("링크 없음", "", "Sat, 31 Oct 2026 10:00:00 +0900"),
        item("가장 최신", "http://a/6", "Mon, 02 Nov 2026 07:00:00 +0900"),
        item("미래 날짜", "http://a/7", "Tue, 03 Nov 2026 07:00:00 +0900"),
    ]
    out = news.parse_items(items, TODAY)
    assert [a["title"] for a in out] == ["가장 최신", "SK하이닉스 실적", "다른 기사"]
    assert out[1]["link"] == "http://orig/2"  # 언론사 원문 링크 우선
    assert out[0]["published_at"] == datetime(2026, 11, 2, 7, 0)


def test_parse_items_limits_to_30():
    items = [item(f"기사 {i}", f"http://a/{i}", f"Mon, 02 Nov 2026 {i % 24:02d}:{i // 24:02d}:00 +0900") for i in range(60)]
    assert len(news.parse_items(items, TODAY)) == 30


# ───────────────────────── 기사 호출
@pytest.fixture
def keys(monkeypatch):
    monkeypatch.setenv("NAVER_CLIENT_ID", "id-secret-1")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "pw-secret-2")
    monkeypatch.setenv("ECOS_API_KEY", "ecos-secret-3")


@pytest.mark.anyio
async def test_fetch_news_sends_company_name_and_headers(keys):
    seen = {}

    def handler(request):
        seen["params"], seen["headers"] = dict(request.url.params), request.headers
        return httpx.Response(200, json={"items": [item("기사", "http://a/1", "Mon, 02 Nov 2026 07:00:00 +0900")]})

    async with mock_client(handler) as c:
        out = await news.fetch_news(c, "SK하이닉스", TODAY)
    assert seen["params"] == {"query": "SK하이닉스", "display": "100", "sort": "date"}
    assert seen["headers"]["X-NCP-APIGW-API-KEY-ID"] == "id-secret-1" and seen["headers"]["X-NCP-APIGW-API-KEY"] == "pw-secret-2"
    assert len(out) == 1


@pytest.mark.anyio
async def test_fetch_news_zero_articles_is_not_an_error(keys):
    async with mock_client(lambda r: httpx.Response(200, json={"items": []})) as c:
        assert await news.fetch_news(c, "SK하이닉스", TODAY) == []


@pytest.mark.parametrize("status,text", [(401, "인증"), (429, "한도"), (500, "HTTP 500")])
@pytest.mark.anyio
async def test_fetch_news_errors_have_messages(keys, status, text):
    async with mock_client(lambda r: httpx.Response(status, json={"errorCode": "X"})) as c:
        with pytest.raises(news.NewsError) as e:
            await news.fetch_news(c, "SK하이닉스", TODAY)
    assert text in str(e.value) and "secret" not in str(e.value)


@pytest.mark.anyio
async def test_fetch_news_missing_key_is_clear(monkeypatch):
    monkeypatch.delenv("NAVER_CLIENT_ID", raising=False)
    async with mock_client(lambda r: httpx.Response(200, json={})) as c:
        with pytest.raises(news.NewsError, match="NAVER_CLIENT_ID"):
            await news.fetch_news(c, "x", TODAY)


@pytest.mark.anyio
async def test_fetch_news_network_error_hides_details(keys):
    def handler(request):
        raise httpx.ConnectError("boom id-secret-1")

    async with mock_client(handler) as c:
        with pytest.raises(news.NewsError) as e:
            await news.fetch_news(c, "x", TODAY)
    assert "ConnectError" in str(e.value) and "secret" not in str(e.value)


# ───────────────────────── ECOS
def ecos_rows(*pairs):
    return {"StatisticSearch": {"list_total_count": len(pairs), "row": [{"TIME": t, "DATA_VALUE": v} for t, v in pairs]}}


def test_parse_rows_sorts_and_skips_bad_values():
    rows = [{"TIME": "20261102", "DATA_VALUE": "1337.2"}, {"TIME": "20261030", "DATA_VALUE": "1,340"},
            {"TIME": "20261031", "DATA_VALUE": "1340.5"}, {"TIME": "bad", "DATA_VALUE": "1"}, {"TIME": "20261029"}]
    assert ecos.parse_rows(rows) == [{"date": "2026-10-31", "value": 1340.5}, {"date": "2026-11-02", "value": 1337.2}]


@pytest.mark.anyio
async def test_fetch_macro_collects_two_series_with_one_year_range(keys):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        return httpx.Response(200, json=ecos_rows(("20261102", "1337.2")))

    async with mock_client(handler) as c:
        out = await ecos.fetch_macro(c, TODAY)
    assert [m["key"] for m in out] == ["usd_krw", "base_rate"]
    assert "/731Y001/D/20251102/20261102/0000001" in urls[0] and "/722Y001/D/20251102/20261102/0101000" in urls[1]
    assert out[0]["points"] == [{"date": "2026-11-02", "value": 1337.2}] and out[1]["unit"] == "%"


@pytest.mark.parametrize("code,text", [("INFO-100", "인증키"), ("ERROR-602", "한도"), ("ERROR-999", "ERROR-999")])
@pytest.mark.anyio
async def test_fetch_series_errors(keys, code, text):
    async with mock_client(lambda r: httpx.Response(200, json={"RESULT": {"CODE": code}})) as c:
        with pytest.raises(ecos.EcosError) as e:
            await ecos.fetch_series(c, "731Y001", "0000001", date(2025, 11, 2), TODAY)
    assert text in str(e.value) and "secret" not in str(e.value)


@pytest.mark.anyio
async def test_fetch_series_no_data_is_empty(keys):
    async with mock_client(lambda r: httpx.Response(200, json={"RESULT": {"CODE": "INFO-200"}})) as c:
        assert await ecos.fetch_series(c, "731Y001", "0000001", date(2025, 11, 2), TODAY) == []


@pytest.mark.anyio
async def test_ecos_network_error_does_not_leak_key(keys):
    def handler(request):
        raise httpx.ConnectError(f"fail {request.url}")  # 예외 문자열에 키가 든 URL이 있는 경우

    async with mock_client(handler) as c:
        with pytest.raises(ecos.EcosError) as e:
            await ecos.fetch_series(c, "731Y001", "0000001", date(2025, 11, 2), TODAY)
    assert "secret" not in str(e.value)


# ───────────────────────── 생성 → 저장 → 조회
@pytest.fixture
def api(tmp_path, monkeypatch):
    db.init(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(company_cache, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(company_cache, "DATA_DIR", tmp_path)
    company_cache.save_cache({k: {"induty_code": v[0], "corp_cls": v[1], "fetched_at": time.time()} for k, v in OVERVIEW.items()})

    async def fake_load(_client):
        return CORPS

    monkeypatch.setattr(reports_api, "load_listed_corps", fake_load)
    monkeypatch.setattr(jobs, "new_fetcher", lambda c: FakeFetcher())
    jobs.manager.jobs.clear()
    with TestClient(main.app) as c:
        yield c
    db.engine.dispose()


def create_and_wait(client):
    started = client.post("/api/reports", json={"corp_code": "00164779", "competitors": ["00126380"]}).json()
    for _ in range(100):
        job = client.get(f"/api/reports/jobs/{started['job_id']}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("작업이 끝나지 않음")


def patch_external(monkeypatch, articles=None, points=None):
    seen = {}

    async def fake_news(_client, query, today=None):
        seen["query"] = query
        return articles or []

    async def fake_macro(_client, today=None):
        return [{"key": k, "label": k, "unit": u, "stat_code": "S", "source_url": "https://ecos.bok.or.kr",
                 "start": "2025-11-02", "end": "2026-11-02", "points": points or []} for k, u in (("usd_krw", "원"), ("base_rate", "%"))]

    monkeypatch.setattr(jobs, "fetch_news", fake_news)
    monkeypatch.setattr(jobs, "fetch_macro", fake_macro)
    return seen


def test_report_saves_articles_and_macro(api, monkeypatch):
    arts = [{"title": "기사 A", "summary": "요약 A", "link": "http://a/1", "published_at": datetime(2026, 11, 1, 9, 0)}]
    seen = patch_external(monkeypatch, arts, [{"date": "2026-11-02", "value": 1337.2}])
    job = create_and_wait(api)
    assert job["status"] == "done" and [s["status"] for s in job["steps"]] == ["done"] * 7
    assert seen["query"] == "SK하이닉스"  # 회사명 하나로 검색
    d = api.get(f"/api/reports/{job['report_id']}").json()
    assert d["articles"]["query"] == "SK하이닉스" and d["articles"]["items"] == [
        {"title": "기사 A", "summary": "요약 A", "link": "http://a/1", "published_at": "2026-11-01T09:00:00"}]
    assert [m["key"] for m in d["macro"]] == ["usd_krw", "base_rate"]
    assert d["macro"][0]["points"] == [{"date": "2026-11-02", "value": 1337.2}]


def test_zero_articles_is_saved_as_empty_not_missing(api, monkeypatch):
    patch_external(monkeypatch)
    d = api.get(f"/api/reports/{create_and_wait(api)['report_id']}").json()
    assert d["articles"] is not None and d["articles"]["items"] == []  # '기사 없음' (수집 전 리포트와 구분)


def test_old_report_without_collection_shows_none(api, monkeypatch):
    patch_external(monkeypatch)
    rid = create_and_wait(api)["report_id"]
    with db.SessionLocal() as s:  # 수집 기능 이전에 만든 리포트처럼 보이게 지운다
        from app.report_models import ArticleSearch, MacroSeries
        s.query(ArticleSearch).delete()
        s.query(MacroSeries).delete()
        s.commit()
    d = api.get(f"/api/reports/{rid}").json()
    assert d["articles"] is None and d["macro"] is None


def test_news_failure_reports_step_and_saves_nothing(api, monkeypatch):
    patch_external(monkeypatch)

    async def boom(_client, query, today=None):
        raise news.NewsError("NAVER API HUB 하루 호출 한도를 넘었습니다")

    monkeypatch.setattr(jobs, "fetch_news", boom)
    job = create_and_wait(api)
    assert job["status"] == "failed" and job["error"]["step"] == "news" and job["error"]["step_label"] == "기사 수집"
    assert "한도" in job["error"]["message"]
    assert api.get("/api/reports").json()["count"] == 0  # 실패한 리포트는 저장하지 않음


def test_macro_failure_reports_step(api, monkeypatch):
    patch_external(monkeypatch)

    async def boom(_client, today=None):
        raise ecos.EcosError("한국은행 ECOS 인증키를 확인해 주세요")

    monkeypatch.setattr(jobs, "fetch_macro", boom)
    job = create_and_wait(api)
    assert job["status"] == "failed" and job["error"]["step"] == "macro" and job["error"]["step_label"] == "지표 수집"


def test_delete_report_removes_articles_and_macro(api, monkeypatch):
    patch_external(monkeypatch, [{"title": "t", "summary": "s", "link": "http://a", "published_at": datetime(2026, 11, 1)}],
                   [{"date": "2026-11-02", "value": 1.0}])
    rid = create_and_wait(api)["report_id"]
    assert api.delete(f"/api/reports/{rid}").status_code == 200
    from app.report_models import Article, ArticleSearch, MacroSeries
    with db.SessionLocal() as s:
        assert [s.query(m).count() for m in (Article, ArticleSearch, MacroSeries)] == [0, 0, 0]
