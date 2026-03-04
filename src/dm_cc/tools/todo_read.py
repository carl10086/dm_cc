"""Todo Read Tool - 读取当前会话的 Todo 列表

参考 opencode: packages/opencode/src/tool/todo.ts
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from dm_cc.tools.base import Tool
from dm_cc.core.todo import TodoStore

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "todo-read.txt").read_text()


class TodoReadTool(Tool):
    """读取 Todo 列表的工具

    无参数，返回当前会话的所有 todo 项。

    参考 opencode TodoReadTool
    """

    name = "todo_read"
    description = _DESCRIPTION
    parameters = None  # 无参数

    async def execute(self, params: BaseModel | None) -> dict[str, Any]:
        """执行 todo_read

        需要 session_id 从上下文中获取。

        Returns:
            dict with title, output, metadata (todos)
        """
        # 从 AgentContextStore 获取当前 session
        from dm_cc.agent import AgentContextStore

        agent = AgentContextStore._current_agent
        if not agent:
            # 没有上下文时使用临时存储
            return {
                "title": "No active session",
                "output": "No active session found. Todos are session-specific.",
                "metadata": {"todos": []},
            }

        # 使用 logger 的 session_id 作为唯一标识
        session_id = agent.logger.session_id
        store = TodoStore(session_id)
        todos = store.get_all()

        # 格式化输出
        if not todos:
            output = "No todos found. Create some with todo_write tool."
        else:
            lines = []
            for i, todo in enumerate(todos, 1):
                status_icon = {
                    "completed": "✓",
                    "in_progress": "•",
                    "pending": " ",
                    "cancelled": "✗",
                }.get(todo.status, " ")

                priority_icon = {
                    "high": "🔴",
                    "medium": "🟡",
                    "low": "🟢",
                }.get(todo.priority, "⚪")

                lines.append(f"{i}. [{status_icon}] {priority_icon} {todo.content} ({todo.status})")

            pending_count = len([t for t in todos if t.status != "completed"])
            lines.append(f"\n{pending_count} pending / {len(todos)} total")
            output = "\n".join(lines)

        return {
            "title": f"{len([t for t in todos if t.status != 'completed'])} todos",
            "output": output,
            "metadata": {
                "todos": [todo.to_dict() for todo in todos],
                "count": len(todos),
                "pending": len([t for t in todos if t.status != "completed"]),
            },
        }
