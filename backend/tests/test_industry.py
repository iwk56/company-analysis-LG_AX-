from app.industry import FINANCIAL_HOLDING_CORP_CODES, is_financial


def test_financial_codes_are_financial():
    assert is_financial("x", "65110") is True  # 생명보험
    assert is_financial("x", "64121") is True
    assert is_financial("x", "66199") is True
    assert is_financial("x", "64") is True  # 2자리 코드도 앞자리로 판단


def test_general_companies():
    assert is_financial("x", "264") is False  # 삼성전자 계열 제조업
    assert is_financial("x", "26410") is False


def test_holding_company_is_general_by_default():
    assert is_financial("lg-corp-code", "64992") is False


def test_listed_financial_holdings_are_financial_regardless_of_code():
    assert len(FINANCIAL_HOLDING_CORP_CODES) == 9
    for code in FINANCIAL_HOLDING_CORP_CODES:
        assert is_financial(code, "64992") is True
        assert is_financial(code, "70100") is True  # 업종코드와 상관없이
        assert is_financial(code, None) is True


def test_current_woori_is_listed_but_old_one_is_not():
    assert is_financial("01350869", "64992") is True
    assert is_financial("00375302", "64992") is False  # 옛 우리금융지주(상장폐지)


def test_unknown_code():
    assert is_financial("x", None) is None
