"""Mid-loop context compaction — auto-summarise old messages when nearing context limit."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.providers.base import LLMProvider


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK-heavy."""
    return max(1, len(text) // 3)


def _messages_token_count(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens across all messages."""
    total = 0
    for msg in messages:
        content = msg.get("content") or ""
        if isinstance(content, str):
            total += _estimate_tokens(content)
        # Tool calls add overhead
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            total += _estimate_tokens(fn.get("name", ""))
            total += _estimate_tokens(fn.get("arguments", ""))
    return total


def _get_context_window(model: str) -> int:
    """Look up context window size for a model. Falls back to 128K."""
    try:
        import litellm

        info = litellm.get_model_info(model)
        return info.get("max_input_tokens") or info.get("max_tokens") or 128_000
    except Exception:
        # Common defaults
        model_lower = model.lower()
        if "claude" in model_lower:
            return 200_000
        if "gpt-4" in model_lower:
            return 128_000
        return 128_000


_COMPACT_SYSTEM = (
    "You are a context compactor. Summarise the following conversation history "
    "into a concise but complete summary that preserves:\n"
    "- Key facts, decisions, and user preferences\n"
    "- Tool call results and their outcomes\n"
    "- Any pending tasks or open questions\n"
    "- Important context the assistant needs to continue\n\n"
    "Be concise but don't lose critical information. Use bullet points."
)


class ContextCompactor:
    """Monitors context usage and compacts old messages when threshold is exceeded.

    Parameters:
        provider: LLM provider for generating summaries.
        model: Model to use (empty = same as main model).
        threshold: Fraction of context window that triggers compaction (0.0-1.0).
        keep_recent_turns: Never compact the last N user-assistant pairs.
        min_messages_to_compact: Don't bother if fewer messages than this.
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "",
        threshold: float = 0.75,
        keep_recent_turns: int = 6,
        min_messages_to_compact: int = 10,
    ) -> None:
        self._provider = provider
        self._model = model
        self._threshold = threshold
        self._keep_recent_turns = keep_recent_turns
        self._min_messages = min_messages_to_compact

    def should_compact(self, messages: list[dict[str, Any]], model: str) -> bool:
        """Check if messages exceed the threshold of the model's context window."""
        if len(messages) < self._min_messages:
            return False
        tokens = _messages_token_count(messages)
        window = _get_context_window(model)
        ratio = tokens / window
        if ratio >= self._threshold:
            logger.debug(
                "Context at {:.0%} ({}/{} tokens) — compaction needed",
                ratio, tokens, window,
            )
            return True
        return False

    async def compact(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> list[dict[str, Any]]:
        """Compact older messages into a summary, keeping system + recent turns.

        Returns a new message list (never mutates the input).
        """
        if len(messages) < self._min_messages:
            return list(messages)

        # Separate system message
        system_msg = messages[0] if messages and messages[0].get("role") == "system" else None
        body = messages[1:] if system_msg else list(messages)

        # Find split point: keep last N turn-pairs (user + assistant)
        keep_count = self._keep_recent_turns * 2  # each turn = user + assistant
        if len(body) <= keep_count:
            return list(messages)  # Nothing to compact

        old_messages = body[:-keep_count]
        recent_messages = body[-keep_count:]

        # Build summary text from old messages
        summary_input = self._format_for_summary(old_messages)
        if not summary_input.strip():
            return list(messages)

        try:
            summary_model = self._model or model
            response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": _COMPACT_SYSTEM},
                    {"role": "user", "content": summary_input},
                ],
                model=summary_model,
                temperature=0.0,
                max_tokens=2048,
            )
            summary_text = (response.content or "").strip()
            if not summary_text:
                return list(messages)
        except Exception as exc:
            logger.warning("Context compaction failed: {}", exc)
            return list(messages)

        # Build new message list
        compacted: list[dict[str, Any]] = []
        if system_msg:
            compacted.append(system_msg)
        compacted.append({
            "role": "user",
            "content": (
                f"[Context Summary — {len(old_messages)} earlier messages compacted]\n\n"
                f"{summary_text}"
            ),
        })
        compacted.append({
            "role": "assistant",
            "content": "Understood. I have the context summary and will continue from here.",
        })
        compacted.extend(recent_messages)

        old_tokens = _messages_token_count(messages)
        new_tokens = _messages_token_count(compacted)
        logger.info(
            "Context compacted: {} msgs → {} msgs, ~{} → ~{} tokens ({:.0%} reduction)",
            len(messages), len(compacted), old_tokens, new_tokens,
            1 - new_tokens / max(old_tokens, 1),
        )
        return compacted

    @staticmethod
    def _format_for_summary(messages: list[dict[str, Any]]) -> str:
        """Format messages into a readable text block for the summariser."""
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if not content:
                # Tool call message
                tool_calls = msg.get("tool_calls", [])
                if tool_calls:
                    names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                    content = f"[Called tools: {', '.join(names)}]"
                else:
                    continue
            # Truncate very long messages
            if isinstance(content, str) and len(content) > 2000:
                content = content[:2000] + "... (truncated)"
            parts.append(f"[{role}] {content}")
        return "\n\n".join(parts)
