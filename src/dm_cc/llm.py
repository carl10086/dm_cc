"""LLM 接口 - Anthropic 封装"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from anthropic import AsyncAnthropic
from anthropic.types import Message, TextBlock, ToolUseBlock

from dm_cc.config import get_api_key, settings

if TYPE_CHECKING:
    from dm_cc.tools.base import Tool


@dataclass
class LLMResponse:
    """LLM 响应封装"""

    text: str = ""
    tool_calls: list[ToolUseBlock] | None = None
    stop_reason: str | None = None
    raw: Message | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls and len(self.tool_calls) > 0)


class AnthropicClient:
    """Anthropic API 客户端"""

    def __init__(self) -> None:
        self.client = AsyncAnthropic(api_key=get_api_key())
        self.model = settings.anthropic_model
        self.max_tokens = settings.anthropic_max_tokens

    def _build_system_prompt(self, tools: list["Tool"]) -> str:
        """构建 System Prompt"""
        tool_list = "\n".join([f"- {t.name}: {t.description}" for t in tools])

        return f"""You are dm_cc, a coding assistant powered by Claude.

Your task is to help users with software engineering tasks through an interactive terminal interface.

## Available Tools

You have access to the following tools:
{tool_list}

## Guidelines

1. Think step by step before taking action
2. Use tools to explore and understand the codebase
3. Read files before editing them
4. Explain what you're doing before making changes
5. Verify your changes work correctly

## Tool Usage

- Use `read` to examine files
- Use `glob` to find files matching patterns
- Use `edit` to modify files
- Use `bash` to run commands

When you need to take action, use the appropriate tool. The system will execute it and return the result to you.
"""

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list["Tool"],
    ) -> LLMResponse:
        """调用 LLM 完成对话"""

        # 转换工具为 Anthropic 格式
        tool_schemas = [t.to_anthropic_schema() for t in tools]

        # 调用 API
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=self._build_system_prompt(tools),
            messages=messages,  # type: ignore
            tools=tool_schemas,  # type: ignore
        )

        # 解析响应
        text_parts = []
        tool_calls = []

        for block in response.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tool_calls.append(block)

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls if tool_calls else None,
            stop_reason=response.stop_reason,
            raw=response,
        )


# 全局客户端实例
_llm_client: AnthropicClient | None = None


async def get_llm() -> AnthropicClient:
    """获取 LLM 客户端（单例）"""
    global _llm_client
    if _llm_client is None:
        _llm_client = AnthropicClient()
    return _llm_client
