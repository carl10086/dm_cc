"""Todo 管理模块 - Session 级别的任务列表

参考 opencode: packages/opencode/src/session/todo.ts

核心设计:
- 简单数据模型: content, status, priority
- Session 级别存储: 每个会话有自己的 todo 列表
- 全量更新: 每次更新传入完整列表，不是增量更新
- JSON 文件存储: 轻量级，无需数据库

存储结构:
- 位置: .dm_cc/todos/{session_id}.json
- 格式: [{"content": str, "status": str, "priority": str}, ...]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

from dm_cc.core.plan import get_dmcc_home


# Todo 状态类型
TodoStatus = Literal["pending", "in_progress", "completed", "cancelled"]

# Todo 优先级类型
TodoPriority = Literal["high", "medium", "low"]


@dataclass
class TodoItem:
    """Todo 项数据模型

    Attributes:
        content: 任务描述
        status: 任务状态 (pending, in_progress, completed, cancelled)
        priority: 优先级 (high, medium, low)
    """

    content: str
    status: TodoStatus = "pending"
    priority: TodoPriority = "medium"

    def to_dict(self) -> dict:
        """转换为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> TodoItem:
        """从字典创建"""
        return cls(
            content=data["content"],
            status=data.get("status", "pending"),
            priority=data.get("priority", "medium"),
        )


class TodoStore:
    """Session 级别的 Todo 存储

    管理单个会话的 todo 列表，使用 JSON 文件存储。

    Attributes:
        session_id: 会话 ID
        file_path: 存储文件路径
    """

    TODOS_SUBDIR = "todos"

    def __init__(self, session_id: str):
        """初始化 Todo 存储

        Args:
            session_id: 会话唯一标识
        """
        self.session_id = session_id
        self._file_path = self._get_file_path(session_id)

    def _get_file_path(self, session_id: str) -> Path:
        """获取存储文件路径

        Args:
            session_id: 会话 ID

        Returns:
            JSON 文件路径
        """
        dmcc_home = get_dmcc_home()
        todos_dir = dmcc_home / self.TODOS_SUBDIR
        todos_dir.mkdir(parents=True, exist_ok=True)
        return todos_dir / f"{session_id}.json"

    @property
    def file_path(self) -> Path:
        """存储文件路径"""
        return self._file_path

    def get_all(self) -> list[TodoItem]:
        """获取所有 todo 项

        Returns:
            TodoItem 列表（按位置排序）
        """
        if not self._file_path.exists():
            return []

        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            return [TodoItem.from_dict(item) for item in data]
        except (json.JSONDecodeError, IOError, KeyError):
            return []

    def update(self, todos: list[TodoItem]) -> None:
        """更新 todo 列表（全量替换）

        参考 opencode: 先删除旧数据，再插入新列表

        Args:
            todos: 新的 todo 列表（会完全替换旧列表）
        """
        # 确保目录存在
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入新列表
        data = [todo.to_dict() for todo in todos]
        self._file_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def clear(self) -> None:
        """清空 todo 列表"""
        if self._file_path.exists():
            self._file_path.unlink()

    def delete(self) -> None:
        """删除存储文件（同 clear）"""
        self.clear()


def get_todo_store(session_id: str) -> TodoStore:
    """获取指定会话的 TodoStore

    Args:
        session_id: 会话 ID

    Returns:
        TodoStore 实例
    """
    return TodoStore(session_id)


def list_session_todos() -> list[tuple[str, list[TodoItem]]]:
    """列出所有会话的 todo 列表

    Returns:
        (session_id, todos) 元组列表
    """
    dmcc_home = get_dmcc_home()
    todos_dir = dmcc_home / TodoStore.TODOS_SUBDIR

    if not todos_dir.exists():
        return []

    result = []
    for file_path in todos_dir.glob("*.json"):
        session_id = file_path.stem
        store = TodoStore(session_id)
        todos = store.get_all()
        result.append((session_id, todos))

    return result
