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
from app.report_models import CalcResult, Comment, Company, FinancialYear, RecentResult, Report, Source
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

    async def fake_news(_client, query, today=None):  # 네이버를 부르지 않는다
        return []

    async def fake_macro(_client, today=None):  # ECOS를 부르지 않는다
        return []

    async def fake_enrich(report_id, lock):  # 공시 원문·AI는 부르지 않는다 (해당 테스트는 test_enrich.py)
        return None

    monkeypatch.setattr(jobs, "fetch_news", fake_news)
    monkeypatch.setattr(jobs, "fetch_macro", fake_macro)
    monkeypatch.setattr(jobs, "enrich_report", fake_enrich)
    jobs.manager.jobs.clear()
    with TestClient(main.app) as c:  # with 문: 백그라운드 작업이 요청 사이에도 같은 이벤트 루프에서 돈다
        yield c
    db.engine.dispose()


def create(client, corp_code="00164779", competitors=("00126380",)):
    r = client.post("/api/reports", json={"corp_code": corp_code, "competitors": list(competitors)})
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
    assert [s["key"] for s in started["steps"]] == ["collect", "recent", "competitors", "news", "macro", "calc", "save", "ai"]
    job = wait_done(client, started["job_id"])
    assert job["status"] == "done" and job["error"] is None
    assert [s["status"] for s in job["steps"]] == ["done"] * 8

    listing = client.get("/api/reports").json()
    assert listing["count"] == 1
    item = listing["items"][0]
    assert item["id"] == job["report_id"] and item["corp_name"] == "SK하이닉스"
    assert item["base_year"] == THIS_YEAR and item["competitor_count"] == 1

    detail = client.get(f"/api/reports/{item['id']}").json()
    assert detail["company"]["industry_code"] == "264" and detail["basis"] == "연결" and detail["year_count"] == 5
    assert detail["unit"] == "원" and [c["corp_name"] for c in detail["competitors"]] == ["삼성전자"]
    assert [y["year"] for y in detail["financial_years"]] == list(range(THIS_YEAR - 4, THIS_YEAR + 1))
    latest = detail["financial_years"][-1]
    assert latest["revenue"] == 10000 and isinstance(latest["revenue"], int)
    assert detail["data_as_of"] == f"{THIS_YEAR}-12-31"  # 최근 실적이 없으면 기준 사업연도 말
    assert detail["recent_results"] is None and detail["recent_reason"]
    assert set(detail["results"]) == {"ratios", "dupont", "cashflow", "signals", "comparison"}
    assert detail["results"]["ratios"][str(THIS_YEAR)]["debt_ratio"]["value"] is not None
    assert detail["sources"][0]["url"].startswith("https://dart.fss.or.kr/dsaf001/main.do?rcpNo=")
    assert len(detail["sources"]) == 5

    assert client.delete(f"/api/reports/{item['id']}").json() == {"deleted": item["id"]}
    assert client.get(f"/api/reports/{item['id']}").status_code == 404
    assert client.get("/api/reports").json()["count"] == 0


def test_delete_removes_child_rows_but_keeps_company(client):
    rid = wait_done(client, create(client)["job_id"])["report_id"]
    before = counts()
    assert before["financial_years"] == 5 and before["calc_results"] == 5 and before["sources"] == 5
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
    wait_done(client, create(client, "00126380", ("00164779",))["job_id"])
    names = lambda q: [i["corp_name"] for i in client.get("/api/reports", params={"q": q}).json()["items"]]
    assert names("하이닉스") == ["SK하이닉스"] and names("삼성") == ["삼성전자"]
    assert names("없는회사") == [] and names("%") == []  # %가 모든 기업에 맞지 않는다
    assert len(names("")) == 2


def test_rejects_financial_unlisted_and_unknown_companies(client):
    for code, text in (("00126256", "금융업"), ("00688996", "금융업"), ("98", "상장"), ("00000000", "찾을 수 없는")):
        r = client.post("/api/reports", json={"corp_code": code, "competitors": ["00126380"]})
        assert r.status_code == 400 and text in r.json()["detail"], code
    assert not jobs.manager.jobs and counts()["reports"] == 0


def test_failed_collect_shows_failed_step_and_saves_nothing(client, monkeypatch):
    monkeypatch.setattr(jobs, "new_fetcher", lambda c: FakeFetcher(empty=True))
    job = wait_done(client, create(client)["job_id"])
    assert job["status"] == "failed" and job["report_id"] is None
    assert job["error"]["step"] == "collect" and job["error"]["step_label"] == "재무 수집" and job["error"]["message"]
    assert [s["status"] for s in job["steps"]] == ["failed"] + ["pending"] * 7
    assert counts()["reports"] == 0


def test_failed_save_rolls_back_everything(client, monkeypatch):
    def boom(session, company, res, analysis, recent, reason, **kw):
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



def test_competitor_selection_rules(client):
    def post(**body):
        return client.post("/api/reports", json={"corp_code": "00164779", **body})

    assert "1곳 이상" in post().json()["detail"] and post().status_code == 400
    assert "1곳 이상" in post(competitors=[]).json()["detail"]
    five = ["00126380", "a1", "a2", "a3", "a4"]
    assert "최대 4곳까지" in post(competitors=five).json()["detail"]
    assert "자신" in post(competitors=["00164779"]).json()["detail"]
    r = post(competitors=["00126256"])  # 금융업 경쟁사
    assert r.status_code == 400 and "금융업" in r.json()["detail"]
    assert not jobs.manager.jobs and counts()["reports"] == 0


