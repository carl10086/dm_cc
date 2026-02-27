"""Plan Enter Tool - 切换到 Plan Agent

参考 opencode: packages/opencode/src/tool/plan.ts L75-130

由 Build Agent 调用，建议切换到 Plan Mode 进行规划。
流程:
1. 询问用户确认
2. 创建 synthetic message (agent="plan")
3. 触发 agent 切换
"""

from pathlib import Path
from typing import Any
from pydantic import BaseModel
from rich.console import Console

from dm_cc.tools.base import Tool
from dm_cc.question import ask_user, UserCancelledError
from dm_cc.core.message import Message
from dm_cc.core.plan import get_plan_path, ensure_plan_dir

console = Console()

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "plan-enter.txt").read_text()


class EmptyParams(BaseModel):
    """无参数"""
    pass


class PlanEnterTool(Tool):
    """切换到 Plan Agent

    调用方式：由 Build Agent 在需要规划时调用
    效果：创建 synthetic message，agent="plan"，触发 agent 切换

    参考 opencode plan.ts L75-130
    """

    name = "plan_enter"
    description = _DESCRIPTION
    parameters = EmptyParams

    async def execute(self, params: EmptyParams) -> dict[str, Any]:
        """执行 plan_enter - 参考 opencode plan.ts L78-129"""

        # 确保 plan 目录存在
        ensure_plan_dir()
        plan_path = get_plan_path()
        display_path = Path(plan_path).relative_to(Path.cwd())

        # 1. 询问用户确认
        try:
            answer = await ask_user(
                question=f"Would you like to switch to the plan agent and create a plan saved to {display_path}?",
                options=[
                    ("Yes", "Switch to plan agent for research and planning"),
                    ("No", "Stay with build agent to continue making changes"),
                ],
                header="Plan Mode",
            )
        except UserCancelledError:
            return {
                "title": "Plan mode cancelled",
                "output": "User chose to stay with build agent.",
            }

        if answer == "No":
            return {
                "title": "Plan mode cancelled",
                "output": "User chose to stay with build agent.",
            }

        # 2. 创建 synthetic message 切换 agent
        # 参考 opencode plan.ts L104-114
        from dm_cc.agent import AgentContextStore

        message = Message.create_synthetic(
            agent="plan",
            content="User has requested to enter plan mode. Switch to plan mode and begin planning.",
        )

        # 3. 添加到当前 session
        AgentContextStore.add_message(message)

        # 4. 返回结果
        return {
            "title": "Switching to plan agent",
            "output": f"""User confirmed to switch to plan mode. A new message has been created to switch you to plan mode.

Plan file location: {plan_path}

You are now in plan mode. You can:
- Read and explore the codebase
- Write plans to the plan file
- Call plan_exit when ready to implement

Note: You cannot edit code files in plan mode.
""",
            "metadata": {
                "plan_path": plan_path,
                "new_agent": "plan",
            }
        }
