"""경쟁사 자동 선정 (2026-11-04): 업종코드 후보 + 시가총액 + AI 고르기, AI 실패 시 시가총액 순."""
import time

import pytest

from app import company_cache, peers
from app.llm import LlmError

CORPS = [{"corp_code": "T", "corp_name": "타깃반도체", "stock_code": "000001"},
         {"corp_code": "A", "corp_name": "큰반도체", "stock_code": "000002"},
         {"corp_code": "B", "corp_name": "작은반도체", "stock_code": "000003"},
         {"corp_code": "C", "corp_name": "비슷한부품", "stock_code": "000004"},
         {"corp_code": "S", "corp_name": "삼성전자", "stock_code": "005930"},
         {"corp_code": "F", "corp_name": "반도체스팩1호", "stock_code": "000005"},
         {"corp_code": "U", "corp_name": "비상장반도체", "stock_code": "000006"}]
NOW = time.time()
CACHE = {"T": {"induty_code": "2612", "corp_cls": "Y", "fetched_at": NOW}, "A": {"induty_code": "2612", "corp_cls": "Y", "fetched_at": NOW},
         "B": {"induty_code": "2612", "corp_cls": "K", "fetched_at": NOW}, "C": {"induty_code": "2611", "corp_cls": "K", "fetched_at": NOW},
         "S": {"induty_code": "264", "corp_cls": "Y", "fetched_at": NOW}, "F": {"induty_code": "2612", "corp_cls": "K", "fetched_at": NOW},
         "U": {"induty_code": "2612", "corp_cls": "E", "fetched_at": NOW}}
CAPS = {"000002": 50 * 10**12, "000003": 1 * 10**12, "000004": 3 * 10**12, "005930": 900 * 10**12}
TARGET = {"corp_code": "T", "corp_name": "타깃반도체", "stock_code": "000001", "industry_code": "2612", "industry_name": "반도체"}


def test_candidates_same_code_then_widen_and_skip_spac_unlisted():
    got = peers.candidates(TARGET, CORPS, CACHE, CAPS)
    # 같은 코드(2612) 상장 일반기업은 2곳뿐 → 앞 3자리(261)로 넓힘, 시가총액 큰 순, 스팩·비상장·자기 자신 제외
    assert [(c["corp_name"], c["match"]) for c in got] == [("큰반도체", "같은 업종"), ("비슷한부품", "비슷한 업종"), ("작은반도체", "같은 업종")]


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(company_cache, "load_cache", lambda: CACHE)

    async def caps(_client, today=None):
        return CAPS

    monkeypatch.setattr(peers, "market_caps", caps)

    async def no_products(_client):
        return {}

    monkeypatch.setattr(peers.kind_products, "load", no_products)


@pytest.mark.anyio
async def test_suggest_maps_ai_names_to_listed_and_adds_known_rival(env, monkeypatch):
    class R:
        data = {"peers": [{"name": "삼성 전자", "reason": "메모리 직접 경쟁"}, {"name": "없는회사", "reason": "x"},
                          {"name": "큰반도체", "reason": "같은 업종 상위"}, {"name": "타깃반도체", "reason": "자기 자신"}]}

    async def ask(_client, task, kind, user):
        assert task == "pick_peers" and "큰반도체" in user and "50.0조 원" in user
        return R()

    monkeypatch.setattr(peers, "ask", ask)
    got = await peers.suggest(None, TARGET, CORPS)
    assert [(p["corp_name"], p["picked_by"]) for p in got] == [("삼성전자", "ai"), ("큰반도체", "ai")]


@pytest.mark.anyio
async def test_suggest_falls_back_to_market_cap_when_ai_fails(env, monkeypatch):
    async def ask(_client, task, kind, user):
        raise LlmError("AI 실패")

    monkeypatch.setattr(peers, "ask", ask)
    got = await peers.suggest(None, TARGET, CORPS)
    # 주요제품 자료가 없으면 같은 세부 업종 → 시가총액 순
    assert [p["corp_name"] for p in got] == ["큰반도체", "작은반도체", "비슷한부품"] and got[0]["picked_by"] == "industry"
    assert "시가총액 50.0조 원" in got[0]["reason"]


