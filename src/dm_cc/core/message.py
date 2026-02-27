"""Message 模型 - 支持 Agent 切换

参考 opencode: packages/opencode/src/session/message-v2.ts
"""

from dataclasses import dataclass, field
from typing import Literal, Any
from datetime import datetime
import uuid


@dataclass
class Message:
    """消息模型 - 支持 Agent 切换

    Attributes:
        role: 消息角色 ("user" | "assistant")
        content: 消息内容，可以是字符串或内容块列表
        agent: 当前 agent 身份标识，用于切换
        synthetic: 是否系统生成（用于 plan 切换）
        id: 唯一标识符
        timestamp: 创建时间
    """

    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]
    agent: str = "build"  # 关键：标识此消息的 agent 身份
    synthetic: bool = False  # 是否系统生成（用于 plan 切换）
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)

    def to_anthropic_format(self) -> dict[str, Any]:
        """转换为 Anthropic API 格式"""
        return {
            "role": self.role,
            "content": self.content,
        }

    @classmethod
    def create_synthetic(
        cls,
        agent: str,
        content: str,
    ) -> "Message":
        """创建 synthetic message - 用于 agent 切换

        参考 opencode plan.ts:
        - plan_enter 创建 agent="plan" 的消息
        - plan_exit 创建 agent="build" 的消息

        Args:
            agent: 目标 agent 名称 ("build" | "plan")
            content: 消息内容

        Returns:
            新的 synthetic Message 实例
        """
        return cls(
            role="user",
            content=content,
            agent=agent,
            synthetic=True,
        )
