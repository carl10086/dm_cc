"""Read Tool - 读取文件内容"""

from pathlib import Path
from pydantic import BaseModel, Field
from dm_cc.tools.base import Tool, ToolResult


class ReadParams(BaseModel):
    """Read 工具参数"""

    file_path: str = Field(
        description="要读取的文件路径（相对路径或绝对路径）"
    )
    offset: int = Field(
        default=1,
        description="起始行号（从1开始）"
    )
    limit: int = Field(
        default=100,
        description="最多读取行数，默认100行"
    )


class ReadTool(Tool):
    """读取文件内容的工具"""

    name = "read"
    description = "读取文件内容。支持指定起始行和读取行数限制。"
    parameters = ReadParams

    async def execute(self, params: ReadParams) -> ToolResult:
        try:
            # 解析路径
            path = Path(params.file_path)
            if not path.is_absolute():
                path = Path.cwd() / path

            path = path.resolve()

            # 安全检查: 确保在工作目录内
            cwd = Path.cwd().resolve()
            try:
                path.relative_to(cwd)
            except ValueError:
                return ToolResult.error(
                    f"只能读取工作目录内的文件: {path}\n当前工作目录: {cwd}"
                )

            # 检查文件存在性
            if not path.exists():
                return ToolResult.error(f"文件不存在: {params.file_path}")

            if not path.is_file():
                return ToolResult.error(f"路径不是文件: {params.file_path}")

            # 读取文件
            content = path.read_text(encoding="utf-8")
            lines = content.split("\n")
            total_lines = len(lines)

            # 处理行范围
            start_idx = max(0, params.offset - 1)
            end_idx = min(total_lines, start_idx + params.limit)

            selected_lines = lines[start_idx:end_idx]

            # 添加行号
            numbered_lines = []
            for i, line in enumerate(selected_lines, start=start_idx + 1):
                numbered_lines.append(f"{i:4d} | {line}")

            result_content = "\n".join([
                f"File: {path}",
                f"Lines: {start_idx + 1}-{end_idx} (total: {total_lines})",
                "-" * 40,
                *numbered_lines,
            ])

            if end_idx < total_lines:
                result_content += f"\n... ({total_lines - end_idx} more lines)"

            return ToolResult.ok(result_content)

        except UnicodeDecodeError:
            return ToolResult.error(f"无法读取文件（可能是二进制文件）: {params.file_path}")
        except Exception as e:
            return ToolResult.error(f"读取失败: {type(e).__name__}: {e}")
