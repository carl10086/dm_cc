"""Read Tool - 读取文件或目录内容"""

from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from dm_cc.tools.base import Tool

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "read.txt").read_text()

# 默认限制
_DEFAULT_READ_LIMIT = 2000
_MAX_LINE_LENGTH = 2000
_MAX_BYTES = 50 * 1024

# 二进制文件扩展名
_BINARY_EXTENSIONS = {
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin",
    ".class", ".jar", ".war", ".ear",
    ".pyc", ".pyo", ".pyd",
    ".obj", ".o", ".a", ".lib",
    ".wasm", ".wasm.gz",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".odt", ".ods", ".odp",
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv",
    ".ttf", ".otf", ".woff", ".woff2",
}


class ReadParams(BaseModel):
    """Read 工具参数 - 完全对齐 opencode 的 camelCase 命名"""

    filePath: str = Field(
        description="The absolute path to the file or directory to read"
    )
    offset: int | None = Field(
        default=None,
        description="The line number to start reading from (1-indexed)"
    )
    limit: int | None = Field(
        default=None,
        description="The maximum number of lines to read (defaults to 2000)"
    )


class ReadTool(Tool):
    """读取文件或目录内容的工具 - 完全对齐 opencode 实现"""

    name = "read"
    description = _DESCRIPTION
    parameters = ReadParams

    async def execute(self, params: ReadParams) -> dict[str, Any]:
        """执行 read 操作 - 抛出异常表示错误"""
        # 验证 offset
        if params.offset is not None and params.offset < 1:
            raise ValueError("offset must be greater than or equal to 1")

        # 解析路径
        filepath = params.filePath
        path = Path(filepath)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()

        # 获取文件信息
        if not path.exists():
            # 文件不存在时推荐相似文件
            dir_path = path.parent
            base = path.name
            suggestions: list[str] = []

            if dir_path.exists():
                try:
                    entries = list(dir_path.iterdir())
                    for entry in entries:
                        entry_name = entry.name.lower()
                        base_lower = base.lower()
                        if entry_name in base_lower or base_lower in entry_name:
                            suggestions.append(str(entry))
                    suggestions = suggestions[:3]
                except Exception:
                    pass

            if suggestions:
                raise FileNotFoundError(
                    f"File not found: {filepath}\n\n"
                    f"Did you mean one of these?\n" + "\n".join(suggestions)
                )
            raise FileNotFoundError(f"File not found: {filepath}")

        # 计算相对路径作为 title
        try:
            title = str(path.relative_to(Path.cwd()))
        except ValueError:
            title = str(path)

        # 处理目录
        if path.is_dir():
            return await self._read_directory(path, params, title)

        # 处理文件
        return await self._read_file(path, params, title)

    async def _read_directory(
        self, path: Path, params: ReadParams, title: str
    ) -> dict[str, Any]:
        """读取目录内容"""
        entries: list[str] = []

        for entry in path.iterdir():
            name = entry.name
            if entry.is_dir():
                name += "/"
            elif entry.is_symlink():
                try:
                    if entry.resolve().is_dir():
                        name += "/"
                except Exception:
                    pass
            entries.append(name)

        entries.sort(key=str.lower)

        limit = params.limit if params.limit is not None else _DEFAULT_READ_LIMIT
        offset = params.offset if params.offset is not None else 1
        start = offset - 1
        sliced = entries[start : start + limit]
        truncated = start + len(sliced) < len(entries)

        output_lines = [
            f"<path>{path}</path>",
            "<type>directory</type>",
            "<entries>",
            *sliced,
        ]

        if truncated:
            output_lines.append(
                f"\n(Showing {len(sliced)} of {len(entries)} entries. "
                f"Use 'offset' parameter to read beyond entry {offset + len(sliced)})"
            )
        else:
            output_lines.append(f"\n({len(entries)} entries)")

        output_lines.append("</entries>")
        output = "\n".join(output_lines)

        return {
            "title": title,
            "output": output,
            "metadata": {
                "preview": "\n".join(sliced[:20]),
                "truncated": truncated,
            },
        }

    async def _read_file(
        self, path: Path, params: ReadParams, title: str
    ) -> dict[str, Any]:
        """读取文件内容"""
        # 二进制检测
        if self._is_binary_file(path):
            raise ValueError(f"Cannot read binary file: {path}")

        # 读取文件
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"Cannot read binary file: {path}")

        lines = text.split("\n")
        limit = params.limit if params.limit is not None else _DEFAULT_READ_LIMIT
        offset = params.offset if params.offset is not None else 1
        start = offset - 1

        if start >= len(lines):
            raise ValueError(
                f"Offset {offset} is out of range for this file ({len(lines)} lines)"
            )

        # 读取内容（限制字节数）
        raw: list[str] = []
        bytes_read = 0
        truncated_by_bytes = False

        for i in range(start, min(len(lines), start + limit)):
            line = lines[i]
            # 截断超长行
            if len(line) > _MAX_LINE_LENGTH:
                line = line[:_MAX_LINE_LENGTH] + "..."

            # 检查字节限制
            line_bytes = len(line.encode("utf-8")) + (1 if raw else 0)
            if bytes_read + line_bytes > _MAX_BYTES:
                truncated_by_bytes = True
                break

            raw.append(line)
            bytes_read += line_bytes

        # 构建带行号的内容
        content_lines = [f"{i + offset}: {line}" for i, line in enumerate(raw)]
        preview = "\n".join(raw[:20])

        # 构建输出
        output_lines = [
            f"<path>{path}</path>",
            "<type>file</type>",
            "<content>",
            *content_lines,
        ]

        total_lines = len(lines)
        last_read_line = offset + len(raw) - 1
        has_more_lines = total_lines > last_read_line
        truncated = has_more_lines or truncated_by_bytes

        if truncated_by_bytes:
            output_lines.append(
                f"\n\n(Output truncated at {_MAX_BYTES} bytes. "
                f"Use 'offset' parameter to read beyond line {last_read_line})"
            )
        elif has_more_lines:
            output_lines.append(
                f"\n\n(File has more lines. "
                f"Use 'offset' parameter to read beyond line {last_read_line})"
            )
        else:
            output_lines.append(f"\n\n(End of file - total {total_lines} lines)")

        output_lines.append("</content>")
        output = "\n".join(output_lines)

        return {
            "title": title,
            "output": output,
            "metadata": {
                "preview": preview,
                "truncated": truncated,
            },
        }

    def _is_binary_file(self, path: Path) -> bool:
        """检测是否为二进制文件"""
        # 1. 扩展名检测
        ext = path.suffix.lower()
        if ext in _BINARY_EXTENSIONS:
            return True

        # 2. 内容检测
        try:
            stat = path.stat()
            file_size = stat.st_size
            if file_size == 0:
                return False

            buffer_size = min(4096, file_size)
            with open(path, "rb") as f:
                buffer = f.read(buffer_size)

            if len(buffer) == 0:
                return False

            non_printable_count = 0
            for byte in buffer:
                if byte == 0:
                    return True
                if byte < 9 or (byte > 13 and byte < 32):
                    non_printable_count += 1

            # >30% 不可打印字符 → 认为是二进制
            return non_printable_count / len(buffer) > 0.3

        except Exception:
            return False
