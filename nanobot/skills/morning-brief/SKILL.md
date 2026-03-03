---
name: morning-brief
description: Daily personalized briefing with weather, news, and tasks.
metadata: {"nanobot":{"emoji":"☀️"}}
---

# Morning Brief

Compose a concise daily briefing for the user. Combine multiple data sources into one message.

## Steps

1. **Weather** — Use the weather skill (`curl -s "wttr.in/{location}?format=3"`) for current conditions.
2. **Pending tasks** — Check cron jobs (`cron_list`) for upcoming scheduled work.
3. **Recent activity** — Summarize last session's key topics (read from memory if available).
4. **News headlines** — Run a web search for top 3-5 headlines in the user's interest area (tech, AI, finance, etc.).

## Output Format

```
Good morning! Here's your brief for {date}:

Weather: {location} — {condition} {temp}
Tasks: {count} scheduled today
News:
  - {headline 1}
  - {headline 2}
  - {headline 3}

Have a great day!
```

## Scheduling

Set up via cron — example prompts the user might say:

- "Schedule a morning brief every day at 8am Vietnam time, deliver to telegram"
- "Give me a morning brief every weekday at 7:30am, send to discord"

The cron skill handles the scheduling; this skill defines what the brief contains.

## Tips

- Customize by telling the agent your interests: "Focus on AI and crypto news"
- Add calendar integration if available via MCP tools
- Keep it short — under 500 words for quick morning reading
