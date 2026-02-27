"""Core 模块 - 消息模型、系统提醒、Plan 管理

此模块包含 Agent 切换机制的核心组件：
- Message: 支持 agent 和 synthetic 字段的消息模型
- reminders: 系统提醒文本（Plan 模式、Build 切换）
- plan: Plan 文件管理
"""

from dm_cc.core.message import Message
from dm_cc.core.reminders import PLAN_MODE_REMINDER, BUILD_SWITCH_REMINDER
from dm_cc.core.plan import (
    get_plan_dir,
    get_plan_path,
    ensure_plan_dir,
    list_plans,
    read_latest_plan,
    PLAN_SUBDIR,
)

__all__ = [
    "Message",
    "PLAN_MODE_REMINDER",
    "BUILD_SWITCH_REMINDER",
    "get_plan_dir",
    "get_plan_path",
    "ensure_plan_dir",
    "list_plans",
    "read_latest_plan",
    "PLAN_SUBDIR",
]
