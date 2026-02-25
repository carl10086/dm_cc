"""Edit Tool - 文件内容编辑工具"""

import difflib
from pathlib import Path
from typing import Any, Generator
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from dm_cc.lsp import LSPChecker
from dm_cc.tools.base import Tool

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "edit.txt").read_text()

console = Console()


def levenshtein_distance(a: str, b: str) -> int:
    """计算两个字符串的 Levenshtein 编辑距离"""
    if a == "" or b == "":
        return max(len(a), len(b))

    # 创建矩阵
    matrix = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]

    # 初始化第一行和第一列
    for i in range(len(a) + 1):
        matrix[i][0] = i
    for j in range(len(b) + 1):
        matrix[0][j] = j

    # 填充矩阵
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,      # 删除
                matrix[i][j - 1] + 1,      # 插入
                matrix[i - 1][j - 1] + cost # 替换
            )

    return matrix[len(a)][len(b)]


def similarity(a: str, b: str) -> float:
    """计算两个字符串的相似度 (0-1)"""
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0

    distance = levenshtein_distance(a, b)
    return 1.0 - (distance / max_len)


# Replacer 类型定义
Replacer = Generator[str, None, None]


def simple_replacer(content: str, find: str) -> Replacer:
    """简单替换器 - 精确匹配"""
    yield find


def line_trimmed_replacer(content: str, find: str) -> Replacer:
    """行修剪替换器 - 去除行首尾空格后匹配"""
    original_lines = content.split("\n")
    search_lines = find.split("\n")

    # 移除末尾的空行
    if search_lines and search_lines[-1] == "":
        search_lines.pop()

    for i in range(len(original_lines) - len(search_lines) + 1):
        matches = True
        for j in range(len(search_lines)):
            if original_lines[i + j].strip() != search_lines[j].strip():
                matches = False
                break

        if matches:
            # 计算匹配的起始和结束索引
            match_start = 0
            for k in range(i):
                match_start += len(original_lines[k]) + 1  # +1 for newline

            match_end = match_start
            for k in range(len(search_lines)):
                match_end += len(original_lines[i + k])
                if k < len(search_lines) - 1:
                    match_end += 1  # +1 for newline

            yield content[match_start:match_end]


def block_anchor_replacer(content: str, find: str) -> Replacer:
    """块锚点替换器 - 使用首行和末行作为锚点匹配

    适用于代码块匹配，即使中间行有差异也能匹配。
    """
    original_lines = content.split("\n")
    search_lines = find.split("\n")

    if len(search_lines) < 3:
        return

    # 移除末尾的空行
    if search_lines[-1] == "":
        search_lines.pop()

    first_line_search = search_lines[0].strip()
    last_line_search = search_lines[-1].strip()
    search_block_size = len(search_lines)

    # 收集所有候选位置（首行和末行都匹配的位置）
    candidates: list[tuple[int, int]] = []
    for i in range(len(original_lines)):
        if original_lines[i].strip() != first_line_search:
            continue

        # 寻找匹配的末行
        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_line_search:
                candidates.append((i, j))
                break  # 只匹配第一个末行

    if not candidates:
        return

    # 单一候选场景
    if len(candidates) == 1:
        start_line, end_line = candidates[0]
        actual_block_size = end_line - start_line + 1

        # 计算相似度（只比较中间行）
        sim = 0.0
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)

        if lines_to_check > 0:
            for j in range(1, search_block_size - 1):
                if start_line + j >= end_line:
                    break
                orig_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                sim += similarity(orig_line, search_line) / lines_to_check

            if sim >= 0.3:  # 阈值 0.3
                # 生成匹配结果
                match_start = 0
                for k in range(start_line):
                    match_start += len(original_lines[k]) + 1

                match_end = match_start
                for k in range(start_line, end_line + 1):
                    match_end += len(original_lines[k])
                    if k < end_line:
                        match_end += 1

                yield content[match_start:match_end]
        else:
            # 没有中间行，直接接受
            match_start = 0
            for k in range(start_line):
                match_start += len(original_lines[k]) + 1

            match_end = match_start
            for k in range(start_line, end_line + 1):
                match_end += len(original_lines[k])
                if k < end_line:
                    match_end += 1

            yield content[match_start:match_end]
        return

    # 多个候选场景 - 选择相似度最高的
    best_match = None
    max_sim = -1.0

    for start_line, end_line in candidates:
        actual_block_size = end_line - start_line + 1
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)

        if lines_to_check > 0:
            sim = 0.0
            for j in range(1, search_block_size - 1):
                if start_line + j >= end_line:
                    break
                orig_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                sim += similarity(orig_line, search_line)
            sim /= lines_to_check
        else:
            sim = 1.0

        if sim > max_sim:
            max_sim = sim
            best_match = (start_line, end_line)

    if max_sim >= 0.5 and best_match:  # 多候选阈值 0.5
        start_line, end_line = best_match
        match_start = 0
        for k in range(start_line):
            match_start += len(original_lines[k]) + 1

        match_end = match_start
        for k in range(start_line, end_line + 1):
            match_end += len(original_lines[k])
            if k < end_line:
                match_end += 1

        yield content[match_start:match_end]


