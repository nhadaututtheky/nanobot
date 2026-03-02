"""Shared text utilities for message splitting and truncation."""

from __future__ import annotations


def split_message(
    content: str,
    max_len: int = 4000,
    mode: str = "newline",
) -> list[str]:
    """Split content into chunks within max_len.

    Args:
        content: Text to split.
        max_len: Maximum characters per chunk.
        mode: ``"newline"`` prefers paragraph boundaries (double newline);
              ``"length"`` prefers single newline then space.
    """
    if not content:
        return []
    if len(content) <= max_len:
        return [content]

    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break

        cut = content[:max_len]

        if mode == "newline":
            pos = cut.rfind("\n\n")
            if pos == -1:
                pos = cut.rfind("\n")
            if pos == -1:
                pos = cut.rfind(" ")
            if pos == -1:
                pos = max_len
        else:
            pos = cut.rfind("\n")
            if pos == -1:
                pos = cut.rfind(" ")
            if pos == -1:
                pos = max_len

        chunks.append(content[:pos])
        content = content[pos:].lstrip()

    return chunks
