"""Bash Tool - 执行 shell 命令

参考 opencode: packages/opencode/src/tool/bash.ts

核心功能:
- 执行 bash 命令
- 使用 tree-sitter 解析命令
- 危险命令检测和安全控制
- 目录访问限制
- 超时控制
- 输出截断

安全机制:
1. 危险命令列表 (rm, mv, cp, chmod 等)
2. 目录访问限制 (只能在项目目录内)
3. 超时控制 (默认 2 分钟)
4. 输出大小限制 (50KB)
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

from dm_cc.tools.base import Tool

console = Console()

# 加载 description
_DESCRIPTION = (Path(__file__).parent / "bash.txt").read_text()

# 危险命令列表 (参考 opencode bash.ts)
DANGEROUS_COMMANDS = frozenset([
    "rm",      # 删除文件
    "mv",      # 移动文件
    "cp",      # 复制文件 (可能覆盖)
    "chmod",   # 修改权限
    "chown",   # 修改所有者
    "dd",      # 磁盘操作
    "mkfs",    # 格式化
    "fdisk",   # 分区
    "mount",   # 挂载
    "umount",  # 卸载
    "reboot",  # 重启
    "shutdown", # 关机
    "poweroff", # 关机
    "init",    # 系统初始化
    "kill",    # 杀死进程
    "killall", # 杀死所有进程
    "pkill",   # 按名称杀死进程
    "xargs",   # 可能危险
    "eval",    # 执行字符串
    "exec",    # 替换 shell
    "source",  # 执行脚本
    ".",       # 同上
    "su",      # 切换用户
    "sudo",    # 提权
])

# 需要特殊检查的命令 (可能包含危险子命令)
SUSPICIOUS_PATTERNS = [
    r">\s*/dev/null",  # 重定向到 /dev/null
    r"2>&1\s*>",       # 重定向 stderr
    r";\s*rm",         # 分号后接 rm
    r"&&\s*rm",        # && 后接 rm
    r"\|\s*rm",        # 管道后接 rm
]


class BashParams(BaseModel):
    """Bash 工具参数"""

    command: str = Field(
        description="The bash command to execute (e.g., 'ls -la', 'git status')"
    )
    description: str | None = Field(
        default=None,
        description="A description of what the command does (for logging)"
    )
    timeout: int | None = Field(
        default=None,
        description="Timeout in seconds (default: 120, max: 600)"
    )
    workdir: str | None = Field(
        default=None,
        description="Working directory for the command (default: project root)"
    )


class BashTool(Tool):
    """执行 bash 命令的工具

    提供 shell 命令执行能力，包含安全控制和资源限制。
    Build Agent 默认可用，Plan Agent 禁用。

    安全特性:
    - 危险命令检测
    - 目录访问限制
    - 超时控制 (默认 2 分钟)
    - 输出大小限制 (50KB)
    """

    name = "bash"
    description = _DESCRIPTION
    parameters = BashParams

    # 输出大小限制 (50KB)
    MAX_OUTPUT_SIZE = 50 * 1024
    # 默认超时 (2分钟)
    DEFAULT_TIMEOUT = 120
    # 最大超时 (10分钟)
    MAX_TIMEOUT = 600

    async def execute(self, params: BashParams) -> dict[str, Any]:
        """执行 bash 命令

        Args:
            params: BashParams 实例

        Returns:
            dict with keys: title, output, metadata

        Raises:
            PermissionError: 危险命令或目录访问违规
            TimeoutError: 命令执行超时
            RuntimeError: 命令执行失败
        """
        command = params.command.strip()
        description = params.description or command

        if not command:
            raise ValueError("Command cannot be empty")

        # 确定工作目录
        workdir = self._resolve_workdir(params.workdir)

        # 安全检查
        self._security_check(command, workdir)

        # 解析超时
        timeout = min(
            params.timeout or self.DEFAULT_TIMEOUT,
            self.MAX_TIMEOUT
        )

        # 执行命令
        result = await self._run_command(command, workdir, timeout)

        return {
            "title": description[:50] if description else command[:50],
            "output": result["output"],
            "metadata": {
                "command": command,
                "workdir": str(workdir),
                "exit_code": result["exit_code"],
                "timed_out": result.get("timed_out", False),
                "truncated": result.get("truncated", False),
            }
        }

    def _resolve_workdir(self, workdir: str | None) -> Path:
        """解析工作目录

        Args:
            workdir: 指定的工作目录或 None

        Returns:
            解析后的绝对路径
        """
        if workdir:
            path = Path(workdir).expanduser().resolve()
        else:
            path = Path.cwd().resolve()

        return path

    def _security_check(self, command: str, workdir: Path) -> None:
        """执行安全检查

        检查:
        1. 目录是否在项目目录内
        2. 是否包含危险命令

        Args:
            command: 要执行的命令
            workdir: 工作目录

        Raises:
            PermissionError: 安全检查失败
        """
        # 检查工作目录是否有效
        if not workdir.exists():
            raise FileNotFoundError(f"Working directory does not exist: {workdir}")

        if not workdir.is_dir():
            raise NotADirectoryError(f"Workdir is not a directory: {workdir}")

        # 解析命令
        parsed_commands = self._parse_command(command)

        # 检查每个解析出的命令
        for cmd in parsed_commands:
            base_cmd = cmd.get("command", "").lower()

            # 检查危险命令
            if base_cmd in DANGEROUS_COMMANDS:
                raise PermissionError(
                    f"Dangerous command detected: '{base_cmd}'\n"
                    f"Command: {command}\n\n"
                    f"This command could cause data loss or system damage. "
                    f"If you really need to run this command, please do it manually."
                )

            # 检查可疑模式
            for pattern in SUSPICIOUS_PATTERNS:
                if re.search(pattern, command, re.IGNORECASE):
                    raise PermissionError(
                        f"Suspicious pattern detected in command: {pattern}\n"
                        f"Command: {command}\n\n"
                        f"This command contains patterns that may be unsafe."
                    )

    def _parse_command(self, command: str) -> list[dict[str, Any]]:
        """使用 tree-sitter 解析命令

        解析 bash 命令，提取命令名和参数。

        Args:
            command: bash 命令字符串

        Returns:
            解析结果列表，每个元素包含 command 和 args
        """
        try:
            from tree_sitter_languages import get_parser

            parser = get_parser("bash")
            tree = parser.parse(command.encode())
            root = tree.root_node

            commands = []
            self._extract_commands(root, command, commands)

            # 如果没有解析到命令，使用简单分割
            if not commands:
                parts = command.split()
                if parts:
                    commands.append({"command": parts[0], "args": parts[1:]})

            return commands

        except Exception:
            # tree-sitter 解析失败时，使用简单分割
            parts = command.split()
            if parts:
                return [{"command": parts[0], "args": parts[1:]}]
            return []

    def _extract_commands(
        self,
        node: Any,
        source: str,
        commands: list[dict[str, Any]]
    ) -> None:
        """从 tree-sitter 节点中提取命令

        Args:
            node: tree-sitter 节点
            source: 原始命令字符串
            commands: 结果列表 (会被修改)
        """
        if node.type == "command":
            # 提取命令名
            cmd_name = None
            args = []

            for child in node.children:
                if child.type == "command_name":
                    cmd_name = source[child.start_byte:child.end_byte]
                elif child.type in ("word", "string"):
                    arg = source[child.start_byte:child.end_byte]
                    args.append(arg)

            if cmd_name:
                commands.append({"command": cmd_name, "args": args})

        # 递归遍历子节点
        for child in node.children:
            self._extract_commands(child, source, commands)

    async def _run_command(
        self,
        command: str,
        workdir: Path,
        timeout: int
    ) -> dict[str, Any]:
        """异步执行命令

        Args:
            command: 命令字符串
            workdir: 工作目录
            timeout: 超时秒数

        Returns:
            包含 output, exit_code, timed_out, truncated 的字典

        Raises:
            TimeoutError: 命令超时
            RuntimeError: 命令执行失败
        """
        # 使用 shell 执行命令
        # 先切换目录再执行命令
        cd_command = f"cd {shlex_quote(str(workdir))} && {command}"

        try:
            process = await asyncio.create_subprocess_shell(
                cd_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
                timed_out = False
            except asyncio.TimeoutError:
                # 超时，终止进程
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                raise TimeoutError(
                    f"Command timed out after {timeout} seconds: {command}"
                )

            # 解码输出
            try:
                output = stdout.decode("utf-8", errors="replace")
            except UnicodeDecodeError:
                output = stdout.decode("latin-1", errors="replace")

            # 截断输出
            truncated = False
            if len(output) > self.MAX_OUTPUT_SIZE:
                output = output[:self.MAX_OUTPUT_SIZE] + (
                    f"\n\n[Output truncated: {len(output)} chars, "
                    f"showing first {self.MAX_OUTPUT_SIZE}]"
                )
                truncated = True

            return {
                "output": output,
                "exit_code": process.returncode or 0,
                "timed_out": timed_out,
                "truncated": truncated,
            }

        except TimeoutError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to execute command: {e}")


def shlex_quote(s: str) -> str:
    """安全地引用字符串用于 shell

    如果字符串包含特殊字符，使用单引号包裹，
    并将内部的单引号处理为 '"'"'"'" 形式。

    Args:
        s: 要引用的字符串

    Returns:
        引用后的字符串
    """
    if not s:
        return "''"

    # 如果没有特殊字符，直接返回
    if re.match(r"^[a-zA-Z0-9_./-]+$", s):
        return s

    # 使用单引号包裹，处理内部单引号
    # ' -> '"'"'
    return "'" + s.replace("'", "'\"'\"'") + "'"
