"""Skill Tool - 按需加载领域知识

参考 opencode: packages/opencode/src/tool/skill.ts

核心设计:
1. description 是动态的，列出所有可用 skills
2. AI 基于 description 自主选择 skill
3. execute 时才加载详细内容
4. 返回 XML 格式注入 LLM 上下文
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List

from pydantic import BaseModel, Field

from dm_cc.core.skill import SkillLoader, SkillInfo, get_skill_loader
from dm_cc.tools.base import Tool

# 加载基础描述模板
_DESCRIPTION_PATH = Path(__file__).parent / "skill.txt"
_BASE_DESCRIPTION = (
    _DESCRIPTION_PATH.read_text() if _DESCRIPTION_PATH.exists() else "Load a specialized skill."
)


class SkillParams(BaseModel):
    """Skill Tool 参数"""

    name: str = Field(
        description="The name of the skill to load (e.g., 'cloudflare', 'react')"
    )


class SkillTool(Tool):
    """Skill 加载工具

    允许 AI 按需加载特定领域的知识库。

    使用流程:
    1. AI 从 description 中看到可用 skills 列表
    2. AI 根据用户请求选择合适的 skill
    3. 调用本工具加载详细内容
    4. 内容以 XML 格式注入 LLM 上下文

    示例:
        用户: "帮我部署 Cloudflare Worker"
        AI: 看到 cloudflare skill → 调用 skill {"name": "cloudflare"}
        Tool: 返回 <skill_content name="cloudflare">...</skill_content>
        AI: 基于 skill 知识指导用户部署
    """

    name = "skill"
    parameters = SkillParams

    def __init__(self):
        self._loader = get_skill_loader()

    @property
    def description(self) -> str:
        """动态生成 description

        关键设计: description 包含当前所有可用 skills 的列表，
        这样 AI 就能自主发现和选择合适的 skill。

        Returns:
            动态生成的 description
        """
        # 加载所有 skills（懒加载，只执行一次）
        skills = self._loader.load_all()

        if not skills:
            return f"""\
{_BASE_DESCRIPTION}

No skills are currently available.

To add skills, create SKILL.md files in:
  - ~/.dm_cc/skills/     (global)
  - ./.dm_cc/skills/     (project-level)
"""

        # 构建 skills 列表
        skill_entries = []
        for name, info in sorted(skills.items()):
            skill_entries.append(f"  - {name}: {info.description}")

        skill_list = "\n".join(skill_entries)

        # 动态生成完整 description
        return f"""\
{_BASE_DESCRIPTION}

Use this tool to load specialized knowledge for specific technologies or platforms.

Available skills:
{skill_list}

Parameters:
  - name: The skill name to load (choose from the list above)

When to use:
  - Working with a specific technology (e.g., Cloudflare, AWS, React)
  - Need best practices or decision trees for a platform
  - User mentions a skill name explicitly

Returns:
  The full skill content including decision trees, quick starts, and best practices.
"""

    async def execute(self, params: SkillParams) -> dict[str, Any]:
        """执行 skill 加载

        Args:
            params: SkillParams 包含 name

        Returns:
            包含 title, output (XML), metadata 的字典

        Raises:
            ValueError: Skill 不存在
        """
        # 1. 获取 skill
        skill = self._loader.get(params.name)
        if not skill:
            available = ", ".join(sorted(self._loader.list_names()))
            raise ValueError(
                f'Skill "{params.name}" not found. '
                f"Available skills: {available or 'none'}"
            )

        # 2. 加载相关文件（同目录下的其他资源）
        related_files = self._load_related_files(skill.location)

        # 3. 构建 XML 输出
        output = self._build_xml_output(skill, related_files)

        return {
            "title": f"Loaded skill: {skill.name}",
            "output": output,
            "metadata": {
                "name": skill.name,
                "location": skill.location,
                "description": skill.description,
                "files_count": len(related_files),
            },
        }

    def _load_related_files(self, skill_location: str) -> List[str]:
        """加载 skill 目录下的相关文件

        扫描同目录下的其他文件（scripts, templates, references），
        返回文件路径列表供 AI 参考。

        Args:
            skill_location: SKILL.md 文件路径

        Returns:
            相关文件路径列表（最多 10 个）
        """
        skill_dir = Path(skill_location).parent
        if not skill_dir.exists():
            return []

        related = []
        try:
            # 遍历目录，收集非 SKILL.md 文件
            for item in skill_dir.iterdir():
                if item.is_file() and item.name != "SKILL.md":
                    related.append(str(item))
                elif item.is_dir():
                    # 递归收集子目录中的文件（最多一层）
                    for subitem in item.iterdir():
                        if subitem.is_file():
                            related.append(str(subitem))

                if len(related) >= 10:
                    break
        except OSError:
            pass

        return related

    def _build_xml_output(self, skill: SkillInfo, files: List[str]) -> str:
        """构建 XML 格式的 skill 内容

        参考 opencode 格式:
        <skill_content name="cloudflare">
        # Skill: cloudflare
        ...
        </skill_content>

        Args:
            skill: SkillInfo 对象
            files: 相关文件路径列表

        Returns:
            XML 格式字符串
        """
        base_dir = Path(skill.location).parent

        # 构建相关文件 XML
        files_xml = ""
        if files:
            file_entries = "\n".join([f"  <file>{f}</file>" for f in files])
            files_xml = f"""
<skill_files>
{file_entries}
</skill_files>"""

        return f"""<skill_content name="{skill.name}">
# Skill: {skill.name}

{skill.content}

Base directory: {base_dir}
Relative paths in this skill are relative to the base directory.{files_xml}
</skill_content>"""
