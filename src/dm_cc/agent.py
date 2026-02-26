"""Agent - 支持多 Agent 和权限控制的实现"""

from dataclasses import dataclass, field
from typing import Any

from rich.console import Console
from rich.panel import Panel

from dm_cc.agents.config import AgentConfig, get_agent_config
from dm_cc.llm import get_llm, LLMResponse
from dm_cc.prompt import PromptBuilder
from dm_cc.session_logger import SessionLogger
from dm_cc.tools.base import Tool
from dm_cc.tools.edit import UserCancelledError
from dm_cc.tools import load_all_tools

console = Console()


@dataclass
class AgentContext:
    """Agent 执行上下文"""

    messages: list[dict[str, Any]] = field(default_factory=list)
    step: int = 0
    max_steps: int = 50  # 防止无限循环


class Agent:
    """Agent - 支持配置和权限控制

    用于:
    - 读取和理解代码
    - 编辑和修改文件
    - 运行命令
    - 完成软件工程任务

    支持通过 agent_name 切换不同角色（build, plan 等）。
    """

    def __init__(
        self,
        tools: list[Tool] | None = None,
        agent_name: str = "build",
    ):
        """初始化 Agent

        Args:
            tools: 可用工具列表，如果为 None 则根据 agent_name 加载
            agent_name: Agent 配置名称，默认 "build"
        """
        self.agent_name = agent_name
        self.config = get_agent_config(agent_name)

        # 加载并过滤工具
        all_tools = tools if tools is not None else load_all_tools()
        if isinstance(all_tools, dict):
            all_tools_dict = all_tools
        else:
            all_tools_dict = {t.name: t for t in all_tools}

        self.tools = self.config.filter_tools(all_tools_dict)
        self.tool_list = list(self.tools.values())

        self.prompt_builder = PromptBuilder()
        self.ctx = AgentContext()
        self.logger = SessionLogger()
        self._system_prompt: str | None = None

    def reset_session(self) -> None:
        """重置 session 状态（创建新的上下文和日志记录器）"""
        self.logger.close()
        self.ctx = AgentContext()
        self.logger = SessionLogger()
        self._system_prompt = None

    async def run(self, user_input: str) -> str:
        """运行 Agent 循环

        Args:
            user_input: 用户输入

        Returns:
            最终响应文本
        """
        # 首次运行时构建 system prompt
        if self._system_prompt is None:
            self._system_prompt = await self.prompt_builder.build(self.tool_list)
            self.logger.log_system_prompt(self._system_prompt)
            console.print(f"[dim]Agent started with {len(self.tools)} tools[/dim]")
            console.print()

        # 初始用户消息
        self.ctx.messages.append({"role": "user", "content": user_input})

        # 记录用户输入
        self.logger.log_user_input(user_input)

        while self.ctx.step < self.ctx.max_steps:
            self.ctx.step += 1

            # 开始新的循环日志
            self.logger.start_loop()
            console.print(f"[dim]Step {self.ctx.step}...[/dim]")

            # 记录给 LLM 的请求
            self.logger.log_llm_request(self.ctx.messages, self.tool_list, self._system_prompt)

            # 调用 LLM
            llm = await get_llm()
            response = await llm.complete(
                self.ctx.messages,
                self.tool_list,
                system_prompt=self._system_prompt,
            )

            # 记录 LLM 响应
            self.logger.log_llm_response(response)

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

                self.ctx.messages.append({"role": "assistant", "content": assistant_content})

                # 显示 AI 的思考
                if response.text:
                    console.print(Panel(response.text, title="Claude", border_style="blue"))

                # 执行工具
                tool_results = await self._execute_tools(response.tool_calls, self.logger)

                # 添加工具结果到消息
                for result in tool_results:
                    self.ctx.messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": result["tool_use_id"],
                            "content": result["content"],
                            "is_error": result.get("is_error", False),
                        }]
                    })

                continue  # 继续循环

            # 纯文本响应，任务完成
            self.logger.log_assistant_text(response.text)
            console.print(Panel(response.text, title="Claude", border_style="green"))
            return response.text

        return f"Reached max steps ({self.ctx.max_steps})"

    async def _execute_tools(
        self, tool_calls: list[Any], logger: SessionLogger
    ) -> list[dict[str, Any]]:
        """执行工具调用

        Args:
            tool_calls: LLM 返回的工具调用列表
            logger: 会话日志记录器

        Returns:
            工具执行结果列表
        """
        results = []

        for call in tool_calls:
            tool_name = call.name
            tool_input = call.input
            tool_id = call.id

            console.print(f"[dim]→ Tool: {tool_name}[/dim]")

            # 查找工具
            tool = self.tools.get(tool_name)
            if not tool:
                error_msg = f"Unknown tool: {tool_name}"
                console.print(Panel(error_msg, title=f"Error: {tool_name}", border_style="red"))
                logger.log_tool_execution(tool_name, tool_input, {"error": error_msg}, is_error=True)
                results.append({
                    "tool_use_id": tool_id,
                    "content": error_msg,
                    "is_error": True,
                })
                continue

            # 执行工具
            try:
                # 解析参数
                if tool.parameters:
                    params = tool.parameters.model_validate(tool_input)
                else:
                    params = None

                # 调用工具
                result = await tool.execute(params)
                output = result.get("output", "")

                # 显示结果
                console.print(Panel(output, title=f"Result: {tool_name}", border_style="green"))

                # 记录工具执行成功
                logger.log_tool_execution(tool_name, tool_input, result, is_error=False)

                results.append({
                    "tool_use_id": tool_id,
                    "content": output,
                    "is_error": False,
                })

            except UserCancelledError as e:
                # 用户取消操作
                error_msg = str(e)
                console.print(Panel(error_msg, title=f"Cancelled: {tool_name}", border_style="yellow"))

                logger.log_tool_execution(tool_name, tool_input, {"cancelled": error_msg}, is_error=True)

                results.append({
                    "tool_use_id": tool_id,
                    "content": error_msg,
                    "is_error": True,
                })

            except Exception as e:
                # 工具抛出异常表示错误
                error_msg = f"{type(e).__name__}: {e}"
                console.print(Panel(error_msg, title=f"Error: {tool_name}", border_style="red"))

                logger.log_tool_execution(tool_name, tool_input, {"error": error_msg}, is_error=True)

                results.append({
                    "tool_use_id": tool_id,
                    "content": error_msg,
                    "is_error": True,
                })

        return results
