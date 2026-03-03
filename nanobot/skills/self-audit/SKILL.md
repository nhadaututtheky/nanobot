---
name: self-audit
description: Agent health check — sessions, cron status, memory, and errors.
metadata: {"nanobot":{"emoji":"🔍"}}
---

# Self Audit

Perform a health check on the agent's state and report any anomalies.

## Checks

1. **Sessions** — Count active session files. Flag if > 150 (approaching 200 limit).
2. **Cron jobs** — List all jobs via `cron_list`. Flag any with `lastStatus: "error"`.
3. **Memory** — Check memory file sizes. Flag if MEMORY.md > 50KB or HISTORY.md > 500KB.
4. **Disk** — Check workspace directory size (sessions + cron + orchestrator).
5. **Errors** — Scan recent session messages for error patterns.

## Commands

```bash
# Session count
ls ~/.nanobot/workspace/sessions/*.jsonl 2>/dev/null | wc -l

# Workspace disk usage
du -sh ~/.nanobot/workspace/

# Memory file sizes
ls -lh ~/.nanobot/workspace/memory/MEMORY.md ~/.nanobot/workspace/memory/HISTORY.md 2>/dev/null
```

## Output Format

```
Agent Health Check — {date}

Sessions: {count}/200 ({status})
Cron jobs: {total} total, {errors} with errors
Memory: MEMORY.md {size}, HISTORY.md {size}
Workspace: {total_size}

{Issues found or "All systems nominal."}
```

## Scheduling

- "Schedule a self-audit every night at 11pm, deliver to telegram"
- "Run a self-audit now"

## Tips

- Run nightly to catch issues early
- If session count is high, old sessions may need cleanup
- If cron jobs show errors, check the job configuration
