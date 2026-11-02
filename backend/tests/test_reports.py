"""리포트 생성·저장·목록·상세·삭제 (DART를 부르지 않는다: 가짜 수집기와 임시 SQLite 파일)."""
import asyncio
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import company_cache, db, jobs, main, reports_api
from app.calc import analyze
from app.fin_collect import collect_company, to_year_list
from app.recent_results import build_recent
from app.report_build import data_as_of
from app.report_models import CalcResult, Company, FinancialYear, RecentResult, Report, Source
from app.report_store import save_report
from tests.test_financials import filing
from tests.test_recent_results import CUR, PRIOR, company as recent_company, interim

CORPS = [
    {"corp_code": "00164779", "corp_name": "SK하이닉스", "stock_code": "000660"},
    {"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930"},
    {"corp_code": "00126256", "corp_name": "삼성생명", "stock_code": "032830"},
    {"corp_code": "00688996", "corp_name": "KB금융", "stock_code": "105560"},
    {"corp_code": "98", "corp_name": "옛날회사", "stock_code": "000002"},
]
OVERVIEW = {"00164779": ("264", "Y"), "00126380": ("264", "Y"), "00126256": ("65110", "Y"),
            "00688996": ("64992", "Y"), "98": ("264", "E")}
THIS_YEAR = date.today().year - 1  # 수집기가 처음 찾는 사업연도


