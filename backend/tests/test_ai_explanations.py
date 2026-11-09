from app.ai_facts import balance_change_text, ratio_driver_text, ratio_group_text
from app.balance_notes import balance_note_text, collect_balance_note_items
from app.ai_income import cash_items_text, cash_text


def ratio(value):
    return {"value": value, "na_reason": None}


def test_ratio_explanations_receive_code_calculated_changes_and_drivers():
    report = {
        "financial_years": [
            {"year": 2024, "total_liabilities": 1_000_000_000_000, "total_equity": 500_000_000_000,
             "current_assets": 700_000_000_000, "current_liabilities": 350_000_000_000, "total_assets": 2_000_000_000_000},
            {"year": 2025, "total_liabilities": 1_300_000_000_000, "total_equity": 650_000_000_000,
             "current_assets": 900_000_000_000, "current_liabilities": 450_000_000_000, "total_assets": 3_000_000_000_000},
        ],
        "results": {"ratios": {
            "2024": {"debt_ratio": ratio(2.0), "current_ratio": ratio(2.0)},
            "2025": {"debt_ratio": ratio(2.0), "current_ratio": ratio(2.0)},
        }},
    }

    trend = ratio_group_text(report, ["debt_ratio"])
    drivers = ratio_driver_text(report, ["debt_ratio", "current_ratio", "roa"])

    assert "2025년 200.0% (전년 대비 +0.0%p)" in trend
    assert "부채총계: 2024년 1.0조 원, 2025년 1.3조 원 (전년 대비 +0.3조 원)" in drivers
    assert "자본총계: 2024년 0.5조 원, 2025년 0.7조 원 (전년 대비 +0.1조 원)" in drivers
    assert "유동자산:" in drivers and "유동부채:" in drivers
    assert "평균 자산총계 (ROA·총자산회전율 분모): 2024년 2.0조 원 (전기 자료 없어 기말 값), 2025년 2.5조 원" in drivers


def test_balance_change_text_pairs_major_account_changes_with_related_cashflows():
    report = {"results": {"balance_details": {
        "2024": {
            "accounts": {
                "assets": [{"key": "receivable", "name": "매출채권", "value": 2_000_000_000_000},
                           {"key": "ppe", "name": "유형자산", "value": 5_000_000_000_000}],
                "liabilities": [{"key": "borrowings", "name": "단기차입금", "value": 1_000_000_000_000}],
            },
            "cashflow": [],
        },
        "2025": {
            "accounts": {
                "assets": [{"key": "receivable", "name": "매출채권", "value": 3_000_000_000_000},
                           {"key": "ppe", "name": "유형자산", "value": 8_000_000_000_000}],
                "liabilities": [{"key": "borrowings", "name": "단기차입금", "value": 1_600_000_000_000}],
            },
            "cashflow": [
                {"section": "operating", "name": "매출채권의 증가", "value": -900_000_000_000},
                {"section": "financing", "name": "차입금의 차입", "value": 700_000_000_000},
            ],
        },
    }}}

    text = balance_change_text(report)

    assert "2024→2025년 자산: 매출채권 2.0조 원→3.0조 원 (증감 +1.0조 원)" in text
    assert "관련 항목 매출채권의 증가 -0.9조 원" in text
    assert "2024→2025년 부채: 단기차입금 1.0조 원→1.6조 원 (증감 +0.6조 원)" in text
    assert "관련 항목 차입금의 차입 +0.7조 원" in text


def test_balance_note_text_includes_rollforwards_for_material_account_changes():
    report = {"base_year": 2025, "results": {"balance_details": {
        "2024": {"accounts": {
            "assets": [{"key": "ppe", "name": "유형자산", "value": 500}],
            "liabilities": [{"key": "borrowings", "name": "단기차입금", "value": 100}],
        }},
        "2025": {"accounts": {
            "assets": [{"key": "ppe", "name": "유형자산", "value": 800}],
            "liabilities": [{"key": "borrowings", "name": "단기차입금", "value": 160}],
        }},
    }}}
    xml = """<SECTION-2><TITLE>연결재무제표 주석</TITLE>
    <P>1. 일반사항</P><P>일반 사항 설명</P>
    <P>2. 유형자산</P><P>당기 취득 및 처분 내역</P><P>기초 500 | 취득 400 | 기말 800</P>
    <P>3. 차입금</P><P>차입 및 상환 내역</P><P>기초 100 | 차입 80 | 상환 20 | 기말 160</P>
    <P>4. 기타</P></SECTION-2>"""

    text = balance_note_text(xml, report)

    assert text is not None
    assert "2. 유형자산" in text and "당기 취득 및 처분 내역" in text
    assert "3. 차입금" in text and "차입 및 상환 내역" in text
    assert "일반 사항 설명" not in text


