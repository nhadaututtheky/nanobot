"""Configuration loading utilities."""

import json
import secrets
from pathlib import Path

from loguru import logger

from nanobot.config.schema import Config


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".nanobot" / "config.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            config = Config.model_validate(data)
            _ensure_gateway_token(config, path)
            return config
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("Failed to load config from {}: {}", path, e)
            logger.warning("Using default configuration.")

    config = Config()
    _ensure_gateway_token(config, path)
    return config


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _ensure_gateway_token(config: Config, config_path: Path) -> None:
    """Generate a random gateway token if none is set, and persist it."""
    if config.gateway.token:
        return
    token = secrets.token_urlsafe(32)
    config.gateway.token = token
    logger.warning(
        "No gateway token configured — generated one automatically. "
        "Dashboard/clients must use this token to connect."
    )
    # Persist to config file so it survives restarts
    try:
        data: dict = {}
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        data.setdefault("gateway", {})["token"] = token
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Gateway token saved to {}", config_path)
    except Exception as e:
        logger.error("Failed to save gateway token to {}: {}", config_path, e)


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
