"""Agent 核心循环 - 基于 opencode 的 loop 架构简化版"""

import json
from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from dm_cc.llm import get_llm, LLMResponse
from dm_cc.tools.base import Tool, ToolResult

console = Console()


@dataclass
class AgentContext:
    """Agent 执行上下文"""

    messages: list[dict[str, Any]] = field(default_factory=list)
    step: int = 0
    max_steps: int = 50  # 防止无限循环


class Agent:
    """Agent 核心"""

    def __init__(self, tools: list[Tool]):
        self.tools = {t.name: t for t in tools}
        self.tool_list = list(tools)

    async def run(self, user_input: str) -> str:
        """运行 Agent 循环"""
        ctx = AgentContext()

        # 初始用户消息
        ctx.messages.append({"role": "user", "content": user_input})

        console.print(f"[dim]Agent started with {len(self.tools)} tools[/dim]")
        console.print()

        while ctx.step < ctx.max_steps:
            ctx.step += 1
            console.print(f"[dim]Step {ctx.step}...[/dim]")

            # 调用 LLM
            llm = await get_llm()
            response = await llm.complete(ctx.messages, self.tool_list)

            # 处理工具调用
            if response.has_tool_calls:
                # 添加助手消息（包含工具调用）
                assistant_content = []
                if response.text:
                    assistant_content.append({"type": "text", "text": response.text})

                for tool_call in response.tool_calls:
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.name,
                        "input": tool_call.input,
                    })

                ctx.messages.append({"role": "assistant", "content": assistant_content})

                # 显示 AI 的思考
                if response.text:
                    console.print(Panel(response.text, title="Claude", border_style="blue"))

                # 执行工具
                tool_results = await self._execute_tools(response.tool_calls)

                # 添加工具结果到消息
                for result in tool_results:
                    ctx.messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": result["tool_use_id"],
                            "content": result["content"],
                        }]
                    })

                continue  # 继续循环

            # 纯文本响应，任务完成
            console.print(Panel(response.text, title="Claude", border_style="green"))
            return response.text

        return f"Reached max steps ({ctx.max_steps})"

    async def _execute_tools(
        self, tool_calls: list[Any]
    ) -> list[dict[str, str]]:
        """执行工具调用"""
        results = []

        for call in tool_calls:
            tool_name = call.name
            tool_input = call.input
            tool_id = call.id

            console.print(f"[dim]→ Tool: {tool_name}[/dim]")

            # 查找工具
            tool = self.tools.get(tool_name)
            if not tool:
                result = ToolResult.error(f"Unknown tool: {tool_name}")
            else:
                # 执行工具
                try:
                    # 解析参数
                    if tool.parameters:
                        params = tool.parameters.model_validate(tool_input)
                    else:
                        params = None

                    result = await tool.execute(params)
                except Exception as e:
                    result = ToolResult.error(f"{type(e).__name__}: {e}")

            # 显示结果
            if result.success:
                # 尝试检测是否为代码并高亮显示
                content = result.content
                console.print(Panel(content, title=f"Result: {tool_name}", border_style="green"))
            else:
                console.print(Panel(result.content, title=f"Error: {tool_name}", border_style="red"))

            results.append({
                "tool_use_id": tool_id,
                "content": result.content,
            })

        return results
