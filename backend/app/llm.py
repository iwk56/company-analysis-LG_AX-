"""AI 호출은 이 모듈 한 곳에서만 한다 (docs/spec.md 0장 규칙 8).

제공자는 `.env`의 LLM_PROVIDER로 고른다: openai(기본) | fake(개발용, 외부 호출 없이 고정 예시 JSON) | anthropic(아직 연결 안 함).
실제 호출은 홈 화면에서 켤 수 있다. 오류 메시지에는 키·요청 내용을 넣지 않는다.
"""
import json
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import get_llm_model, get_llm_provider, get_openai_api_key, live_ai_allowed

FIXTURE_DIR = Path(__file__).resolve().parent / "ai_fixtures"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
TIMEOUT = 120
MAX_OUTPUT_TOKENS = {"extract": 3000, "write": 8000}  # 추론 토큰이 섞일 수 있어 여유를 둔다


class LlmError(Exception):
    """AI 호출 실패. retryable이면 같은 요청을 한 번 더 보낼 만하다(형식 오류 등)."""

    def __init__(self, message: str, retryable: bool = False, input_tokens: int = 0, output_tokens: int = 0):
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.input_tokens, self.output_tokens = input_tokens, output_tokens  # 형식 오류여도 이미 쓴 토큰


@dataclass(frozen=True)
class LlmResult:
    data: dict
    model: str
    input_tokens: int
    output_tokens: int


