"""Retry helper with exponential backoff for Telegram API calls."""

from __future__ import annotations

import asyncio
import random
from typing import Any, Awaitable, Callable, TypeVar

from loguru import logger

from nanobot.config.schema import TelegramRetryConfig

T = TypeVar("T")


class RetryHelper:
    """Execute async callables with exponential backoff and jitter."""

    def __init__(self, config: TelegramRetryConfig) -> None:
        self._cfg = config

    async def call(
        self,
        fn: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute *fn* with retry on failure.

        Handles Telegram ``RetryAfter`` exceptions by waiting the
        server-specified duration instead of the backoff formula.
        """
        last_exc: BaseException | None = None

        for attempt in range(self._cfg.attempts):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                last_exc = e

                if attempt == self._cfg.attempts - 1:
                    break

                # Telegram rate-limit: respect server retry_after
                retry_after = getattr(e, "retry_after", None)
                if retry_after is not None:
                    delay_s = float(retry_after)
                else:
                    delay_ms = min(
                        self._cfg.min_delay_ms * (2**attempt),
                        self._cfg.max_delay_ms,
                    )
                    if self._cfg.jitter:
                        delay_ms = random.randint(delay_ms // 2, delay_ms)
                    delay_s = delay_ms / 1000

                logger.warning(
                    "Telegram API call failed (attempt {}/{}): {}. Retrying in {:.1f}s",
                    attempt + 1,
                    self._cfg.attempts,
                    e,
                    delay_s,
                )
                await asyncio.sleep(delay_s)

        raise last_exc  # type: ignore[misc]