def test_collect_balance_note_items_maps_rollforwards_to_changed_accounts():
    report = {"base_year": 2025, "results": {"balance_details": {
        "2024": {"accounts": {
            "assets": [{"key": "ppe", "name": "유형자산", "value": 500}],
            "liabilities": [{"key": "borrowings", "name": "단기차입금", "value": 100}],
            "equity": [],
        }},
        "2025": {"accounts": {
            "assets": [{"key": "ppe", "name": "유형자산", "value": 800}],
            "liabilities": [{"key": "borrowings", "name": "단기차입금", "value": 160}],
            "equity": [],
        }},
    }}}
    xml = """<SECTION-2><TITLE>연결재무제표 주석</TITLE>
    <P>1. 유형자산</P><P>당기 취득 및 처분 내역</P><P>기초 500 | 취득 400 | 기말 800</P>
    <P>2. 차입금</P><P>기초 100 | 차입 80 | 상환 20 | 기말 160</P>
    <P>3. 기타</P></SECTION-2>"""

    content = collect_balance_note_items(xml, report)
    items = {item["key"]: item for item in content["items"]}

    assert content["year"] == 2025
    assert items["ppe"]["change"] == 300
    assert "당기 취득 및 처분 내역" in items["ppe"]["note_excerpt"]
    assert items["borrowings"]["change"] == 60
    assert "차입 80" in items["borrowings"]["note_excerpt"]


def test_collect_balance_note_items_keeps_changed_accounts_when_notes_unavailable():
    report = {"base_year": 2025, "results": {"balance_details": {
        "2024": {"accounts": {"assets": [{"key": "ppe", "name": "유형자산", "value": 500}]}},
        "2025": {"accounts": {"assets": [{"key": "ppe", "name": "유형자산", "value": 800}]}},
    }}}

    content = collect_balance_note_items(None, report)

    assert content["items"] == [{
        "key": "ppe", "name": "유형자산", "group": "assets",
        "prior": 500, "current": 800, "change": 300,
        "note_title": None, "note_excerpt": None,
    }]


def test_cashflow_explanation_receives_all_years_and_separate_activity_drivers():
    cash = {
        "years": {
            "2023": {"cfo": 10, "net_income": 4, "cfo_to_net_income": 2.5, "capex_to_revenue": 0.1},
            "2024": {"cfo": 12, "net_income": 5, "cfo_to_net_income": 2.4, "capex_to_revenue": 0.2},
            "2025": {"cfo": 15, "net_income": 8, "cfo_to_net_income": 1.9, "capex_to_revenue": 0.3},
        },
        "bridge": None,
    }
    detail = {"items": [
        {"section": "operating", "name": f"영업 항목 {i}", "total": False, "current": 100 + i, "prior": 0}
        for i in range(7)
    ] + [
        {"section": "investing", "name": "유형자산 취득", "total": False, "current": -100, "prior": -40},
        {"section": "financing", "name": "차입금의 차입", "total": False, "current": 80, "prior": 20},
        {"section": "operating", "name": "비교 불가", "total": False, "current": 99, "prior": None},
    ]}

    trend = cash_text({"years": cash["years"]}, 2025)
    items = cash_items_text(detail, top=1)

    assert "2023년" in trend and "2024년" in trend and "2025년" in trend
    assert "영업활동 · 영업 항목 6" in items
    assert "투자활동 · 유형자산 취득" in items
    assert "재무활동 · 차입금의 차입" in items
    assert "비교 불가" not in items


def test_cashflow_prompt_context_defines_other_investing_as_net_cash_flow():
    from app.ai_prompts import EXPLAIN_CASHFLOW

    assert "비용·손실 또는 현금이 사라졌다는 뜻은 아닙니다" in EXPLAIN_CASHFLOW
    assert "설비투자 외 투자활동 순액" in EXPLAIN_CASHFLOW
