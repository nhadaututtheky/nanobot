"""Tool registry for dynamic tool management."""

from fnmatch import fnmatch
from typing import Any

from nanobot.agent.tools.base import Tool


class ToolRegistry:
    """
    Registry for agent tools.

    Allows dynamic registration and execution of tools.
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_definitions(
        self,
        allowed: list[str] | None = None,
        denied: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Get tool definitions in OpenAI format, optionally filtered.

        Args:
            allowed: fnmatch whitelist — if non-empty, only matching tools are included.
            denied: fnmatch blacklist — matching tools are excluded.
        """
        filtered: list[Tool] = list(self._tools.values())
        if allowed:
            filtered = [t for t in filtered if any(fnmatch(t.name, p) for p in allowed)]
        if denied:
            filtered = [t for t in filtered if not any(fnmatch(t.name, p) for p in denied)]
        return [t.to_schema() for t in filtered]

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        """Execute a tool by name with given parameters."""
        hint = "\n\n[Analyze the error above and try a different approach.]"

        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"

        try:
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors) + hint
            result = await tool.execute(**params)
            if isinstance(result, str) and result.startswith("Error"):
                return result + hint
            return result
        except Exception as e:
            return f"Error executing {name}: {str(e)}" + hint

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
