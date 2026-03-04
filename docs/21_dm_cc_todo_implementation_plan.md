# dm_cc Todo 系统实现方案

## 1. 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **存储** | JSON 文件 | 简单，无需 SQLite 依赖 |
| **位置** | `.dm_cc/todos/{session_id}.json` | 与 plan 文件目录结构一致 |
| **更新策略** | 全量替换 | 对齐 opencode，简化实现 |
| **Agent 权限** | Build/Plan 允许，Subagent 禁用 | 与 opencode 保持一致 |
| **触发方式** | LLM 自主判断 (Prompt 驱动) | 无代码硬编码逻辑 |

---

## 2. 数据模型

```python
# dm_cc/core/todo.py
from dataclasses import dataclass
from typing import Literal

@dataclass
class TodoItem:
    """Todo 项 - 对齐 opencode"""
    content: str
    status: Literal["pending", "in_progress", "completed", "cancelled"] = "pending"
    priority: Literal["high", "medium", "low"] = "medium"
```

**字段说明**：
- `content`: 任务描述（如 "创建用户数据库模型"）
- `status`: 状态流转 `pending → in_progress → completed`
- `priority`: 优先级图标 🔴🟡🟢

---

## 3. 存储层

```python
# dm_cc/core/todo.py
import json
from pathlib import Path
from dm_cc.core.plan import get_dmcc_home

class TodoStore:
    """Session 级别的 Todo 存储"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.file_path = get_dmcc_home() / "todos" / f"{session_id}.json"
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def get_all(self) -> list[TodoItem]:
        """读取所有 todo"""
        if not self.file_path.exists():
            return []
        data = json.loads(self.file_path.read_text())
        return [TodoItem(**item) for item in data]

    def update(self, todos: list[TodoItem]) -> None:
        """全量替换更新"""
        data = [
            {"content": t.content, "status": t.status, "priority": t.priority}
            for t in todos
        ]
        self.file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
```

**存储示例** (`.dm_cc/todos/20250304_120000_a1b2c3d4.json`)：
```json
[
  {"content": "创建用户数据库模型", "status": "completed", "priority": "high"},
  {"content": "实现登录 API 接口", "status": "in_progress", "priority": "high"},
  {"content": "创建登录页面表单", "status": "pending", "priority": "medium"}
]
```

---

## 4. 工具层

### 4.1 todo_read 工具

```python
# dm_cc/tools/todo_read.py
from dm_cc.tools.base import Tool
from dm_cc.core.todo import TodoStore

class TodoReadTool(Tool):
    name = "todo_read"
    description = (Path(__file__).parent / "todo-read.txt").read_text()
    parameters = None  # 无参数

    async def execute(self, params) -> dict:
        # 从 AgentContextStore 获取当前 session
        from dm_cc.agent import AgentContextStore
        agent = AgentContextStore._current_agent

        session_id = agent.logger.session_id
        store = TodoStore(session_id)
        todos = store.get_all()

        # 格式化输出
        lines = []
        for i, todo in enumerate(todos, 1):
            icon = {"completed": "✓", "in_progress": "•", "pending": " "}.get(todo.status, " ")
            lines.append(f"{i}. [{icon}] {todo.content}")

        pending = len([t for t in todos if t.status != "completed"])
        return {
            "title": f"{pending} todos",
            "output": "\n".join(lines) if lines else "No todos found",
            "metadata": {"todos": [t.__dict__ for t in todos]},
        }
```

### 4.2 todo_write 工具

```python
# dm_cc/tools/todo_write.py
from pydantic import BaseModel
from dm_cc.tools.base import Tool
from dm_cc.core.todo import TodoStore, TodoItem

class TodoItemParams(BaseModel):
    content: str
    status: str = "pending"
    priority: str = "medium"

class TodoWriteParams(BaseModel):
    todos: list[TodoItemParams]

class TodoWriteTool(Tool):
    name = "todo_write"
    description = (Path(__file__).parent / "todo-write.txt").read_text()
    parameters = TodoWriteParams

    async def execute(self, params: BaseModel) -> dict:
        write_params = TodoWriteParams.model_validate(params)

        from dm_cc.agent import AgentContextStore
        agent = AgentContextStore._current_agent

        session_id = agent.logger.session_id
        store = TodoStore(session_id)

        todo_items = [
            TodoItem(content=t.content, status=t.status, priority=t.priority)
            for t in write_params.todos
        ]
        store.update(todo_items)

        pending = len([t for t in todo_items if t.status != "completed"])
        return {
            "title": f"{pending} todos",
            "output": f"Updated {len(todo_items)} todos",
            "metadata": {"todos": [t.__dict__ for t in todo_items]},
        }
```

