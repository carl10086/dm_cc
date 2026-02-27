"""用户交互模块 - 询问用户确认

提供简单的交互式提问功能，用于：
- plan_enter/plan_exit 确认
- 权限确认
- 一般性用户确认

参考 opencode: packages/opencode/src/question.ts
"""

from dataclasses import dataclass
from typing import Literal

from rich.console import Console

console = Console()


class UserCancelledError(Exception):
    """用户取消操作"""
    pass


@dataclass
class QuestionOption:
    """选项定义"""
    label: str  # 显示标签，如 "Yes"
    description: str  # 详细描述


async def ask_user(
    question: str,
    options: list[tuple[str, str]],
    header: str | None = None,
) -> str:
    """询问用户选择

    Args:
        question: 问题文本
        options: 选项列表，每个选项是 (label, description) 元组
        header: 可选的标题头

    Returns:
        用户选择的 label

    Raises:
        UserCancelledError: 用户取消或输入无效
    """
    if header:
        console.print(f"\n[bold]{header}[/bold]")

    console.print(f"\n{question}\n")

    # 显示选项
    for i, (label, desc) in enumerate(options, 1):
        console.print(f"  [{i}] {label}: {desc}")

    console.print()

    try:
        response = input("Enter choice (number or label): ").strip()
    except (EOFError, KeyboardInterrupt):
        raise UserCancelledError("User cancelled")

    # 解析输入
    # 支持数字或标签
    if response.isdigit():
        idx = int(response) - 1
        if 0 <= idx < len(options):
            return options[idx][0]
    else:
        # 直接匹配 label
        for label, _ in options:
            if label.lower() == response.lower():
                return label

    # 无效输入
    raise UserCancelledError(f"Invalid choice: {response}")


async def confirm(
    message: str,
    default: bool = False,
) -> bool:
    """简单的确认提问

    Args:
        message: 确认消息
        default: 默认选择

    Returns:
        用户是否确认
    """
    suffix = " [Y/n]" if default else " [y/N]"
    console.print(f"\n{message}{suffix} ", end="")

    try:
        response = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False

    if not response:
        return default

    return response in ('y', 'yes')
