# dm_cc Skill 系统技术设计文档

## 1. 概述

### 1.1 什么是 Skill

Skill 是领域知识的结构化文档，让 AI 能够快速获取特定技术栈的专业知识。

**与 Tool 的区别：**
- **Tool**: 可执行的功能（读文件、执行命令）
- **Skill**: 只读的知识库（Cloudflare、React、AWS 等最佳实践）

### 1.2 核心设计理念

1. **按需加载**: 不是启动时加载所有 skills，而是 AI 自主决定何时加载
2. **动态发现**: Tool description 动态列出可用 skills，AI 自主选择
3. **分层覆盖**: 项目级 skill > 全局 skill > 内置 skill
4. **权限控制**: 通过 Agent 配置控制可访问的 skills

## 2. 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Skill 系统架构                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  Skill 文件层                            │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │   │
│  │  │ ~/.dm_cc/   │  │ ./.dm_cc/   │  │ 远程 URL        │  │   │
│  │  │ skills/     │  │ skills/     │  │ (下载到缓存)     │  │   │
│  │  │ (全局)      │  │ (项目级)    │  │                 │  │   │
│  │  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │   │
│  │         └─────────────────┼──────────────────┘            │   │
│  │                           ↓                               │   │
│  │  ┌─────────────────────────────────────────────────────┐  │   │
│  │  │              SkillLoader (扫描 + 解析)               │  │   │
│  │  │  • 扫描多层级目录                                   │  │   │
│  │  │  • 使用 python-frontmatter 解析 YAML frontmatter    │  │   │
│  │  │  • 按优先级合并（项目级覆盖全局）                    │  │   │
│  │  │  • 缓存到内存（SkillStore）                         │  │   │
│  │  └────────────────────────┬────────────────────────────┘  │   │
│  └───────────────────────────┼────────────────────────────────┘   │
│                              ↓                                    │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              SkillTool (Tool 基类)                      │     │
│  │  • 动态生成 description（列出可用 skills）               │     │
│  │  • 权限过滤（基于 AgentConfig）                         │     │
│  │  • 按需加载（execute 时读取 content）                   │     │
│  │  • 返回 XML 格式: <skill_content>                       │     │
│  └─────────────────────────┬───────────────────────────────┘     │
│                            ↓                                      │
│              ┌─────────────────────────┐                         │
│              │    LLM 对话上下文       │                         │
│              │  （Skill 知识注入）      │                         │
│              └─────────────────────────┘                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 3. 数据模型

### 3.1 Skill 文件格式 (SKILL.md)

```markdown
---
name: cloudflare
description: Comprehensive Cloudflare platform skill covering Workers, Pages...
references:
  - workers
  - pages
  - d1
---

# Cloudflare Platform Skill

## Quick Decision Trees

### "I need to run code"
```
Need to run code?
├─ Serverless functions at the edge → workers/
├─ Full-stack web app with Git deploys → pages/
```

## Workers Quick Start
...
```

### 3.2 Python 数据模型

```python
# dm_cc/core/skill.py
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path

class SkillMetadata(BaseModel):
    """YAML frontmatter 模型"""
    name: str
    description: str
    references: Optional[List[str]] = None

class SkillInfo(BaseModel):
    """完整的 Skill 信息"""
    name: str
    description: str
    location: str           # 文件绝对路径
    content: str           # Markdown 内容（不含 frontmatter）
    metadata: SkillMetadata

    def to_tool_description(self) -> str:
        """生成 Tool description 中的一行描述"""
        return f"  - {self.name}: {self.description}"
```

## 4. 核心模块设计

### 4.1 SkillLoader - 扫描和解析

