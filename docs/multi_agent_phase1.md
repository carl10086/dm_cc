# Multi-Agent 系统 Phase 1 设计与测试文档

## 概述

Phase 1 实现了 dm_cc 的多 Agent 系统基础架构，包括：

- **Agent 配置系统**：定义 Agent 的行为和工具权限
- **工具过滤机制**：基于配置的动态工具访问控制
- **预定义 Agents**：`build`（完全权限）和 `plan`（只读）

## 架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                      Agent System                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐      ┌─────────────┐      ┌─────────────┐ │
│  │   Config    │─────▶│    Agent    │◀─────│   Tools     │ │
│  │  (agents/)  │      │  (agent.py) │      │  (tools/)   │ │
│  └─────────────┘      └─────────────┘      └─────────────┘ │
│         │                    │                    │         │
│         ▼                    ▼                    ▼         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Tool Filtering Logic                     │  │
│  │  allowed_tools=["*"] → 允许所有                      │  │
│  │  denied_tools=["write"] → 排除指定                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Agent 配置结构

```python
@dataclass
class AgentConfig:
    name: str              # Agent 标识
    description: str       # 功能描述
    system_prompt: str     # 系统提示词
    allowed_tools: list[str]   # 允许的工具 ["*"] 表示全部
    denied_tools: list[str]    # 排除的工具（优先级高）
```

### 预定义 Agents

| Agent | 描述 | 允许工具 | 用途 |
|-------|------|---------|------|
| `build` | 默认执行 Agent | `["*"]` | 代码编辑、文件操作 |
| `plan` | 规划分析 Agent | `["read", "glob"]` | 代码分析、方案规划 |

## 文件结构

```
dm_cc/src/dm_cc/
├── agents/
│   ├── __init__.py          # 导出 AgentConfig, AGENTS, get_agent_config
│   └── config.py            # Agent 配置定义和工具过滤逻辑
├── agent.py                 # 更新后的 Agent 类
├── tools/
│   ├── __init__.py          # 添加 load_all_tools() 函数
│   └── ...                  # 现有工具实现
└── cli.py                   # 简化后的 CLI 初始化
```

## 使用方式

### 1. 使用默认 Build Agent

```python
from dm_cc.agent import Agent

# 默认创建 build agent（所有工具）
agent = Agent()
# 或显式指定
agent = Agent(agent_name="build")

print(agent.tools.keys())  # ['read', 'write', 'edit', 'glob']
```

### 2. 使用 Plan Agent（只读）

```python
from dm_cc.agent import Agent

# 创建 plan agent（只有 read/glob）
agent = Agent(agent_name="plan")

print(agent.tools.keys())  # ['read', 'glob']
```

### 3. 自定义 Agent 配置

```python
from dm_cc.agents import AgentConfig, register_agent

# 定义新 Agent
readonly_config = AgentConfig(
    name="readonly",
    description="只读 Agent",
    system_prompt="你只能读取文件...",
    allowed_tools=["read", "glob"],
    denied_tools=[],
)

# 注册
register_agent(readonly_config)

# 使用
agent = Agent(agent_name="readonly")
```

### 4. 配置级工具过滤

```python
from dm_cc.agents import AgentConfig
from dm_cc.tools import load_all_tools

config = AgentConfig(
    name="custom",
    description="自定义 Agent",
    system_prompt="测试",
    allowed_tools=["*"],           # 允许所有
    denied_tools=["write", "edit"] # 但排除 write 和 edit
)

all_tools = load_all_tools()
filtered = config.filter_tools(all_tools)
# 结果: ['read', 'glob']
```

## 测试指南

### 运行所有测试

```bash
cd /Users/carlyu/soft/projects/coding_agents/dm_cc

# 运行配置测试
uv run pytest tests/test_agents_config.py -v

# 运行集成测试
uv run pytest tests/test_agent_integration.py -v

# 运行所有测试
uv run pytest tests/ -v
```

### 测试覆盖

#### AgentConfig 测试 (`test_agents_config.py`)

