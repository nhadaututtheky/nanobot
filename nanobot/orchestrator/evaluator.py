"""Evaluate loop — generator-evaluator feedback cycle for orchestrator nodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from loguru import logger

if TYPE_CHECKING:
    from nanobot.orchestrator.models import TaskNode
    from nanobot.providers.base import LLMProvider


@dataclass(frozen=True)
class EvalResult:
    """Outcome of a single evaluation round."""

    passed: bool
    score: float  # 0.0 – 1.0
    feedback: str
    attempt: int


_EVAL_SYSTEM = (
    "You are a strict quality evaluator. Given a task description and its output, "
    "evaluate whether the output meets the requirements.\n\n"
    "Respond with ONLY a JSON object:\n"
    '{"pass": true/false, "score": 0.0-1.0, "feedback": "specific improvement suggestions"}\n\n'
    "Score guidelines:\n"
    "- 0.9-1.0: Excellent, meets all requirements\n"
    "- 0.7-0.89: Good, minor improvements possible\n"
    "- 0.5-0.69: Acceptable but needs work\n"
    "- Below 0.5: Does not meet requirements"
)


class TaskEvaluator:
    """Evaluates task node outputs and optionally runs a generate-evaluate loop.

    Parameters:
        provider: LLM provider for evaluation calls.
        model: Model to use for evaluation (empty = auto-select).
        threshold: Minimum score to pass (0.0-1.0).
        max_rounds: Maximum evaluate-regenerate rounds.
    """

    def __init__(
        self,
        provider: LLMProvider,
        model: str = "",
        threshold: float = 0.7,
        max_rounds: int = 3,
    ) -> None:
        self._provider = provider
        self._model = model
        self._threshold = threshold
        self._max_rounds = max_rounds

    async def evaluate(
        self,
        node: TaskNode,
        result: str,
        attempt: int = 1,
    ) -> EvalResult:
        """Evaluate a single result against the node's task description."""
        import json

        prompt = (
            f"## Task\n{node.description}\n\n"
            f"## Output (attempt {attempt})\n{result[:4000]}"
        )

        try:
            response = await self._provider.chat(
                messages=[
                    {"role": "system", "content": _EVAL_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                model=self._model or None,
                temperature=0.0,
                max_tokens=256,
            )

            text = (response.content or "").strip()
            # Strip markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(text)
            passed = bool(data.get("pass", False))
            score = float(data.get("score", 0.0))
            feedback = str(data.get("feedback", ""))

            # Override pass based on threshold
            if score >= self._threshold:
                passed = True

            return EvalResult(
                passed=passed,
                score=score,
                feedback=feedback,
                attempt=attempt,
            )

        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning("Evaluator parse error: {}", exc)
            return EvalResult(passed=True, score=0.8, feedback="Could not parse evaluation", attempt=attempt)
        except Exception as exc:
            logger.warning("Evaluator error: {}", exc)
            return EvalResult(passed=True, score=0.8, feedback=str(exc), attempt=attempt)

    async def evaluate_loop(
        self,
        node: TaskNode,
        generate_fn: Callable[..., Awaitable[str]],
        initial_result: str,
    ) -> tuple[str, EvalResult]:
        """Run generator-evaluator feedback loop.

        Args:
            node: The task node being evaluated.
            generate_fn: Async callable that regenerates output given feedback.
                         Signature: generate_fn(feedback: str) -> str
            initial_result: First generation result to evaluate.

        Returns:
            Tuple of (best_result, final_eval_result).
        """
        best_result = initial_result
        best_eval = EvalResult(passed=False, score=0.0, feedback="", attempt=0)

        for attempt in range(1, self._max_rounds + 1):
            result_to_eval = best_result if attempt == 1 else best_result

            eval_result = await self.evaluate(node, result_to_eval, attempt)
            logger.info(
                "Eval round {}/{} for node '{}': score={:.2f} passed={}",
                attempt, self._max_rounds, node.id, eval_result.score, eval_result.passed,
            )

            if eval_result.score > best_eval.score:
                best_eval = eval_result

            if eval_result.passed:
                return best_result, eval_result

            # Not passed — regenerate with feedback
            if attempt < self._max_rounds:
                logger.info("Regenerating node '{}' with feedback: {}", node.id, eval_result.feedback[:200])
                try:
                    best_result = await generate_fn(eval_result.feedback)
                except Exception as exc:
                    logger.warning("Regeneration failed for node '{}': {}", node.id, exc)
                    break

        # Return best result even if not passing
        return best_result, best_eval