```python
# dm_cc/core/skill.py
class SkillLoader:
    """Skill 文件扫描和解析器"""

    # 扫描路径优先级（从高到低）
    SCAN_PATHS = [
        "{home}/.dm_cc/skills",           # 全局
        "{project}/.dm_cc/skills",         # 项目级（覆盖全局）
        "{config}/skills",                 # 配置目录
    ]

    def __init__(self):
        self._skills: Dict[str, SkillInfo] = {}
        self._loaded = False

    def load_all(self) -> Dict[str, SkillInfo]:
        """加载所有 skills（懒加载）"""
        if self._loaded:
            return self._skills

        # 1. 扫描全局目录
        self._scan_directory(get_global_skills_dir())

        # 2. 扫描项目目录（覆盖全局）
        self._scan_directory(get_project_skills_dir())

        # 3. 扫描配置中的额外路径
        for path in get_config().skill_paths:
            self._scan_directory(Path(path))

        self._loaded = True
        return self._skills

    def _scan_directory(self, directory: Path) -> None:
        """扫描目录下的所有 SKILL.md 文件"""
        if not directory.exists():
            return

        for skill_file in directory.rglob("SKILL.md"):
            try:
                skill = self._parse_skill_file(skill_file)
                self._skills[skill.name] = skill  # 同名覆盖
            except Exception as e:
                logger.warning(f"Failed to load skill {skill_file}: {e}")

    def _parse_skill_file(self, file_path: Path) -> SkillInfo:
        """解析单个 Skill 文件"""
        import frontmatter

        post = frontmatter.loads(file_path.read_text(encoding="utf-8"))
        metadata = SkillMetadata.model_validate(post.metadata)

        return SkillInfo(
            name=metadata.name,
            description=metadata.description,
            location=str(file_path),
            content=post.content,
            metadata=metadata
        )
```

### 4.2 SkillTool - 按需加载接口

```python
# dm_cc/tools/skill.py
from dm_cc.tools.base import Tool
from dm_cc.core.skill import SkillLoader

class SkillTool(Tool):
    """
    Skill 加载工具 - 实现按需加载机制

    核心设计：
    1. description 是动态的，列出所有可用 skills
    2. AI 基于 description 自主选择 skill
    3. execute 时才加载详细内容
    """

    name = "skill"
    parameters = SkillParams  # {name: str}

    def __init__(self):
        self._loader = SkillLoader()

    @property
    def description(self) -> str:
        """
        动态生成 description

        这是关键：AI 通过 description 发现有哪些 skills 可用
        """
        skills = self._loader.load_all()

        skill_list = "\n".join([
            f"  - {name}: {info.description}"
            for name, info in skills.items()
        ])

        return f"""\
Load a specialized skill that provides domain-specific instructions.

Use this tool when you need expertise in a specific technology or platform.

Available skills:
{skill_list}

Parameters:
  name: The name of the skill to load (from the list above)

Returns:
  The full skill content including decision trees, best practices, and examples.
"""

    async def execute(self, params: SkillParams) -> dict:
        """执行 skill 加载"""
        # 1. 获取 skill
        skill = self._loader.get(params.name)
        if not skill:
            available = ", ".join(self._loader.list_names())
            raise ValueError(
                f'Skill "{params.name}" not found. '
                f'Available: {available or "none"}'
            )

        # 2. 权限检查（通过 AgentConfig）
        self._check_permission(skill.name)

        # 3. 加载相关文件（同目录下的其他资源）
        related_files = self._load_related_files(skill.location)

        # 4. 构建 XML 输出
        output = self._build_xml_output(skill, related_files)

        return {
            "title": f"Loaded skill: {skill.name}",
            "output": output,
            "metadata": {
                "name": skill.name,
                "location": skill.location,
            }
        }

    def _build_xml_output(self, skill: SkillInfo, files: List[str]) -> str:
        """构建 XML 格式的 skill 内容"""
        return f"""\
<skill_content name="{skill.name}">
# Skill: {skill.name}

{skill.content}

Base directory: {Path(skill.location).parent}

<skill_files>
{chr(10).join(files)}
</skill_files>
</skill_content>
"""
```

### 4.3 Agent 配置集成