@pytest.mark.anyio
async def test_write_peers_keeps_only_items_with_table_numbers_and_known_keys(monkeypatch):
    from app import ai_peers
    from app.comparison import COLUMN_DEFS
    vals = lambda **kw: {d.key: {"value": kw.get(d.key), "na_reason": None, "rank": None, "vs_average": None} for d in COLUMN_DEFS}  # noqa: E731
    comp = {"base_year": 2025, "columns": [{"key": d.key, "label": d.label, "format": d.format, "higher_is_better": d.higher_is_better,
                                            "ranked": d.ranked, "in_position": d.in_position} for d in COLUMN_DEFS],
            "rows": [{"corp_name": "타깃", "is_target": True, "basis": "연결", "values": vals(operating_margin=0.486)},
                     {"corp_name": "경쟁", "is_target": False, "basis": "연결", "values": vals(operating_margin=0.12)}],
            "averages": {"operating_margin": 0.303}}

    class R:
        model, input_tokens, output_tokens = "m", 1, 1
        data = {"summary": "경쟁사보다 수익성이 높습니다.",
                "strengths": [{"text": "영업이익률 48.6%로 경쟁(12.0%)보다 높습니다.", "basis": ["operating_margin"]},
                              {"text": "영업이익률이 4배입니다.", "basis": ["operating_margin"]},
                              {"text": "좋습니다.", "basis": ["없는키"]}],
                "weaknesses": []}

    async def ask(_client, task, kind, user):
        assert "48.6%" in user and "경쟁 [경쟁사" in user
        return R()

    monkeypatch.setattr(ai_peers, "ask", ask)
    out = await ai_peers.write_peers(None, {"results": {"comparison": comp}})
    assert out.status == "ok" and [x["text"] for x in out.content["strengths"]] == ["영업이익률 48.6%로 경쟁(12.0%)보다 높습니다."]
    assert len(out.warnings) == 2 and out.content["peers"] == ["경쟁"]
    none = await ai_peers.write_peers(None, {"results": {"comparison": {**comp, "rows": comp["rows"][:1]}}})
    assert none.status == "empty" and none.model is None  # 경쟁사가 없으면 AI를 부르지 않는다


# ───────── 2026-11-04 주요제품 기준 (같은 제품 → 같은 고객 → 비슷한 사업 구조)
from app import kind_products  # noqa: E402

PRODUCTS = {"000001": {"products": "DRAM, NAND Flash 등 메모리 반도체"}, "000002": {"products": "LED 패키지, 조명"},
            "000003": {"products": "태양광 모듈"}, "000004": {"products": "메모리 반도체 패키징"},
            "005930": {"products": "휴대폰, 반도체(DRAM·NAND), 가전"}}


def test_kind_parse_finds_columns_by_header_and_pads_codes():
    page = ("<table><tr><th>회사명</th><th>시장구분</th><th>종목코드</th><th>업종</th><th>주요제품</th></tr>"
            "<tr><td>삼성전자</td><td>유가</td><td>5930</td><td>통신 및 방송 장비 제조업</td><td>휴대폰, 반도체 &amp; 가전</td></tr></table>")
    assert kind_products.parse(page) == {"005930": {"name": "삼성전자", "sector": "통신 및 방송 장비 제조업", "products": "휴대폰, 반도체 & 가전"}}


def test_candidates_put_same_product_first_even_from_other_industry_code():
    got = peers.candidates(TARGET, CORPS, CACHE, CAPS, PRODUCTS)
    names = [c["corp_name"] for c in got]
    # 제품 단어가 겹치는 곳(삼성전자는 업종코드 264인데도 들어옴, 비슷한부품=메모리 패키징) 먼저, 그다음 같은 업종 시가총액 순
    assert names[:2] == ["삼성전자", "비슷한부품"] and set(names[2:]) == {"큰반도체", "작은반도체"}
    assert "같은 제품 단어" in got[0]["match"] and got[0]["products"].startswith("휴대폰")


@pytest.mark.anyio
async def test_suggest_sends_products_and_shows_basis(env, monkeypatch):
    async def products(_client):
        return PRODUCTS

    monkeypatch.setattr(kind_products, "load", products)

    class R:
        data = {"peers": [{"name": "삼성전자", "basis": ["product", "customer"], "reason": "메모리 직접 경쟁"}]}

    async def ask(_client, task, kind, user):
        assert "주요제품: DRAM, NAND Flash 등 메모리 반도체" in user and "주요제품: LED 패키지, 조명" in user
        return R()

    monkeypatch.setattr(peers, "ask", ask)
    got = await peers.suggest(None, TARGET, CORPS)
    assert got[0]["reason"] == "같은 제품 · 같은 고객 — 메모리 직접 경쟁"


@pytest.mark.anyio
async def test_fallback_prefers_product_overlap_over_market_cap(env, monkeypatch):
    async def products(_client):
        return PRODUCTS

    async def ask(_client, task, kind, user):
        raise LlmError("AI 실패")

    monkeypatch.setattr(kind_products, "load", products)
    monkeypatch.setattr(peers, "ask", ask)
    got = await peers.suggest(None, TARGET, CORPS)
    assert [p["corp_name"] for p in got][:2] == ["삼성전자", "비슷한부품"]
