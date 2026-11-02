"""키 확인 도구 테스트 — 외부 호출 없이 httpx.MockTransport로 응답을 흉내 낸다."""
import json

import httpx
import pytest

import check_keys
from app.key_specs import startup_warnings

SECRETS = {
    "DART_API_KEY": "dartSECRET111",
    "DATA_GO_KR_KEY": "dgkSECRET%2B222",
    "NAVER_CLIENT_ID": "navidSECRET333",
    "NAVER_CLIENT_SECRET": "navsecSECRET444",
    "ECOS_API_KEY": "ecosSECRET555",
    "OPENAI_API_KEY": "sk-openaiSECRET666",
}


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def no_call(request):
    raise AssertionError(f"외부 호출이 발생함: {request.url.host}")


def run(argv, env, handler=no_call, capsys=None):
    code = check_keys.main(argv, env=env, client=client_for(handler))
    return code, capsys.readouterr().out


def status_of(out, key_id):
    line = next(l for l in out.splitlines() if l.startswith(key_id + " "))
    return line


def test_default_mode_makes_no_external_calls_and_reports_presence(capsys):
    env = dict(SECRETS, NAVER_CLIENT_SECRET="")
    code, out = run([], env, capsys=capsys)
    assert "입력됨" in status_of(out, "dart") and "호출 안 함" in status_of(out, "dart")
    assert "미입력" in status_of(out, "naver") and "NAVER_CLIENT_SECRET" in status_of(out, "naver")
    assert "미입력(선택)" in status_of(out, "anthropic")  # 기본 제공자 openai 라면 선택 항목
    assert code == 1  # 필수 키 미입력


def test_all_present_in_default_mode_exits_zero(capsys):
    code, out = run([], SECRETS, capsys=capsys)
    assert code == 0


def test_secret_values_never_printed(capsys):
    def handler(request):
        return httpx.Response(401, text="bad key " + " ".join(SECRETS.values()))

    code, out = run(["--live"], SECRETS, handler, capsys)
    for value in SECRETS.values():
        assert value not in out
    assert "dgkSECRET" not in out and "dgkSECRET%2B222" not in out


def test_all_live_checks_ok(capsys):
    def handler(request):
        host = request.url.host
        if host == "opendart.fss.or.kr":
            return httpx.Response(200, json={"status": "000", "corp_name": "삼성전자(주)"})
        if host == "apis.data.go.kr":
            return httpx.Response(200, json={"response": {"header": {"resultCode": "00"}, "body": {}}})
        if host == "naverapihub.apigw.ntruss.com":
            assert request.url.path == "/search/v1/news"
            assert request.headers["X-NCP-APIGW-API-KEY-ID"] == SECRETS["NAVER_CLIENT_ID"]
            assert request.headers["X-NCP-APIGW-API-KEY"] == SECRETS["NAVER_CLIENT_SECRET"]
            assert "X-Naver-Client-Id" not in request.headers  # 예전 헤더는 쓰지 않는다
            assert request.url.params["display"] == "1"
            return httpx.Response(200, json={"items": []})
        if host == "ecos.bok.or.kr":
            return httpx.Response(200, json={"StatisticSearch": {"list_total_count": 1, "row": []}})
        if host == "api.openai.com":
            assert request.method == "GET" and request.url.path == "/v1/models"  # 텍스트 생성 금지
            return httpx.Response(200, json={"data": []})
        raise AssertionError(host)

    code, out = run(["--live"], SECRETS, handler, capsys)
    for k in ("dart", "data_go_kr", "naver", "ecos", "openai"):
        assert "정상" in status_of(out, k), out
    assert "미입력(선택)" in status_of(out, "anthropic")
    assert code == 0  # anthropic은 선택 항목이라 미입력이어도 실패가 아니다