---

## 5. 关键：Prompt 设计

**文件**: `dm_cc/tools/todo-write.txt`

```
Use this tool to create and manage a structured task list for your current coding session.

## When to Use This Tool

Use this tool proactively in these scenarios:

1. Complex multistep tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task can be completed in less than 3 trivial steps
3. The task is purely conversational or informational

## Task States

- pending: Task not yet started
- in_progress: Currently working on (limit to ONE task at a time)
- completed: Task finished successfully
- cancelled: Task no longer needed

## Example

User: "I want to add a dark mode toggle"
Assistant: Creates todo list:
1. Create dark mode toggle component
2. Add state management
3. Implement CSS styles
4. Update existing components

Then mark first task as in_progress and begin working.
```

---

## 6. Agent 配置更新

```python
# dm_cc/agents/config.py

AGENTS = {
    "build": AgentConfig(
        name="build",
        system_prompt="...",
        allowed_tools=["*"],
        denied_tools=["plan_exit"],
        # todo_read/todo_write 默认可用
    ),
    "plan": AgentConfig(
        name="plan",
        system_prompt="...",
        allowed_tools=["read", "glob", "write", "edit", "plan_exit",
                      "todo_read", "todo_write"],  # Plan 也可用 todo
        denied_tools=["bash"],
    ),
}
```

---

## 7. 工具注册

```python
# dm_cc/tools/__init__.py

def load_all_tools() -> dict[str, Tool]:
    tools = [
        ReadTool(),
        WriteTool(),
        GlobTool(),
        EditTool(),
        BashTool(),
        PlanEnterTool(),
        PlanExitTool(),
        TodoReadTool(),    # 新增
        TodoWriteTool(),   # 新增
    ]
    return {t.name: t for t in tools}
```

---

## 8. 使用流程示例

### 场景：实现用户登录功能

```
用户: "帮我实现一个完整的用户登录功能"

LLM 思考 (基于 todowrite.txt prompt):
  - 这个任务复杂吗？需要几步？
  - 数据库模型 + API + 前端 + 加密 + 会话 = 5 步 > 3步 ✓
  - 应该使用 todo_write

LLM 调用工具:
  todo_write(todos=[
    {"content": "创建用户数据库模型", "status": "pending", "priority": "high"},
    {"content": "实现登录 API 接口", "status": "pending", "priority": "high"},
    {"content": "创建登录页面表单", "status": "pending", "priority": "medium"},
    {"content": "添加密码加密", "status": "pending", "priority": "high"},
    {"content": "实现会话管理", "status": "pending", "priority": "medium"},
  ])

AI 输出: "我将为您实现用户登录功能，已创建 5 个任务"

开始执行:
  1. 标记第一个为 in_progress
  2. 完成后标记 completed
  3. 继续下一个
```

---

## 9. 与 Plan 模式的区别

| | Todo 工具 | Plan 模式 |
|--|----------|-----------|
| **触发** | `todowrite` | `plan_enter` |
| **Agent 切换** | ❌ 否 | ✅ build→plan |
| **权限变化** | 无 | Plan 只读 |
| **存储** | `.dm_cc/todos/*.json` | `.dm_cc/plans/*.md` |
| **用途** | 跟踪执行进度 | 调研规划 |

---

## 10. 验收标准

- [ ] `todo_read` 无参数，返回当前 session 的 todo 列表
- [ ] `todo_write` 接收完整列表，全量替换存储
- [ ] Build/Plan agent 都可以使用 todo 工具
- [ ] 数据存储在 `.dm_cc/todos/{session_id}.json`
- [ ] Prompt 包含 "3 or more steps" 触发条件
- [ ] 状态流转：pending → in_progress → completed

---

*方案设计日期: 2026-03-04*
