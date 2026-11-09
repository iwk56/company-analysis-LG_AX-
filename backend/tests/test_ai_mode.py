import pytest
from fastapi.testclient import TestClient

from app import config, main


@pytest.fixture(autouse=True)
def reset_ai_mode(monkeypatch):
    monkeypatch.setattr(config, "_runtime_live_ai_override", None)
    monkeypatch.delenv("LLM_ALLOW_LIVE", raising=False)


def local_client():
    return TestClient(main.app, client=("127.0.0.1", 12345))


def test_ai_mode_starts_disabled_and_can_be_toggled(monkeypatch):
    monkeypatch.setattr(config, "get_llm_provider", lambda: "openai")
    monkeypatch.setattr(config, "get_openai_api_key", lambda: "configured")
    monkeypatch.setattr(config, "get_llm_model", lambda _kind: "test-model")

    with local_client() as client:
        assert client.get("/api/ai-mode").json()["live"] is False
        enabled = client.post("/api/ai-mode", json={"live": True})
        assert enabled.status_code == 200 and enabled.json()["live"] is True
        assert config.live_ai_allowed() is True
        disabled = client.post("/api/ai-mode", json={"live": False})
        assert disabled.status_code == 200 and disabled.json()["live"] is False
        assert config.live_ai_allowed() is False


def test_ai_mode_cannot_be_enabled_from_a_remote_client(monkeypatch):
    monkeypatch.setattr(config, "get_llm_provider", lambda: "openai")
    remote = TestClient(main.app, client=("192.0.2.1", 12345))

    response = remote.post("/api/ai-mode", json={"live": True})

    assert response.status_code == 403
    assert config.live_ai_allowed() is False


def test_ai_mode_requires_openai_credentials_before_enabling(monkeypatch):
    monkeypatch.setattr(config, "get_llm_provider", lambda: "openai")

    def missing_key():
        raise RuntimeError("backend/.env 에 OPENAI_API_KEY 가 없습니다.")

    monkeypatch.setattr(config, "get_openai_api_key", missing_key)
    with local_client() as client:
        response = client.post("/api/ai-mode", json={"live": True})

    assert response.status_code == 400
    assert "OPENAI_API_KEY" in response.json()["detail"]
    assert config.live_ai_allowed() is False


def test_ai_mode_rejects_non_openai_provider(monkeypatch):
    monkeypatch.setattr(config, "get_llm_provider", lambda: "fake")

    with local_client() as client:
        response = client.post("/api/ai-mode", json={"live": True})

    assert response.status_code == 400
    assert config.live_ai_allowed() is False