| 测试 | 描述 |
|------|------|
| `test_basic_config` | 基本配置创建 |
| `test_filter_tools_wildcard` | 通配符 `["*"]` 允许所有工具 |
| `test_filter_tools_specific` | 指定允许列表 |
| `test_filter_tools_denied_priority` | denied_tools 优先级高于 allowed_tools |
| `test_filter_tools_specific_with_denied` | 允许列表 + 排除项组合 |
| `test_filter_tools_empty_allowed` | 空允许列表返回空工具集 |
| `test_build_agent_exists` | build agent 预定义配置正确 |
| `test_plan_agent_exists` | plan agent 预定义配置正确 |
| `test_get_agent_config_success` | 获取已知 agent 配置 |
| `test_get_agent_config_failure` | 未知 agent 报错 |
| `test_list_agents` | 列出所有 agents |
| `test_register_new_agent` | 注册新 agent |
| `test_register_overwrite_existing` | 覆盖已有 agent |

#### Agent 集成测试 (`test_agent_integration.py`)

| 测试 | 描述 |
|------|------|
| `test_default_build_agent` | 默认创建 build agent |
| `test_build_agent_explicit` | 显式创建 build agent |
| `test_plan_agent` | 创建 plan agent（工具受限） |
| `test_plan_agent_tool_count` | plan agent 只有 2 个工具 |
| `test_unknown_agent_raises` | 未知 agent 报错 |
| `test_custom_tools_dict` | 传入自定义工具字典 |
| `test_custom_tools_list` | 传入自定义工具列表 |
| `test_tools_filtered_by_config` | 工具按配置过滤 |
| `test_tools_parameter_optional` | tools 参数可选 |
| `test_default_agent_name` | 默认 agent_name 为 build |

### 手动测试

#### 测试 1: 验证工具过滤

```python
uv run python -c "
from dm_cc.agent import Agent

# Build agent - 所有工具
build = Agent(agent_name='build')
print('Build tools:', list(build.tools.keys()))

# Plan agent - 只读工具
plan = Agent(agent_name='plan')
print('Plan tools:', list(plan.tools.keys()))
"
```

预期输出：
```
Build tools: ['read', 'write', 'glob', 'edit']
Plan tools: ['read', 'glob']
```

#### 测试 2: 验证 CLI 正常工作

```bash
uv run dmcc --help
```

预期输出：帮助信息正常显示。

#### 测试 3: 验证未知 Agent 报错

```python
uv run python -c "
from dm_cc.agent import Agent
agent = Agent(agent_name='unknown')
"
```

预期输出：
```
ValueError: Unknown agent: unknown. Available: build, plan
```

## 向后兼容性

### 变更前代码（仍然有效）

```python
from dm_cc.agent import Agent
from dm_cc.tools import ReadTool, WriteTool, GlobTool, EditTool

# 旧方式：显式传入工具列表
tools = [ReadTool(), WriteTool(), GlobTool(), EditTool()]
agent = Agent(tools)
```

### 推荐的新方式

```python
from dm_cc.agent import Agent

# 新方式：通过 agent_name 自动加载和过滤
agent = Agent(agent_name="build")
```

---

# Phase 1b: Plan/Build 自动切换

## 目标

实现 Plan 和 Build Agent 之间的自动切换机制，参考 opencode 设计。

## 核心机制（基于 opencode 研究）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Agent 切换流程                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  用户输入: "实现一个复杂功能"                                             │
│       │                                                                 │
│       ▼                                                                 │
│  ┌──────────┐    判断需要规划     ┌──────────────┐                      │
│  │  Build   │ ─────────────────▶ │ plan_enter   │                      │
│  │  Agent   │     调用工具        │   工具       │                      │
│  └──────────┘                     └──────┬───────┘                      │
│                                          │                              │
│                                          ▼                              │
│                               询问用户确认?                              │
│                                    │                                    │
│                           是 ◄─────┴─────► 否                           │
│                           │                      │                       │
│                           ▼                      ▼                       │
│                    创建 synthetic        拒绝，继续                        │
│                    message(agent="plan")   Build                        │
│                           │                                            │
│                           ▼                                            │
│                    ┌──────────┐     plan_exit    ┌──────────┐         │
│                    │   Plan   │ ◄─────────────── │ 完成规划 │         │
│                    │  Agent   │                  │ 调用工具 │         │
│                    └────┬─────┘                  └──────────┘         │
│                         │                                               │
│                         ▼                                               │
│                  编辑 plan.md 文件                                       │
│                  （只能编辑此文件）                                       │
│                         │                                               │
│                         ▼                                               │
│                    询问用户执行?                                         │
│                         │                                               │
│                         ▼                                               │
│                  创建 synthetic                                          │
│                  message(agent="build")                                  │
│                         │                                               │
│                         ▼                                               │
│                  ┌──────────┐                                           │
│                  │  Build   │ ◄──── 读取 plan.md 执行                  │
│                  │  Agent   │                                           │
│                  └──────────┘                                           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 关键设计决策

