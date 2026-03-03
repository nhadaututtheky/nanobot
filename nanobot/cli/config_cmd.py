"""CLI commands for config validation and inspection."""

import json
from typing import Any

import typer
from rich.console import Console

config_app = typer.Typer(help="Configuration management commands.")
console = Console()


def _mask_secret(value: str) -> str:
    """Mask a secret string, showing only first 4 chars."""
    if not value or len(value) <= 4:
        return "***"
    return f"{value[:4]}***"


def _collect_secrets(data: dict[str, Any], path: str = "") -> dict[str, Any]:
    """Recursively mask secret-like fields in a config dict (returns new dict)."""
    secret_keys = {
        "api_key",
        "apiKey",
        "token",
        "secret",
        "password",
        "app_secret",
        "appSecret",
        "api_hash",
        "apiHash",
        "access_token",
        "accessToken",
        "refresh_token",
        "refreshToken",
        "webhook_secret",
        "webhookSecret",
        "encrypt_key",
        "encryptKey",
        "client_secret",
        "clientSecret",
        "bot_token",
        "botToken",
        "bridge_token",
        "bridgeToken",
        "imap_password",
        "imapPassword",
        "smtp_password",
        "smtpPassword",
        "claw_token",
        "clawToken",
        "telegram_bot_token",
        "telegramBotToken",
    }

    result: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, dict):
            result[key] = _collect_secrets(value, f"{path}.{key}")
        elif isinstance(value, list):
            result[key] = [
                _collect_secrets(item, f"{path}.{key}[]") if isinstance(item, dict) else item
                for item in value
            ]
        elif isinstance(value, str) and value and key in secret_keys:
            result[key] = _mask_secret(value)
        else:
            result[key] = value
    return result


@config_app.command("validate")
def validate(
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Validate the nanobot configuration file."""
    from pydantic import ValidationError

    from nanobot.config.loader import get_config_path

    config_path = get_config_path()

    if not config_path.exists():
        if as_json:
            typer.echo(
                json.dumps(
                    {"valid": False, "errors": [{"msg": f"Config file not found: {config_path}"}]}
                )
            )
        else:
            console.print(f"[red]Config file not found:[/red] {config_path}")
            console.print("Run [cyan]nanobot onboard[/cyan] to create one.")
        raise typer.Exit(1)

    # Try loading raw JSON first
    try:
        with open(config_path, encoding="utf-8") as f:
            raw = json.load(f)
    except json.JSONDecodeError as e:
        if as_json:
            typer.echo(json.dumps({"valid": False, "errors": [{"msg": f"Invalid JSON: {e}"}]}))
        else:
            console.print(f"[red]Invalid JSON in config file:[/red] {e}")
        raise typer.Exit(1)

    # Validate with pydantic
    from nanobot.config.schema import Config

    try:
        Config.model_validate(raw)
    except ValidationError as e:
        errors = [
            {"loc": ".".join(str(x) for x in err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in e.errors()
        ]
        if as_json:
            typer.echo(json.dumps({"valid": False, "errors": errors}, indent=2))
        else:
            console.print(f"[red]Config validation failed ({len(errors)} error(s)):[/red]\n")
            for err in errors:
                console.print(f"  [yellow]{err['loc']}[/yellow]: {err['msg']}")
        raise typer.Exit(1)

    if as_json:
        typer.echo(json.dumps({"valid": True, "errors": []}))
    else:
        console.print(f"[green]Config is valid[/green] ({config_path})")


@config_app.command("show")
def show(
    as_json: bool = typer.Option(False, "--json", help="Output as raw JSON"),
) -> None:
    """Show current config with secrets masked."""
    from nanobot.config.loader import load_config

    config = load_config()
    data = config.model_dump(by_alias=True)
    masked = _collect_secrets(data)

    if as_json:
        typer.echo(json.dumps(masked, indent=2, ensure_ascii=False))
    else:
        from rich.syntax import Syntax

        formatted = json.dumps(masked, indent=2, ensure_ascii=False)
        syntax = Syntax(formatted, "json", theme="monokai", line_numbers=False)
        console.print(syntax)
