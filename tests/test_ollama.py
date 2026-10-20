"""آزمون ارائه‌دهندهٔ Ollama — سلامت، خطاها و degradation صادقانه."""
from __future__ import annotations

import httpx

from omid.ai.ollama import OllamaProvider


def mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=2.0)


def test_health_unreachable_is_honest():
    provider = OllamaProvider("http://127.0.0.1:9", "any", timeout=1.0)
    status = provider.health()
    assert status.available is False
    assert status.error
    assert "Ollama" in status.error
    provider.close()


def test_health_ok_lists_models():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": "qwen2.5:7b"}, {"name": "llama3:8b"}]})

    provider = OllamaProvider("http://fake", "qwen2.5:7b", client=mock_client(handler))
    status = provider.health()
    assert status.available is True
    assert "qwen2.5:7b" in status.models
    assert status.latency_ms is not None
    assert provider.model_available("qwen2.5") is True  # تطابق پیشوند
    assert provider.model_available("mistral") is False


def test_chat_success():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "سلام"}})

    provider = OllamaProvider("http://fake", "qwen2.5:7b", client=mock_client(handler))
    result = provider.chat([{"role": "user", "content": "hi"}])
    assert result.ok is True
    assert result.text == "سلام"
    assert result.model == "qwen2.5:7b"


def test_chat_without_model_configured_is_honest():
    provider = OllamaProvider("http://fake", "", client=mock_client(lambda r: httpx.Response(200)))
    result = provider.chat([{"role": "user", "content": "hi"}])
    assert result.ok is False
    assert "پیکربندی نشده" in (result.error or "")


def test_chat_http_error_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model exploded")

    provider = OllamaProvider("http://fake", "m", client=mock_client(handler))
    result = provider.chat([{"role": "user", "content": "hi"}])
    assert result.ok is False
    assert "500" in (result.error or "")


def test_chat_network_error_reported():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    provider = OllamaProvider("http://fake", "m", client=mock_client(handler))
    result = provider.chat([{"role": "user", "content": "hi"}])
    assert result.ok is False
    assert "ConnectError" in (result.error or "")


def test_ai_available_requires_model_and_health(config):
    from omid.context import AppContext

    ctx = AppContext(config)
    try:
        # مدل پیکربندی نشده → حتی با سرویس سالم، ai_available نیست
        assert ctx.ai_available() is False
    finally:
        ctx.close()
