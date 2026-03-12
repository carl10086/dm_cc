"""Skill 系统核心模块

提供 Skill 文件的扫描、解析和存储功能。

参考 opencode: packages/opencode/src/skill/skill.ts
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

import frontmatter
from pydantic import BaseModel, ValidationError

from dm_cc.core.plan import get_dmcc_home

logger = logging.getLogger(__name__)


class SkillMetadata(BaseModel):
    """Skill YAML frontmatter 模型"""

    name: str
    description: str
    references: Optional[List[str]] = None


class SkillInfo(BaseModel):
    """完整的 Skill 信息"""

    name: str
    description: str
    location: str  # 文件绝对路径
    content: str  # Markdown 内容（不含 frontmatter）
    metadata: SkillMetadata

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "location": self.location,
            "metadata": self.metadata.model_dump(),
        }


class SkillLoader:
    """Skill 文件扫描和解析器

    支持多层级扫描和优先级覆盖：
    1. 全局: ~/.dm_cc/skills/
    2. 项目级: ./.dm_cc/skills/ (覆盖全局)
    3. 自定义路径: config.skills.paths

    参考 opencode skill.ts 的扫描逻辑
    """

    def __init__(self):
        self._skills: Dict[str, SkillInfo] = {}
        self._loaded = False

    def load_all(self, force_reload: bool = False) -> Dict[str, SkillInfo]:
        """加载所有 skills（懒加载）

        Args:
            force_reload: 是否强制重新加载

        Returns:
            Skill 名称到 SkillInfo 的映射字典
        """
        if self._loaded and not force_reload:
            return self._skills

        self._skills = {}

        # 1. 扫描全局目录（优先级最低）
        global_dir = get_global_skills_dir()
        self._scan_directory(global_dir)

        # 2. 扫描项目目录（覆盖全局）
        project_dir = get_project_skills_dir()
        self._scan_directory(project_dir)

        self._loaded = True
        logger.info(f"Loaded {len(self._skills)} skills")
        return self._skills

    def get(self, name: str) -> Optional[SkillInfo]:
        """获取指定名称的 Skill

        Args:
            name: Skill 名称

        Returns:
            SkillInfo 或 None
        """
        if not self._loaded:
            self.load_all()
        return self._skills.get(name)

    def list_names(self) -> List[str]:
        """获取所有 Skill 名称列表

        Returns:
            Skill 名称列表
        """
        if not self._loaded:
            self.load_all()
        return list(self._skills.keys())

    def _scan_directory(self, directory: Path) -> None:
        """扫描目录下的所有 SKILL.md 文件

        Args:
            directory: 要扫描的目录
        """
        if not directory.exists():
            logger.debug(f"Skill directory not found: {directory}")
            return

        logger.debug(f"Scanning skill directory: {directory}")

        # 递归查找所有 SKILL.md 文件
        for skill_file in directory.rglob("SKILL.md"):
            try:
                skill = self._parse_skill_file(skill_file)
                # 同名覆盖（项目级覆盖全局）
                if skill.name in self._skills:
                    logger.debug(
                        f"Overriding skill '{skill.name}' from {skill_file}"
                    )
                self._skills[skill.name] = skill
            except Exception as e:
                logger.warning(f"Failed to load skill {skill_file}: {e}")

    def _parse_skill_file(self, file_path: Path) -> SkillInfo:
        """解析单个 Skill 文件

        Args:
            file_path: SKILL.md 文件路径

        Returns:
            SkillInfo 对象

        Raises:
            ValueError: 解析或验证失败
        """
        try:
            post = frontmatter.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            raise ValueError(f"Failed to parse frontmatter: {e}")

        # 验证必要字段
        if not post.metadata:
            raise ValueError("Empty frontmatter")

        try:
            metadata = SkillMetadata.model_validate(post.metadata)
        except ValidationError as e:
            raise ValueError(f"Invalid skill metadata: {e}")

        # 确保 name 和 description 不为空
        if not metadata.name:
            raise ValueError("Missing required field: name")
        if not metadata.description:
            raise ValueError("Missing required field: description")

        return SkillInfo(
            name=metadata.name,
            description=metadata.description,
            location=str(file_path.absolute()),
            content=post.content,
            metadata=metadata,
        )


# 全局 SkillLoader 实例（单例模式）
_skill_loader: Optional[SkillLoader] = None


def get_skill_loader() -> SkillLoader:
    """获取全局 SkillLoader 实例

    Returns:
        SkillLoader 实例（单例）
    """
    global _skill_loader
    if _skill_loader is None:
        _skill_loader = SkillLoader()
    return _skill_loader


def reset_skill_loader() -> None:
    """重置全局 SkillLoader 实例

    用于测试或需要重新加载的场景
    """
    global _skill_loader
    _skill_loader = None


def get_global_skills_dir() -> Path:
    """获取全局 Skill 目录

    Returns:
        ~/.dm_cc/skills/
    """
    return Path.home() / ".dm_cc" / "skills"


def get_project_skills_dir() -> Path:
    """获取项目级 Skill 目录

    Returns:
        ./.dm_cc/skills/
    """
    return get_dmcc_home() / "skills"


def ensure_skills_dirs() -> None:
    """确保 Skill 目录存在"""
    get_global_skills_dir().mkdir(parents=True, exist_ok=True)
    get_project_skills_dir().mkdir(parents=True, exist_ok=True)


# 便捷函数

def load_all_skills() -> Dict[str, SkillInfo]:
    """加载所有 Skills"""
    return get_skill_loader().load_all()


def get_skill(name: str) -> Optional[SkillInfo]:
    """获取指定 Skill"""
    return get_skill_loader().get(name)


def list_skills() -> List[str]:
    """列出所有 Skill 名称"""
    return get_skill_loader().list_names()
