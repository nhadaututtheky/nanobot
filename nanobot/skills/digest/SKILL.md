---
name: digest
description: Curate and summarize news or content from web sources on any topic.
metadata: {"nanobot":{"emoji":"📰"}}
---

# News Digest

Research and summarize content from multiple web sources into a concise digest.

## Steps

1. **Search** — Run 2-3 web searches on the requested topic (use `web_search` tool).
2. **Evaluate** — Score each result for relevance and recency (prefer last 24h).
3. **Summarize** — Write a 1-2 sentence summary per item.
4. **Format** — Output as a numbered list with source attribution.

## Output Format

```
{Topic} Digest — {date}

1. {Headline} — {1-2 sentence summary}
   Source: {domain}

2. {Headline} — {1-2 sentence summary}
   Source: {domain}

3. {Headline} — {1-2 sentence summary}
   Source: {domain}

---
{count} items curated from {source_count} sources.
```

## Usage Examples

- "Give me a tech news digest"
- "Summarize AI research news from today"
- "Weekly crypto digest — top 5 stories"
- "Schedule a daily AI digest at 9am, deliver to telegram"

## Tips

- Default to 5 items unless the user specifies otherwise
- Always include the source domain for attribution
- Prefer primary sources over aggregators
- If using the summarize skill for long articles, link to the full source
