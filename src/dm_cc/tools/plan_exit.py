"""Plan Exit Tool - 切换回 Build Agent

参考 opencode: packages/opencode/src/tool/plan.ts L20-73

由 Plan Agent 调用，完成规划后切换回 Build Agent。
流程:
1. 检查 plan 文件是否存在
2. 询问用户确认
3. 创建 synthetic message (agent="build")
4. 触发 agent 切换
"""

from pathlib import Path
from typing import Any
from pydantic import BaseModel
from rich.console import Console

from dm_cc.tools.base import Tool
from dm_cc.question import ask_user, UserCancelledError
from dm_cc.core.message import Message
from dm_cc.core.plan import get_plan_dir, read_latest_plan

console = Console()

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "plan-exit.txt").read_text()


class EmptyParams(BaseModel):
    """无参数"""
    pass


class PlanExitTool(Tool):
    """完成规划，切换回 Build Agent

    调用方式：由 Plan Agent 在完成规划后调用
    效果：创建 synthetic message，agent="build"，触发 agent 切换

    参考 opencode plan.ts L20-73
    """

    name = "plan_exit"
    description = _DESCRIPTION
    parameters = EmptyParams

    async def execute(self, params: EmptyParams) -> dict[str, Any]:
        """执行 plan_exit - 参考 opencode plan.ts L23-72"""

        # 1. 检查 plan 文件
        plan_result = read_latest_plan()
        plan_path_str = plan_result[0] if plan_result else "<no plan file>"
        display_path = "<no plan file>"
        if plan_result:
            try:
                display_path = str(Path(plan_path_str).relative_to(Path.cwd()))
            except ValueError:
                display_path = plan_path_str

        # 2. 询问用户确认
        try:
            answer = await ask_user(
                question=f"Plan at {display_path} is complete. Would you like to switch to the build agent and start implementing?",
                options=[
                    ("Yes", "Switch to build agent and start implementing the plan"),
                    ("No", "Stay with plan agent to continue refining the plan"),
                ],
                header="Build Agent",
            )
        except UserCancelledError:
            raise UserCancelledError("User chose to continue refining the plan")

        if answer == "No":
            raise UserCancelledError("User chose to continue refining the plan")

        # 3. 创建 synthetic message 切换回 build
        # 参考 opencode plan.ts L47-57
        from dm_cc.agent import AgentContextStore

        message = Message.create_synthetic(
            agent="build",
            content=f"The plan at {plan_path_str} has been approved, you can now edit files. Execute the plan",
        )

        # 4. 添加到当前 session
        AgentContextStore.add_message(message)

        return {
            "title": "Switching to build agent",
            "output": """User approved switching to build agent. Wait for further instructions.

You can now edit files and execute the plan.
""",
            "metadata": {
                "plan_path": plan_path_str,
                "new_agent": "build",
            }
        }
