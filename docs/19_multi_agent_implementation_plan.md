# dm_cc Multiple-Agent 系统实现计划

## 目录

1. [背景与目标](#1-背景与目标)
2. [参考：Opencode 设计解析](#2-参考opencode-设计解析)
3. [总体架构演进](#3-总体架构演进)
4. [Phase 1: Multi-Agent 基础](#4-phase-1-multi-agent-基础)
5. [Phase 2: 权限系统](#5-phase-2-权限系统)
6. [Phase 3: Subagent](#6-phase-3-subagent)
7. [技术决策记录](#7-技术决策记录)
8. [验收标准](#8-验收标准)

---

## 1. 背景与目标

### 核心设计理念

基于对 opencode 的深入研究，提炼出三种多 agent 协作模式：

| 模式 | 说明 | 类比 |
|------|------|------|
| **Plan 模式** | 同一 Session 内切换 Agent 身份 | 演员换装（同一舞台） |
| **Subagent** | 独立的 Child Session 并行执行 | 分剧场演出（各自独立） |
| **权限系统** | 基于规则的工具访问控制 | 门禁系统 |

### 解决的问题

1. **复杂任务规划**：先研究后执行，避免盲目修改
2. **权限隔离**：Plan 模式只读，防止误操作
3. **并行处理**：Subagent 可以同时处理多个独立任务

---

## 2. 参考：Opencode 设计解析

### 2.1 关键源码位置

| 功能 | 文件路径 | 关键行号 |
|------|----------|----------|
| Agent 定义 | `packages/opencode/src/agent/agent.ts` | L24-49 (Info schema), L76-202 (native agents) |
| 权限系统 | `packages/opencode/src/permission/next.ts` | L1-100 (Rule/Action 定义), L44-72 (evaluate 函数) |
| Plan 工具 | `packages/opencode/src/tool/plan.ts` | L20-73 (plan_exit), L75-130 (plan_enter) |
| Task 工具 | `packages/opencode/src/tool/task.ts` | L45-165 (完整实现) |
| Loop 集成 | `packages/opencode/src/session/prompt.ts` | L553-606 (agent 获取与工具解析) |

### 2.2 核心设计洞察

#### Agent 不是进程，是配置+身份

```typescript
// agent.ts
export const Info = z.object({
  name: z.string(),
  mode: z.enum(["subagent", "primary", "all"]),
  permission: PermissionNext.Ruleset,  // 权限规则集
  prompt: z.string().optional(),       // system prompt
  // ...
})
```

**洞察**：Agent = 权限配置 + System Prompt + 行为模式，不是独立的进程或实例。

#### Plan 切换机制：Message-based

```typescript
// plan.ts L104-114
const userMsg: MessageV2.User = {
  sessionID: ctx.sessionID,  // 同一个 session！
  agent: "plan",             // 只是改了 agent 字段
  // ...
}
await Session.updateMessage(userMsg)  // update，不是 create
```

**洞察**：Plan/Build 切换不是创建新会话，而是创建 synthetic message 改变 `agent` 字段。Loop 下次迭代读取 `lastUser.agent` 就知道该用哪个 agent。

#### Subagent：真正独立的 Session

```typescript
// task.ts L72-102
const session = await Session.create({  // 创建新 session！
  parentID: ctx.sessionID,  // 记录父子关系
  title: params.description,
  permission: [...],        // 独立的权限
})

await SessionPrompt.prompt({
  sessionID: session.id,    // 不同的 session ID
  agent: agent.name,
  parts: promptParts,       // 只传 prompt，无历史
})
```

**洞察**：Subagent 是独立的 Session，有自己的消息历史，只收到 Task 的 prompt，看不到 parent 的聊天记录。

#### 权限评估：Last-Match-Wins

```typescript
// permission/next.ts L44-72
export function evaluate(permission: string, pattern: string, ...rulesets: Ruleset[]): Rule {
  const merged = merge(...rulesets)

  // 找到最后一个匹配的规则
  const match = merged.findLast(
    (rule) => Wildcard.match(permission, rule.permission) &&
              Wildcard.match(pattern, rule.pattern)
  )

  return match ?? { action: "ask", permission, pattern: "*" }  // 默认 ask
}
```

**洞察**：规则按顺序评估，后定义的规则覆盖先定义的。例如：
```yaml
edit: deny           # 先匹配
"*.md": allow        # 后匹配 ← 生效！
```

### 2.3 Build vs Plan vs Explore 对比

| Agent | mode | 核心权限 | 用途 |
|-------|------|----------|------|
| **build** | primary | `plan_enter: allow`, 其他默认 allow | 默认执行 agent |
| **plan** | primary | `edit: { "*": "deny" }`, `plan_exit: allow` | 只读规划模式 |
| **explore** | subagent | `*": "deny"`, `read/glob/grep: "allow"` | 代码探索（只读） |
| **general** | subagent | `todoread/write: "deny"` | 通用任务代理 |

---

## 3. 总体架构演进

```
当前状态                    Phase 1                 Phase 2                 Phase 3
────────────────────────────────────────────────────────────────────────────────────
单一 Agent            →   Multi-Agent (Plan)   →   Permission System   →   Subagent
- 无 session 概念         - build/plan 切换        - 细粒度权限控制        - Task 工具
- 无 agent 配置           - Agent 配置中心         - 路径/工具权限         - 并行执行
- 所有工具可用            - 简单权限区分           - User confirm          - Child Session
                        - Session 概念建立         - 权限持久化
```

### 数据模型演进

**Phase 1 新增：**
```python
@dataclass
class AgentConfig:
    name: str
    mode: Literal["primary", "subagent"]
    allowed_tools: list[str]
    denied_tools: list[str]

@dataclass
class Message:
    role: str
    content: str
    agent: str = "build"  # 新增
    synthetic: bool = False  # 新增
```

**Phase 2 新增：**
```python
@dataclass
class PermissionRule:
    permission: str  # 工具名
    pattern: str     # 路径/参数模式
    action: Literal["allow", "deny", "ask"]

class PermissionEngine:
    def evaluate(tool, pattern, rules) -> Action
```

**Phase 3 新增：**
```python
class ChildSession:
    id: str
    parent_id: str
    agent: AgentConfig
    messages: list[Message]  # 独立的历史
```

---

## 4. Phase 1: Multi-Agent 基础

### 4.1 目标

实现最基本的 Plan/Build Agent 切换机制，建立 Agent 配置系统和 Session 概念。

### 4.2 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                     Session                             │
│  ┌──────────┐        plan_enter        ┌──────────┐    │
│  │  Build   │  ══════════════════════► │   Plan   │    │
│  │  Agent   │                          │  Agent   │    │
│  │          │  ◄══════════════════════ │          │    │
│  └──────────┘        plan_exit         └──────────┘    │
│       │                                        │        │
│       ▼                                        ▼        │
│   [edit, bash,                              [read,     │
│    write, ...]                              glob, ...] │
│                                                        │
│  同一 Session，通过 message.agent 字段切换身份          │
└─────────────────────────────────────────────────────────┘
```

### 4.3 实现清单

#### 4.3.1 Agent 配置系统

**参考源码**: `opencode/packages/opencode/src/agent/agent.ts`

**文件**: `dm_cc/src/dm_cc/agents/config.py`

```python
from dataclasses import dataclass
from typing import Literal


@dataclass
class AgentConfig:
    """Agent 配置 - 对齐 opencode Agent.Info"""
    name: str
    mode: Literal["primary", "subagent"]
    description: str
    system_prompt: str
    # Phase 1: 简单权限控制
    allowed_tools: list[str]  # ["*"] 表示全部
    denied_tools: list[str]   # 优先级高于 allowed


# 预定义 Agents - 参考 opencode agent.ts L76-155
AGENTS: dict[str, AgentConfig] = {
    "build": AgentConfig(
        name="build",
        mode="primary",
        description="默认执行 Agent，可编辑文件",
        system_prompt="""你是 dm_cc 的默认执行 Agent。

你的职责：
1. 理解用户需求并执行代码编辑
2. 使用 read 理解代码结构
3. 使用 edit/write 修改代码
4. 使用 bash 运行测试

重要：
- 复杂任务先调用 plan_enter 切换到 Plan Agent
- 不能直接调用 plan_exit（这是 Plan Agent 的权限）
""",
        allowed_tools=["*"],
        denied_tools=["plan_exit"],
    ),
    "plan": AgentConfig(
        name="plan",
        mode="primary",
        description="规划模式，只读",
        system_prompt="""你是 dm_cc 的规划 Agent。

你的职责：
1. 研究现有代码结构
2. 制定详细的执行计划
3. 将计划写入 .dm_cc/plans/ 目录

限制：
- 不能编辑代码文件（只能编辑计划文件）
- 完成后调用 plan_exit 切换回 Build Agent
""",
        allowed_tools=["read", "glob", "grep", "bash", "plan_exit"],
        denied_tools=["edit", "write"],  # 后续通过路径细化
    ),
}


def get_agent_config(name: str) -> AgentConfig:
    """获取 Agent 配置"""
    if name not in AGENTS:
        raise ValueError(f"Unknown agent: {name}")
    return AGENTS[name]


def list_agents(mode: Literal["primary", "subagent", "all"]) -> list[AgentConfig]:
    """列出 agents - 参考 opencode agent.ts L256-263"""
    if mode == "all":
        return list(AGENTS.values())
    return [a for a in AGENTS.values() if a.mode == mode]
```

#### 4.3.2 Message 模型扩展

**参考源码**: `opencode/packages/opencode/src/session/message-v2.ts`

**文件**: `dm_cc/src/dm_cc/models/message.py`

```python
from dataclasses import dataclass, field
from typing import Literal, Any
from datetime import datetime
import uuid


@dataclass
class Message:
    """消息模型 - 参考 opencode MessageV2"""

    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]

    # Phase 1 新增字段
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent: str = "build"  # 关键：标识此消息的 agent 身份
    synthetic: bool = False  # 是否系统生成（用于 plan 切换）
    timestamp: datetime = field(default_factory=datetime.now)

    def to_anthropic_format(self) -> dict[str, Any]:
        """转换为 Anthropic API 格式"""
        return {
            "role": self.role,
            "content": self.content,
        }

    @classmethod
    def create_synthetic(
        cls,
        agent: str,
        content: str,
    ) -> "Message":
        """创建 synthetic message - 用于 agent 切换"""
        return cls(
            role="user",
            content=content,
            agent=agent,
            synthetic=True,
        )
```

#### 4.3.3 Session 管理

**文件**: `dm_cc/src/dm_cc/session/manager.py`

```python
from dataclasses import dataclass, field
from typing import Any
import uuid

from dm_cc.models.message import Message
from dm_cc.agents.config import get_agent_config


@dataclass
class Session:
    """会话管理 - 简化版 opencode Session"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)
    current_agent: str = "build"
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: Message) -> None:
        """添加消息，如果消息指定了 agent，更新当前 agent"""
        if message.agent:
            self.current_agent = message.agent
        self.messages.append(message)

    def switch_agent(self, agent_name: str, reason: str = "") -> Message:
        """切换 agent - 创建 synthetic message

        参考 opencode plan.ts L104-114
        """
        content = reason or f"Switch to {agent_name} agent"
        message = Message.create_synthetic(agent_name, content)
        self.add_message(message)
        return message

    def get_last_user_message(self) -> Message | None:
        """获取最后一条用户消息 - Loop 用此确定当前 agent"""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg
        return None

    def get_messages_for_llm(self) -> list[dict[str, Any]]:
        """获取用于 LLM 调用的消息列表"""
        return [msg.to_anthropic_format() for msg in self.messages]
```

#### 4.3.4 Plan Enter 工具

**参考源码**: `opencode/packages/opencode/src/tool/plan.ts L75-130`

**文件**: `dm_cc/src/dm_cc/tools/plan_enter.py`

```python
"""Plan Enter Tool - 切换到 Plan Agent

参考 opencode plan.ts 的 PlanEnterTool 实现
"""

from pathlib import Path
from typing import Any
from pydantic import BaseModel

from dm_cc.tools.base import Tool
from dm_cc.session.manager import Session


class EmptyParams(BaseModel):
    """无参数"""
    pass


class PlanEnterTool(Tool):
    """切换到 Plan Agent

    调用方式：由 Build Agent 调用
    效果：创建 synthetic message，agent="plan"，触发 agent 切换
    """

    name = "plan_enter"
    description = """
Use this tool to suggest switching to plan agent when the user's request
would benefit from planning before implementation.

Call this tool when:
- The user's request is complex and would benefit from planning first
- You want to research and design before making changes
- The task involves multiple files or significant architectural decisions

Do NOT call this tool:
- For simple, straightforward tasks
- When the user explicitly wants immediate implementation
"""
    parameters = EmptyParams

    def __init__(self, session: Session):
        self.session = session

    async def execute(self, params: EmptyParams) -> dict[str, Any]:
        """执行 plan_enter - 参考 opencode plan.ts L78-129"""

        # 1. 询问用户确认（简化版，实际实现可能有 UI）
        # 在 CLI 版本中，可以打印提示并等待用户输入
        print("\n[Plan Mode] Would you like to switch to plan agent?")
        print("  Yes - Switch to plan agent for research and planning")
        print("  No  - Stay with build agent")

        # 实际实现中需要获取用户输入
        # 这里简化为假设用户确认
        confirmed = True  # TODO: 实际实现需要交互

        if not confirmed:
            return {
                "title": "Plan mode cancelled",
                "output": "User chose to stay with build agent.",
            }

        # 2. 创建 synthetic message 切换 agent
        # 参考 opencode plan.ts L104-114
        message = self.session.switch_agent(
            agent_name="plan",
            reason="User has requested to enter plan mode. Switch to plan mode and begin planning."
        )

        # 3. 返回结果
        plan_path = Path(".dm_cc/plans/current.md")
        return {
            "title": "Switching to plan agent",
            "output": f"""User confirmed to switch to plan mode.

Plan file location: {plan_path}

You are now in plan mode. You can:
- Read and explore the codebase
- Write plans to {plan_path}
- Call plan_exit when ready to implement

Note: You cannot edit code files in plan mode.
""",
            "metadata": {
                "plan_path": str(plan_path),
                "new_agent": "plan",
            }
        }
```

#### 4.3.5 Plan Exit 工具

**参考源码**: `opencode/packages/opencode/src/tool/plan.ts L20-73`

**文件**: `dm_cc/src/dm_cc/tools/plan_exit.py`

```python
"""Plan Exit Tool - 切换回 Build Agent

参考 opencode plan.ts 的 PlanExitTool 实现
"""

from pathlib import Path
from typing import Any
from pydantic import BaseModel

from dm_cc.tools.base import Tool
from dm_cc.session.manager import Session


class EmptyParams(BaseModel):
    pass


class PlanExitTool(Tool):
    """完成规划，切换回 Build Agent

    调用方式：由 Plan Agent 调用
    效果：创建 synthetic message，agent="build"，触发 agent 切换
    """

    name = "plan_exit"
    description = """
Use this tool when you have completed the planning phase and are ready
to exit plan agent.

Call this tool:
- After you have written a complete plan to the plan file
- After you have clarified any questions with the user
- When you are confident the plan is ready for implementation

Do NOT call this tool:
- Before you have created or finalized the plan
- If you still have unanswered questions about the implementation
"""
    parameters = EmptyParams

    def __init__(self, session: Session):
        self.session = session

    async def execute(self, params: EmptyParams) -> dict[str, Any]:
        """执行 plan_exit - 参考 opencode plan.ts L23-72"""

        plan_path = Path(".dm_cc/plans/current.md")

        # 1. 检查是否有规划文件（可选）
        if not plan_path.exists():
            print("\n[Warning] No plan file found at", plan_path)

        # 2. 询问用户确认
        print(f"\n[Build Agent] Plan at {plan_path} is complete.")
        print("Would you like to switch to the build agent and start implementing?")
        print("  Yes - Switch to build agent")
        print("  No  - Stay with plan agent")

        confirmed = True  # TODO: 实际实现需要交互

        if not confirmed:
            return {
                "title": "Staying in plan mode",
                "output": "User chose to continue refining the plan.",
            }

        # 3. 创建 synthetic message 切换回 build
        # 参考 opencode plan.ts L47-57
        message = self.session.switch_agent(
            agent_name="build",
            reason=f"The plan at {plan_path} has been approved, you can now edit files. Execute the plan"
        )

        return {
            "title": "Switching to build agent",
            "output": f"""User approved switching to build agent.

Plan location: {plan_path}
You can now edit files and execute the plan.
""",
            "metadata": {
                "plan_path": str(plan_path),
                "new_agent": "build",
            }
        }
```

#### 4.3.6 Agent 类改造

**文件**: `dm_cc/src/dm_cc/agent.py`（改造现有 Agent 类）

```python
"""Multi-Agent 支持 - 改造现有 Agent 类

关键变更：
1. 接收 agent_name 参数
2. 根据 agent 配置过滤工具
3. 使用 Session 管理消息历史
"""

from dataclasses import dataclass
from typing import Any

from dm_cc.agents.config import get_agent_config, AgentConfig
from dm_cc.session.manager import Session
from dm_cc.models.message import Message
from dm_cc.tools.base import Tool
from dm_cc.tools.read import ReadTool
from dm_cc.tools.edit import EditTool, UserCancelledError
from dm_cc.tools.write import WriteTool
from dm_cc.tools.glob import GlobTool
from dm_cc.tools.bash import BashTool
from dm_cc.tools.plan_enter import PlanEnterTool
from dm_cc.tools.plan_exit import PlanExitTool


class MultiAgent:
    """多 Agent 支持 - Phase 1 实现

    参考 opencode 的 loop 设计：
    - 通过 Session 管理消息和当前 agent
    - 每次 loop 读取 session.current_agent 确定身份
    - 根据 agent 配置过滤可用工具
    """

    ALL_TOOLS: list[type[Tool]] = [
        ReadTool,
        EditTool,
        WriteTool,
        GlobTool,
        BashTool,
        PlanEnterTool,
        PlanExitTool,
    ]

    def __init__(self, session: Session):
        self.session = session
        self.config = get_agent_config(session.current_agent)
        self.tools = self._load_tools()

    def _load_tools(self) -> dict[str, Tool]:
        """根据 agent 配置加载可用工具"""
        tools = {}

        for tool_class in self.ALL_TOOLS:
            tool = tool_class()

            # 检查是否允许使用
            if self._can_use_tool(tool.name):
                tools[tool.name] = tool

        return tools

    def _can_use_tool(self, tool_name: str) -> bool:
        """检查 agent 是否有权使用工具"""
        # denied 优先级高于 allowed
        if tool_name in self.config.denied_tools:
            return False

        if "*" in self.config.allowed_tools:
            return True

        return tool_name in self.config.allowed_tools

    def get_system_prompt(self) -> str:
        """获取当前 agent 的 system prompt"""
        return self.config.system_prompt

    def get_current_agent(self) -> str:
        """获取当前 agent 名称"""
        return self.session.current_agent

    async def run(self, user_input: str) -> str:
        """运行 agent loop

        流程：
        1. 添加用户消息
        2. 检查是否需要切换 agent（处理 synthetic message）
        3. 根据当前 agent 获取工具和 system prompt
        4. 调用 LLM
        5. 处理工具调用
        6. 循环直到完成
        """
        # 添加用户消息
        self.session.add_message(Message(
            role="user",
            content=user_input,
            agent=self.session.current_agent,
        ))

        # 如果 agent 发生变化，重新加载工具和 prompt
        if self.session.current_agent != self.config.name:
            self.config = get_agent_config(self.session.current_agent)
            self.tools = self._load_tools()

        # ... 原有的 LLM 调用和工具执行逻辑
        # 但使用 self.tools（已过滤的）
        # 和 self.get_system_prompt()（当前 agent 的）
```

### 4.4 Phase 1 验证方式

#### 测试用例 1：Plan 进入
```python
# 场景：Build Agent 识别到复杂任务，调用 plan_enter
session = Session()
agent = MultiAgent(session)

# Build Agent 调用 plan_enter
result = await agent.tools["plan_enter"].execute(EmptyParams())

# 验证
assert session.current_agent == "plan"
assert len(session.messages) == 2  # 用户消息 + synthetic 切换消息
assert session.messages[1].synthetic == True
```

#### 测试用例 2：Plan Agent 工具限制
```python
# Plan Agent 不能使用的工具
agent = MultiAgent(session)  # session.current_agent == "plan"

assert "edit" not in agent.tools  # 被过滤掉
assert "write" not in agent.tools
assert "read" in agent.tools       # 允许使用
assert "plan_exit" in agent.tools  # 允许使用
```

#### 测试用例 3：Plan 退出
```python
# Plan Agent 调用 plan_exit
result = await agent.tools["plan_exit"].execute(EmptyParams())

assert session.current_agent == "build"
```

---

## 5. Phase 2: 权限系统

### 5.1 目标

实现细粒度的权限控制，支持：
- 工具级别的权限（edit/bash/read）
- 路径级别的权限（`*.py`, `src/*`）
- 三态评估（allow/deny/ask）
- 用户批准的持久化

### 5.2 参考实现

**源码**: `opencode/packages/opencode/src/permission/next.ts`

```typescript
// 核心类型
export const Rule = z.object({
  permission: z.string(),
  pattern: z.string(),
  action: z.enum(["allow", "deny", "ask"]),
})

// 评估函数
export function evaluate(
  permission: string,
  pattern: string,
  ...rulesets: Ruleset[]
): Rule {
  const merged = merge(...rulesets)
  const match = merged.findLast(
    (rule) => Wildcard.match(permission, rule.permission) &&
              Wildcard.match(pattern, rule.pattern)
  )
  return match ?? { action: "ask", permission, pattern: "*" }
}
```

### 5.3 实现清单

#### 5.3.1 权限引擎

**文件**: `dm_cc/src/dm_cc/permissions/engine.py`

```python
"""权限系统 - 参考 opencode permission/next.ts"""

from dataclasses import dataclass
from typing import Literal
import fnmatch


Action = Literal["allow", "deny", "ask"]


@dataclass(frozen=True)
class PermissionRule:
    """权限规则"""
    permission: str  # 工具名或 "*"
    pattern: str     # 路径/参数模式或 "*"
    action: Action


class PermissionEngine:
    """权限评估引擎 - Last Match Wins"""

    @staticmethod
    def evaluate(
        tool_name: str,
        target: str,  # 文件路径或参数
        rules: list[PermissionRule],
    ) -> Action:
        """
        评估权限

        算法：
        1. 逆序遍历规则（后定义优先）
        2. 找到第一个匹配 permission 和 pattern 的规则
        3. 返回其 action
        4. 无匹配则返回 "ask"

        参考 opencode permission/next.ts L44-72
        """
        for rule in reversed(rules):
            if PermissionEngine._match(rule.permission, tool_name) and \
               PermissionEngine._match(rule.pattern, target):
                return rule.action

        return "ask"  # 默认询问

    @staticmethod
    def _match(pattern: str, target: str) -> bool:
        """匹配规则 - 支持通配符"""
        if pattern == "*":
            return True
        return fnmatch.fnmatch(target, pattern)
```

#### 5.3.2 增强 Agent 配置

**文件**: `dm_cc/src/dm_cc/agents/config.py`（扩展 Phase 1）

```python
from dm_cc.permissions.engine import PermissionRule

# 新的 Agent 配置格式
AGENTS: dict[str, AgentConfig] = {
    "build": AgentConfig(
        name="build",
        mode="primary",
        description="默认执行 Agent",
        system_prompt="...",
        # Phase 2: 使用权限规则替代简单列表
        permissions=[
            PermissionRule("*", "*", "allow"),           # 默认允许
            PermissionRule("plan_exit", "*", "deny"),    # 但不能 exit plan
        ],
    ),
    "plan": AgentConfig(
        name="plan",
        mode="primary",
        description="规划模式",
        system_prompt="...",
        permissions=[
            PermissionRule("*", "*", "allow"),           # 默认允许
            PermissionRule("edit", "*", "deny"),         # 但禁止 edit
            PermissionRule("write", "*", "deny"),        # 禁止 write
            # 例外：允许编辑计划文件
            PermissionRule("edit", ".dm_cc/plans/*.md", "allow"),
            PermissionRule("write", ".dm_cc/plans/*.md", "allow"),
            PermissionRule("plan_exit", "*", "allow"),   # 允许退出
        ],
    ),
}
```

#### 5.3.3 用户权限存储

**文件**: `dm_cc/src/dm_cc/permissions/user_store.py`

```python
"""用户权限存储 - 持久化用户已批准的权限"""

from dataclasses import dataclass
from pathlib import Path
import json

from dm_cc.permissions.engine import PermissionRule, Action


class UserPermissionStore:
    """用户已批准的权限

    参考 opencode permission/next.ts 中的 approved 状态
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.approved: list[PermissionRule] = []
        self._load()

    def approve(
        self,
        permission: str,
        pattern: str = "*",
        persistent: bool = False,
    ) -> None:
        """批准权限

        Args:
            persistent: 是否持久化到文件
        """
        rule = PermissionRule(permission, pattern, "allow")
        self.approved.append(rule)

        if persistent:
            self._save()

    def is_approved(self, permission: str, pattern: str) -> bool:
        """检查是否已批准"""
        for rule in reversed(self.approved):
            if rule.permission == permission and \
               self._match(rule.pattern, pattern):
                return rule.action == "allow"
        return False

    def _load(self) -> None:
        """从文件加载"""
        path = Path(f".dm_cc/sessions/{self.session_id}/permissions.json")
        if path.exists():
            data = json.loads(path.read_text())
            self.approved = [
                PermissionRule(**rule) for rule in data.get("approved", [])
            ]

    def _save(self) -> None:
        """保存到文件"""
        path = Path(f".dm_cc/sessions/{self.session_id}/permissions.json")
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "approved": [
                {"permission": r.permission, "pattern": r.pattern, "action": r.action}
                for r in self.approved
            ]
        }
        path.write_text(json.dumps(data, indent=2))
```

#### 5.3.4 工具权限检查

**文件**: `dm_cc/src/dm_cc/agent.py`（更新工具执行逻辑）

```python
from dm_cc.permissions.engine import PermissionEngine, Action
from dm_cc.permissions.user_store import UserPermissionStore


class MultiAgent:
    def __init__(self, session: Session, user_store: UserPermissionStore):
        self.session = session
        self.user_store = user_store
        self.permission_engine = PermissionEngine()

    async def _execute_tool_with_permission(
        self,
        tool: Tool,
        params: dict,
    ) -> dict[str, Any]:
        """带权限检查的工具执行"""

        # 1. 获取目标路径/参数
        target = params.get("filePath", params.get("command", "*"))

        # 2. 评估权限
        # 合并 agent 配置和用户已批准的权限
        all_rules = self.config.permissions + self.user_store.approved

        action = self.permission_engine.evaluate(
            tool_name=tool.name,
            target=target,
            rules=all_rules,
        )

        # 3. 处理评估结果
        if action == "deny":
            raise PermissionDenied(
                f"Tool '{tool.name}' with target '{target}' is denied"
            )

        if action == "ask":
            # 询问用户
            confirmed = await self._ask_user_permission(tool.name, target)
            if not confirmed:
                raise UserCancelledError("Permission denied by user")

            # 记录用户批准
            self.user_store.approve(tool.name, target, persistent=True)

        # 4. 执行工具
        return await tool.execute(params)

    async def _ask_user_permission(
        self,
        tool_name: str,
        target: str,
    ) -> bool:
        """询问用户是否批准权限"""
        print(f"\n[Permission Request]")
        print(f"Tool: {tool_name}")
        print(f"Target: {target}")
        print("\nAllow this action?")
        print("  [1] once    - Allow this time only")
        print("  [2] always  - Allow for this target pattern")
        print("  [3] reject  - Deny this action")

        # TODO: 获取用户输入
        choice = input("> ").strip()
        return choice in ["1", "2"]
```

### 5.5 Phase 2 验证方式

#### 测试用例 1：Last Match Wins
```python
rules = [
    PermissionRule("edit", "*", "deny"),
    PermissionRule("edit", "*.md", "allow"),
]

engine = PermissionEngine()

assert engine.evaluate("edit", "main.py", rules) == "deny"
assert engine.evaluate("edit", "README.md", rules) == "allow"
```

#### 测试用例 2：权限询问与持久化
```python
store = UserPermissionStore("session-123")

# 用户批准
store.approve("bash", "ls *", persistent=True)

# 重新加载
store2 = UserPermissionStore("session-123")
assert store2.is_approved("bash", "ls -la")
```

---

## 6. Phase 3: Subagent

### 6.1 目标

实现 Task 工具，支持：
- 创建独立的 Child Session
- 并行执行多个 Subagent
- Subagent 与 Parent 的权限继承

### 6.2 参考实现

**源码**: `opencode/packages/opencode/src/tool/task.ts`

```typescript
// 创建 child session
const session = await Session.create({
  parentID: ctx.sessionID,
  title: params.description + ` (@${agent.name} subagent)`,
  permission: [
    { permission: "todowrite", pattern: "*", action: "deny" },
    { permission: "todoread", pattern: "*", action: "deny" },
    ...(hasTaskPermission ? [] : [{ permission: "task", pattern: "*", action: "deny" }]),
  ],
})

// 运行 subagent
const result = await SessionPrompt.prompt({
  sessionID: session.id,
  agent: agent.name,
  tools: { todowrite: false, todoread: false, ... },
  parts: promptParts,
})
```

### 6.3 实现清单

#### 6.3.1 Subagent Agent 配置

**文件**: `dm_cc/src/dm_cc/agents/config.py`（扩展）

```python
# 新增 Subagent 配置
AGENTS.update({
    "explore": AgentConfig(
        name="explore",
        mode="subagent",  # 关键：mode="subagent"
        description="代码探索专家，只读访问",
        system_prompt="""你是代码探索助手。

你的职责：
1. 快速理解代码库结构
2. 查找特定文件或代码片段
3. 回答关于代码的问题

限制：
- 只能读取文件，不能修改
- 使用 glob/grep/read 等工具
- 完成后返回发现总结
""",
        permissions=[
            PermissionRule("read", "*", "allow"),
            PermissionRule("glob", "*", "allow"),
            PermissionRule("grep", "*", "allow"),
            PermissionRule("bash", "*", "allow"),  # 允许 ls/find 等
            PermissionRule("*", "*", "deny"),      # 其他全部禁止
        ],
    ),
    "general": AgentConfig(
        name="general",
        mode="subagent",
        description="通用任务代理",
        system_prompt="通用任务执行助手...",
        permissions=[
            PermissionRule("*", "*", "allow"),     # 大部分允许
            PermissionRule("task", "*", "deny"),   # 但不能创建子任务
        ],
    ),
})
```

#### 6.3.2 Child Session

**文件**: `dm_cc/src/dm_cc/session/child.py`

```python
"""Child Session - Subagent 使用的独立会话

参考 opencode task.ts L66-102
"""

from dataclasses import dataclass, field
from typing import Any
import uuid

from dm_cc.session.manager import Session
from dm_cc.models.message import Message
from dm_cc.agents.config import AgentConfig


@dataclass
class ChildSession:
    """子会话 - 由 Task 工具创建

    特点：
    1. 独立的 session ID
    2. 独立的 message 历史
    3. 只收到 prompt，无 parent 历史
    4. 继承 parent 的部分权限
    """

    parent_id: str
    agent: AgentConfig
    prompt: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[Message] = field(default_factory=list)
    result: str | None = None

    def __post_init__(self):
        """初始化时添加 system message 和 user prompt"""
        # System message
        self.messages.append(Message(
            role="assistant",  # Anthropic 用 assistant 放 system
            content=self.agent.system_prompt,
            agent=self.agent.name,
        ))

        # User prompt
        self.messages.append(Message(
            role="user",
            content=self.prompt,
            agent=self.agent.name,
        ))

    async def run(self, llm_client) -> str:
        """执行 subagent 任务"""
        # 创建临时的 MultiAgent 实例
        from dm_cc.agent import MultiAgent

        # 使用独立的 Session
        temp_session = Session()
        temp_session.messages = self.messages
        temp_session.current_agent = self.agent.name

        agent = MultiAgent(temp_session)

        # 执行直到完成（简化版）
        # 实际实现需要完整的 loop 逻辑
        self.result = await self._run_loop(agent, llm_client)
        return self.result

    async def _run_loop(self, agent, llm_client) -> str:
        """运行 agent loop"""
        # 简化实现：调用一次 LLM 获取结果
        # 实际应该支持多轮工具调用
        messages = [m.to_anthropic_format() for m in agent.session.messages]

        response = await llm_client.complete(
            messages=messages,
            tools=list(agent.tools.values()),
            system_prompt=agent.get_system_prompt(),
        )

        return response.text
```

#### 6.3.3 Task 工具

**文件**: `dm_cc/src/dm_cc/tools/task.py`

```python
"""Task Tool - 创建并运行 Subagent

参考 opencode task.ts L45-165
"""

from typing import Any
from pydantic import BaseModel, Field

from dm_cc.tools.base import Tool
from dm_cc.session.manager import Session
from dm_cc.session.child import ChildSession
from dm_cc.agents.config import get_agent_config, list_agents
from dm_cc.permissions.engine import PermissionRule


class TaskParams(BaseModel):
    """Task 工具参数"""
    description: str = Field(
        ...,
        description="简短描述（3-5词）"
    )
    prompt: str = Field(
        ...,
        description="任务的详细描述"
    )
    subagent_type: str = Field(
        ...,
        description="Subagent 类型（如 explore, general）"
    )
    task_id: str | None = Field(
        None,
        description="恢复已有任务（传递之前的 task_id）"
    )


class TaskTool(Tool):
    """启动 Subagent 处理任务

    特点：
    1. 创建独立的 Child Session
    2. Subagent 只能访问指定的工具
    3. 支持 task_id 恢复任务
    4. 并行执行多个 Task
    """

    name = "task"
    description = """Launch a specialized agent to handle complex, multi-step tasks autonomously.

Use the Task tool in these scenarios:
1. Custom slash commands
2. Parallel execution: launch multiple agents concurrently
3. Complex multi-step tasks

Available subagents:
{agents}

When NOT to use:
- If you want to read a specific file path (use Read instead)
- If you are searching for a specific class (use Glob instead)
"""
    parameters = TaskParams

    def __init__(self, session: Session, llm_client):
        self.session = session
        self.llm_client = llm_client

        # 动态生成 description，列出可用 subagents
        subagents = list_agents("subagent")
        self.description = self.description.format(
            agents="\n".join([
                f"- {a.name}: {a.description}"
                for a in subagents
            ])
        )

    async def execute(self, params: TaskParams) -> dict[str, Any]:
        """执行 Task - 参考 opencode task.ts"""

        # 1. 获取 subagent 配置
        try:
            agent_config = get_agent_config(params.subagent_type)
        except ValueError:
            available = [a.name for a in list_agents("subagent")]
            raise ValueError(
                f"Unknown subagent: {params.subagent_type}. "
                f"Available: {available}"
            )

        # 验证是 subagent
        if agent_config.mode != "subagent":
            raise ValueError(
                f"'{params.subagent_type}' is not a subagent"
            )

        # 2. 检查 caller 是否有权限使用此 subagent
        # （简化版，实际应检查 permission）

        # 3. 获取或创建 Child Session
        if params.task_id:
            # 恢复已有任务
            child_session = self._load_child_session(params.task_id)
        else:
            # 创建新的 Child Session
            child_session = ChildSession(
                parent_id=self.session.id,
                agent=agent_config,
                prompt=params.prompt,
            )

        # 4. 运行 subagent
        # 注意：这里可以并行执行
        result = await child_session.run(self.llm_client)

        # 5. 返回结果
        return {
            "title": params.description,
            "output": f"""task_id: {child_session.id} (for resuming)

<task_result>
{result}
</task_result>
""",
            "metadata": {
                "task_id": child_session.id,
                "subagent": params.subagent_type,
            }
        }

    def _load_child_session(self, task_id: str) -> ChildSession:
        """从存储加载 Child Session"""
        # TODO: 实现从文件/数据库加载
        raise NotImplementedError("Task resume not yet implemented")
```

#### 6.3.4 并行 Task 支持

**文件**: `dm_cc/src/dm_cc/agent.py`（添加并行方法）

```python
import asyncio


class MultiAgent:
    async def run_parallel_tasks(
        self,
        task_params_list: list[TaskParams],
    ) -> list[dict[str, Any]]:
        """并行执行多个 Task

        示例：
        >>> tasks = [
        ...     TaskParams("分析 frontend", "探索 src/frontend", "explore"),
        ...     TaskParams("分析 backend", "探索 src/backend", "explore"),
        ... ]
        >>> results = await agent.run_parallel_tasks(tasks)
        """

        async def run_single(params: TaskParams) -> dict[str, Any]:
            tool = TaskTool(self.session, self.llm_client)
            return await tool.execute(params)

        # 同时启动所有 task
        results = await asyncio.gather(*[
            run_single(params)
            for params in task_params_list
        ])

        return results
```

### 6.4 Phase 3 验证方式

#### 测试用例 1：单 Task 执行
```python
session = Session()
tool = TaskTool(session, llm_client)

result = await tool.execute(TaskParams(
    description="探索 src 目录",
    prompt="分析 src 目录下的所有 Python 文件结构",
    subagent_type="explore",
))

assert "task_id" in result["metadata"]
assert "<task_result>" in result["output"]
```

#### 测试用例 2：并行 Task
```python
agent = MultiAgent(session, llm_client)

tasks = [
    TaskParams("分析 A", "分析模块 A", "explore"),
    TaskParams("分析 B", "分析模块 B", "explore"),
    TaskParams("分析 C", "分析模块 C", "explore"),
]

import time
start = time.time()
results = await agent.run_parallel_tasks(tasks)
elapsed = time.time() - start

# 验证并行：总时间应该接近单个任务时间，不是 3 倍
assert elapsed < 3 * single_task_time
```

#### 测试用例 3：Child Session 隔离
```python
# Parent Session 有复杂历史
parent_session = Session()
parent_session.add_message(Message(role="user", content="历史消息 1"))
parent_session.add_message(Message(role="assistant", content="历史回复 1"))
# ... 更多消息

# Child Session 只收到 prompt
child = ChildSession(
    parent_id=parent_session.id,
    agent=get_agent_config("explore"),
    prompt="只看到这个",
)

assert len(child.messages) == 2  # system + prompt
assert "历史消息 1" not in str(child.messages)
```

---

## 7. 技术决策记录

### 7.1 ADR-001: Agent 切换机制

**决策**: 使用 Message-based 切换（synthetic message）

**参考**: `opencode/packages/opencode/src/tool/plan.ts L104-114`

```typescript
const userMsg: MessageV2.User = {
  sessionID: ctx.sessionID,  // 同一个 session
  agent: "plan",             // 只是改 agent 字段
  // ...
}
await Session.updateMessage(userMsg)
```

**理由**:
- 保持消息流完整可追溯
- 实现简单，无需复杂状态管理
- 与 opencode 保持一致，便于理解

**替代方案**:
- 直接修改 session.current_agent：会破坏消息流的可追溯性
- 创建新 session：会丢失历史上下文

### 7.2 ADR-002: 权限评估策略

**决策**: Last-Match-Wins

**参考**: `opencode/packages/opencode/src/permission/next.ts L44-72`

```typescript
const match = merged.findLast(
  (rule) => Wildcard.match(permission, rule.permission) &&
            Wildcard.match(pattern, rule.pattern)
)
```

**理由**:
- 符合直觉（后定义的规则覆盖先定义的）
- 配置灵活，可以"先禁止所有，再允许特定"

**替代方案**:
- First-Match-Wins：不符合直觉，配置起来更复杂
- 优先级数字：增加了配置复杂度

### 7.3 ADR-003: Subagent 上下文隔离

**决策**: 完全隔离，只传 prompt

**参考**: `opencode/packages/opencode/src/tool/task.ts L128-143`

```typescript
const result = await SessionPrompt.prompt({
  sessionID: session.id,    // 新 session
  parts: promptParts,       // 只传 prompt
})
```

**理由**:
- 并行执行安全，无状态竞争
- 减少 token 消耗
- 强制用户明确传递上下文，避免隐式依赖

**替代方案**:
- 传递部分历史：增加了复杂性，且可能包含无关信息
- 共享 Session：退化成 Plan 模式，失去并行能力

### 7.4 ADR-004: Agent Mode 分类

**决策**: 三类 mode（primary/subagent/all）

**参考**: `opencode/packages/opencode/src/agent/agent.ts L28`

```typescript
mode: z.enum(["subagent", "primary", "all"])
```

**理由**:
- `primary`: 用户可直接使用
- `subagent`: 只能通过 task 调用，防止误用
- `all`: 用户自定义 agent 的灵活性

---

## 8. 验收标准

### Phase 1: Multi-Agent 基础

- [ ] **Agent 配置**: `dm_cc/agents/config.py` 可以定义多个 agent
- [ ] **Message 扩展**: Message 类有 `agent` 和 `synthetic` 字段
- [ ] **Session 管理**: Session 类可以管理消息历史和当前 agent
- [ ] **Plan Enter**: Build Agent 可以调用 plan_enter 切换到 Plan Agent
- [ ] **Plan Exit**: Plan Agent 可以调用 plan_exit 切换回 Build Agent
- [ ] **工具过滤**: Plan Agent 只能使用 read/glob/grep，不能使用 edit/write
- [ ] **System Prompt**: 不同 agent 使用不同的 system prompt

### Phase 2: 权限系统

- [ ] **权限引擎**: PermissionEngine 可以评估规则
- [ ] **Last Match Wins**: 后定义的规则覆盖先定义的
- [ ] **三态评估**: 支持 allow/deny/ask
- [ ] **路径权限**: 可以控制 `*.py` 或 `src/*` 的访问
- [ ] **用户批准**: 可以持久化用户批准的权限
- [ ] **权限询问**: ask 时会提示用户
- [ ] **Plan 文件例外**: Plan Agent 可以编辑 `.dm_cc/plans/*.md`

### Phase 3: Subagent

- [ ] **Subagent 定义**: 可以配置 mode="subagent" 的 agent
- [ ] **Task 工具**: TaskTool 可以创建 Child Session
- [ ] **Context 隔离**: Child Session 只收到 prompt，无 parent 历史
- [ ] **并行执行**: 可以同时运行多个 Task
- [ ] **结果返回**: Subagent 结果正确返回 parent
- [ ] **Task ID**: 可以通过 task_id 恢复任务
- [ ] **权限继承**: Child Session 继承 parent 部分权限

---

## 附录 A: Opencode 源码速查

### 核心文件导航

```
opencode/packages/opencode/src/
├── agent/
│   └── agent.ts              # Agent 定义和配置
├── permission/
│   └── next.ts               # 权限系统
├── session/
│   ├── prompt.ts             # Loop 和 Agent 切换
│   └── message-v2.ts         # 消息模型
└── tool/
    ├── plan.ts               # Plan 工具
    └── task.ts               # Task 工具
```

### 关键函数/类

| 名称 | 文件 | 行号 | 说明 |
|------|------|------|------|
| `Agent.Info` | agent.ts | L24-49 | Agent 配置 Schema |
| `PermissionNext.evaluate` | next.ts | L44-72 | 权限评估核心 |
| `PlanEnterTool` | plan.ts | L75-130 | 进入 Plan 模式 |
| `PlanExitTool` | plan.ts | L20-73 | 退出 Plan 模式 |
| `TaskTool` | task.ts | L45-165 | 创建 Subagent |
| `Session.create` | session.ts | - | 创建 Child Session |

---

*计划创建日期: 2026-02-26*
*参考 Opencode 版本: commit-ish (最新 main)*