@pytest.mark.parametrize("handler_resp, key_id, expected", [
    (lambda r: httpx.Response(200, json={"status": "010"}), "dart", "실패(키 오류)"),
    (lambda r: httpx.Response(200, json={"status": "020"}), "dart", "실패(한도 초과)"),
    (lambda r: httpx.Response(200, json={"status": "800"}), "dart", "실패(기타)"),
    (lambda r: httpx.Response(401, json={"error": {"errorCode": "200", "message": "Authentication Failed"}}), "naver", "실패(키 오류)"),
    (lambda r: httpx.Response(429, json={"error": {"errorCode": "429", "message": "Quota Exceeded"}}), "naver", "실패(한도 초과)"),
    (lambda r: httpx.Response(403, text="Forbidden"), "naver", "실패(기타)"),
    (lambda r: httpx.Response(400, json={"errorCode": "SE02", "errorMessage": "Invalid display value"}), "naver", "실패(기타)"),
    (lambda r: httpx.Response(404, json={"errorCode": "SE05", "errorMessage": "Invalid search api"}), "naver", "실패(기타)"),
    (lambda r: httpx.Response(200, json={"RESULT": {"CODE": "INFO-100"}}), "ecos", "실패(키 오류)"),
    (lambda r: httpx.Response(200, json={"RESULT": {"CODE": "ERROR-602"}}), "ecos", "실패(한도 초과)"),
    (lambda r: httpx.Response(401, json={"error": {}}), "openai", "실패(키 오류)"),
    (lambda r: httpx.Response(429, json={"error": {}}), "openai", "실패(한도 초과)"),
    (lambda r: httpx.Response(200, text="<OpenAPI_ServiceResponse><cmmMsgHeader>"
                              "<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
                              "</cmmMsgHeader></OpenAPI_ServiceResponse>"), "data_go_kr", "실패(키 오류)"),
    (lambda r: httpx.Response(200, json={"response": {"header": {"resultCode": "22"}}}), "data_go_kr", "실패(한도 초과)"),
])
def test_failure_reasons_are_distinguished(handler_resp, key_id, expected, capsys):
    code, out = run(["--live", "--only", key_id], SECRETS, handler_resp, capsys)
    assert expected in status_of(out, key_id), out
    assert code == 1


def test_ecos_no_data_means_key_is_fine(capsys):
    h = lambda r: httpx.Response(200, json={"RESULT": {"CODE": "INFO-200"}})
    _, out = run(["--live", "--only", "ecos"], SECRETS, h, capsys)
    assert "정상" in status_of(out, "ecos")


def test_connection_failure_is_reported_without_url(capsys):
    def handler(request):
        raise httpx.ConnectError("boom " + str(request.url))  # 예외 문자열에 URL(키 포함)이 들어 있어도

    code, out = run(["--live", "--only", "dart,ecos"], SECRETS, handler, capsys)
    assert "실패(연결 끊김)" in status_of(out, "dart") and "실패(연결 끊김)" in status_of(out, "ecos")
    assert "ConnectError" in out and "dartSECRET111" not in out and "ecosSECRET555" not in out


def test_only_option_limits_calls_and_rejects_unknown(capsys):
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(200, json={"status": "000"})

    run(["--live", "--only", "dart"], SECRETS, handler, capsys)
    assert hosts == ["opendart.fss.or.kr"]
    code, out = run(["--only", "nope"], SECRETS, capsys=capsys)
    assert code == 2 and "알 수 없는 키" in out


def test_llm_provider_decides_which_ai_key_is_required(capsys):
    env = dict(SECRETS, OPENAI_API_KEY="", LLM_PROVIDER="anthropic")
    code, out = run([], env, capsys=capsys)
    assert "미입력(선택)" in status_of(out, "openai")
    assert status_of(out, "anthropic").split()[2] == "미입력"  # 선택한 제공자의 키는 필수
    assert "LLM_PROVIDER = anthropic" in out and code == 1


def test_startup_warnings_name_only_missing_required_keys():
    assert startup_warnings(SECRETS) == []  # anthropic은 선택이라 경고 없음
    w = startup_warnings(dict(SECRETS, ECOS_API_KEY="", OPENAI_API_KEY=""))
    assert len(w) == 2 and any("ECOS_API_KEY" in x for x in w) and any("OPENAI_API_KEY" in x for x in w)
    assert startup_warnings({**SECRETS, "LLM_PROVIDER": "gemini"})[0].startswith("LLM_PROVIDER")
    joined = " ".join(startup_warnings(dict(SECRETS, ECOS_API_KEY="")))
    assert all(value not in joined for value in SECRETS.values())  # 이름만 알리고 값은 다루지 않는다


def test_naver_error_code_shown_but_403_is_not_a_key_error(capsys):
    h = lambda r: httpx.Response(400, json={"errorCode": "SE02", "errorMessage": "Invalid display value"})
    _, out = run(["--live", "--only", "naver"], SECRETS, h, capsys)
    assert "HTTP 400, SE02" in status_of(out, "naver")
    h403 = lambda r: httpx.Response(403, json={"errorCode": "weird code with spaces and secret " + SECRETS["NAVER_CLIENT_SECRET"]})
    _, out = run(["--live", "--only", "naver"], SECRETS, h403, capsys)
    assert "실패(기타)" in status_of(out, "naver") and SECRETS["NAVER_CLIENT_SECRET"] not in out
