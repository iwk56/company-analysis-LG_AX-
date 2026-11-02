import pytest

from app import ksic

pytestmark = pytest.mark.skipif(not ksic.load_table(), reason="KSIC 10차 표 없음")


def test_names_for_3_and_5_digit_codes():
    assert ksic.industry_name("264") == "통신 및 방송장비 제조업"  # DART 3자리
    assert ksic.industry_name("26410") == "유선 통신장비 제조업"  # 5자리
    assert ksic.industry_name("65110") == "생명보험업"
    assert ksic.industry_name("64992") == "지주회사"


def test_table_size_matches_file_header():
    sizes = {n: sum(1 for k in ksic.load_table() if len(k) == n) for n in (2, 3, 4, 5)}
    assert sizes == {2: 77, 3: 232, 4: 495, 5: 1196}


def test_unknown_and_empty():
    assert ksic.industry_name("99999") is None
    assert ksic.industry_name(None) is None
