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

## 下一步（Phase 1b）

Phase 1b 将实现 Plan/Build Agent 的切换机制：

1. **Message 模型扩展**：添加 `agent` 字段记录当前身份
2. **plan_enter 工具**：切换到 Plan Agent
3. **plan_exit 工具**：切换回 Build Agent
4. **Session 管理**：维护当前 Agent 状态

```
用户输入 → Build Agent → plan_enter → Plan Agent
                                           ↓
                           plan_exit ← 分析完成
                               ↓
                          Build Agent → 执行修改
```

## 参考

- [原实现计划](/Users/carlyu/.claude/plans/melodic-enchanting-dijkstra.md)
- [opencode Agent 系统参考](/Users/carlyu/soft/projects/coding_agents/opencode/packages/opencode/src/agent/)