def test_duplicate_competitors_are_merged_and_comparison_is_saved(client):
    job = wait_done(client, create(client, competitors=("00126380", "00126380"))["job_id"])
    d = client.get(f"/api/reports/{job['report_id']}").json()
    assert len(d["competitors"]) == 1 and d["competitors"][0]["included"] is True
    comp = d["results"]["comparison"]
    assert [r["corp_name"] for r in comp["rows"]] == ["SK하이닉스", "삼성전자"] and comp["rows"][0]["is_target"]
    assert [c["key"] for c in comp["columns"]] == ["revenue", "revenue_growth", "operating_margin", "roe", "debt_ratio"]
    assert comp["rows"][1]["source_url"].startswith("https://dart.fss.or.kr/")
    assert comp["excluded"] == []


def test_competitor_without_financials_is_excluded_not_fatal(client, monkeypatch):
    class Selective(FakeFetcher):
        async def fetch(self, corp_code, year, fs_div, reprt_code="11011"):
            if corp_code == "00126380":
                return {"status": "013", "message": "no data", "list": []}
            return await super().fetch(corp_code, year, fs_div, reprt_code)

    monkeypatch.setattr(jobs, "new_fetcher", lambda c: Selective())
    job = wait_done(client, create(client)["job_id"])
    assert job["status"] == "done"
    d = client.get(f"/api/reports/{job['report_id']}").json()
    assert d["competitors"][0]["included"] is False and "데이터 부족" in d["competitors"][0]["excluded_reason"]
    assert [r["corp_name"] for r in d["results"]["comparison"]["rows"]] == ["SK하이닉스"]
    assert d["results"]["comparison"]["excluded"][0]["corp_name"] == "삼성전자"


# ───────── Phase 8: 내 코멘트와 다시 시도
def put_comment(client, rid, key, content):
    return client.put(f"/api/reports/{rid}/comments/{key}", json={"content": content})


def test_comment_save_edit_and_delete_by_empty(client):
    rid = wait_done(client, create(client)["job_id"])["report_id"]
    assert client.get(f"/api/reports/{rid}").json()["comments"] == {}

    saved = put_comment(client, rid, "ratios", "  부채비율이 낮아 안정적  ")
    assert saved.status_code == 200 and saved.json()["comment"]["content"] == "부채비율이 낮아 안정적"
    assert saved.json()["comment"]["updated_at"]
    assert client.get(f"/api/reports/{rid}").json()["comments"]["ratios"]["content"] == "부채비율이 낮아 안정적"

    put_comment(client, rid, "ratios", "수정한 내용")  # 같은 섹션은 덮어쓴다 (행이 늘지 않음)
    put_comment(client, rid, "dupont", "듀퐁 메모")
    comments = client.get(f"/api/reports/{rid}").json()["comments"]
    assert set(comments) == {"ratios", "dupont"} and comments["ratios"]["content"] == "수정한 내용"

    deleted = put_comment(client, rid, "ratios", "   ")  # 공백만 있으면 삭제
    assert deleted.status_code == 200 and deleted.json()["comment"] is None
    assert set(client.get(f"/api/reports/{rid}").json()["comments"]) == {"dupont"}
    assert put_comment(client, rid, "ratios", "").status_code == 200  # 없는 코멘트를 비워도 오류 아님


def test_comment_length_limit_and_section_key_rules(client):
    rid = wait_done(client, create(client)["job_id"])["report_id"]
    assert put_comment(client, rid, "ratios", "가" * 1000).status_code == 200
    too_long = put_comment(client, rid, "ratios", "가" * 1001)
    assert too_long.status_code == 400 and "1,000" in too_long.json()["detail"]
    assert client.get(f"/api/reports/{rid}").json()["comments"]["ratios"]["content"] == "가" * 1000  # 거부되면 기존 내용 유지
    assert put_comment(client, rid, "Bad-Key", "x").status_code == 400
    assert put_comment(client, rid, "swot_page3", "나중에 생길 섹션도 키만 맞으면 저장").status_code == 200
    assert put_comment(client, 999, "ratios", "x").status_code == 404


def test_comments_are_per_report_and_deleted_with_report(client):
    first = wait_done(client, create(client)["job_id"])["report_id"]
    second = wait_done(client, create(client)["job_id"])["report_id"]
    put_comment(client, first, "ratios", "첫 리포트 메모")
    assert client.get(f"/api/reports/{second}").json()["comments"] == {}  # 같은 기업의 다른 리포트와 공유하지 않음
    client.delete(f"/api/reports/{first}")
    with db.SessionLocal() as s:
        assert s.scalar(select(func.count()).select_from(Comment)) == 0
    assert client.get(f"/api/reports/{second}").status_code == 200


def test_retry_failed_job_starts_new_job_with_same_input(client, monkeypatch):
    monkeypatch.setattr(jobs, "new_fetcher", lambda c: FakeFetcher(empty=True))
    failed = wait_done(client, create(client)["job_id"])
    assert failed["status"] == "failed" and counts()["reports"] == 0
    monkeypatch.setattr(jobs, "new_fetcher", lambda c: FakeFetcher())  # 원인이 사라졌다고 가정
    retried = client.post(f"/api/reports/jobs/{failed['job_id']}/retry")
    assert retried.status_code == 202 and retried.json()["job_id"] != failed["job_id"]
    done = wait_done(client, retried.json()["job_id"])
    assert done["status"] == "done" and counts()["reports"] == 1
    detail = client.get(f"/api/reports/{done['report_id']}").json()
    assert [c["corp_name"] for c in detail["competitors"]] == ["삼성전자"]  # 경쟁사 선택이 그대로 유지됨


def test_retry_rejects_unknown_and_non_failed_jobs(client):
    assert client.post("/api/reports/jobs/nope/retry").status_code == 404
    done = wait_done(client, create(client)["job_id"])
    assert client.post(f"/api/reports/jobs/{done['job_id']}/retry").status_code == 400
