from meeting.intelligence.llm_client import LlmClient, LlmConfig, LlmMessage


class _FakeGroqClient:
    """Mimics groq.Groq().chat.completions.create()."""

    class _Resp:
        class _Choice:
            class _Msg:
                content = "Resposta gerada pela mock"
            message = _Msg()
        choices = [_Choice()]

    class _Completions:
        def create(self, **kwargs):
            return _FakeGroqClient._Resp()

    class _Chat:
        pass

    _Chat.completions = _Completions()
    chat = _Chat()


def test_llm_client_calls_provider_and_returns_text(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    cfg = LlmConfig(provider="groq", model="x", api_key_env="GROQ_API_KEY")
    client = LlmClient(cfg)
    client._groq = _FakeGroqClient()  # type: ignore[attr-defined]

    out = client.complete([LlmMessage(role="user", content="oi")])
    assert "Resposta" in out


def test_llm_client_missing_key_raises(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    cfg = LlmConfig(provider="groq", model="x", api_key_env="GROQ_API_KEY")
    client = LlmClient(cfg)
    try:
        client.complete([LlmMessage(role="user", content="oi")])
    except RuntimeError as e:
        assert "GROQ_API_KEY" in str(e)
        return
    raise AssertionError("expected RuntimeError")
