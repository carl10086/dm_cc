"""Agent - 支持多 Agent 切换和权限控制的实现

参考 opencode:
- packages/opencode/src/tool/plan.ts (plan_enter/plan_exit)
- packages/opencode/src/session/prompt.ts (insertReminders)

核心机制:
1. Message-based agent 切换：通过 synthetic message 的 agent 字段
2. System Reminder 注入：根据当前 agent 模式注入不同提醒
3. Plan 文件管理：Plan agent 只能编辑 plan 目录下的文件
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel

from dm_cc.agents.config import AgentConfig, get_agent_config
from dm_cc.llm import get_llm, LLMResponse
from dm_cc.prompt import PromptBuilder
from dm_cc.session_logger import SessionLogger
from dm_cc.tools.base import Tool
from dm_cc.tools.edit import UserCancelledError
from dm_cc.tools import load_all_tools
from dm_cc.core.message import Message
from dm_cc.core.reminders import (
    PLAN_MODE_REMINDER,
    BUILD_SWITCH_REMINDER,
    build_switch_with_plan,
)
from dm_cc.core.plan import read_latest_plan, is_plan_file, get_plan_dir

console = Console()


@dataclass
class AgentContext:
    """Agent 执行上下文"""

    messages: list[Message] = field(default_factory=list)
    step: int = 0
    max_steps: int = 50  # 防止无限循环


class AgentContextStore:
    """全局 Agent 上下文存储

    用于工具（如 plan_enter, plan_exit）访问和修改当前 session。
    参考 opencode 的 ctx.sessionID 模式。
    """

    _current_context: Optional[AgentContext] = None
    _current_agent: Optional[Agent] = None
    _pending_messages: list[Message] = []

    @classmethod
    def set_context(cls, context: AgentContext, agent: "Agent") -> None:
        """设置当前上下文"""
        cls._current_context = context
        cls._current_agent = agent
        cls._pending_messages = []

    @classmethod
    def clear_context(cls) -> None:
        """清除上下文"""
        cls._current_context = None
        cls._current_agent = None
        cls._pending_messages = []

    @classmethod
    def get_context(cls) -> Optional[AgentContext]:
        """获取当前上下文"""
        return cls._current_context

    @classmethod
    def add_message(cls, message: Message) -> None:
        """添加消息到 pending 列表

        由 plan_enter/plan_exit 调用以触发 agent 切换。
        消息会在 tool results 之后添加到上下文，确保消息顺序正确。
        """
        cls._pending_messages.append(message)
        if cls._current_agent:
            # 标记需要切换 agent
            cls._current_agent._pending_agent_switch = message.agent

    @classmethod
    def get_and_clear_pending_messages(cls) -> list[Message]:
        """获取并清除 pending messages"""
        messages = cls._pending_messages
        cls._pending_messages = []
        return messages


class Agent:
    """Agent - 支持配置、权限控制和 Agent 切换

    用于:
    - 读取和理解代码
    - 编辑和修改文件
    - 运行命令
    - 完成软件工程任务
    - Plan/Build Agent 自动切换

    支持通过 message.agent 字段切换不同角色（build, plan 等）。
    参考 opencode plan.ts 的 message-based 切换机制。
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

        # Agent 切换状态
        self._pending_agent_switch: str | None = None
        self._was_plan_mode: bool = False

    def reset_session(self) -> None:
        """重置 session 状态（创建新的上下文和日志记录器）"""
        self.logger.close()
        self.ctx = AgentContext()
        self.logger = SessionLogger()
        self._system_prompt = None
        self._pending_agent_switch = None
        self._was_plan_mode = False

    def _detect_target_agent(self) -> str:
        """从最新消息中检测目标 Agent

        参考 opencode: 查找最后一条消息的 agent 字段

        Returns:
            目标 agent 名称
        """
        # 优先检查 pending messages（如果有 synthetic message 待添加）
        pending = AgentContextStore.get_and_clear_pending_messages()
        if pending:
            # 将 pending messages 添加到上下文中
            for msg in pending:
                self.ctx.messages.append(msg)
            # 返回最后一条 synthetic message 的 agent
            return pending[-1].agent

        # 否则检查现有消息
        for msg in reversed(self.ctx.messages):
            if hasattr(msg, 'agent') and msg.agent:
                return msg.agent
        return "build"  # 默认 build

    def _switch_agent(self, new_agent: str) -> None:
        """切换到新 Agent

        Args:
            new_agent: 新 agent 名称
        """
        if new_agent == self.agent_name:
            return

        # 记录是否从 plan 模式切换
        if self.agent_name == "plan":
            self._was_plan_mode = True

        console.print(f"[dim]Switching from {self.agent_name} to {new_agent} agent...[/dim]")

        self.agent_name = new_agent
        self.config = get_agent_config(new_agent)

        # 重新过滤工具
        all_tools = load_all_tools()
        self.tools = self.config.filter_tools(all_tools)
        self.tool_list = list(self.tools.values())

        # 清除 system prompt 缓存，将重新构建
        self._system_prompt = None

        console.print(f"[green]Now using {new_agent} agent with {len(self.tools)} tools[/green]")

    def _build_system_prompt(self) -> str:
        """构建系统提示 - 包含 agent-specific reminder

        参考 opencode insertReminders:
        - Plan 模式: 注入 PLAN_MODE_REMINDER
        - Build 从 Plan 切换: 注入 BUILD_SWITCH_REMINDER + plan 内容

        Returns:
            完整的 system prompt
        """
        base_prompt = self.config.system_prompt
        reminders = []

        # Plan 模式提醒
        if self.agent_name == "plan":
            reminders.append(PLAN_MODE_REMINDER)

        # 从 Plan 切换回 Build 的提醒
        elif self._was_plan_mode:
            # 读取 plan 文件内容
            plan_result = read_latest_plan()
            if plan_result:
                plan_path, plan_content = plan_result
                reminders.append(build_switch_with_plan(plan_content, plan_path))
            else:
                reminders.append(BUILD_SWITCH_REMINDER)
            # 重置标志
            self._was_plan_mode = False

        if reminders:
            base_prompt = base_prompt + "\n\n" + "\n\n".join(reminders)

        return base_prompt

    async def run(self, user_input: str) -> str:
        """运行 Agent 循环 - 支持 Agent 切换

        Args:
            user_input: 用户输入

        Returns:
            最终响应文本
        """
        # 注册上下文到全局存储（供工具使用）
        AgentContextStore.set_context(self.ctx, self)
        try:
            return await self._run_loop(user_input)
        finally:
            AgentContextStore.clear_context()

    async def _run_loop(self, user_input: str) -> str:
        """内部运行循环"""
        # 首次运行时构建 system prompt
        if self._system_prompt is None:
            self._system_prompt = await self.prompt_builder.build(
                self.tool_list,
                extra_prompt=self._build_system_prompt()
            )
            self.logger.log_system_prompt(self._system_prompt)
            console.print(f"[dim]Agent started with {len(self.tools)} tools[/dim]")
            console.print()

        # 添加用户消息
        user_message = Message(
            role="user",
            content=user_input,
            agent=self.agent_name,  # 标记当前 agent
        )
        self.ctx.messages.append(user_message)

        # 记录用户输入
        self.logger.log_user_input(user_input)

        while self.ctx.step < self.ctx.max_steps:
            self.ctx.step += 1

            # 检查是否有待处理的 agent 切换
            if self._pending_agent_switch:
                self._switch_agent(self._pending_agent_switch)
                self._pending_agent_switch = None

            # 检查消息中的 agent 字段是否变化
            target_agent = self._detect_target_agent()
            if target_agent != self.agent_name:
                self._switch_agent(target_agent)
                # 重新构建 system prompt
                self._system_prompt = await self.prompt_builder.build(
                    self.tool_list,
                    extra_prompt=self._build_system_prompt()
                )

            # 开始新的循环日志
            self.logger.start_loop()
            console.print(f"[dim]Step {self.ctx.step} ({self.agent_name})...[/dim]")

            # 转换为 Anthropic 格式的消息
            anthropic_messages = [msg.to_anthropic_format() for msg in self.ctx.messages]

            # 记录给 LLM 的请求
            self.logger.log_llm_request(anthropic_messages, self.tool_list, self._system_prompt)

            # 调用 LLM
            llm = await get_llm()
            response = await llm.complete(
                anthropic_messages,
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

                assistant_message = Message(
                    role="assistant",
                    content=assistant_content,
                    agent=self.agent_name,
                )
                self.ctx.messages.append(assistant_message)

                # 显示 AI 的思考
                if response.text:
                    console.print(Panel(response.text, title="Claude", border_style="blue"))

                # 执行工具
                tool_results = await self._execute_tools(response.tool_calls, self.logger)

                # 添加工具结果到消息
                for result in tool_results:
                    tool_result_message = Message(
                        role="user",
                        content=[{
                            "type": "tool_result",
                            "tool_use_id": result["tool_use_id"],
                            "content": result["content"],
                            "is_error": result.get("is_error", False),
                        }],
                        agent=self.agent_name,
                    )
                    self.ctx.messages.append(tool_result_message)

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
                # Plan 模式权限检查：不能编辑非 plan 文件
                if self.agent_name == "plan" and tool_name in ("write", "edit"):
                    file_path = tool_input.get("filePath", "")
                    if file_path and not is_plan_file(file_path):
                        raise PermissionError(
                            f"Plan agent can only edit plan files in the plan directory. "
                            f"Attempted to edit: {file_path}\n"
                            f"Plan directory: {get_plan_dir()}"
                        )

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

            except PermissionError as e:
                # 权限错误
                error_msg = str(e)
                console.print(Panel(error_msg, title=f"Permission Denied: {tool_name}", border_style="red"))

                logger.log_tool_execution(tool_name, tool_input, {"permission_error": error_msg}, is_error=True)

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
