from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class LlmConfig:
    provider: str           # "groq" | "anthropic" | "openai" | "local"
    model: str
    api_key_env: str = "GROQ_API_KEY"
    temperature: float = 0.4
    max_tokens: int = 400
    local_model_path: str | None = None
    local_n_ctx: int = 8192
    local_n_threads: int = 8


@dataclass
class LlmMessage:
    role: str               # "system" | "user" | "assistant"
    content: str


class LlmClient:
    """Thin abstraction. Default backend is Groq (OpenAI-compatible API).
    Tests inject `_groq` directly; real usage instantiates lazily.
    """

    def __init__(self, config: LlmConfig) -> None:
        self.config = config
        self._groq = None
        self._llama = None

    def complete(self, messages: list[LlmMessage]) -> str:
        if self.config.provider == "groq":
            return self._complete_groq(messages)
        if self.config.provider == "local":
            return self._complete_local(messages)
        raise NotImplementedError(f"provider {self.config.provider} not supported in v1")

    def _ensure_groq(self):
        if self._groq is not None:
            return
        key = os.environ.get(self.config.api_key_env, "").strip()
        if not key:
            raise RuntimeError(
                f"{self.config.api_key_env} env var not set; configure your Groq key"
            )
        from groq import Groq
        self._groq = Groq(api_key=key)

    def _complete_groq(self, messages: list[LlmMessage]) -> str:
        self._ensure_groq()
        assert self._groq is not None
        resp = self._groq.chat.completions.create(
            model=self.config.model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()

    def _ensure_local(self):
        if self._llama is not None:
            return
        if not self.config.local_model_path:
            raise RuntimeError("local_model_path not configured")
        from llama_cpp import Llama
        self._llama = Llama(
            model_path=self.config.local_model_path,
            n_ctx=self.config.local_n_ctx,
            n_threads=self.config.local_n_threads,
            verbose=False,
        )

    def _complete_local(self, messages: list[LlmMessage]) -> str:
        self._ensure_local()
        assert self._llama is not None
        prompt_parts: list[str] = []
        for m in messages:
            prompt_parts.append(f"<|im_start|>{m.role}\n{m.content}<|im_end|>")
        prompt_parts.append("<|im_start|>assistant\n")
        prompt = "\n".join(prompt_parts)
        out = self._llama(
            prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
            stop=["<|im_end|>"],
        )
        return out["choices"][0]["text"].strip()
