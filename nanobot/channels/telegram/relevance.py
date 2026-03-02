"""Relevance gate — lightweight LLM check for team bot response decisions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.channels.telegram.team_bus import TeamMessage
    from nanobot.config.schema import SubAgentRoleConfig, TelegramTeamGroupConfig
    from nanobot.providers.base import LLMProvider


@dataclass(frozen=True)
class RelevanceResult:
    """Result of a relevance check."""

    should_respond: bool
    confidence: float
    reason: str


_RELEVANCE_PROMPT = """\
You are the **{role_name}** ({description}) in a team of AI assistants sharing a Telegram group.

Your strengths: {strengths}
Your persona summary: {persona_short}

Team members who are ALREADY responding to this message: {already_claimed}

The user message:
---
{message}
---

Decide if YOU should respond. Consider:
1. Does this message match your expertise area?
2. Is another team member already handling it well?
3. Would your response add unique value that others cannot provide?
4. Is the user specifically asking for your kind of help?

Respond with ONLY this JSON (no markdown, no extra text):
{{"respond": true, "confidence": 0.85, "reason": "brief explanation"}}

Rules:
- confidence 0.0-1.0
- respond=true only if you have genuine expertise to contribute
- If the message is casual chat/greeting, respond=false unless you are the coordinator
- If another role already claimed it and can handle it well, respond=false
"""


class RelevanceGate:
    """Lightweight LLM call to decide if a role should respond to a message."""

    def __init__(
        self,
        provider: LLMProvider,
        config: TelegramTeamGroupConfig,
    ) -> None:
        self._provider = provider
        self._config = config

    async def check(
        self,
        role: str,
        role_config: SubAgentRoleConfig,
        message: TeamMessage,
        already_claimed: set[str],
    ) -> RelevanceResult:
        """Run a cheap LLM call to determine if this role should respond.

        Returns RelevanceResult with should_respond based on threshold.
        """
        prompt = _RELEVANCE_PROMPT.format(
            role_name=role_config.display_name or role,
            description=role_config.description or "general assistant",
            strengths=", ".join(role_config.strengths) if role_config.strengths else "general",
            persona_short=role_config.persona[:200] if role_config.persona else "helpful assistant",
            already_claimed=", ".join(already_claimed) if already_claimed else "none yet",
            message=message.content[:500],
        )

        try:
            model = self._config.relevance_model or self._pick_cheap_model()
            llm_response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Decide now."},
                ],
                model=model,
                max_tokens=100,
                temperature=0.1,
            )

            content = (llm_response.content or "").strip()
            # Strip markdown fences if present
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            parsed = json.loads(content)
            confidence = float(parsed.get("confidence", 0.0))
            should = bool(parsed.get("respond", False)) and confidence >= self._config.relevance_threshold
            reason = str(parsed.get("reason", ""))

            return RelevanceResult(
                should_respond=should,
                confidence=confidence,
                reason=reason,
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("RelevanceGate: failed to parse LLM response for {}: {}", role, e)
            return RelevanceResult(should_respond=False, confidence=0.0, reason=f"parse error: {e}")
        except Exception as e:
            logger.error("RelevanceGate: LLM call failed for {}: {}", role, e)
            return RelevanceResult(should_respond=False, confidence=0.0, reason=f"error: {e}")

    def _pick_cheap_model(self) -> str:
        """Pick the cheapest available model for relevance checks."""
        # Prefer haiku-class models for cost efficiency
        return "anthropic/claude-haiku-4-5-20251001"