def replace_content(content: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """执行内容替换

    按优先级尝试不同的匹配策略，直到成功。

    Args:
        content: 原始文件内容
        old_string: 要替换的文本
        new_string: 新文本
        replace_all: 是否替换所有匹配

    Returns:
        替换后的内容

    Raises:
        ValueError: 未找到匹配或有多处匹配（非 replace_all）
    """
    if old_string == new_string:
        raise ValueError("No changes to apply: oldString and newString are identical.")

    not_found = True

    # 按优先级尝试各种替换器
    replacers = [
        simple_replacer,
        line_trimmed_replacer,
        block_anchor_replacer,
    ]

    for replacer in replacers:
        for search in replacer(content, old_string):
            index = content.find(search)
            if index == -1:
                continue

            not_found = False

            if replace_all:
                return content.replace(search, new_string)

            # 检查是否唯一匹配
            last_index = content.rfind(search)
            if index != last_index:
                continue  # 有多处匹配，尝试下一个替换器

            # 执行替换
            return content[:index] + new_string + content[index + len(search):]

    if not_found:
        raise ValueError(
            "Could not find oldString in the file. "
            "It must match exactly, including whitespace, indentation, and line endings."
        )

    raise ValueError(
        "Found multiple matches for oldString. "
        "Provide more surrounding context to make the match unique, "
        "or use replaceAll to change every instance."
    )


class EditParams(BaseModel):
    """Edit 工具参数 - 对齐 opencode 设计"""

    filePath: str = Field(
        description="The absolute path to the file to modify"
    )
    oldString: str = Field(
        description="The text to replace"
    )
    newString: str = Field(
        description="The text to replace it with (must be different from oldString)"
    )
    replaceAll: bool | None = Field(
        default=None,
        description="Replace all occurrences of oldString (default false)"
    )
    # 内部参数，不暴露给 LLM，用于测试
    _auto_confirm: bool = False


class UserCancelledError(Exception):
    """用户取消编辑操作"""
    pass


def generate_diff(old_content: str, new_content: str, filepath: str) -> str:
    """生成 unified diff

    Args:
        old_content: 原始文件内容
        new_content: 新文件内容
        filepath: 文件路径（用于 diff 头部）

    Returns:
        unified diff 字符串
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # 确保每行都以换行符结尾
    if old_lines and not old_lines[-1].endswith('\n'):
        old_lines[-1] += '\n'
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm=""
    )
    return "".join(diff)


def confirm_edit(diff: str, filepath: str) -> bool:
    """显示 diff 并请求用户确认

    Args:
        diff: unified diff 字符串
        filepath: 文件路径

    Returns:
        用户是否确认执行
    """
    # 计算相对路径显示
    try:
        display_path = str(Path(filepath).relative_to(Path.cwd()))
    except ValueError:
        display_path = filepath

    # 显示 diff
    console.print()
    console.print(Panel(
        Syntax(diff, "diff", theme="monokai", line_numbers=True),
        title=f"[yellow]Proposed Edit: {display_path}[/yellow]",
        border_style="yellow"
    ))

    # 请求确认
    console.print("[dim]Apply this edit? (y/n): [/dim]", end="")
    try:
        response = input().lower().strip()
        return response in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        return False


class EditTool(Tool):
    """文件内容编辑工具 - 对齐 opencode 实现"""

    name = "edit"
    description = _DESCRIPTION
    parameters = EditParams

    async def execute(self, params: EditParams) -> dict[str, Any]:
        """执行 edit 操作 - 抛出异常表示错误"""
        # 验证参数
        if params.oldString == params.newString:
            raise ValueError("No changes to apply: oldString and newString are identical.")

        # 解析路径
        filepath = params.filePath
        path = Path(filepath)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()

        # 验证文件存在
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        if path.is_dir():
            raise IsADirectoryError(f"Path is a directory, not a file: {filepath}")

        # 读取文件内容
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"Cannot edit binary file: {path}")

        # 执行替换（生成新内容，但不写入）
        replace_all = params.replaceAll if params.replaceAll is not None else False
        new_content = replace_content(content, params.oldString, params.newString, replace_all)

        # 生成 diff
        diff = generate_diff(content, new_content, str(path))

        # 请求用户确认（除非 _auto_confirm 为 True）
        if not getattr(params, '_auto_confirm', False):
            if not confirm_edit(diff, str(path)):
                raise UserCancelledError("Edit cancelled by user")

        # 确认后才写入文件
        path.write_text(new_content, encoding="utf-8")

        # 计算相对路径作为 title
        try:
            title = str(path.relative_to(Path.cwd()))
        except ValueError:
            title = str(path)

        # 计算替换次数
        replacements = content.count(params.oldString) if replace_all else 1

        # ===== 新增: LSP 检查 =====
        output = "Edit applied successfully."

        # 只对 Python 文件进行 LSP 检查
        if path.suffix == ".py":
            checker = LSPChecker()
            errors = checker.check_python(path)
            if errors:
                output += checker.format_diagnostics(errors, path)
        # ==========================

        return {
            "title": title,
            "output": output,
            "metadata": {
                "replacements": replacements,
            }
        }
