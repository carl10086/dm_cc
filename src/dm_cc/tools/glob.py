"""Glob Tool - 文件模式匹配搜索工具"""

from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from dm_cc.tools.base import Tool

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "glob.txt").read_text()

# 结果限制
_LIMIT = 100


class GlobParams(BaseModel):
    """Glob 工具参数 - 对齐 opencode 设计"""

    pattern: str = Field(
        description="The glob pattern to match files against"
    )
    path: str | None = Field(
        default=None,
        description=(
            "The directory to search in. If not specified, the current working directory "
            "will be used. IMPORTANT: Omit this field to use the default directory. "
            "DO NOT enter 'undefined' or 'null' - simply omit it for the default behavior. "
            "Must be a valid directory path if provided."
        )
    )


class GlobTool(Tool):
    """文件模式匹配搜索工具 - 完全对齐 opencode 实现"""

    name = "glob"
    description = _DESCRIPTION
    parameters = GlobParams

    async def execute(self, params: GlobParams) -> dict[str, Any]:
        """执行 glob 搜索 - 抛出异常表示错误"""
        # 确定搜索路径
        if params.path:
            search_path = Path(params.path)
            if not search_path.is_absolute():
                search_path = Path.cwd() / search_path
        else:
            search_path = Path.cwd()

        search_path = search_path.resolve()

        # 验证路径是目录
        if not search_path.exists():
            raise FileNotFoundError(f"Directory not found: {params.path}")
        if not search_path.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {params.path}")

        # 执行 glob 搜索
        pattern = params.pattern
        files: list[dict[str, Any]] = []
        truncated = False

        # 使用 rglob 进行递归匹配
        # 转换 glob 模式：如果模式包含 **，使用 rglob，否则使用 glob
        if "**" in pattern:
            # 递归模式：rglob 自动处理 **
            # 移除 **/ 前缀，因为 rglob 从当前目录开始递归
            actual_pattern = pattern.replace("**/", "") if pattern.startswith("**/") else pattern
            iterator = search_path.rglob(actual_pattern)
        else:
            # 非递归模式
            iterator = search_path.glob(pattern)

        for file_path in iterator:
            if len(files) >= _LIMIT:
                truncated = True
                break

            if file_path.is_file():
                try:
                    mtime = file_path.stat().st_mtime
                except (OSError, IOError):
                    mtime = 0
                files.append({
                    "path": file_path.resolve(),
                    "mtime": mtime,
                })

        # 按修改时间排序（最新的在前）
        files.sort(key=lambda x: x["mtime"], reverse=True)

        # 构建输出
        output_lines: list[str] = []
        if not files:
            output_lines.append("No files found")
        else:
            output_lines.extend(str(f["path"]) for f in files)
            if truncated:
                output_lines.append("")
                output_lines.append(
                    f"(Results are truncated: showing first {_LIMIT} results. "
                    "Consider using a more specific path or pattern.)"
                )

        # 计算相对路径作为 title
        try:
            title = str(search_path.relative_to(Path.cwd()))
        except ValueError:
            title = str(search_path)

        return {
            "title": title,
            "output": "\n".join(output_lines),
            "metadata": {
                "count": len(files),
                "truncated": truncated,
            }
        }
