"""Plan 文件管理

管理 plan 文件的存储路径、创建、读取和列表。
支持 DMCC_HOME 环境变量自定义存储位置。

存储结构:
- 默认: $DMCC_HOME/plans/ 或 ./.dm_cc/plans/
- 文件名格式: {timestamp}-{slug}.md

参考 opencode: Session.plan() 方法
"""

import os
import time
from pathlib import Path

# Plan 文件子目录
PLAN_SUBDIR = "plans"

# 默认 DMCC 目录名
DEFAULT_DMCC_DIR = ".dm_cc"


def get_dmcc_home() -> Path:
    """获取 DMCC Home 目录

    优先级:
    1. DMCC_HOME 环境变量
    2. 当前工作目录下的 .dm_cc/

    Returns:
        DMCC Home 目录路径
    """
    if dmcc_home := os.getenv("DMCC_HOME"):
        return Path(dmcc_home).expanduser().resolve()
    return Path.cwd() / DEFAULT_DMCC_DIR


def get_plan_dir() -> Path:
    """获取 plan 文件存储目录

    Returns:
        plan 目录路径 (例如: /path/to/.dm_cc/plans)
    """
    return get_dmcc_home() / PLAN_SUBDIR


def ensure_plan_dir() -> Path:
    """确保 plan 目录存在

    Returns:
        plan 目录路径
    """
    plan_dir = get_plan_dir()
    plan_dir.mkdir(parents=True, exist_ok=True)
    return plan_dir


def get_plan_path(slug: str | None = None) -> str:
    """生成 plan 文件路径

    文件名格式: {timestamp}-{slug}.md

    Args:
        slug: plan 标识，如 "feature-x"。为 None 时使用 "plan"

    Returns:
        plan 文件完整路径
    """
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-{slug or 'plan'}.md"
    return str(ensure_plan_dir() / filename)


def list_plans() -> list[str]:
    """列出所有 plan 文件

    按文件名降序排列（最新的在前）

    Returns:
        plan 文件名列表（不含路径）
    """
    plan_dir = get_plan_dir()
    if not plan_dir.exists():
        return []

    plans = [f for f in plan_dir.iterdir() if f.is_file() and f.suffix == ".md"]
    # 按文件名降序（时间戳最新的在前）
    plans.sort(key=lambda p: p.name, reverse=True)
    return [p.name for p in plans]


def read_latest_plan() -> tuple[str, str] | None:
    """读取最新的 plan 文件

    Returns:
        (plan_path, plan_content) 元组，如果没有 plan 文件则返回 None
    """
    plans = list_plans()
    if not plans:
        return None

    plan_path = get_plan_dir() / plans[0]
    try:
        content = plan_path.read_text(encoding="utf-8")
        return (str(plan_path), content)
    except (IOError, UnicodeDecodeError):
        return None


def is_plan_file(filepath: str) -> bool:
    """检查文件是否在 plan 目录下

    Args:
        filepath: 文件路径

    Returns:
        是否是 plan 文件
    """
    try:
        path = Path(filepath).resolve()
        plan_dir = get_plan_dir().resolve()
        return plan_dir in path.parents or path == plan_dir
    except (ValueError, OSError):
        return False
