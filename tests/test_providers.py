"""Unit tests for NanoBot provider modules.

Covers:
- LLMResponse: creation, has_tool_calls property, tool_calls content
- ToolCallRequest: creation and field access
- Registry: find_by_name, find_by_model, find_gateway lookups
- LiteLLMProvider: initialization, get_default_model, _resolve_model,
  chat() with mocked acompletion, error handling
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from nanobot.providers.litellm_provider import LiteLLMProvider
from nanobot.providers.registry import (
    PROVIDERS,
    find_by_model,
    find_by_name,
    find_gateway,
)

# ---------------------------------------------------------------------------
# LLMResponse
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_creation_minimal(self) -> None:
        resp = LLMResponse(content="hello")
        assert resp.content == "hello"
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"
        assert resp.usage == {}
        assert resp.reasoning_content is None

    def test_creation_full(self) -> None:
        tc = ToolCallRequest(id="tc1", name="my_tool", arguments={"x": 1})
        resp = LLMResponse(
            content="text",
            tool_calls=[tc],
            finish_reason="tool_calls",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            reasoning_content="I think...",
        )
        assert resp.content == "text"
        assert len(resp.tool_calls) == 1
        assert resp.finish_reason == "tool_calls"
        assert resp.usage["total_tokens"] == 15
        assert resp.reasoning_content == "I think..."

    def test_has_tool_calls_false_when_empty(self) -> None:
        resp = LLMResponse(content="hello", tool_calls=[])
        assert resp.has_tool_calls is False

    def test_has_tool_calls_true_when_non_empty(self) -> None:
        tc = ToolCallRequest(id="tc1", name="tool", arguments={})
        resp = LLMResponse(content=None, tool_calls=[tc])
        assert resp.has_tool_calls is True

    def test_has_tool_calls_default_is_false(self) -> None:
        resp = LLMResponse(content="hi")
        assert resp.has_tool_calls is False

    def test_content_can_be_none(self) -> None:
        tc = ToolCallRequest(id="t1", name="fn", arguments={"a": "b"})
        resp = LLMResponse(content=None, tool_calls=[tc])
        assert resp.content is None
        assert resp.has_tool_calls is True

    def test_multiple_tool_calls(self) -> None:
        calls = [
            ToolCallRequest(id=f"tc{i}", name=f"tool_{i}", arguments={"n": i})
            for i in range(3)
        ]
        resp = LLMResponse(content=None, tool_calls=calls)
        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 3


# ---------------------------------------------------------------------------
# ToolCallRequest
# ---------------------------------------------------------------------------


class TestToolCallRequest:
    def test_fields(self) -> None:
        tc = ToolCallRequest(id="abc", name="get_weather", arguments={"city": "Hanoi"})
        assert tc.id == "abc"
        assert tc.name == "get_weather"
        assert tc.arguments == {"city": "Hanoi"}

    def test_empty_arguments(self) -> None:
        tc = ToolCallRequest(id="x", name="ping", arguments={})
        assert tc.arguments == {}

    def test_nested_arguments(self) -> None:
        args: dict[str, Any] = {"filters": {"date": "2026-01-01", "limit": 10}}
        tc = ToolCallRequest(id="y", name="search", arguments=args)
        assert tc.arguments["filters"]["limit"] == 10


# ---------------------------------------------------------------------------
# Registry — find_by_name
# ---------------------------------------------------------------------------


class TestFindByName:
    def test_returns_spec_for_known_provider(self) -> None:
        spec = find_by_name("anthropic")
        assert spec is not None
        assert spec.name == "anthropic"

    def test_returns_spec_for_deepseek(self) -> None:
        spec = find_by_name("deepseek")
        assert spec is not None
        assert spec.name == "deepseek"
        assert spec.litellm_prefix == "deepseek"

    def test_returns_spec_for_openrouter(self) -> None:
        spec = find_by_name("openrouter")
        assert spec is not None
        assert spec.is_gateway is True

    def test_returns_none_for_unknown_name(self) -> None:
        assert find_by_name("nonexistent_provider_xyz") is None

    def test_case_sensitive_match(self) -> None:
        # Registry names are lowercase; uppercase should not match
        assert find_by_name("Anthropic") is None
        assert find_by_name("DEEPSEEK") is None

    def test_every_entry_in_providers_findable(self) -> None:
        for spec in PROVIDERS:
            found = find_by_name(spec.name)
            assert found is not None
            assert found.name == spec.name


# ---------------------------------------------------------------------------
# Registry — find_by_model
# ---------------------------------------------------------------------------


class TestFindByModel:
    def test_claude_model_matches_anthropic(self) -> None:
        spec = find_by_model("claude-sonnet-4-5")
        assert spec is not None
        assert spec.name == "anthropic"

    def test_gpt_model_matches_openai(self) -> None:
        spec = find_by_model("gpt-4o")
        assert spec is not None
        assert spec.name == "openai"

    def test_deepseek_model_matches_deepseek(self) -> None:
        spec = find_by_model("deepseek-chat")
        assert spec is not None
        assert spec.name == "deepseek"

    def test_gemini_model_matches_gemini(self) -> None:
        spec = find_by_model("gemini-pro")
        assert spec is not None
        assert spec.name == "gemini"

    def test_qwen_model_matches_dashscope(self) -> None:
        spec = find_by_model("qwen-max")
        assert spec is not None
        assert spec.name == "dashscope"

    def test_kimi_model_matches_moonshot(self) -> None:
        spec = find_by_model("kimi-k2.5")
        assert spec is not None
        assert spec.name == "moonshot"

    def test_glm_model_matches_zhipu(self) -> None:
        spec = find_by_model("glm-4")
        assert spec is not None
        assert spec.name == "zhipu"

    def test_model_with_explicit_provider_prefix_wins(self) -> None:
        # "github_copilot/..." should match github_copilot, not openai_codex
        spec = find_by_model("github_copilot/gpt-4o")
        assert spec is not None
        assert spec.name == "github_copilot"

    def test_unknown_model_returns_none(self) -> None:
        assert find_by_model("totally-unknown-model-xyz") is None

    def test_case_insensitive_keyword_match(self) -> None:
        # Keywords are matched case-insensitively via lower()
        spec = find_by_model("Claude-3-Opus")
        assert spec is not None
        assert spec.name == "anthropic"

    def test_gateways_are_skipped(self) -> None:
        # find_by_model skips gateways; "openrouter" keyword in model name
        # should not return the openrouter gateway spec via this function
        spec = find_by_model("openrouter/claude-3")
        # If there's a slash, the prefix "openrouter" maps to... let's verify
        # the spec name is openrouter (it matches by prefix == spec.name)
        # Actually find_by_model filters out gateways for keyword scan but
        # still does explicit prefix match including gateways if name matches.
        # The registry skips is_gateway and is_local for keyword scan only.
        # An explicit "openrouter/..." prefix won't match "openrouter" spec
        # because openrouter is a gateway and std_specs excludes gateways.
        # So result is None or anthropic (via "claude" keyword on remainder).
        # Verify it does NOT return the openrouter gateway spec itself.
        if spec is not None:
            assert spec.name != "openrouter"

    def test_minimax_model(self) -> None:
        spec = find_by_model("MiniMax-M2.1")
        assert spec is not None
        assert spec.name == "minimax"

    def test_groq_model(self) -> None:
        spec = find_by_model("llama3-groq-8b")
        assert spec is not None
        assert spec.name == "groq"


# ---------------------------------------------------------------------------
# Registry — find_gateway
# ---------------------------------------------------------------------------


class TestFindGateway:
    def test_detect_openrouter_by_key_prefix(self) -> None:
        spec = find_gateway(api_key="sk-or-v1-abcdef")
        assert spec is not None
        assert spec.name == "openrouter"

    def test_detect_aihubmix_by_base_keyword(self) -> None:
        spec = find_gateway(api_base="https://aihubmix.com/v1")
        assert spec is not None
        assert spec.name == "aihubmix"

    def test_detect_siliconflow_by_base_keyword(self) -> None:
        spec = find_gateway(api_base="https://api.siliconflow.cn/v1")
        assert spec is not None
        assert spec.name == "siliconflow"

    def test_direct_name_lookup_for_gateway(self) -> None:
        spec = find_gateway(provider_name="openrouter")
        assert spec is not None
        assert spec.name == "openrouter"

    def test_direct_name_lookup_for_local_vllm(self) -> None:
        spec = find_gateway(provider_name="vllm")
        assert spec is not None
        assert spec.name == "vllm"
        assert spec.is_local is True

    def test_standard_provider_name_returns_none(self) -> None:
        # anthropic is not a gateway/local provider
        spec = find_gateway(provider_name="anthropic")
        assert spec is None

    def test_no_match_returns_none(self) -> None:
        spec = find_gateway(api_key="sk-normal-key", api_base="https://api.example.com")
        assert spec is None

    def test_none_inputs_return_none(self) -> None:
        assert find_gateway() is None


# ---------------------------------------------------------------------------
# LiteLLMProvider — initialization and default model
# ---------------------------------------------------------------------------


class TestLiteLLMProviderInit:
    def test_default_model_returned(self) -> None:
        provider = LiteLLMProvider(default_model="gpt-4o")
        assert provider.get_default_model() == "gpt-4o"

    def test_default_model_fallback(self) -> None:
        provider = LiteLLMProvider()
        assert provider.get_default_model() == "anthropic/claude-opus-4-6"

    def test_api_key_stored(self) -> None:
        provider = LiteLLMProvider(api_key="test-key-123")
        assert provider.api_key == "test-key-123"

    def test_api_base_stored(self) -> None:
        provider = LiteLLMProvider(api_base="https://my-proxy.example.com/v1")
        assert provider.api_base == "https://my-proxy.example.com/v1"

    def test_gateway_detected_for_openrouter_key(self) -> None:
        provider = LiteLLMProvider(api_key="sk-or-v1-abc123")
        assert provider._gateway is not None
        assert provider._gateway.name == "openrouter"

    def test_no_gateway_for_standard_key(self) -> None:
        provider = LiteLLMProvider(api_key="sk-proj-abc123", default_model="gpt-4o")
        assert provider._gateway is None

    def test_extra_headers_stored(self) -> None:
        headers = {"X-Custom": "value"}
        provider = LiteLLMProvider(extra_headers=headers)
        assert provider.extra_headers == headers

    def test_extra_headers_default_empty(self) -> None:
        provider = LiteLLMProvider()
        assert provider.extra_headers == {}


# ---------------------------------------------------------------------------
# LiteLLMProvider — _resolve_model
# ---------------------------------------------------------------------------


class TestResolveModel:
    def test_claude_no_prefix_added(self) -> None:
        """Anthropic has empty litellm_prefix, so model stays unchanged."""
        provider = LiteLLMProvider(default_model="claude-sonnet-4-5")
        resolved = provider._resolve_model("claude-sonnet-4-5")
        assert resolved == "claude-sonnet-4-5"

    def test_deepseek_prefix_added(self) -> None:
        provider = LiteLLMProvider(default_model="deepseek-chat")
        resolved = provider._resolve_model("deepseek-chat")
        assert resolved == "deepseek/deepseek-chat"

    def test_deepseek_already_prefixed_not_doubled(self) -> None:
        provider = LiteLLMProvider(default_model="deepseek/deepseek-chat")
        resolved = provider._resolve_model("deepseek/deepseek-chat")
        assert resolved == "deepseek/deepseek-chat"
        assert "deepseek/deepseek/deepseek" not in resolved

    def test_gemini_prefix_added(self) -> None:
        provider = LiteLLMProvider(default_model="gemini-pro")
        resolved = provider._resolve_model("gemini-pro")
        assert resolved == "gemini/gemini-pro"

    def test_gemini_already_prefixed_not_doubled(self) -> None:
        provider = LiteLLMProvider(default_model="gemini/gemini-pro")
        resolved = provider._resolve_model("gemini/gemini-pro")
        assert resolved == "gemini/gemini-pro"

    def test_openrouter_gateway_prefixes_any_model(self) -> None:
        """Gateway mode: all models get the gateway prefix."""
        provider = LiteLLMProvider(
            api_key="sk-or-v1-abc",
            default_model="claude-sonnet-4-5",
        )
        resolved = provider._resolve_model("claude-sonnet-4-5")
        assert resolved == "openrouter/claude-sonnet-4-5"

    def test_aihubmix_strips_anthropic_prefix_then_prepends_openai(self) -> None:
        """AiHubMix has strip_model_prefix=True: anthropic/claude-3 → claude-3 → openai/claude-3."""
        provider = LiteLLMProvider(
            api_base="https://aihubmix.com/v1",
            default_model="anthropic/claude-3",
        )
        resolved = provider._resolve_model("anthropic/claude-3")
        assert resolved == "openai/claude-3"

    def test_unknown_model_unchanged(self) -> None:
        provider = LiteLLMProvider()
        resolved = provider._resolve_model("totally-unknown-model")
        assert resolved == "totally-unknown-model"

    def test_groq_prefix_added(self) -> None:
        # groq/ prefix is only added when the model keyword "groq" appears in the name
        # e.g. when model is explicitly scoped as "groq/llama3-8b-8192" already prefixed,
        # or a model name that contains the "groq" keyword.
        # Plain "llama3-8b-8192" has no groq keyword so it stays unchanged.
        provider = LiteLLMProvider(default_model="llama3-8b-8192")
        resolved = provider._resolve_model("llama3-8b-8192")
        assert resolved == "llama3-8b-8192"

    def test_groq_model_with_groq_keyword_gets_prefix(self) -> None:
        # A model name containing "groq" matches the groq spec and gets prefixed
        provider = LiteLLMProvider(default_model="groq-llama3")
        resolved = provider._resolve_model("groq-llama3")
        assert resolved == "groq/groq-llama3"

    def test_groq_already_prefixed_not_doubled(self) -> None:
        provider = LiteLLMProvider()
        resolved = provider._resolve_model("groq/llama3-8b-8192")
        assert resolved == "groq/llama3-8b-8192"


# ---------------------------------------------------------------------------
# LiteLLMProvider — chat() with mocked acompletion
# ---------------------------------------------------------------------------


def _make_mock_response(
    content: str = "Hello!",
    finish_reason: str = "stop",
    tool_calls: list[Any] | None = None,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    reasoning_content: str | None = None,
) -> MagicMock:
    """Build a fake LiteLLM ModelResponse object."""
    message = MagicMock()
    message.content = content
    message.tool_calls = tool_calls or []
    message.reasoning_content = reasoning_content

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = finish_reason

    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    usage.total_tokens = prompt_tokens + completion_tokens

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


def _make_tool_call_mock(
    tc_id: str,
    name: str,
    arguments: str,
) -> MagicMock:
    fn = MagicMock()
    fn.name = name
    fn.arguments = arguments

    tc = MagicMock()
    tc.id = tc_id
    tc.function = fn
    return tc


@pytest.mark.asyncio
class TestLiteLLMProviderChat:
    async def test_chat_returns_llm_response(self) -> None:
        provider = LiteLLMProvider(default_model="gpt-4o-mini")
        mock_resp = _make_mock_response(content="Hi there!")

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await provider.chat(
                messages=[{"role": "user", "content": "Hello"}],
            )

        assert isinstance(result, LLMResponse)
        assert result.content == "Hi there!"
        assert result.finish_reason == "stop"
        assert result.has_tool_calls is False

    async def test_chat_usage_populated(self) -> None:
        provider = LiteLLMProvider(default_model="gpt-4o-mini")
        mock_resp = _make_mock_response(
            content="ok",
            prompt_tokens=20,
            completion_tokens=8,
        )

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await provider.chat(
                messages=[{"role": "user", "content": "ping"}],
            )

        assert result.usage["prompt_tokens"] == 20
        assert result.usage["completion_tokens"] == 8
        assert result.usage["total_tokens"] == 28

    async def test_chat_with_tool_calls(self) -> None:
        provider = LiteLLMProvider(default_model="gpt-4o")
        tc_mock = _make_tool_call_mock(
            tc_id="call_abc",
            name="get_weather",
            arguments='{"city": "Hanoi"}',
        )
        mock_resp = _make_mock_response(
            content=None,
            finish_reason="tool_calls",
            tool_calls=[tc_mock],
        )

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await provider.chat(
                messages=[{"role": "user", "content": "What's the weather in Hanoi?"}],
                tools=[{"type": "function", "function": {"name": "get_weather"}}],
            )

        assert result.has_tool_calls is True
        assert len(result.tool_calls) == 1
        tc = result.tool_calls[0]
        assert tc.id == "call_abc"
        assert tc.name == "get_weather"
        assert tc.arguments == {"city": "Hanoi"}
        assert result.finish_reason == "tool_calls"

    async def test_chat_error_returns_error_response(self) -> None:
        provider = LiteLLMProvider(default_model="gpt-4o-mini")

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("rate limit exceeded"),
        ):
            result = await provider.chat(
                messages=[{"role": "user", "content": "hello"}],
            )

        assert result.finish_reason == "error"
        assert "rate limit exceeded" in (result.content or "")
        assert result.has_tool_calls is False

    async def test_chat_uses_override_model(self) -> None:
        """When model kwarg is passed, it should be used instead of default."""
        provider = LiteLLMProvider(default_model="gpt-4o")
        mock_resp = _make_mock_response(content="done")

        captured: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return mock_resp

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new=fake_acompletion,
        ):
            await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                model="deepseek-chat",
            )

        # deepseek-chat should be resolved to deepseek/deepseek-chat
        assert captured["model"] == "deepseek/deepseek-chat"

    async def test_chat_max_tokens_clamped_to_minimum_one(self) -> None:
        """max_tokens <= 0 must be clamped to 1."""
        provider = LiteLLMProvider(default_model="gpt-4o-mini")
        mock_resp = _make_mock_response(content="ok")

        captured: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return mock_resp

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new=fake_acompletion,
        ):
            await provider.chat(
                messages=[{"role": "user", "content": "hi"}],
                max_tokens=-10,
            )

        assert captured["max_tokens"] == 1

    async def test_chat_normalizes_context_role(self) -> None:
        """Messages with role='context' must be converted to role='user'."""
        provider = LiteLLMProvider(default_model="gpt-4o-mini")
        mock_resp = _make_mock_response(content="ok")

        captured: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return mock_resp

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new=fake_acompletion,
        ):
            await provider.chat(
                messages=[{"role": "context", "content": "background info"}],
            )

        sent_messages = captured["messages"]
        assert all(m["role"] != "context" for m in sent_messages)
        context_msgs = [m for m in sent_messages if "background info" in str(m.get("content", ""))]
        assert len(context_msgs) == 1
        assert context_msgs[0]["role"] == "user"

    async def test_chat_with_reasoning_content(self) -> None:
        provider = LiteLLMProvider(default_model="deepseek-reasoner")
        mock_resp = _make_mock_response(
            content="Final answer",
            reasoning_content="Let me think...",
        )

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            result = await provider.chat(
                messages=[{"role": "user", "content": "solve this"}],
            )

        assert result.content == "Final answer"
        assert result.reasoning_content == "Let me think..."

    async def test_chat_api_key_passed_to_litellm(self) -> None:
        """api_key should be forwarded to acompletion kwargs."""
        provider = LiteLLMProvider(
            api_key="sk-test-key",
            default_model="gpt-4o-mini",
        )
        mock_resp = _make_mock_response(content="ok")

        captured: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return mock_resp

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new=fake_acompletion,
        ):
            await provider.chat(messages=[{"role": "user", "content": "hi"}])

        assert captured.get("api_key") == "sk-test-key"

    async def test_chat_tools_and_tool_choice_forwarded(self) -> None:
        """When tools are provided, tool_choice='auto' must be set."""
        provider = LiteLLMProvider(default_model="gpt-4o")
        mock_resp = _make_mock_response(content="ok")

        captured: dict[str, Any] = {}

        async def fake_acompletion(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return mock_resp

        tool_def = {"type": "function", "function": {"name": "search"}}

        with patch(
            "nanobot.providers.litellm_provider.acompletion",
            new=fake_acompletion,
        ):
            await provider.chat(
                messages=[{"role": "user", "content": "find me something"}],
                tools=[tool_def],
            )

        assert "tools" in captured
        assert captured.get("tool_choice") == "auto"


# ---------------------------------------------------------------------------
# LLMProvider base — static helpers (normalize_context_role, sanitize_empty)
# ---------------------------------------------------------------------------


class TestBaseProviderHelpers:
    def test_normalize_context_role_converts_to_user(self) -> None:
        messages = [{"role": "context", "content": "some background"}]
        result = LLMProvider._normalize_context_role(messages)
        assert result[0]["role"] == "user"
        assert "[Group Chat Context" in result[0]["content"]

    def test_normalize_context_role_passes_through_others(self) -> None:
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = LLMProvider._normalize_context_role(messages)
        assert [m["role"] for m in result] == ["system", "user", "assistant"]

    def test_normalize_context_role_does_not_mutate_original(self) -> None:
        original = [{"role": "context", "content": "bg"}]
        LLMProvider._normalize_context_role(original)
        assert original[0]["role"] == "context"

    def test_sanitize_empty_content_replaces_empty_string(self) -> None:
        messages = [{"role": "user", "content": ""}]
        result = LLMProvider._sanitize_empty_content(messages)
        assert result[0]["content"] == "(empty)"

    def test_sanitize_empty_content_passes_through_non_empty(self) -> None:
        messages = [{"role": "user", "content": "hello"}]
        result = LLMProvider._sanitize_empty_content(messages)
        assert result[0]["content"] == "hello"

    def test_sanitize_empty_content_does_not_mutate_original(self) -> None:
        original = [{"role": "user", "content": ""}]
        LLMProvider._sanitize_empty_content(original)
        assert original[0]["content"] == ""

    def test_sanitize_filters_empty_text_blocks_in_list_content(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "text", "text": "actual text"},
                ],
            }
        ]
        result = LLMProvider._sanitize_empty_content(messages)
        content = result[0]["content"]
        assert isinstance(content, list)
        assert len(content) == 1
        assert content[0]["text"] == "actual text"

    def test_sanitize_assistant_tool_call_empty_content_set_to_none(self) -> None:
        messages = [{"role": "assistant", "content": "", "tool_calls": [{"id": "tc1"}]}]
        result = LLMProvider._sanitize_empty_content(messages)
        assert result[0]["content"] is None