```python
# dm_cc/agents/config.py
@dataclass
class AgentConfig:
    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str]
    denied_tools: list[str]
    allowed_skills: list[str] = field(default_factory=lambda: ["*"])  # 新增
    denied_skills: list[str] = field(default_factory=list)            # 新增

    def filter_skills(self, all_skills: Dict[str, SkillInfo]) -> Dict[str, SkillInfo]:
        """根据配置过滤可访问的 skills"""
        if "*" in self.allowed_skills:
            allowed = set(all_skills.keys())
        else:
            allowed = set(self.allowed_skills)

        # denied 优先级更高
        for denied in self.denied_skills:
            allowed.discard(denied)

        return {name: skill for name, skill in all_skills.items() if name in allowed}

# 预定义 Agent 配置
AGENTS = {
    "build": AgentConfig(
        name="build",
        allowed_tools=["*"],
        denied_tools=["plan_exit"],
        allowed_skills=["*"],      # Build agent 可以使用所有 skills
        denied_skills=[],
    ),
    "plan": AgentConfig(
        name="plan",
        allowed_tools=["read", "glob", "write", "edit", "plan_exit"],
        denied_tools=["bash"],
        allowed_skills=["*"],      # Plan agent 也可以使用 skills
        denied_skills=[],
    ),
    # Subagent 可以限制 skills
    "explore": AgentConfig(
        name="explore",
        allowed_tools=["read", "glob", "skill"],
        denied_tools=["bash"],
        allowed_skills=["basic"],  # 只能使用基础 skills
        denied_skills=["*"],
    ),
}
```

## 5. 使用流程

### 5.1 AI 自主加载流程

```
用户: "帮我部署一个 Cloudflare Worker"

AI 思考:
  1. 分析用户意图 → 需要 Cloudflare 知识
  2. 查看可用 tools → 看到 skill tool 的 description
  3. description 中有: "- cloudflare: Comprehensive Cloudflare platform..."
  4. 匹配成功！→ 调用 skill {"name": "cloudflare"}

Tool 执行:
  1. 加载 cloudflare/SKILL.md
  2. 返回 <skill_content> XML

AI 获得知识:
  1. 阅读 skill content（决策树、快速开始等）
  2. 基于知识指导用户:
     "根据 Cloudflare skill，你应该:
      1. 安装 wrangler
      2. 运行 wrangler init
      3. ..."
  3. 调用其他 tools（如 bash）执行部署
```

### 5.2 用户主动指定

```
用户: "使用 cloudflare skill 帮我创建 Worker"

AI:
  1. 识别到明确的 skill 请求
  2. 直接调用 skill {"name": "cloudflare"}
  3. 基于返回的知识继续对话
```

## 6. 目录结构

```
dm_cc/
├── src/dm_cc/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── skill.py          # SkillLoader + SkillInfo
│   │   └── todo.py
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── skill.py          # SkillTool
│   │   └── skill.txt         # Tool 基础描述模板
│   └── agents/
│       └── config.py         # AgentConfig 添加 skill 权限
├── .dm_cc/                    # 项目级 skill 存储
│   └── skills/
│       ├── cloudflare/
│       │   └── SKILL.md
│       └── react/
│           └── SKILL.md
└── docs/
    └── skill_system_design.md # 本文档
```

## 7. 依赖

```toml
[project.dependencies]
python-frontmatter = "^1.0.0"  # 解析 YAML frontmatter
pydantic = "^2.0.0"            # 数据验证（已有）
```

## 8. 验收标准

- [ ] SkillLoader 能扫描多层级目录
- [ ] 正确解析 YAML frontmatter（name, description, references）
- [ ] 项目级 skill 覆盖全局 skill
- [ ] SkillTool description 动态列出可用 skills
- [ ] AI 能基于 description 自主选择 skill
- [ ] 加载后返回 XML 格式的 skill_content
- [ ] AgentConfig 支持 skill 权限控制
- [ ] Plan/Build agent 都可以使用 skills
- [ ] 提供示例 skill 文件

## 9. 实现优先级

1. **P0**: SkillLoader + SkillInfo 数据模型
2. **P0**: SkillTool 基础实现
3. **P1**: AgentConfig skill 权限集成
4. **P1**: 动态 description 生成
5. **P2**: 远程 skill 下载
6. **P2**: 相关文件加载（scripts, templates）

---

**设计日期**: 2026-03-11
**参考实现**: opencode (TypeScript)
**设计目标**: 轻量级、可扩展、AI 友好的 Skill 系统