class FakeFetcher:
    """사업보고서 3건(N, N-1, N-2)만 있고 반기·3분기는 없다. 날짜와 상관없이 같은 결과가 나오도록 오늘 기준으로 연도를 만든다."""

    def __init__(self, client=None, delay=0.0, empty=False):
        self.delay, self.empty = delay, empty

    async def fetch(self, corp_code, year, fs_div, reprt_code="11011"):
        await asyncio.sleep(self.delay)
        if self.empty or reprt_code != "11011" or fs_div != "CFS" or year not in (THIS_YEAR, THIS_YEAR - 1, THIS_YEAR - 2):
            return {"status": "013", "message": "no data", "list": []}
        return filing(year, 10000 + (year - THIS_YEAR) * 1000, f"R{year}")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db.init(f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(company_cache, "CACHE_FILE", tmp_path / "cache.json")
    monkeypatch.setattr(company_cache, "DATA_DIR", tmp_path)
    company_cache.save_cache({k: {"induty_code": v[0], "corp_cls": v[1], "fetched_at": time.time()} for k, v in OVERVIEW.items()})

    async def fake_load(_client):
        return CORPS

    monkeypatch.setattr(reports_api, "load_listed_corps", fake_load)
    monkeypatch.setattr(jobs, "new_fetcher", lambda c: FakeFetcher())
    jobs.manager.jobs.clear()
    with TestClient(main.app) as c:  # with 문: 백그라운드 작업이 요청 사이에도 같은 이벤트 루프에서 돈다
        yield c
    db.engine.dispose()


def create(client, corp_code="00164779"):
    r = client.post("/api/reports", json={"corp_code": corp_code})
    assert r.status_code == 202, r.text
    return r.json()


def wait_done(client, job_id, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/api/reports/jobs/{job_id}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("작업이 끝나지 않음")


def counts():
    with db.SessionLocal() as s:
        return {m.__tablename__: s.scalar(select(func.count()).select_from(m))
                for m in (Report, Company, FinancialYear, RecentResult, CalcResult, Source)}


def test_create_list_detail_delete_flow(client):
    started = create(client)
    assert [s["key"] for s in started["steps"]] == ["collect", "recent", "calc", "save"]
    job = wait_done(client, started["job_id"])
    assert job["status"] == "done" and job["error"] is None
    assert [s["status"] for s in job["steps"]] == ["done"] * 4

    listing = client.get("/api/reports").json()
    assert listing["count"] == 1
    item = listing["items"][0]
    assert item["id"] == job["report_id"] and item["corp_name"] == "SK하이닉스"
    assert item["base_year"] == THIS_YEAR and item["competitor_count"] == 0

    detail = client.get(f"/api/reports/{item['id']}").json()
    assert detail["company"]["industry_code"] == "264" and detail["basis"] == "연결" and detail["year_count"] == 5
    assert detail["unit"] == "원" and detail["competitors"] == []
    assert [y["year"] for y in detail["financial_years"]] == list(range(THIS_YEAR - 4, THIS_YEAR + 1))
    latest = detail["financial_years"][-1]
    assert latest["revenue"] == 10000 and isinstance(latest["revenue"], int)
    assert detail["data_as_of"] == f"{THIS_YEAR}-12-31"  # 최근 실적이 없으면 기준 사업연도 말
    assert detail["recent_results"] is None and detail["recent_reason"]
    assert set(detail["results"]) == {"ratios", "dupont", "cashflow", "signals"}
    assert detail["results"]["ratios"][str(THIS_YEAR)]["debt_ratio"]["value"] is not None
    assert detail["sources"][0]["url"].startswith("https://dart.fss.or.kr/dsaf001/main.do?rcpNo=")
    assert len(detail["sources"]) == 5

    assert client.delete(f"/api/reports/{item['id']}").json() == {"deleted": item["id"]}
    assert client.get(f"/api/reports/{item['id']}").status_code == 404
    assert client.get("/api/reports").json()["count"] == 0


def test_delete_removes_child_rows_but_keeps_company(client):
    rid = wait_done(client, create(client)["job_id"])["report_id"]
    before = counts()
    assert before["financial_years"] == 5 and before["calc_results"] == 4 and before["sources"] == 5
    client.delete(f"/api/reports/{rid}")
    after = counts()
    assert after["reports"] == after["financial_years"] == after["calc_results"] == after["sources"] == 0
    assert after["companies"] == 1


def test_same_company_again_makes_new_report_newest_first(client):
    first = wait_done(client, create(client)["job_id"])["report_id"]
    second = wait_done(client, create(client)["job_id"])["report_id"]
    assert first != second
    assert [i["id"] for i in client.get("/api/reports").json()["items"]] == [second, first]
    assert counts()["companies"] == 1


def test_list_filter_by_name(client):
    wait_done(client, create(client, "00164779")["job_id"])
    wait_done(client, create(client, "00126380")["job_id"])
    names = lambda q: [i["corp_name"] for i in client.get("/api/reports", params={"q": q}).json()["items"]]
    assert names("하이닉스") == ["SK하이닉스"] and names("삼성") == ["삼성전자"]
    assert names("없는회사") == [] and names("%") == []  # %가 모든 기업에 맞지 않는다
    assert len(names("")) == 2


def test_rejects_financial_unlisted_and_unknown_companies(client):
    for code, text in (("00126256", "금융업"), ("00688996", "금융업"), ("98", "상장"), ("00000000", "찾을 수 없는")):
        r = client.post("/api/reports", json={"corp_code": code})
        assert r.status_code == 400 and text in r.json()["detail"], code
    assert not jobs.manager.jobs and counts()["reports"] == 0


def test_failed_collect_shows_failed_step_and_saves_nothing(client, monkeypatch):
    monkeypatch.setattr(jobs, "new_fetcher", lambda c: FakeFetcher(empty=True))
    job = wait_done(client, create(client)["job_id"])
    assert job["status"] == "failed" and job["report_id"] is None
    assert job["error"]["step"] == "collect" and job["error"]["step_label"] == "재무 수집" and job["error"]["message"]
    assert [s["status"] for s in job["steps"]] == ["failed", "pending", "pending", "pending"]
    assert counts()["reports"] == 0


def test_failed_save_rolls_back_everything(client, monkeypatch):
    def boom(session, company, res, analysis, recent, reason):
        session.merge(Company(corp_code="00164779", corp_name="x", stock_code="1", industry_code=None, industry_name=None))
        session.flush()
        raise RuntimeError("디스크 오류")

    monkeypatch.setattr(jobs, "save_report", boom)
    job = wait_done(client, create(client)["job_id"])
    assert job["status"] == "failed" and job["error"]["step"] == "save" and "디스크" not in job["error"]["message"]
    assert counts() == {"reports": 0, "companies": 0, "financial_years": 0, "recent_results": 0, "calc_results": 0, "sources": 0}


def test_request_for_company_already_running_returns_same_job(client, monkeypatch):
    monkeypatch.setattr(jobs, "new_fetcher", lambda c: FakeFetcher(delay=0.3))
    a, b = create(client), create(client)
    assert a["job_id"] == b["job_id"]
    wait_done(client, a["job_id"])
    assert counts()["reports"] == 1


def test_unknown_ids_return_404(client):
    assert client.get("/api/reports/jobs/nope").status_code == 404
    assert client.get("/api/reports/999").status_code == 404
    assert client.delete("/api/reports/999").status_code == 404


def test_save_with_recent_results_stores_period_and_data_as_of(client):
    res = asyncio.run(collect_company(FakeFetcher(), "00164779"))
    rec = build_recent(interim(CUR, PRIOR, rcept="RQ"), recent_company(latest=res.latest_year), res.latest_year + 1, "11012", "반기", 6)
    assert data_as_of(res, rec) == date(res.latest_year + 1, 6, 30)
    with db.SessionLocal() as s:
        rid = save_report(s, {"corp_code": "00164779", "corp_name": "SK하이닉스", "stock_code": "000660",
                              "industry_code": "264", "industry_name": None, "is_financial": False},
                          res, analyze(to_year_list(res)), rec, None)
    d = client.get(f"/api/reports/{rid}").json()
    assert d["recent_results"]["period_current"].endswith("01~06") and d["recent_results"]["current"]["revenue"] == 1000
    assert d["data_as_of"] == f"{res.latest_year + 1}-06-30" and d["recent_reason"] is None
    assert "recent_changes" in d["results"] and d["sources"][-1]["kind"] == "interim_report"
    assert d["results"]["recent_changes"]["changes"]["revenue"]["value"] == pytest.approx(1.5)

