"""分层 System Prompt 构建器 - MVP 简化版"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dm_cc.tools.base import Tool


# Layer 1: Provider 层 - Claude 模板
PROVIDER_TEMPLATE = """You are dm_cc, a coding assistant powered by Claude.

Your task is to help users with software engineering tasks through an interactive terminal interface.

## Guidelines

1. Think step by step before taking action
2. Read files before editing them
3. Explain what you're doing before making changes
4. Verify your changes work correctly
"""


# Layer 4: Agent 层 - 默认 Agent 指南
AGENT_TEMPLATE = """## Tool Usage

- Use `read` to examine files before editing
- Use `glob` to find files matching patterns
- Use `edit` to modify files with surgical precision
- Use `bash` to run commands when needed

When you need to take action, use the appropriate tool. The system will execute it and return the result to you.
"""


def _build_environment_layer() -> str:
    """Layer 2: 环境信息"""
    cwd = os.getcwd()
    platform = sys.platform
    date = datetime.now().strftime("%Y-%m-%d")

    # Check git
    is_git = False
    branch = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            capture_output=True,
            check=False,
        )
        is_git = result.returncode == 0
        if is_git:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
    except Exception:
        pass

    lines = [
        "<env>",
        f"  Working directory: {cwd}",
        f"  Is directory a git repo: {'yes' if is_git else 'no'}",
    ]
    if branch:
        lines.append(f"  Git branch: {branch}")
    lines.extend([
        f"  Platform: {platform}",
        f"  Today's date: {date}",
        "</env>",
    ])
    return "\n".join(lines)


def _build_custom_layer() -> str | None:
    """Layer 3: 加载 CLAUDE.md"""
    current = Path(os.getcwd()).resolve()

    for filename in ["CLAUDE.md", "AGENTS.md", ".claude.md", ".agents.md"]:
        for parent in [current, *current.parents]:
            rule_file = parent / filename
            if rule_file.exists():
                try:
                    content = rule_file.read_text(encoding="utf-8").strip()
                    return f"## Project Rules (from {filename})\n\n{content}\n"
                except Exception:
                    return None
    return None


def _build_tools_section(tools: list["Tool"]) -> str:
    """工具列表段落"""
    lines = ["## Available Tools", ""]
    for tool in tools:
        lines.append(f"- **{tool.name}**: {tool.description}")
    return "\n".join(lines)


class PromptBuilder:
    """分层 System Prompt 构建器"""

    async def build(self, tools: list["Tool"], extra_prompt: str | None = None) -> str:
        """构建完整的 System Prompt

        Args:
            tools: 可用工具列表
            extra_prompt: 额外的 prompt 内容（如 agent-specific system reminder）

        Returns:
            完整的 system prompt
        """
        layers = [
            PROVIDER_TEMPLATE,  # Layer 1
            _build_environment_layer(),  # Layer 2
            _build_custom_layer(),  # Layer 3 (可能为 None)
            _build_tools_section(tools),  # Layer 4 (工具列表)
            AGENT_TEMPLATE,  # Layer 4 (Agent 指南)
        ]

        # 添加额外的 prompt（如 Plan 模式的 system reminder）
        if extra_prompt:
            layers.append(extra_prompt)

        return "\n\n".join([layer for layer in layers if layer])
