"""Shared helpers for Microsoft Agent Framework clients and options."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from agent_framework import ChatOptions
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential


DEFAULT_TEMPERATURE = float(os.getenv("AGENT_FRAMEWORK_TEMPERATURE", "0.2"))
DEFAULT_MAX_TOKENS = int(os.getenv("AGENT_FRAMEWORK_MAX_TOKENS", "900"))


def _clean_options(options: ChatOptions | Dict[str, Any]) -> Dict[str, Any]:
    """Convert ChatOptions to a kwargs dict accepted by AzureOpenAIChatClient."""
    if isinstance(options, dict):
        raw = dict(options)
    elif hasattr(options, "__dict__"):
        raw = options.__dict__
    else:
        raw = dict(getattr(options, "__iter__", lambda: [])())  # type: ignore[arg-type]
    cleaned: Dict[str, Any] = {k: v for k, v in raw.items() if v is not None and k != "_tools"}
    if raw.get("_tools") is not None:
        cleaned["tools"] = raw["_tools"]
    return cleaned


def build_chat_options(
    *,
    conversation_id: Optional[str] = None,
    allow_multiple_tool_calls: bool = True,
    store: bool = False,
    temperature: Optional[float] = DEFAULT_TEMPERATURE,
    max_tokens: Optional[int] = DEFAULT_MAX_TOKENS,
    tool_choice: Optional[str] = "auto",
    tools: Optional[Any] = None,
    metadata: Optional[Dict[str, Any]] = None,
    response_format: Optional[Any] = None,
) -> Dict[str, Any]:
    """Create a serialized ChatOptions dict with sensible defaults."""
    options = ChatOptions(
        conversation_id=conversation_id,
        allow_multiple_tool_calls=allow_multiple_tool_calls,
        store=store,
        temperature=temperature,
        max_tokens=max_tokens,
        tool_choice=tool_choice,
        tools=tools,
        metadata=metadata,
        response_format=response_format,
    )
    return _clean_options(options)


def create_chat_client() -> Optional[AzureOpenAIChatClient]:
    """Create a shared AzureOpenAIChatClient using env/managed identity fallbacks."""
    deployment = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or os.getenv(
        "AZURE_OPENAI_DEPLOYMENT"
    )
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION")

    client_kwargs: Dict[str, Any] = {}
    if deployment:
        client_kwargs["deployment_name"] = deployment
    if endpoint:
        client_kwargs["endpoint"] = endpoint
    if api_version:
        client_kwargs["api_version"] = api_version
    if api_key:
        client_kwargs["api_key"] = api_key
    else:
        try:
            credential = DefaultAzureCredential(
                exclude_interactive_browser_credential=True,
                exclude_shared_token_cache_credential=True,
                exclude_visual_studio_code_credential=True,
                exclude_powershell_credential=True,
            )
            client_kwargs["credential"] = credential
        except Exception:
            # Leave client_kwargs without credential if identity creation fails
            pass

    try:
        return AzureOpenAIChatClient(**client_kwargs)
    except Exception:
        return None
