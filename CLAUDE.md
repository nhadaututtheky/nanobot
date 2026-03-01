# NanoBot — Claude Code Project Config

## Overview
NanoBot is a lightweight personal AI assistant framework and CLI launcher. It supports multiple AI providers (Claude CLI subprocess, LiteLLM, direct APIs) and multiple communication channels (Telegram, Slack, DingTalk, Feishu, WebSocket bridge). Config lives at `~/.nanobot/config.json`.

## Tech Stack
- **Language**: Python 3.12+
- **CLI**: Typer + Rich (entry: `nanobot.cli.commands:app`)
- **AI Provider**: LiteLLM + Claude CLI subprocess (node + cli.js)
- **Channels**: Telegram, Slack, DingTalk, Feishu, WebSocket bridge
- **Testing**: pytest + pytest-asyncio
- **Linting**: ruff (lint + format) + mypy (strict)
- **Package Manager**: pip + pyproject.toml (hatchling)

## Project Structure
```
nanobot/
  agent/      — Core agent loop
  bus/        — Internal message bus
  channels/   — Channel integrations (telegram, slack, etc.)
  cli/        — Typer CLI commands
  config/     — Config loading + pydantic-settings
  cron/       — Scheduled tasks
  gateway/    — API gateway / WebSocket bridge
  heartbeat/  — Health checks
  providers/  — AI provider adapters (claude_cli, litellm, etc.)
  session/    — Session management
  skills/     — Built-in skill definitions (.md + .sh)
  templates/  — Prompt templates (.md)
  utils/      — Shared utilities
tests/        — Test suite (mirrors nanobot/ structure)
bridge/       — Node.js WebSocket bridge
```

## Development Commands
```bash
# Install
pip install -e ".[dev]"

# Run
python -m nanobot

# Individual checks
ruff check nanobot/ tests/           # lint
ruff format --check nanobot/ tests/  # format check
mypy nanobot/ --ignore-missing-imports  # type check
pytest tests/ -v                     # tests
```

## Key Conventions

### Immutability (CRITICAL)
- Never mutate function parameters. Create new objects with `replace()` or `{**d, key: val}`.
- Core models are frozen dataclasses. Use `replace()` to derive new instances.
- No mutable default arguments.

### Type Safety
- ALL functions MUST have type hints.
- Use generic type params: `dict[str, Any]` not bare `dict`.
- CI must pass `mypy nanobot/` with 0 errors.
- No stale `# type: ignore` — use specific error codes.

### Error Handling
- Never bare `except: pass`. Always log or re-raise.
- Use specific exceptions with context messages.
- No `print()` in production — use `logger` (loguru).

### Claude CLI Subprocess (CRITICAL — project-specific)
- Use `node` + `cli.js` directly, NOT the npm shell wrapper (hangs on Windows).
- CLI path: `%APPDATA%/npm/node_modules/@anthropic-ai/claude-code/cli.js`
- Always pipe prompt via stdin (`proc.communicate(input=prompt.encode("utf-8"))`).
  - Do NOT pass prompt as CLI arg — hits Windows 32KB command line limit.
- Flags: `--model` (not `-m`), `--print`, `--permission-mode bypassPermissions`.
- Do NOT use `drain_stderr` + `proc.communicate()` together (race condition).

### Security
- Validate all paths with `Path.resolve()` + `is_relative_to()`.
- Never hardcode secrets — use env vars + pydantic-settings.
- Config at `~/.nanobot/config.json` — never commit real config.

### Testing
- Minimum coverage: 70% (enforced by CI).
- Test immutability: verify functions don't mutate inputs.
- Use `pytest-asyncio` with `asyncio_mode = "auto"`.

### Naming
- `snake_case` for functions/variables
- `PascalCase` for classes
- `SCREAMING_SNAKE_CASE` for constants
- `_private` prefix for internal functions

## Git Workflow
- Branch: `main` (production)
- Feature branches: `feat/{description}`
- Commit format: `type: description` (feat, fix, refactor, docs, test, chore)
- All changes via PR with at least 1 review