1. **半自动切换**: AI 自主决定何时建议切换（通过调用工具），但需要用户确认
2. **Synthetic Message**: 通过特殊的用户消息触发切换，消息包含 `agent` 字段
3. **Plan 文件**: Plan agent 只能编辑 plan 文件，其他操作只读
4. **System Reminder**: 根据当前 agent 注入不同的系统提醒

---

## 实现内容

### 2.1 Message 模型扩展

**文件**: `dm_cc/src/dm_cc/core/message.py`（新增）

```python
from dataclasses import dataclass, field
from typing import Literal, Any

@dataclass
class Message:
    """消息模型 - 支持 Agent 切换"""
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]
    agent: str = "build"  # 当前 agent 身份
    synthetic: bool = False  # 是否系统生成（用于切换）

    # 可选：用于追踪
    timestamp: float = field(default_factory=lambda: __import__('time').time())

@dataclass
class SystemReminder:
    """系统提醒 - 注入到消息中指导 AI 行为"""
    text: str
    agent: str  # 针对哪个 agent
```

### 2.2 Plan Enter 工具

**文件**: `dm_cc/src/dm_cc/tools/plan_enter.py`（新增）

```python
"""plan_enter 工具 - Build Agent 调用以建议切换到 Plan Mode"""

from dm_cc.tools.base import Tool
from dm_cc.question import ask_user  # 需要新增交互模块

class PlanEnterTool(Tool):
    name = "plan_enter"
    description = """\
使用此工具建议切换到 Plan Agent 当用户请求需要规划后再执行。

调用时机：
- 用户请求复杂，需要先进行研究和设计
- 涉及多个文件或重大架构决策
- 用户明确提到"制定计划"

不要调用：
- 简单、直接的任务
- 用户要求立即执行
"""
    parameters = None  # 无参数

    async def execute(self, params) -> dict:
        # 1. 询问用户确认
        answer = await ask_user(
            question="是否切换到 Plan Agent 进行规划？",
            options=[
                ("是", "切换到 Plan Agent 进行研究和规划"),
                ("否", "继续使用 Build Agent 执行"),
            ]
        )

        if answer == "否":
            return {
                "title": "保持 Build Agent",
                "output": "用户选择不切换，继续当前模式",
            }

        # 2. 创建 synthetic message 触发切换
        from dm_cc.core.message import Message
        synthetic_msg = Message(
            role="user",
            content="用户已同意进入 Plan Mode，请切换到 Plan Agent 开始规划。",
            agent="plan",
            synthetic=True,
        )

        # 3. 添加到 session
        from dm_cc.session.manager import get_current_session
        session = get_current_session()
        session.add_message(synthetic_msg)

        return {
            "title": "切换到 Plan Agent",
            "output": "已创建切换消息，下一轮将使用 Plan Agent",
        }
```

### 2.3 Plan Exit 工具

**文件**: `dm_cc/src/dm_cc/tools/plan_exit.py`（新增）

