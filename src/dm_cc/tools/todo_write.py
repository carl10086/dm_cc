"""Todo Write Tool - 更新当前会话的 Todo 列表

参考 opencode: packages/opencode/src/tool/todo.ts

核心设计:
- 全量更新: 传入完整的 todo 列表，不是增量更新
- 替换策略: 先删除旧列表，再写入新列表
"""

from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field

from dm_cc.tools.base import Tool
from dm_cc.core.todo import TodoStore, TodoItem

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "todo-write.txt").read_text()

# 类型定义
TodoStatus = Literal["pending", "in_progress", "completed", "cancelled"]
TodoPriority = Literal["high", "medium", "low"]


class TodoItemParams(BaseModel):
    """单个 Todo 项参数"""

    content: str = Field(
        description="Brief description of the task"
    )
    status: TodoStatus = Field(
        default="pending",
        description="Current status: pending, in_progress, completed, or cancelled"
    )
    priority: TodoPriority = Field(
        default="medium",
        description="Priority level: high, medium, or low"
    )


class TodoWriteParams(BaseModel):
    """Todo Write 工具参数

    传入完整的 todo 列表，会完全替换当前列表。
    """

    todos: list[TodoItemParams] = Field(
        description="The updated todo list. This will completely replace the current list."
    )


class TodoWriteTool(Tool):
    """更新 Todo 列表的工具

    全量更新策略: 传入的列表会完全替换当前列表。

    参考 opencode TodoWriteTool
    """

    name = "todo_write"
    description = _DESCRIPTION
    parameters = TodoWriteParams

    async def execute(self, params: BaseModel) -> dict[str, Any]:
        """执行 todo_write

        全量替换当前会话的 todo 列表。

        Args:
            params: 包含完整 todo 列表的参数

        Returns:
            dict with title, output, metadata
        """
        # 转换参数为具体类型
        write_params = TodoWriteParams.model_validate(params)

        # 从 AgentContextStore 获取当前 session
        from dm_cc.agent import AgentContextStore

        agent = AgentContextStore._current_agent
        if not agent:
            return {
                "title": "No active session",
                "output": "No active session found. Todos are session-specific.",
                "metadata": {"todos": []},
            }

        # 转换参数为 TodoItem
        todo_items = [
            TodoItem(
                content=todo.content,
                status=todo.status,
                priority=todo.priority,
            )
            for todo in write_params.todos
        ]

        # 更新存储
        session_id = agent.logger.session_id
        store = TodoStore(session_id)
        store.update(todo_items)

        # 格式化输出
        pending_count = len([t for t in todo_items if t.status != "completed"])

        if not todo_items:
            output = "Todo list cleared."
        else:
            lines = [f"Updated todo list with {len(todo_items)} items:"]
            for i, todo in enumerate(todo_items, 1):
                status_icon = {
                    "completed": "✓",
                    "in_progress": "•",
                    "pending": " ",
                    "cancelled": "✗",
                }.get(todo.status, " ")
                lines.append(f"  {i}. [{status_icon}] {todo.content}")
            output = "\n".join(lines)

        return {
            "title": f"{pending_count} todos",
            "output": output,
            "metadata": {
                "todos": [todo.to_dict() for todo in todo_items],
                "count": len(todo_items),
                "pending": pending_count,
            },
        }
