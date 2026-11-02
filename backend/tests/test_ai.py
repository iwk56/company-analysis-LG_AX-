"""AI 모듈 단위 테스트: 값 검증, 원문 절 추출, AI 호출 모듈(가짜·OpenAI 차단·오류 분류). 외부 호출 없음."""
import asyncio
import json

import httpx
import pytest

from app import llm
from app.ai_verify import numbers_in, parse_amount, quote_in_source, unknown_numbers, verified_amount
from app.dart_docs import find_section, note_text, section_text, to_text
from app.llm import LlmError, call_json, parse_json_object


def test_parse_amount_converts_units_and_negatives():
    assert parse_amount("923,703", "백만원") == 923_703_000_000
    assert parse_amount("(247,087)", "백만원") == -247_087_000_000
    assert parse_amount("1.5", "조원") == 1_500_000_000_000
    assert parse_amount("12", "만원") is None  # 모르는 단위
    assert parse_amount("약 12", "원") is None
    assert parse_amount(None, "원") is None


def test_verified_amount_requires_quote_in_source_and_value_in_quote():
    source = "당기 | (단위 : 백만원)\n이자비용 | 923,703\n외환차이 | 3,186,451"
    assert verified_amount("923,703", "백만원", "이자비용 | 923,703", source) == 923_703_000_000
    assert verified_amount("923,703", "백만원", "이자비용 923,703", source) == 923_703_000_000  # 표 칸 구분선·공백 차이는 무시
    assert verified_amount("923,703", "백만원", "이자비용 | 999,999", source) is None  # 인용이 원문에 없음
    assert verified_amount("111,111", "백만원", "이자비용 | 923,703", source) is None  # 값이 인용 안에 없음
    assert verified_amount("923,703", "백만원", None, source) is None
    assert not quote_in_source("ab", "xxabxx")  # 너무 짧은 인용은 증거가 못 된다


def test_unknown_numbers_flags_only_numbers_missing_from_facts():
    allowed = numbers_in("영업이익률 48.6%, 전년 35.5%, 매출 97.1조 원, 2025년 1,234명")
    assert allowed == {"48.6", "35.5", "97.1", "2025", "1234"}
    assert unknown_numbers("영업이익률은 48.6%로 2025년에 올랐습니다", allowed) == set()
    assert unknown_numbers("영업이익률이 13.1%p 올랐습니다", allowed) == {"13.1"}


def row(*cells):
    return "<TR>" + "".join(f"<TD>{c}</TD>" for c in cells) + "</TR>"


def test_to_text_keeps_table_rows_on_one_line():
    xml = "<P>제목</P><TABLE>\n<TR>\n<TD>DRAM</TD>\n<TD>1,000</TD>\n</TR></TABLE>"
    assert to_text(xml) == "제목\nDRAM | 1,000"


def test_section_and_note_extraction():
    xml = ("<SECTION-1><TITLE>III. 재무</TITLE><SECTION-2><TITLE>3. 연결재무제표 주석</TITLE>"
           "<P>26. 비용 (연결)</P><P>가</P><P>27. 금융수익 및 금융비용 (연결)</P>" + row("이자비용", "10") + "<P>28. 기타 (연결)</P><P>나</P>"
           "</SECTION-2><SECTION-2><TITLE>4. 재무제표</TITLE><P>다</P></SECTION-2></SECTION-1>")
    notes = section_text(xml, "3. 연결재무제표 주석")
    assert "다" not in notes and "27. 금융수익" in notes
    assert find_section(xml, "연결재무제표주석") == notes
    assert note_text(notes, "금융수익 및 금융비용") == "27. 금융수익 및 금융비용 (연결)\n이자비용 | 10"
    assert note_text(notes, "없는 주석") is None
    assert section_text(xml, "9. 없음") is None


def test_parse_json_object_accepts_fenced_and_rejects_garbage():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(LlmError) as e:
        parse_json_object("그냥 문장")
    assert e.value.retryable


def run(coro):
    return asyncio.run(coro)


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_fake_provider_returns_fixture_without_network(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "fake")

    async def go():
        async with client_for(lambda r: (_ for _ in ()).throw(AssertionError("호출하면 안 됨"))) as c:
            return await call_json(c, "extract_rnd", "extract", "s", "u")

    r = run(go())
    assert r.model == "fake" and r.input_tokens == 0 and r.data["amount"] == "6,732,527"


def test_openai_is_blocked_unless_live_allowed(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRET")
    monkeypatch.delenv("LLM_ALLOW_LIVE", raising=False)

    async def go():
        async with client_for(lambda r: (_ for _ in ()).throw(AssertionError("호출하면 안 됨")) ) as c:
            await call_json(c, "t", "extract", "s", "u")

    with pytest.raises(LlmError) as e:
        run(go())
    assert "LLM_ALLOW_LIVE" in e.value.message and "sk-SECRET" not in e.value.message


def live_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_ALLOW_LIVE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-SECRET")
    monkeypatch.setenv("OPENAI_MODEL_EXTRACT", "small-model")
    monkeypatch.setenv("OPENAI_MODEL_WRITE", "mid-model")


def test_openai_success_sends_model_and_reports_usage(monkeypatch):
    live_env(monkeypatch)
    seen = {}

    def handler(request):
        seen["auth"], seen["body"] = request.headers["authorization"], json.loads(request.content)
        return httpx.Response(200, json={"model": "small-model-2026", "usage": {"prompt_tokens": 120, "completion_tokens": 30},
                                         "choices": [{"message": {"content": '{"ok": true}'}}]})

    async def go():
        async with client_for(handler) as c:
            return await call_json(c, "t", "extract", "규칙", "자료")

    r = run(go())
    assert r.data == {"ok": True} and (r.input_tokens, r.output_tokens) == (120, 30) and r.model == "small-model-2026"
    assert seen["body"]["model"] == "small-model" and seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][0]["content"] == "규칙"


@pytest.mark.parametrize("status,text", [(401, "키 오류"), (403, "키 오류"), (429, "한도"), (500, "서비스 오류")])
def test_openai_error_messages_never_contain_the_key(monkeypatch, status, text):
    live_env(monkeypatch)

    async def go():
        async with client_for(lambda r: httpx.Response(status, json={"error": {"type": "x", "message": "sk-SECRET 자료"}})) as c:
            await call_json(c, "t", "write", "s", "u")

    with pytest.raises(LlmError) as e:
        run(go())
    assert text in e.value.message and "sk-SECRET" not in e.value.message and "자료" not in e.value.message


def test_openai_bad_json_is_retryable_and_keeps_token_count(monkeypatch):
    live_env(monkeypatch)

    async def go():
        async with client_for(lambda r: httpx.Response(200, json={"usage": {"prompt_tokens": 7, "completion_tokens": 3},
                                                                  "choices": [{"message": {"content": "JSON 아님"}}]})) as c:
            await call_json(c, "t", "write", "s", "u")

    with pytest.raises(LlmError) as e:
        run(go())
    assert e.value.retryable and (e.value.input_tokens, e.value.output_tokens) == (7, 3)


def test_missing_model_name_is_reported_without_calling(monkeypatch):
    live_env(monkeypatch)
    monkeypatch.delenv("OPENAI_MODEL_WRITE")

    async def go():
        async with client_for(lambda r: (_ for _ in ()).throw(AssertionError("호출하면 안 됨")) ) as c:
            await call_json(c, "t", "write", "s", "u")

    with pytest.raises(LlmError) as e:
        run(go())
    assert "OPENAI_MODEL_WRITE" in e.value.message
