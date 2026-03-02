"""Telegram message formatting utilities."""

from __future__ import annotations

import re


def _looks_like_html(text: str) -> bool:
    """Check if text already contains Telegram HTML tags."""
    return bool(re.search(r"</?(?:b|i|u|s|code|pre|a|tg-spoiler|blockquote)\b", text))


def _sanitize_html(text: str) -> str:
    """Escape non-Telegram HTML tags while preserving allowed ones."""
    # Telegram allowed tags
    allowed = r"(?:b|i|u|s|code|pre|a|tg-spoiler|blockquote|tg-emoji)"
    # Protect allowed tags
    protected: list[str] = []

    def save_tag(m: re.Match[str]) -> str:
        protected.append(m.group(0))
        return f"\x00TG{len(protected) - 1}\x00"

    text = re.sub(rf"</?{allowed}(?:\s[^>]*)?>", save_tag, text)

    # Escape everything else
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Restore allowed tags
    for i, tag in enumerate(protected):
        text = text.replace(f"\x00TG{i}\x00", tag)

    return text


def markdown_to_telegram_html(text: str) -> str:
    """Convert markdown to Telegram-safe HTML.

    If the text already contains Telegram HTML tags, sanitize and pass through.
    """
    if not text:
        return ""

    # If LLM already output HTML, just sanitize non-Telegram tags and return
    if _looks_like_html(text):
        return _sanitize_html(text)

    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []

    def save_code_block(m: re.Match[str]) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"

    text = re.sub(r"```[\w]*\n?([\s\S]*?)```", save_code_block, text)

    # 2. Extract and protect inline code
    inline_codes: list[str] = []

    def save_inline_code(m: re.Match[str]) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", save_inline_code, text)

    # 3. Headers # Title -> just the title text
    text = re.sub(r"^#{1,6}\s+(.+)$", r"\1", text, flags=re.MULTILINE)

    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r"^>\s*(.*)$", r"\1", text, flags=re.MULTILINE)

    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # 7. Bold **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<i>\1</i>", text)

    # 9. Strikethrough ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 10. Bullet lists - item -> bullet item
    text = re.sub(r"^[-*]\s+", "\u2022 ", text, flags=re.MULTILINE)

    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")

    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")

    return text


def split_message(
    content: str,
    max_len: int = 4000,
    mode: str = "newline",
) -> list[str]:
    """Split content into chunks within max_len.

    Args:
        content: Text to split.
        max_len: Maximum characters per chunk (Telegram limit is 4096).
        mode: ``"newline"`` prefers line-break boundaries (paragraph-aware);
              ``"length"`` does a hard cut at max_len.
    """
    if len(content) <= max_len:
        return [content]

    chunks: list[str] = []
    while content:
        if len(content) <= max_len:
            chunks.append(content)
            break

        cut = content[:max_len]

        if mode == "newline":
            # Prefer double-newline (paragraph), then single newline, then space
            pos = cut.rfind("\n\n")
            if pos == -1:
                pos = cut.rfind("\n")
            if pos == -1:
                pos = cut.rfind(" ")
            if pos == -1:
                pos = max_len
        else:
            # "length" mode: prefer newline, then space, then hard cut
            pos = cut.rfind("\n")
            if pos == -1:
                pos = cut.rfind(" ")
            if pos == -1:
                pos = max_len

        chunks.append(content[:pos])
        content = content[pos:].lstrip()

    return chunks