```python
"""plan_exit 工具 - Plan Agent 调用以建议切换回 Build Agent"""

from dm_cc.tools.base import Tool
from dm_cc.question import ask_user

class PlanExitTool(Tool):
    name = "plan_exit"
    description = """\
使用此工具完成规划并建议切换回 Build Agent 开始执行。

在以下情况调用：
- 计划已完成并写入 plan.md
- 准备开始执行计划
- 用户同意执行方案

重要：调用此工具前确保 plan.md 已保存
"""
    parameters = None

    async def execute(self, params) -> dict:
        # 1. 检查 plan 文件是否存在
        plan_path = self._get_plan_path()
        plan_exists = await self._check_plan_exists(plan_path)

        # 2. 询问用户确认
        answer = await ask_user(
            question=f"计划文件 {plan_path} 已完成。是否切换到 Build Agent 开始执行？",
            options=[
                ("是", "切换到 Build Agent 执行计划"),
                ("否", "继续完善计划"),
            ]
        )

        if answer == "否":
            return {
                "title": "继续规划",
                "output": "用户选择继续完善计划",
            }

        # 3. 创建 synthetic message
        from dm_cc.core.message import Message
        content = "计划已完成，请切换回 Build Agent 执行。"
        if plan_exists:
            content += f"\n\n计划文件位置: {plan_path}"

        synthetic_msg = Message(
            role="user",
            content=content,
            agent="build",
            synthetic=True,
        )

        # 4. 添加到 session
        from dm_cc.session.manager import get_current_session
        session = get_current_session()
        session.add_message(synthetic_msg)

        return {
            "title": "切换到 Build Agent",
            "output": "已创建切换消息，下一轮将使用 Build Agent",
        }

    def _get_plan_path(self) -> str:
        # 返回 plan.md 文件路径
        # 例如: .dm_cc/plans/2026-02-27-feature-x.md
        pass
```

### 2.4 Agent Loop 改造

**文件**: `dm_cc/src/dm_cc/agent.py`（修改）

```python
class Agent:
    def __init__(self, agent_name: str = "build", ...):
        # ... 原有初始化代码 ...
        self.current_agent_name = agent_name

    async def run(self, user_input: str | None = None) -> str:
        """运行 Agent 循环 - 支持 Agent 切换"""
        # 检查是否需要切换 Agent（基于最新消息）
        target_agent = self._detect_target_agent()
        if target_agent != self.current_agent_name:
            await self._switch_agent(target_agent)

        # 原有循环逻辑...

        # 在构造 prompt 时注入 system reminder
        system_prompt = self._build_system_prompt()

        # ... 调用 LLM ...

    def _detect_target_agent(self) -> str:
        """从最新消息中检测目标 Agent"""
        for msg in reversed(self.ctx.messages):
            if hasattr(msg, 'agent') and msg.agent:
                return msg.agent
        return "build"

    async def _switch_agent(self, new_agent: str):
        """切换到新 Agent"""
        self.current_agent_name = new_agent
        self.config = get_agent_config(new_agent)

        # 重新过滤工具
        all_tools = load_all_tools()
        self.tools = self.config.filter_tools(all_tools)
        self.tool_list = list(self.tools.values())

        # 重新构建 system prompt
        self._system_prompt = None

        console.print(f"[dim]Switched to {new_agent} agent[/dim]")

    def _build_system_prompt(self) -> str:
        """构建系统提示 - 包含 agent-specific reminder"""
        base_prompt = self.config.system_prompt

        # 注入 system reminder
        if self.current_agent_name == "plan":
            reminder = PLAN_MODE_REMINDER
        elif self._was_plan_mode():  # 从 plan 切换回来
            reminder = BUILD_SWITCH_REMINDER
            # 读取 plan 文件内容
            plan_content = self._read_plan_file()
            if plan_content:
                reminder += f"\n\n计划内容:\n{plan_content}"
        else:
            reminder = ""

        if reminder:
            base_prompt += f"\n\n{reminder}"

        return base_prompt
```

### 2.5 System Reminder 定义

**文件**: `dm_cc/src/dm_cc/core/reminders.py`（新增）

```python
"""系统提醒 - 指导 AI 在不同模式下的行为"""

PLAN_MODE_REMINDER = """\
<system-reminder>
# Plan Mode - System Reminder

CRITICAL: Plan mode ACTIVE - you are in READ-ONLY phase. STRICTLY FORBIDDEN:
ANY file edits except the plan file. You may ONLY observe, analyze, and plan.

## Responsibility

Your current responsibility is to think, read, search, and construct a well-formed
plan that accomplishes the goal the user wants to achieve.

## Plan File Location

You should write your plan to: {plan_path}

This is the ONLY file you are allowed to edit - other than this you are only
allowed to take READ-ONLY actions.
</system-reminder>
"""

BUILD_SWITCH_REMINDER = """\
<system-reminder>
Your operational mode has changed from plan to build.
You are no longer in read-only mode.
You are permitted to make file changes, run shell commands, and utilize your
arsenal of tools as needed.
</system-reminder>
"""
```

