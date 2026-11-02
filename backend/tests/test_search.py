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
