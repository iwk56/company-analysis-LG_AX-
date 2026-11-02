import io
import zipfile

import pytest

from app.corp_codes import parse_listed, search_listed

XML = """<?xml version="1.0" encoding="UTF-8"?><result>
<list><corp_code>1</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code></list>
<list><corp_code>2</corp_code><corp_name>삼성전기</corp_name><stock_code>009150</stock_code></list>
<list><corp_code>3</corp_code><corp_name>에스삼성</corp_name><stock_code>111111</stock_code></list>
<list><corp_code>4</corp_code><corp_name>삼성비상장</corp_name><stock_code> </stock_code></list>
</result>"""


def _zip(xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", xml)
    return buf.getvalue()


def test_parse_keeps_only_corps_with_stock_code():
    names = [c["corp_name"] for c in parse_listed(_zip(XML))]
    assert "삼성비상장" not in names and len(names) == 3


def test_search_order_prefix_before_contains_and_limit():
    corps = parse_listed(_zip(XML))
    assert [c["corp_name"] for c in search_listed(corps, "삼성")] == ["삼성전기", "삼성전자", "에스삼성"]
    assert len(search_listed(corps, "삼성", limit=1)) == 1
    assert search_listed(corps, "없는회사") == []


def test_exact_then_prefix_then_contains_and_shorter_names_first():
    corps = [{"corp_code": str(i), "corp_name": n, "stock_code": "1"} for i, n in enumerate(
        ["에스삼성", "삼성바이오로직스", "삼성전자", "삼성", "삼성물산", "한국삼성", "삼성SDI"])]
    names = [c["corp_name"] for c in search_listed(corps, "삼성")]
    assert names == ["삼성", "삼성물산", "삼성전자", "삼성SDI", "삼성바이오로직스", "에스삼성", "한국삼성"]


def test_spac_companies_are_excluded():
    corps = [{"corp_code": str(i), "corp_name": n, "stock_code": "1"} for i, n in enumerate(
        ["삼성전자", "삼성스팩1호", "삼성머스트스팩2호", "엔에이치스팩30호"])]
    assert [c["corp_name"] for c in search_listed(corps, "삼성")] == ["삼성전자"]
    assert search_listed(corps, "스팩") == []


def test_names_with_corporate_acquisition_purpose_are_excluded_too():
    corps = [{"corp_code": str(i), "corp_name": n, "stock_code": "1"} for i, n in enumerate(
        ["하나금융지주", "하나금융14호기업인수목적", "하나금융25호기업인수목적", "하나머티리얼즈"])]
    assert [c["corp_name"] for c in search_listed(corps, "하나")] == ["하나금융지주", "하나머티리얼즈"]
    assert search_listed(corps, "기업인수목적") == []
