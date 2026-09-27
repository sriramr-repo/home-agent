from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ModelProviderError(RuntimeError):
    pass


class LocalModelError(ModelProviderError):
    pass


class NineRouterModelError(ModelProviderError):
    pass


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


class ModelProvider(ABC):
    model: str

    @abstractmethod
    def invoke(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        yield self.invoke(messages, tools)


def _normalize_response(raw: dict[str, Any], message: dict[str, Any]) -> dict[str, Any]:
    calls = []
    for call in message.get("tool_calls", []):
        function = call.get("function", {})
        name = function.get("name")
        arguments = function.get("arguments", {})
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ModelProviderError("malformed tool call") from exc
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise ModelProviderError("malformed tool call")
        calls.append(ToolCall(name, arguments))
    return {"content": message.get("content", ""), "tool_calls": calls, "message": message, "raw": raw}


class LocalModel(ModelProvider):
    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "qwen3.5:9b")
        self.timeout = timeout or float(os.getenv("MODEL_TIMEOUT", "120"))

    def invoke(self, messages, tools=None):
        payload = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        request = Request(f"{self.base_url}/api/chat", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = json.loads(response.read())
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise LocalModelError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise LocalModelError(f"Ollama unavailable at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LocalModelError("malformed Ollama response") from exc
        message = raw.get("message")
        if not isinstance(message, dict):
            raise LocalModelError("malformed Ollama response: missing message")
        try:
            return _normalize_response(raw, message)
        except ModelProviderError as exc:
            raise LocalModelError(str(exc)) from exc


class NineRouterModel(ModelProvider):
    def __init__(self, base_url: str | None = None, model: str | None = None, api_key: str | None = None, timeout: float | None = None) -> None:
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "")).rstrip("/")
        self.model = model or os.getenv("LLM_MODEL", "")
        self.api_key = api_key or os.getenv("LLM_API_KEY")
        self.timeout = timeout or float(os.getenv("MODEL_TIMEOUT", "120"))
        if not self.base_url or not self.model:
            raise NineRouterModelError("9router requires LLM_BASE_URL and LLM_MODEL")

    def invoke(self, messages, tools=None):
        payload = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            with urlopen(Request(f"{self.base_url}/v1/chat/completions", data=json.dumps(payload).encode(), headers=headers), timeout=self.timeout) as response:
                raw = json.loads(response.read())
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise NineRouterModelError(f"9router request failed: {exc}") from exc
        try:
            message = raw["choices"][0]["message"]
            return _normalize_response(raw, message)
        except (KeyError, IndexError, TypeError, ModelProviderError) as exc:
            raise NineRouterModelError("malformed 9router response") from exc


def get_model_provider() -> ModelProvider:
    provider = os.getenv("LLM_PROVIDER", "ollama").lower()
    if provider in {"ollama", "local"}:
        return LocalModel()
    if provider in {"9router", "ninerouter"}:
        return NineRouterModel()
    raise ModelProviderError(f"unsupported model provider: {provider}")
