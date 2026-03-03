"""Configuration schema using Pydantic."""

from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_settings import BaseSettings

_T = TypeVar("_T", bound="Base")


class Base(BaseModel):
    """Base model that accepts both camelCase and snake_case keys."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def _merge_role_defaults(
    builtins: dict[str, dict[str, Any]],
    overrides: dict[str, _T],
    cls: type[_T],
) -> dict[str, _T]:
    """Merge builtin role defaults with user overrides.

    Pattern: builtin defaults → override non-falsy values on top → preserve list fields.
    """
    result: dict[str, _T] = {}

    for role_id, defaults in builtins.items():
        base = cls(**defaults)
        if role_id in overrides:
            override = overrides[role_id]
            merged = {
                **base.model_dump(),
                **{k: v for k, v in override.model_dump().items() if v},
            }
            merged["builtin"] = defaults.get("builtin", False)
            # Preserve list fields from override if non-empty
            for k, v in override.model_dump().items():
                if isinstance(v, list) and v:
                    merged[k] = v
            result[role_id] = cls(**merged)
        else:
            result[role_id] = base

    # Custom roles not in builtins
    for role_id, role_cfg in overrides.items():
        if role_id not in builtins:
            result[role_id] = role_cfg

    return result


class WhatsAppConfig(Base):
    """WhatsApp channel configuration."""

    enabled: bool = False
    bridge_url: str = "ws://localhost:3001"
    bridge_token: str = ""  # Shared token for bridge auth (optional, recommended)
    allow_from: list[str] = Field(default_factory=list)  # Allowed phone numbers


class TelegramRetryConfig(Base):
    """Retry with exponential backoff for Telegram API calls."""

    attempts: int = 3
    min_delay_ms: int = 500
    max_delay_ms: int = 10000
    jitter: bool = True


class TelegramDMConfig(Base):
    """DM access policy for Telegram."""

    mode: Literal["open", "allowlist", "disabled"] = "open"
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs (for allowlist mode)
    history_limit: int = 50


class TelegramGroupConfig(Base):
    """Per-group override config (keyed by chat_id string in groups dict)."""

    enabled: bool = True
    require_mention: bool = True  # If false, bot responds to all messages
    system_prompt: str = ""  # Injected system prompt for this group
    allow_from: list[str] = Field(default_factory=list)  # Per-group allowlist
    ignore_senders: list[str] = Field(
        default_factory=list
    )  # Sender name/username prefixes to ignore
    ignore_patterns: list[str] = Field(default_factory=list)  # Regex patterns on content to ignore
    history_limit: int = 100


class TelegramActionsConfig(Base):
    """Toggle Telegram bot actions on/off."""

    send_message: bool = True
    delete_message: bool = False
    set_reaction: bool = True


class RoleConfig(Base):
    """Shared role identity + LLM params — used by both SubagentManager and TeamRoleAgent."""

    model: str = ""  # empty = inherit from main agent
    display_name: str = ""
    description: str = ""
    persona: str = ""  # Extra system prompt (personality)
    icon: str = ""  # Emoji: "🔍", "💻"
    strengths: list[str] = Field(default_factory=list)
    builtin: bool = False  # True for default 4 (UI blocks deletion)
    temperature: float = 0.0  # 0 = inherit defaults
    max_tokens: int = 0  # 0 = inherit defaults


class SubAgentRoleConfig(RoleConfig):
    """Background sub-agent config — human-friendly presets for SubagentManager."""

    # Human-friendly presets (mapped to LLM params by SubagentManager)
    thinking_style: str = ""  # "creative" | "balanced" | "precise" → maps to temperature
    persistence: str = ""  # "quick" | "normal" | "thorough" → maps to max_iterations
    response_length: str = ""  # "brief" | "normal" | "detailed" → maps to max_tokens
    max_iterations: int = 0  # 0 = inherit defaults
    tool_profile: str = ""  # "minimal" | "coding" | "messaging" | "full"
    tools: list[str] = Field(default_factory=list)  # explicit tool whitelist (overrides profile)

    # Telegram identity (optional, for orchestrator multi-bot posting)
    telegram_bot_token: str = ""  # Bot token for this role (empty = use main bot)


class TeamRoleConfig(RoleConfig):
    """Telegram team bot config — raw LLM params + bot identity for TeamRoleAgent."""

    telegram_bot_token: str = ""  # Bot token for this role (required for team bots)
    allowed_tools: list[str] = Field(
        default_factory=list
    )  # fnmatch whitelist: ["nmem_*", "web_search", "exec"]
    denied_tools: list[str] = Field(default_factory=list)  # fnmatch blacklist: ["exec", "write_file"]


BUILTIN_ROLES: dict[str, dict] = {
    "general": {
        "display_name": "General",
        "icon": "🤖",
        "builtin": True,
        "description": "General-purpose agent with all tools",
        "strengths": ["versatile", "all tools"],
        "persona": (
            "Bạn là Jarvis — trợ lý AI đa năng. "
            "Giao tiếp bằng tiếng Việt có dấu, rõ ràng, thân thiện. "
            "Code, comments, biến: luôn dùng tiếng Anh. "
            "Phong cách: thực tế, đi thẳng vấn đề, không dài dòng. "
            "Khi cần sáng tạo thì đề xuất nhiều hướng. "
            "Luôn tóm tắt kết quả ở cuối response."
        ),
    },
    "researcher": {
        "display_name": "Researcher",
        "icon": "🔍",
        "builtin": True,
        "description": "Read-only research — web search, file reading, memory",
        "strengths": ["web research", "file analysis", "memory"],
        "tools": ["read_file", "list_dir", "web_search", "web_fetch"],
        "persona": (
            "Bạn là nhà nghiên cứu — tỉ mỉ, chính xác, có phương pháp. "
            "Giao tiếp bằng tiếng Việt có dấu. Code/thuật ngữ kỹ thuật: tiếng Anh. "
            "Phong cách: phân tích logic, trình bày có cấu trúc (bullet points, headings). "
            "Luôn ghi rõ nguồn thông tin. Khi không chắc chắn, nói rõ mức độ tin cậy. "
            "Tóm tắt findings ở cuối với key takeaways."
        ),
    },
    "coder": {
        "display_name": "Code Writer",
        "icon": "💻",
        "builtin": True,
        "description": "Code writing and execution — files, shell, web",
        "strengths": ["coding", "file editing", "shell"],
        "tools": [
            "read_file",
            "write_file",
            "edit_file",
            "list_dir",
            "exec",
            "web_search",
            "web_fetch",
        ],
        "persona": (
            "Bạn là lập trình viên senior — code clean, hiệu quả, có pattern. "
            "Giao tiếp bằng tiếng Việt có dấu. Code, comments, variable names: tiếng Anh. "
            "Phong cách: ngắn gọn, tập trung vào code. Giải thích khi logic phức tạp. "
            "Tuân thủ: immutability, type hints, error handling cụ thể, không print() production. "
            "Mỗi file < 500 LOC. Test khi cần. "
            "Tóm tắt thay đổi ở cuối: file nào, sửa gì, tại sao."
        ),
    },
    "reviewer": {
        "display_name": "Reviewer",
        "icon": "📋",
        "builtin": True,
        "description": "Read-only code and content analysis",
        "strengths": ["code review", "analysis"],
        "tools": ["read_file", "list_dir"],
        "persona": (
            "Bạn là code reviewer kỹ tính — mắt tinh, tiêu chuẩn cao. "
            "Giao tiếp bằng tiếng Việt có dấu. Thuật ngữ kỹ thuật: tiếng Anh. "
            "Phong cách: thẳng thắn, constructive. Phân loại issue: CRITICAL / HIGH / MEDIUM / LOW. "
            "Kiểm tra: security, performance, maintainability, edge cases, naming, immutability. "
            "Khen khi code tốt. Đề xuất fix cụ thể cho mỗi issue. "
            "Tóm tắt ở cuối: bao nhiêu issues theo severity, overall assessment."
        ),
    },
}


BUILTIN_TEAM_ROLES: dict[str, dict] = {
    role_id: {
        k: v
        for k, v in defaults.items()
        if k in ("display_name", "icon", "builtin", "description", "strengths", "persona")
    }
    for role_id, defaults in BUILTIN_ROLES.items()
}


class TelegramTeamGroupConfig(Base):
    """Config for a multi-bot team group where sub-agent bots act as team members."""

    enabled: bool = True
    chat_id: str = ""  # Telegram group chat ID
    roles: list[str] = Field(
        default_factory=list
    )  # Which roles participate (empty = all with tokens)
    coordinator_role: str = "general"  # Role that always responds to direct mentions
    relevance_model: str = ""  # Model for relevance check (empty = cheapest available)
    relevance_threshold: float = 0.6  # 0-1, how confident a role must be to speak
    max_concurrent_responses: int = 2  # Max roles responding to same message simultaneously
    cooldown_s: float = 10.0  # Min seconds between unsolicited responses per role
    dedup_window_s: float = 5.0  # Window to prevent duplicate responses to same message

    # Safety: allowlisted Telegram user IDs (empty = allow all — NOT recommended for exec)
    allowed_user_ids: list[str] = Field(default_factory=list)

    # Per-role team bot config (overrides BUILTIN_TEAM_ROLES defaults)
    team_roles: dict[str, TeamRoleConfig] = Field(default_factory=dict)

    def get_effective_team_roles(self) -> dict[str, TeamRoleConfig]:
        """Merge BUILTIN_TEAM_ROLES defaults with user overrides + custom roles."""
        return _merge_role_defaults(BUILTIN_TEAM_ROLES, self.team_roles, TeamRoleConfig)


class TelegramConfig(Base):
    """Telegram channel configuration."""

    # --- Existing (backward compatible) ---
    enabled: bool = False
    token: str = ""  # Bot token from @BotFather
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs or usernames
    proxy: str | None = (
        None  # HTTP/SOCKS5 proxy URL, e.g. "http://127.0.0.1:7890" or "socks5://127.0.0.1:1080"
    )
    reply_to_message: bool = False  # If true, bot replies quote the original message

    # --- Retry ---
    retry: TelegramRetryConfig = Field(default_factory=TelegramRetryConfig)

    # --- Access control ---
    dm: TelegramDMConfig = Field(default_factory=TelegramDMConfig)
    groups: dict[str, TelegramGroupConfig] = Field(default_factory=dict)
    actions: TelegramActionsConfig = Field(default_factory=TelegramActionsConfig)

    # --- Behavior ---
    ack_reaction: str = (
        ""  # Emoji to react with on processing start (e.g. "eyes"). Empty = disabled
    )
    link_preview: bool = True  # False → sends disable_web_page_preview=True
    response_prefix: str = ""  # Text prepended to every response
    chunk_mode: Literal["length", "newline"] = "newline"  # How to split long messages
    history_limit: int = 100  # Default history window

    # --- Streaming ---
    streaming: Literal["off", "draft", "edit"] = (
        "off"  # draft=sendMessageDraft, edit=edit_message_text
    )

    # --- Transport ---
    mode: Literal["polling", "webhook"] = "polling"
    webhook_url: str = ""  # HTTPS URL for webhook mode
    webhook_port: int = 8443
    webhook_path: str = "/telegram/webhook"
    allowed_updates: list[str] = Field(
        default_factory=lambda: ["message", "edited_message", "callback_query", "message_reaction"]
    )

    # --- Multi-bot team groups ---
    team_groups: dict[str, TelegramTeamGroupConfig] = Field(default_factory=dict)


class FeishuConfig(Base):
    """Feishu/Lark channel configuration using WebSocket long connection."""

    enabled: bool = False
    app_id: str = ""  # App ID from Feishu Open Platform
    app_secret: str = ""  # App Secret from Feishu Open Platform
    encrypt_key: str = ""  # Encrypt Key for event subscription (optional)
    verification_token: str = ""  # Verification Token for event subscription (optional)
    allow_from: list[str] = Field(default_factory=list)  # Allowed user open_ids
    react_emoji: str = (
        "THUMBSUP"  # Emoji type for message reactions (e.g. THUMBSUP, OK, DONE, SMILE)
    )


class DingTalkConfig(Base):
    """DingTalk channel configuration using Stream mode."""

    enabled: bool = False
    client_id: str = ""  # AppKey
    client_secret: str = ""  # AppSecret
    allow_from: list[str] = Field(default_factory=list)  # Allowed staff_ids


class DiscordConfig(Base):
    """Discord channel configuration."""

    enabled: bool = False
    token: str = ""  # Bot token from Discord Developer Portal
    allow_from: list[str] = Field(default_factory=list)  # Allowed user IDs
    gateway_url: str = "wss://gateway.discord.gg/?v=10&encoding=json"
    intents: int = 37377  # GUILDS + GUILD_MESSAGES + DIRECT_MESSAGES + MESSAGE_CONTENT


class MatrixConfig(Base):
    """Matrix (Element) channel configuration."""

    enabled: bool = False
    homeserver: str = "https://matrix.org"
    access_token: str = ""
    user_id: str = ""  # @bot:matrix.org
    device_id: str = ""
    e2ee_enabled: bool = True  # Enable Matrix E2EE support (encryption + encrypted room handling).
    sync_stop_grace_seconds: int = (
        2  # Max seconds to wait for sync_forever to stop gracefully before cancellation fallback.
    )
    max_media_bytes: int = (
        20 * 1024 * 1024
    )  # Max attachment size accepted for Matrix media handling (inbound + outbound).
    allow_from: list[str] = Field(default_factory=list)
    group_policy: Literal["open", "mention", "allowlist"] = "open"
    group_allow_from: list[str] = Field(default_factory=list)
    allow_room_mentions: bool = False


class EmailConfig(Base):
    """Email channel configuration (IMAP inbound + SMTP outbound)."""

    enabled: bool = False
    consent_granted: bool = False  # Explicit owner permission to access mailbox data

    # IMAP (receive)
    imap_host: str = ""
    imap_port: int = 993
    imap_username: str = ""
    imap_password: str = ""
    imap_mailbox: str = "INBOX"
    imap_use_ssl: bool = True

    # SMTP (send)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    from_address: str = ""

    # Behavior
    auto_reply_enabled: bool = (
        True  # If false, inbound email is read but no automatic reply is sent
    )
    poll_interval_seconds: int = 30
    mark_seen: bool = True
    max_body_chars: int = 12000
    subject_prefix: str = "Re: "
    allow_from: list[str] = Field(default_factory=list)  # Allowed sender email addresses


class MochatMentionConfig(Base):
    """Mochat mention behavior configuration."""

    require_in_groups: bool = False


class MochatGroupRule(Base):
    """Mochat per-group mention requirement."""

    require_mention: bool = False


class MochatConfig(Base):
    """Mochat channel configuration."""

    enabled: bool = False
    base_url: str = "https://mochat.io"
    socket_url: str = ""
    socket_path: str = "/socket.io"
    socket_disable_msgpack: bool = False
    socket_reconnect_delay_ms: int = 1000
    socket_max_reconnect_delay_ms: int = 10000
    socket_connect_timeout_ms: int = 10000
    refresh_interval_ms: int = 30000
    watch_timeout_ms: int = 25000
    watch_limit: int = 100
    retry_delay_ms: int = 500
    max_retry_attempts: int = 0  # 0 means unlimited retries
    claw_token: str = ""
    agent_user_id: str = ""
    sessions: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    allow_from: list[str] = Field(default_factory=list)
    mention: MochatMentionConfig = Field(default_factory=MochatMentionConfig)
    groups: dict[str, MochatGroupRule] = Field(default_factory=dict)
    reply_delay_mode: str = "non-mention"  # off | non-mention
    reply_delay_ms: int = 120000


class SlackDMConfig(Base):
    """Slack DM policy configuration."""

    enabled: bool = True
    policy: str = "open"  # "open" or "allowlist"
    allow_from: list[str] = Field(default_factory=list)  # Allowed Slack user IDs


class SlackConfig(Base):
    """Slack channel configuration."""

    enabled: bool = False
    mode: str = "socket"  # "socket" supported
    webhook_path: str = "/slack/events"
    bot_token: str = ""  # xoxb-...
    app_token: str = ""  # xapp-...
    user_token_read_only: bool = True
    reply_in_thread: bool = True
    react_emoji: str = "eyes"
    group_policy: str = "mention"  # "mention", "open", "allowlist"
    group_allow_from: list[str] = Field(default_factory=list)  # Allowed channel IDs if allowlist
    dm: SlackDMConfig = Field(default_factory=SlackDMConfig)


class QQConfig(Base):
    """QQ channel configuration using botpy SDK."""

    enabled: bool = False
    app_id: str = ""  # 机器人 ID (AppID) from q.qq.com
    secret: str = ""  # 机器人密钥 (AppSecret) from q.qq.com
    allow_from: list[str] = Field(
        default_factory=list
    )  # Allowed user openids (empty = public access)


class ZaloConfig(Base):
    """Zalo Official Account channel configuration."""

    enabled: bool = False
    app_id: str = ""  # Zalo app ID from developers.zalo.me
    app_secret: str = ""  # Zalo app secret
    access_token: str = ""  # OA access token (auto-refreshed at runtime)
    refresh_token: str = ""  # OA refresh token (single-use, 3-month lifetime)
    webhook_secret: str = ""  # X-Bot-Api-Secret-Token for webhook verification
    webhook_port: int = 8444  # Port for webhook HTTP server
    oa_id: str = ""  # Official Account ID
    allow_from: list[str] = Field(default_factory=list)  # Allowed Zalo user IDs


class TelegramUserbotConfig(Base):
    """Telegram userbot (Telethon MTProto) configuration for observing bot messages."""

    enabled: bool = False
    api_id: int = 0
    api_hash: str = ""
    phone: str = ""
    session_path: str = "~/.nanobot/telegram_userbot"
    observe_groups: list[str] = Field(default_factory=list)  # Chat IDs to observe (empty = all)
    ignore_senders: list[str] = Field(
        default_factory=list
    )  # Sender name/username prefixes to ignore (e.g. ["ray_"])
    ignore_patterns: list[str] = Field(default_factory=list)  # Regex patterns on content to ignore


class ChannelsConfig(Base):
    """Configuration for chat channels."""

    send_progress: bool = True  # stream agent's text progress to the channel
    send_tool_hints: bool = False  # stream tool-call hints (e.g. read_file("…"))
    whatsapp: WhatsAppConfig = Field(default_factory=WhatsAppConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    telegram_userbot: TelegramUserbotConfig = Field(default_factory=TelegramUserbotConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    feishu: FeishuConfig = Field(default_factory=FeishuConfig)
    mochat: MochatConfig = Field(default_factory=MochatConfig)
    dingtalk: DingTalkConfig = Field(default_factory=DingTalkConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)
    slack: SlackConfig = Field(default_factory=SlackConfig)
    qq: QQConfig = Field(default_factory=QQConfig)
    zalo: ZaloConfig = Field(default_factory=ZaloConfig)
    matrix: MatrixConfig = Field(default_factory=MatrixConfig)


class AgentDefaults(Base):
    """Default agent configuration."""

    workspace: str = "~/.nanobot/workspace"
    model: str = "anthropic/claude-opus-4-6"
    provider: str = (
        "auto"  # Provider name (e.g. "anthropic", "openrouter") or "auto" for auto-detection
    )
    max_tokens: int = 8192
    temperature: float = 0.1
    max_tool_iterations: int = 40
    memory_window: int = 100


class SubAgentConfig(Base):
    """Subagent system configuration."""

    enabled: bool = True
    default_max_iterations: int = 15
    default_temperature: float = 0.7
    default_max_tokens: int = 4096
    roles: dict[str, SubAgentRoleConfig] = Field(default_factory=dict)

    def get_effective_roles(self) -> dict[str, SubAgentRoleConfig]:
        """Merge BUILTIN_ROLES defaults with user overrides + custom roles."""
        return _merge_role_defaults(BUILTIN_ROLES, self.roles, SubAgentRoleConfig)


class ModelCapabilityConfig(Base):
    """User-configurable model capability entry for orchestrator routing."""

    model: str = ""  # e.g. "anthropic/claude-opus-4-6"
    provider: str = ""  # e.g. "anthropic"
    capabilities: list[str] = Field(default_factory=list)  # ["reasoning", "coding", ...]
    tier: str = "mid"  # "high" | "mid" | "low"
    cost_input: float = 0.0  # per 1K tokens
    cost_output: float = 0.0
    context_window: int = 128_000


class OrchestratorConfig(Base):
    """Task graph orchestrator configuration."""

    enabled: bool = True
    max_concurrent_graphs: int = 3
    default_task_timeout_s: int = 300
    max_tasks_per_graph: int = 20
    models: list[ModelCapabilityConfig] = Field(default_factory=list)

    # Telegram integration (multi-bot orchestrator)
    telegram_group_id: str = ""  # Chat ID where sub-agents post progress
    telegram_result_channel: str = ""  # Channel/chat ID for final summary
    telegram_progress_throttle_s: float = 20.0  # Min seconds between progress posts per node


class AgentsConfig(Base):
    """Agent configuration."""

    defaults: AgentDefaults = Field(default_factory=AgentDefaults)
    subagent: SubAgentConfig = Field(default_factory=SubAgentConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)


class ProviderConfig(Base):
    """LLM provider configuration."""

    api_key: str = ""
    api_base: str | None = None
    extra_headers: dict[str, str] | None = None  # Custom headers (e.g. APP-Code for AiHubMix)


class ProvidersConfig(Base):
    """Configuration for LLM providers."""

    custom: ProviderConfig = Field(default_factory=ProviderConfig)  # Any OpenAI-compatible endpoint
    anthropic: ProviderConfig = Field(default_factory=ProviderConfig)
    openai: ProviderConfig = Field(default_factory=ProviderConfig)
    openrouter: ProviderConfig = Field(default_factory=ProviderConfig)
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    groq: ProviderConfig = Field(default_factory=ProviderConfig)
    zhipu: ProviderConfig = Field(default_factory=ProviderConfig)
    dashscope: ProviderConfig = Field(default_factory=ProviderConfig)  # 阿里云通义千问
    vllm: ProviderConfig = Field(default_factory=ProviderConfig)
    gemini: ProviderConfig = Field(default_factory=ProviderConfig)
    moonshot: ProviderConfig = Field(default_factory=ProviderConfig)
    minimax: ProviderConfig = Field(default_factory=ProviderConfig)
    aihubmix: ProviderConfig = Field(default_factory=ProviderConfig)  # AiHubMix API gateway
    siliconflow: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # SiliconFlow (硅基流动) API gateway
    volcengine: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # VolcEngine (火山引擎) API gateway
    openai_codex: ProviderConfig = Field(default_factory=ProviderConfig)  # OpenAI Codex (OAuth)
    github_copilot: ProviderConfig = Field(default_factory=ProviderConfig)  # Github Copilot (OAuth)
    cli_proxy: ProviderConfig = Field(
        default_factory=ProviderConfig
    )  # CLI Proxy API (OpenAI-compatible local proxy)


class HeartbeatConfig(Base):
    """Heartbeat service configuration."""

    enabled: bool = True
    interval_s: int = 30 * 60  # 30 minutes


class AiGatewayConfig(Base):
    """AI Gateway (CLIProxyAPI) service configuration."""

    enabled: bool = False
    binary_path: str = ""  # Path to cli-proxy-api.exe
    config_path: str = ""  # Path to config.yaml (auto-created if missing)
    management_url: str = "http://localhost:8317/v0/management"
    proxy_url: str = "http://localhost:20128/v1"
    api_key: str = ""  # API key for CLI Proxy API (from config.yaml api-keys list)
    auto_start: bool = False  # Start AI Gateway automatically with NanoBot


class GatewayConfig(Base):
    """Gateway/server configuration."""

    host: str = "127.0.0.1"  # Default to localhost only — set "0.0.0.0" to expose to network
    port: int = 18790
    token: str = ""  # Auth token for WS clients (auto-generated on first run if empty)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    ai_gateway: AiGatewayConfig = Field(default_factory=AiGatewayConfig)


class WebSearchConfig(Base):
    """Web search tool configuration."""

    api_key: str = ""  # Brave Search API key
    max_results: int = 5


class WebToolsConfig(Base):
    """Web tools configuration."""

    search: WebSearchConfig = Field(default_factory=WebSearchConfig)


class ExecToolConfig(Base):
    """Shell exec tool configuration."""

    timeout: int = 60
    path_append: str = ""


class MCPServerConfig(Base):
    """MCP server connection configuration (stdio or HTTP)."""

    command: str = ""  # Stdio: command to run (e.g. "npx")
    args: list[str] = Field(default_factory=list)  # Stdio: command arguments
    env: dict[str, str] = Field(default_factory=dict)  # Stdio: extra env vars
    url: str = ""  # HTTP: streamable HTTP endpoint URL
    headers: dict[str, str] = Field(default_factory=dict)  # HTTP: Custom HTTP Headers
    tool_timeout: int = 30  # Seconds before a tool call is cancelled


class ToolsConfig(Base):
    """Tools configuration."""

    web: WebToolsConfig = Field(default_factory=WebToolsConfig)
    exec: ExecToolConfig = Field(default_factory=ExecToolConfig)
    restrict_to_workspace: bool = False  # If true, restrict all tool access to workspace directory
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class Config(BaseSettings):
    """Root configuration for nanobot."""

    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    channels: ChannelsConfig = Field(default_factory=ChannelsConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)

    @property
    def workspace_path(self) -> Path:
        """Get expanded workspace path."""
        return Path(self.agents.defaults.workspace).expanduser()

    def _match_provider(
        self, model: str | None = None
    ) -> tuple["ProviderConfig | None", str | None]:
        """Match provider config and its registry name. Returns (config, spec_name)."""
        from nanobot.providers.registry import PROVIDERS

        forced = self.agents.defaults.provider
        if forced != "auto":
            p = getattr(self.providers, forced, None)
            return (p, forced) if p else (None, None)

        model_lower = (model or self.agents.defaults.model).lower()
        model_normalized = model_lower.replace("-", "_")
        model_prefix = model_lower.split("/", 1)[0] if "/" in model_lower else ""
        normalized_prefix = model_prefix.replace("-", "_")

        def _kw_matches(kw: str) -> bool:
            kw = kw.lower()
            return kw in model_lower or kw.replace("-", "_") in model_normalized

        # Explicit provider prefix wins — prevents `github-copilot/...codex` matching openai_codex.
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if not isinstance(p, ProviderConfig):
                continue
            if p and model_prefix and normalized_prefix == spec.name:
                if spec.is_oauth or spec.is_direct or p.api_key:
                    return p, spec.name

        # Match by keyword (order follows PROVIDERS registry)
        for spec in PROVIDERS:
            p = getattr(self.providers, spec.name, None)
            if not isinstance(p, ProviderConfig):
                continue
            if p and any(_kw_matches(kw) for kw in spec.keywords):
                if spec.is_oauth or spec.is_direct or p.api_key:
                    return p, spec.name

        # Fallback: gateways first, then others (follows registry order)
        # OAuth and direct providers are NOT valid fallbacks — they require explicit selection
        for spec in PROVIDERS:
            if spec.is_oauth or spec.is_direct:
                continue
            p = getattr(self.providers, spec.name, None)
            if not isinstance(p, ProviderConfig):
                continue
            if p and p.api_key:
                return p, spec.name
        return None, None

    def get_provider(self, model: str | None = None) -> ProviderConfig | None:
        """Get matched provider config (api_key, api_base, extra_headers). Falls back to first available."""
        p, _ = self._match_provider(model)
        return p

    def get_provider_name(self, model: str | None = None) -> str | None:
        """Get the registry name of the matched provider (e.g. "deepseek", "openrouter")."""
        _, name = self._match_provider(model)
        return name

    def get_api_key(self, model: str | None = None) -> str | None:
        """Get API key for the given model. Falls back to first available key."""
        p = self.get_provider(model)
        return p.api_key if p else None

    def get_api_base(self, model: str | None = None) -> str | None:
        """Get API base URL for the given model. Applies default URLs for known gateways."""
        from nanobot.providers.registry import find_by_name

        p, name = self._match_provider(model)
        if p and p.api_base:
            return p.api_base
        # Only gateways get a default api_base here. Standard providers
        # (like Moonshot) set their base URL via env vars in _setup_env
        # to avoid polluting the global litellm.api_base.
        if name:
            spec = find_by_name(name)
            if spec and spec.is_gateway and spec.default_api_base:
                return spec.default_api_base
        return None

    model_config = ConfigDict(env_prefix="NANOBOT_", env_nested_delimiter="__")
