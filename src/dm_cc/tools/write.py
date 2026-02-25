"""Write Tool - 写入文件到本地文件系统"""

import difflib
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from dm_cc.tools.base import Tool

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "write.txt").read_text()

console = Console()


class WriteParams(BaseModel):
    """Write 工具参数 - 对齐 opencode 设计"""

    filePath: str = Field(
        description="The absolute path to the file to write (must be absolute, not relative)"
    )
    content: str = Field(
        description="The content to write to the file"
    )
    # 内部参数，不暴露给 LLM，用于测试
    _auto_confirm: bool = False


class UserCancelledError(Exception):
    """用户取消写入操作"""
    pass


def generate_diff(old_content: str | None, new_content: str, filepath: str) -> str:
    """生成 unified diff

    Args:
        old_content: 原始文件内容（None 表示文件不存在）
        new_content: 新文件内容
        filepath: 文件路径（用于 diff 头部）

    Returns:
        unified diff 字符串
    """
    old_lines = old_content.splitlines(keepends=True) if old_content else []
    new_lines = new_content.splitlines(keepends=True)

    # 确保每行都以换行符结尾
    if old_lines and not old_lines[-1].endswith('\n'):
        old_lines[-1] += '\n'
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filepath}" if old_content else "/dev/null",
        tofile=f"b/{filepath}",
        lineterm=""
    )
    return "".join(diff)


def confirm_write(diff: str, filepath: str, exists: bool) -> bool:
    """显示 diff 并请求用户确认

    Args:
        diff: unified diff 字符串
        filepath: 文件路径
        exists: 文件是否已存在

    Returns:
        用户是否确认执行
    """
    # 计算相对路径显示
    try:
        display_path = str(Path(filepath).relative_to(Path.cwd()))
    except ValueError:
        display_path = filepath

    action = "Overwrite" if exists else "Create"

    # 显示 diff
    console.print()
    console.print(Panel(
        Syntax(diff, "diff", theme="monokai", line_numbers=True),
        title=f"[yellow]{action}: {display_path}[/yellow]",
        border_style="yellow"
    ))

    # 请求确认
    console.print("[dim]Apply this write? (y/n): [/dim]", end="")
    try:
        response = input().lower().strip()
        return response in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        return False


class WriteTool(Tool):
    """写入文件到本地文件系统的工具 - 对齐 opencode 实现"""

    name = "write"
    description = _DESCRIPTION
    parameters = WriteParams

    async def execute(self, params: WriteParams) -> dict[str, Any]:
        """执行 write 操作 - 抛出异常表示错误"""
        # 解析路径
        filepath = params.filePath
        path = Path(filepath)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()

        # 检查父目录是否存在
        parent = path.parent
        if not parent.exists():
            raise FileNotFoundError(
                f"Directory does not exist: {parent}\n"
                f"Please create the directory first before writing the file."
            )

        # 检查路径是否是目录
        if path.exists() and path.is_dir():
            raise IsADirectoryError(f"Path is a directory, not a file: {filepath}")

        # 读取旧内容（如果文件存在）
        exists = path.exists()
        old_content = None
        if exists:
            try:
                old_content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise ValueError(f"Cannot overwrite binary file: {path}")

        # 生成 diff
        diff = generate_diff(old_content, params.content, str(path))

        # 请求用户确认（除非 _auto_confirm 为 True）
        if not getattr(params, '_auto_confirm', False):
            if not confirm_write(diff, str(path), exists):
                raise UserCancelledError("Write cancelled by user")

        # 确认后才写入文件
        path.write_text(params.content, encoding="utf-8")

        # 计算相对路径作为 title
        try:
            title = str(path.relative_to(Path.cwd()))
        except ValueError:
            title = str(path)

        # 构建输出
        action = "overwritten" if exists else "created"
        output = f"File {action} successfully."

        # TODO: 未来可以添加 LSP 诊断检查（类似 opencode）
        # 目前 dm_cc 还没有 LSP 集成

        return {
            "title": title,
            "output": output,
            "metadata": {
                "filepath": str(path),
                "exists": exists,
            }
        }