def parse_json_object(text: str) -> dict:
    """응답 문자열에서 JSON 객체를 읽는다. ```json 울타리가 붙어 있어도 읽는다."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else ""
        s = s.rsplit("```", 1)[0]
    try:
        data = json.loads(s)
    except ValueError:
        raise LlmError("AI 응답이 JSON 형식이 아닙니다", retryable=True) from None
    if not isinstance(data, dict):
        raise LlmError("AI 응답이 JSON 객체가 아닙니다", retryable=True)
    return data


async def call_json(client: httpx.AsyncClient, task: str, kind: str, system: str, user: str) -> LlmResult:
    """task: 작업 이름(가짜 응답 파일 이름), kind: 'extract' | 'write'."""
    provider = get_llm_provider()
    if provider == "fake":
        return _fake(task)
    if provider == "openai":
        if not live_ai_allowed():
            raise LlmError("실제 AI 호출이 꺼져 있습니다 (홈 화면에서 실제 AI를 켜면 호출)")
        return await _openai(client, kind, system, user)
    if provider == "anthropic":
        raise LlmError("LLM_PROVIDER=anthropic 은 아직 연결하지 않았습니다")
    raise LlmError("LLM_PROVIDER 값이 올바르지 않습니다 (openai, anthropic, fake 중 하나)")


def _fake(task: str) -> LlmResult:
    path = FIXTURE_DIR / f"{task}.json"
    if not path.exists():
        raise LlmError(f"가짜 응답 파일이 없습니다 ({path.name})")
    return LlmResult(data=json.loads(path.read_text(encoding="utf-8")), model="fake", input_tokens=0, output_tokens=0)


async def _openai(client: httpx.AsyncClient, kind: str, system: str, user: str) -> LlmResult:
    try:
        model = get_llm_model(kind)
        key = get_openai_api_key()
    except RuntimeError as e:
        raise LlmError(str(e)) from None
    body = {"model": model, "response_format": {"type": "json_object"},
            "max_completion_tokens": MAX_OUTPUT_TOKENS[kind],
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    try:
        resp = await client.post(OPENAI_URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise LlmError(f"AI 서비스 연결 실패 ({type(e).__name__})") from None
    if resp.status_code in (401, 403):
        raise LlmError("AI 키 오류 (HTTP %d) — 키·사용 권한 확인" % resp.status_code)
    if resp.status_code == 429:
        raise LlmError("AI 사용 한도 초과 (HTTP 429)")
    if resp.status_code != 200:
        raise LlmError(f"AI 서비스 오류 (HTTP {resp.status_code}){_error_hint(resp)}")
    try:
        payload = resp.json()
        text = payload["choices"][0]["message"]["content"] or ""
        usage = payload.get("usage") or {}
    except (ValueError, KeyError, IndexError, TypeError):
        raise LlmError("AI 응답 구조를 읽지 못했습니다", retryable=True) from None
    try:
        data = parse_json_object(text)
    except LlmError as e:
        e.input_tokens, e.output_tokens = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        raise
    return LlmResult(data=data, model=str(payload.get("model") or model),
                     input_tokens=int(usage.get("prompt_tokens") or 0), output_tokens=int(usage.get("completion_tokens") or 0))


def _error_hint(resp: httpx.Response) -> str:
    """OpenAI 오류 본문의 type/code만 덧붙인다(메시지 본문에는 요청 내용이 섞일 수 있어 쓰지 않는다)."""
    try:
        err = resp.json().get("error") or {}
        parts = [str(err.get(k)) for k in ("type", "code") if isinstance(err.get(k), str) and len(str(err.get(k))) < 60]
        return f" — {', '.join(parts)}" if parts else ""
    except ValueError:
        return ""


# ───────────────────────── 2026-11-04 웹 검색 (OpenAI Responses API의 web_search 도구)
RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_SEARCHES = 3  # 리포트 한 건에 검색 최대 3번 (비용 상한, 사용자 결정: 2~3번·약 200원)


@dataclass(frozen=True)
class WebResult:
    data: dict
    model: str
    input_tokens: int
    output_tokens: int
    searches: int  # 실제로 한 검색 수 (검색마다 도구 요금이 따로 붙는다)
    cited: frozenset  # 모델이 실제로 읽거나 인용한 URL (AI가 쓴 링크가 여기 없으면 버린다)


def _strip_utm(url: str) -> str:
    return url.split("?utm_source=")[0].split("&utm_source=")[0].rstrip("/")


async def call_web_json(client: httpx.AsyncClient, task: str, system: str, user: str) -> WebResult:
    """웹 검색을 허용한 AI 호출. 응답 글은 JSON으로 받는다. fake면 고정 예시(ai_fixtures/<task>.json, '_cited'에 인용 URL 목록)."""
    provider = get_llm_provider()
    if provider == "fake":
        path = FIXTURE_DIR / f"{task}.json"
        if not path.exists():
            raise LlmError(f"가짜 응답 파일이 없습니다 ({path.name})")
        data = json.loads(path.read_text(encoding="utf-8"))
        cited = frozenset(_strip_utm(u) for u in data.pop("_cited", []))
        return WebResult(data, "fake", 0, 0, 0, cited)
    if provider != "openai":
        raise LlmError("웹 검색은 LLM_PROVIDER=openai 에서만 씁니다")
    if not live_ai_allowed():
        raise LlmError("실제 AI 호출이 꺼져 있습니다 (홈 화면에서 실제 AI를 켜면 호출)")
    try:
        model, key = get_llm_model("write"), get_openai_api_key()
    except RuntimeError as e:
        raise LlmError(str(e)) from None
    body = {"model": model, "instructions": system, "input": user, "max_output_tokens": MAX_OUTPUT_TOKENS["write"],
            "tools": [{"type": "web_search", "search_context_size": "low", "user_location": {"type": "approximate", "country": "KR"}}],
            "max_tool_calls": MAX_SEARCHES, "include": ["web_search_call.action.sources"]}
    try:
        resp = await client.post(RESPONSES_URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT * 2)
    except httpx.HTTPError as e:
        raise LlmError(f"AI 웹 검색 연결 실패 ({type(e).__name__})") from None
    if resp.status_code in (401, 403):
        raise LlmError("AI 키 오류 (HTTP %d) — 키·사용 권한 확인" % resp.status_code)
    if resp.status_code == 429:
        raise LlmError("AI 사용 한도 초과 (HTTP 429)")
    if resp.status_code != 200:
        raise LlmError(f"AI 웹 검색 오류 (HTTP {resp.status_code}){_error_hint(resp)}")
    try:
        payload = resp.json()
        usage = payload.get("usage") or {}
        texts, cited, searches = [], set(), 0
        for item in payload.get("output") or []:
            if item.get("type") == "web_search_call":
                action = item.get("action") or {}
                if action.get("type") == "search":
                    searches += 1
                for s in action.get("sources") or []:
                    if isinstance(s, dict) and s.get("url"):
                        cited.add(_strip_utm(s["url"]))
                if action.get("url"):
                    cited.add(_strip_utm(action["url"]))
            elif item.get("type") == "message":
                for c in item.get("content") or []:
                    if c.get("type") == "output_text":
                        texts.append(c.get("text") or "")
                        for a in c.get("annotations") or []:
                            if a.get("type") == "url_citation" and a.get("url"):
                                cited.add(_strip_utm(a["url"]))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise LlmError("AI 웹 검색 응답 구조를 읽지 못했습니다") from None
    data = parse_json_object("".join(texts))
    return WebResult(data, str(payload.get("model") or model), int(usage.get("input_tokens") or 0),
                     int(usage.get("output_tokens") or 0), searches, frozenset(cited))