### 2.6 Plan 文件管理

**文件**: `dm_cc/src/dm_cc/session/plan.py`（新增）

```python
"""Plan 文件管理"""

import os
import time
from pathlib import Path

PLAN_DIR = ".dm_cc/plans"

def get_plan_path(slug: str | None = None) -> str:
    """获取 plan 文件路径

    Args:
        slug: plan 标识，如 "feature-x"

    Returns:
        plan 文件完整路径
    """
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    if slug:
        filename = f"{timestamp}-{slug}.md"
    else:
        filename = f"{timestamp}-plan.md"

    return os.path.join(PLAN_DIR, filename)

def ensure_plan_dir() -> str:
    """确保 plan 目录存在"""
    os.makedirs(PLAN_DIR, exist_ok=True)
    return PLAN_DIR

def list_plans() -> list[str]:
    """列出所有 plan 文件"""
    if not os.path.exists(PLAN_DIR):
        return []
    return sorted(
        [f for f in os.listdir(PLAN_DIR) if f.endswith('.md')],
        reverse=True
    )

def read_latest_plan() -> str | None:
    """读取最新的 plan 文件内容"""
    plans = list_plans()
    if not plans:
        return None

    plan_path = os.path.join(PLAN_DIR, plans[0])
    with open(plan_path, 'r') as f:
        return f.read()
```

### 2.7 AgentConfig 更新

**文件**: `dm_cc/src/dm_cc/agents/config.py`（修改）

```python
# 更新 Plan Agent 配置，允许编辑 plan 文件
plan_agent = AgentConfig(
    name="plan",
    description="规划 Agent，只读模式，用于分析和规划",
    system_prompt="...",
    allowed_tools=["read", "glob", "write", "edit"],  # 添加 write/edit
    denied_tools=[],  # 但在 tool 层限制只能编辑 plan 文件
    # 新增：文件级权限控制
    file_permissions={
        ".dm_cc/plans/*.md": "allow",  # 允许编辑 plan 文件
        "*": "read-only",  # 其他只读
    }
)
```

### 2.8 Plan Agent 的 Write/Edit 工具限制

需要修改 WriteTool 和 EditTool，在 Plan Agent 模式下：
1. 检查目标文件是否在 `.dm_cc/plans/` 目录下
2. 如果不是，拒绝执行并提示用户

---

## Phase 1b 文件清单

### 新增文件
1. `dm_cc/src/dm_cc/core/__init__.py` - core 包初始化
2. `dm_cc/src/dm_cc/core/message.py` - Message 模型
3. `dm_cc/src/dm_cc/core/reminders.py` - 系统提醒文本
4. `dm_cc/src/dm_cc/tools/plan_enter.py` - plan_enter 工具
5. `dm_cc/src/dm_cc/tools/plan_exit.py` - plan_exit 工具
6. `dm_cc/src/dm_cc/session/plan.py` - plan 文件管理
7. `dm_cc/src/dm_cc/question.py` - 用户交互模块（如果尚未存在）

### 修改文件
1. `dm_cc/src/dm_cc/agent.py` - Agent Loop 支持切换
2. `dm_cc/src/dm_cc/agents/config.py` - 更新 Plan Agent 配置
3. `dm_cc/src/dm_cc/tools/write.py` - Plan 模式限制
4. `dm_cc/src/dm_cc/tools/edit.py` - Plan 模式限制

---

## Phase 1b 验收标准

- [ ] Build Agent 可以调用 `plan_enter` 工具建议切换
- [ ] 用户确认后切换到 Plan Agent
- [ ] Plan Agent 只能编辑 `.dm_cc/plans/*.md` 文件
- [ ] Plan Agent 调用 `plan_exit` 建议切换回 Build
- [ ] Build Agent 切换回来时读取 plan 文件内容
- [ ] System Reminder 正确注入到 prompt 中

---

## Phase 2: Subagent（Task 工具）

### 目标
实现 Task 工具，支持创建独立的 Child Session 并行执行。

（详细设计待 Phase 1b 完成后制定）

---

## 参考

- [原实现计划](/Users/carlyu/.claude/plans/melodic-enchanting-dijkstra.md)
- [opencode Agent 系统参考](/Users/carlyu/soft/projects/coding_agents/opencode/packages/opencode/src/agent/)
