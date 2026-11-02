"""API 키 목록과 입력 여부 확인. 외부 호출은 하지 않고, 키 값은 돌려주지도 출력하지도 않는다."""
from dataclasses import dataclass
from typing import Mapping

PROVIDERS = ("openai", "anthropic")


@dataclass(frozen=True)
class KeySpec:
    id: str
    label: str
    env_names: tuple[str, ...]
    provider: str | None = None  # AI 키면 어느 제공자용인지


KEY_SPECS = (
    KeySpec("dart", "OpenDART", ("DART_API_KEY",)),
    KeySpec("data_go_kr", "공공데이터포털(주식시세)", ("DATA_GO_KR_KEY",)),
    KeySpec("naver", "네이버 검색(뉴스)", ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")),
    KeySpec("ecos", "한국은행 ECOS", ("ECOS_API_KEY",)),
    KeySpec("openai", "OpenAI", ("OPENAI_API_KEY",), provider="openai"),
    KeySpec("anthropic", "Anthropic(Claude)", ("ANTHROPIC_API_KEY",), provider="anthropic"),
)


def get_provider(env: Mapping[str, str]) -> str:
    """LLM_PROVIDER 값. 비어 있으면 기본값 openai."""
    return (env.get("LLM_PROVIDER") or "").strip().lower() or "openai"


def missing_env_names(spec: KeySpec, env: Mapping[str, str]) -> list[str]:
    return [n for n in spec.env_names if not (env.get(n) or "").strip()]


def is_required(spec: KeySpec, env: Mapping[str, str]) -> bool:
    """AI 키는 선택한 제공자의 것만 필수이고, 나머지는 선택 항목."""
    return spec.provider is None or spec.provider == get_provider(env)


def startup_warnings(env: Mapping[str, str]) -> list[str]:
    """서버 시작 때 보여줄 경고. 비어 있는 필수 키의 이름만 알려준다(값은 다루지 않음)."""
    warnings = []
    provider = get_provider(env)
    if provider not in PROVIDERS:
        warnings.append(f"LLM_PROVIDER 값이 올바르지 않습니다 ({' 또는 '.join(PROVIDERS)} 중 하나여야 합니다)")
    for spec in KEY_SPECS:
        missing = missing_env_names(spec, env)
        if missing and is_required(spec, env):
            warnings.append(f"{', '.join(missing)} 가 비어 있습니다 ({spec.label}) — backend/.env 확인")
    return warnings
