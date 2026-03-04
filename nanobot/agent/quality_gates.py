"""Quality gates — hook-based output validation for agent responses and orchestrator nodes."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from nanobot.config.schema import QualityGateConfig
    from nanobot.providers.base import LLMProvider


@dataclass(frozen=True)
class GateResult:
    """Outcome of a single quality-gate check."""

    gate_name: str
    passed: bool
    message: str


class QualityGateRunner:
    """Runs quality gates registered for specific events.

    Two gate types:
    - **shell**: Runs a shell command.  Exit-code 0 = pass, non-zero = fail.
      The command template may contain ``{output}`` which is replaced with
      the text to validate.
    - **reviewer**: Sends the output to an LLM with a structured pass/fail
      prompt.  The LLM must respond with a JSON ``{"pass": true/false, "reason": "..."}``.
    """

    def __init__(
        self,
        gates: list[QualityGateConfig],
        provider: LLMProvider | None = None,
        reviewer_model: str = "",
    ) -> None:
        self._gates = gates
        self._provider = provider
        self._reviewer_model = reviewer_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(self, event: str, context: dict[str, Any]) -> list[GateResult]:
        """Run all gates that match *event* against *context*.

        Args:
            event: Event name, e.g. ``"agent.response"`` or ``"node.completed"``.
            context: Must include ``"output"`` (the text to validate).

        Returns:
            List of :class:`GateResult` — one per matching gate.
        """
        matching = [g for g in self._gates if event in g.on_events]
        if not matching:
            return []

        output = context.get("output", "")
        results: list[GateResult] = []
        for gate in matching:
            try:
                if gate.gate_type == "shell":
                    result = await self._run_shell_gate(gate, output)
                elif gate.gate_type == "reviewer":
                    result = await self._run_reviewer_gate(gate, output)
                else:
                    result = GateResult(gate_name=gate.name, passed=True, message=f"Unknown type: {gate.gate_type}")
                results.append(result)
            except Exception as exc:
                logger.warning("Quality gate '{}' error: {}", gate.name, exc)
                results.append(GateResult(gate_name=gate.name, passed=not gate.blocking, message=str(exc)))

        return results

    def has_gates_for(self, event: str) -> bool:
        """Return True if any gate is registered for *event*."""
        return any(event in g.on_events for g in self._gates)

    # ------------------------------------------------------------------
    # Shell gate
    # ------------------------------------------------------------------

    async def _run_shell_gate(
        self, gate: "QualityGateConfig", output: str
    ) -> GateResult:
        """Run a shell command gate.  ``{output}`` in the command is replaced."""
        cmd = gate.command.replace("{output}", output[:2000])
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=gate.timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return GateResult(gate_name=gate.name, passed=False, message="Timed out")

        passed = proc.returncode == 0
        msg = (stdout or stderr or b"").decode(errors="replace").strip()[:500]
        return GateResult(gate_name=gate.name, passed=passed, message=msg)

    # ------------------------------------------------------------------
    # Reviewer gate (LLM-based)
    # ------------------------------------------------------------------

    async def _run_reviewer_gate(
        self, gate: "QualityGateConfig", output: str
    ) -> GateResult:
        """Send the output to an LLM reviewer with a structured pass/fail prompt."""
        if not self._provider:
            return GateResult(gate_name=gate.name, passed=True, message="No provider — skipped")

        prompt = gate.command.replace("{output}", output[:4000])
        system = (
            "You are a quality reviewer. Evaluate the following output and respond "
            'with ONLY a JSON object: {"pass": true, "reason": "..."} or '
            '{"pass": false, "reason": "..."}. No other text.'
        )

        import json

        response = await self._provider.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            model=self._reviewer_model or None,
            temperature=0.0,
            max_tokens=256,
        )

        text = (response.content or "").strip()
        # Strip markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        try:
            data = json.loads(text)
            passed = bool(data.get("pass", True))
            reason = str(data.get("reason", ""))
        except (json.JSONDecodeError, TypeError):
            passed = True
            reason = f"Could not parse reviewer response: {text[:200]}"

        return GateResult(gate_name=gate.name, passed=passed, message=reason)
