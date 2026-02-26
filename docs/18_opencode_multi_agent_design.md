# Opencode Multi-Agent 设计深度解析

## 目录

1. [架构概述](#1-架构概述)
2. [Agent 定义与配置](#2-agent-定义与配置)
3. [权限系统](#3-权限系统)
4. [Plan 机制](#4-plan-机制)
5. [Task 机制](#5-task-机制)
6. [Loop 集成](#6-loop-集成)
7. [设计原则总结](#7-设计原则总结)

---

## 1. 架构概述

Opencode 的 Multi-Agent 系统采用**基于权限的 agent 切换**架构：

```
┌─────────────────────────────────────────────────────────────────┐
│                        Session (会话)                            │
│  ┌─────────────┐    plan_enter/plan_exit    ┌─────────────┐     │
│  │ Build Agent │  <───────────────────────> │  Plan Agent │     │
│  │  (primary)  │                            │  (primary)  │     │
│  └──────┬──────┘                            └─────────────┘     │
│         │                                                        │
│         │ task                                                   │
│         ▼                                                        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Subagent Sessions                     │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │    │
│  │  │ explore  │  │ general  │  │  bash    │  │   ...    │  │    │
│  │  │(subagent)│  │(subagent)│  │(subagent)│  │(subagent)│  │    │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

**核心概念：**
- **Agent = 权限 + 行为配置**：不是独立的进程，而是同一 loop 的不同"身份"
- **模式切换**：通过创建新的 UserMessage 改变 `agent` 字段实现
- **权限隔离**：不同 agent 有不同的工具访问权限
- **会话层级**：Subagent 创建 child session，形成层级结构

---

## 2. Agent 定义与配置

### 2.1 Agent Schema

```typescript
// packages/opencode/src/agent/agent.ts
export const Info = z.object({
  name: z.string(),                    // 唯一标识
  description: z.string().optional(),  // 描述
  mode: z.enum(["subagent", "primary", "all"]),  // 模式
  native: z.boolean().optional(),      // 是否原生 agent
  hidden: z.boolean().optional(),      // 是否隐藏
  permission: PermissionNext.Ruleset,  // 权限规则集
  model: z.object({                    // 专用模型配置
    modelID: z.string(),
    providerID: z.string(),
  }).optional(),
  prompt: z.string().optional(),       // 自定义 system prompt
  steps: z.number().int().positive().optional(),  // 最大步数
  // ... 其他配置
})
```

### 2.2 Agent Mode 详解

| Mode | 说明 | 使用场景 |
|------|------|----------|
| **primary** | 可作为主 agent，用户可直接使用 | build, plan |
| **subagent** | 只能通过 `task` 工具调用 | explore, general, bash |
| **all** | 两者皆可 | 用户自定义 agent |

**关键区别：**
```typescript
// 只有 primary 可以被设为 default agent
const primaryVisible = Object.values(agents).find(
  (a) => a.mode !== "subagent" && a.hidden !== true
)

// subagent 只能在 task 工具中选择
const agents = await Agent.list().then(
  (x) => x.filter((a) => a.mode !== "primary")  // 过滤掉 primary
)
```

### 2.3 原生 Agent 配置

#### Build Agent (默认执行 agent)
```typescript
build: {
  name: "build",
  mode: "primary",
  description: "The default agent. Executes tools based on configured permissions.",
  permission: PermissionNext.merge(
    defaults,  // 基础权限: "*": "allow"
    PermissionNext.fromConfig({
      question: "allow",
      plan_enter: "allow",  // 可进入 plan 模式
    }),
    user,  // 用户自定义覆盖
  ),
}
```

#### Plan Agent (规划模式)
```typescript
plan: {
  name: "plan",
  mode: "primary",
  description: "Plan mode. Disallows all edit tools.",
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      question: "allow",
      plan_exit: "allow",  // 可退出 plan 模式
      edit: {
        "*": "deny",  // 禁止编辑所有文件
        ".opencode/plans/*.md": "allow",  // 除了 plan 文件
      },
    }),
    user,
  ),
}
```

#### Explore Agent (代码探索)
```typescript
explore: {
  name: "explore",
  mode: "subagent",
  description: "Fast agent specialized for exploring codebases...",
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      "*": "deny",  // 默认拒绝所有
      // 只允许只读工具
      grep: "allow",
      glob: "allow",
      list: "allow",
      bash: "allow",
      webfetch: "allow",
      websearch: "allow",
      codesearch: "allow",
      read: "allow",
    }),
    user,
  ),
}
```

### 2.4 权限对比表

| 工具 | build | plan | explore | general |
|------|-------|------|---------|---------|
| read | ✓ | ✓ | ✓ | ✓ |
| edit | ✓ | ✗* | ✗ | ✓ |
| write | ✓ | ✗* | ✗ | ✓ |
| bash | ✓ | ✓ | ✓ | ✓ |
| grep/glob | ✓ | ✓ | ✓ | ✓ |
| plan_enter | ✓ | ✗ | ✗ | ✗ |
| plan_exit | ✗ | ✓ | ✗ | ✗ |
| task | ✓ | ✓ | ✗ | ✗ |

*plan agent 只能编辑 `.opencode/plans/*.md` 文件

---

## 3. 权限系统

### 3.1 核心类型

```typescript
// packages/opencode/src/permission/next.ts
export const Action = z.enum(["allow", "deny", "ask"])

export const Rule = z.object({
  permission: z.string(),  // 工具名或权限类型
  pattern: z.string(),     // 匹配模式
  action: Action,          // allow/deny/ask
})

export const Ruleset = Rule.array()
```

### 3.2 权限评估逻辑 (Last-Match-Wins)

```typescript
export function evaluate(
  permission: string,
  pattern: string,
  ...rulesets: Ruleset[]
): Rule {
  const merged = merge(...rulesets)

  // 找到**最后一个**匹配的规则
  const match = merged.findLast((rule) =>
    Wildcard.match(permission, rule.permission) &&
    Wildcard.match(pattern, rule.pattern)
  )

  // 默认 ask
  return match ?? { action: "ask", permission, pattern: "*" }
}
```

**示例：**
```typescript
const ruleset = [
  { permission: "edit", pattern: "*", action: "deny" },      // 先匹配
  { permission: "edit", pattern: "*.md", action: "allow" },  // 后匹配 - 生效！
]

evaluate("edit", "README.md", ruleset)  // → allow
```

### 3.3 配置格式转换

```typescript
export function fromConfig(permission: Config.Permission): Ruleset {
  const ruleset: Ruleset = []

  for (const [key, value] of Object.entries(permission)) {
    if (typeof value === "string") {
      // 简单形式: "permission": "action"
      ruleset.push({ permission: key, action: value, pattern: "*" })
    } else {
      // 嵌套形式: "permission": { "pattern": "action" }
      ruleset.push(
        ...Object.entries(value).map(([pattern, action]) => ({
          permission: key,
          pattern: expand(pattern),  // 展开 ~/ $HOME
          action,
        }))
      )
    }
  }
  return ruleset
}
```

**配置示例 → 规则转换：**
```yaml
# 用户配置
permission:
  edit: deny
  bash:
    "ls *": allow
    "rm *": ask

# 转换为规则
[
  { permission: "edit", pattern: "*", action: "deny" },
  { permission: "bash", pattern: "ls *", action: "allow" },
  { permission: "bash", pattern: "rm *", action: "ask" },
]
```

### 3.4 权限请求流程

```typescript
export const ask = fn(Request.partial({ id: true }).extend({
  ruleset: Ruleset,
}), async (input) => {
  const s = await state()
  const { ruleset, ...request } = input

  for (const pattern of request.patterns ?? []) {
    // 评估：已批准的 + 当前规则集
    const rule = evaluate(
      request.permission,
      pattern,
      ruleset,           // 当前 agent/session 的规则
      s.approved         // 用户已批准的规则
    )

    if (rule.action === "deny") {
      throw new DeniedError(/* ... */)
    }

    if (rule.action === "ask") {
      // 发布事件到 UI，等待用户响应
      Bus.publish(Event.Asked, info)
      return new Promise<void>((resolve, reject) => {
        s.pending[id] = { info, resolve, reject }
      })
    }

    // allow → 继续检查下一个 pattern
  }
})
```

### 3.5 用户响应处理

```typescript
// 用户可以选择
export const Reply = z.enum(["once", "always", "reject"])

// always → 添加到已批准规则集
if (input.reply === "always") {
  for (const pattern of existing.info.always) {
    s.approved.push({
      permission: existing.info.permission,
      pattern,
      action: "allow",
    })
  }

  // 检查是否有其他 pending 请求现在可以批准
  for (const [id, pending] of Object.entries(s.pending)) {
    const ok = pending.info.patterns.every(
      (pattern) => evaluate(pending.info.permission, pattern, s.approved).action === "allow"
    )
    if (ok) {
      delete s.pending[id]
      pending.resolve()
    }
  }
}
```

---

## 4. Plan 机制

### 4.1 核心思想

**Plan 不是独立的 agent，而是同一 loop 的不同"模式"：**

```
Build Mode                    Plan Mode
───────────                   ─────────
可编辑任何文件        →        只读 + 只能写 plan 文件
直接执行用户请求      →        先研究再规划
使用 edit/write/bash  →        使用 read/grep/glob
```

### 4.2 PlanEnterTool 实现

```typescript
// packages/opencode/src/tool/plan.ts
export const PlanEnterTool = Tool.define("plan_enter", {
  description: ENTER_DESCRIPTION,
  parameters: z.object({}),  // 无参数

  async execute(_params, ctx) {
    // 1. 询问用户确认
    const answers = await Question.ask({
      sessionID: ctx.sessionID,
      questions: [{
        question: `Would you like to switch to the plan agent...`,
        header: "Plan Mode",
        options: [
          { label: "Yes", description: "Switch to plan agent..." },
          { label: "No", description: "Stay with build agent..." },
        ],
      }],
    })

    if (answers[0]?.[0] === "No") {
      throw new Question.RejectedError()
    }

    // 2. 创建 synthetic user message 切换 agent
    const userMsg: MessageV2.User = {
      id: Identifier.ascending("message"),
      sessionID: ctx.sessionID,
      role: "user",
      agent: "plan",  // ← 关键：切换到 plan agent
      model,
      // ...
    }
    await Session.updateMessage(userMsg)

    // 3. 添加切换指令
    await Session.updatePart({
      messageID: userMsg.id,
      type: "text",
      text: "User has requested to enter plan mode. Switch to plan mode and begin planning.",
      synthetic: true,  // 标记为系统生成
    })

    return {
      title: "Switching to plan agent",
      output: "User confirmed to switch to plan mode...",
    }
  },
})
```

### 4.3 PlanExitTool 实现

```typescript
export const PlanExitTool = Tool.define("plan_exit", {
  description: EXIT_DESCRIPTION,
  parameters: z.object({}),

  async execute(_params, ctx) {
    // 1. 询问用户确认
    const answers = await Question.ask({
      sessionID: ctx.sessionID,
      questions: [{
        question: `Plan is complete. Would you like to switch to the build agent?`,
        header: "Build Agent",
        options: [
          { label: "Yes", description: "Switch to build agent..." },
          { label: "No", description: "Stay with plan agent..." },
        ],
      }],
    })

    if (answers[0]?.[0] === "No") {
      throw new Question.RejectedError()
    }

    // 2. 创建 synthetic user message 切回 build
    const userMsg: MessageV2.User = {
      id: Identifier.ascending("message"),
      sessionID: ctx.sessionID,
      role: "user",
      agent: "build",  // ← 关键：切回 build agent
      model,
      // ...
    }
    await Session.updateMessage(userMsg)

    // 3. 添加执行指令
    await Session.updatePart({
      messageID: userMsg.id,
      type: "text",
      text: `The plan has been approved, you can now edit files. Execute the plan`,
      synthetic: true,
    })

    return {
      title: "Switching to build agent",
      output: "User approved switching to build agent...",
    }
  },
})
```

### 4.4 Plan 工具的描述文件

**plan-enter.txt:**
```
Use this tool to suggest switching to plan agent when the user's request
would benefit from planning before implementation.

Call this tool when:
- The user's request is complex and would benefit from planning first
- You want to research and design before making changes
- The task involves multiple files or significant architectural decisions

Do NOT call this tool:
- For simple, straightforward tasks
- When the user explicitly wants immediate implementation
```

**plan-exit.txt:**
```
Use this tool when you have completed the planning phase and are ready
to exit plan agent.

Call this tool:
- After you have written a complete plan to the plan file
- After you have clarified any questions with the user
- When you are confident the plan is ready for implementation
```

### 4.5 切换流程图

```
User: "帮我重构认证模块"
    ↓
┌─────────────────────────────────────────┐
│ Build Agent                             │
│ - 分析请求复杂度                        │
│ - 调用 plan_enter                       │
└─────────────────────────────────────────┘
    ↓ 创建 synthetic message: agent="plan"
┌─────────────────────────────────────────┐
│ Plan Agent                              │
│ - 只能 read/grep/glob                   │
│ - 研究现有代码                          │
│ - 撰写重构计划到 plan.md                │
│ - 调用 plan_exit                        │
└─────────────────────────────────────────┘
    ↓ 创建 synthetic message: agent="build"
┌─────────────────────────────────────────┐
│ Build Agent                             │
│ - 读取 plan.md                          │
│ - 执行重构计划                          │
└─────────────────────────────────────────┘
```

---

## 5. Task 机制

### 5.1 核心思想

**Task 工具创建真正的子会话，用于并行执行：**

```
Parent Session
    │
    ├── task @explore → Child Session 1 (explore agent)
    │
    ├── task @bash    → Child Session 2 (bash agent)
    │
    └── task @general → Child Session 3 (general agent)
```

### 5.2 Task Tool 实现

```typescript
// packages/opencode/src/tool/task.ts
export const TaskTool = Tool.define("task", async (ctx) => {
  // 获取所有 subagent（排除 primary）
  const agents = await Agent.list().then(
    (x) => x.filter((a) => a.mode !== "primary")
  )

  // 过滤 caller 有权限使用的 agent
  const caller = ctx?.agent
  const accessibleAgents = caller
    ? agents.filter((a) =>
        PermissionNext.evaluate("task", a.name, caller.permission).action !== "deny"
      )
    : agents

  return {
    description: description(accessibleAgents),
    parameters: z.object({
      description: z.string().describe("A short (3-5 words) description"),
      prompt: z.string().describe("The task for the agent to perform"),
      subagent_type: z.enum(accessibleAgents.map((a) => a.name) as [string, ...string[]]),
      task_id: z.string().optional().describe("For resuming a previous task"),
    }),

    async execute(params, ctx) {
      // 1. 检查 caller 是否有权限使用此 subagent
      if (!ctx.extra?.bypassAgentCheck) {
        await ctx.ask({
          permission: "task",
          patterns: [params.subagent_type],
          always: ["*"],
        })
      }

      // 2. 获取 subagent 配置
      const agent = await Agent.get(params.subagent_type)

      // 3. 检查 subagent 是否有 task 权限（防嵌套）
      const hasTaskPermission = agent.permission.some(
        (rule) => rule.permission === "task"
      )

      // 4. 创建 child session
      const session = await Session.create({
        parentID: ctx.sessionID,  // 关联 parent
        title: params.description + ` (@${agent.name} subagent)`,
        permission: [
          // 禁止 todo 工具
          { permission: "todowrite", pattern: "*", action: "deny" },
          { permission: "todoread", pattern: "*", action: "deny" },
          // 禁止嵌套 task（除非 subagent 显式有 task 权限）
          ...(hasTaskPermission ? [] : [
            { permission: "task", pattern: "*", action: "deny" }
          ]),
        ],
      })

      // 5. 创建 message 并调用 subagent
      const result = await SessionPrompt.prompt({
        sessionID: session.id,
        agent: agent.name,
        tools: {
          todowrite: false,
          todoread: false,
          ...(hasTaskPermission ? {} : { task: false }),
        },
        parts: [{
          type: "subtask",
          prompt: params.prompt,
          agent: agent.name,
          // ...
        }],
      })

      return { output: formatResult(result) }
    },
  }
})
```

### 5.3 Subagent 限制机制

| 限制 | 实现方式 | 目的 |
|------|----------|------|
| **禁止 todo 工具** | Session permission + tools 参数 | 隔离任务列表 |
| **禁止嵌套 task** | 检查 hasTaskPermission | 防止无限递归 |
| **权限继承** | 合并 parent + subagent + session 权限 | 安全隔离 |
| **独立 session** | 创建 child session | 生命周期独立 |

### 5.4 Task 工具描述文件

**task.txt:**
```
Launch a specialized agent to handle complex, multi-step tasks autonomously.

Use the Task tool in these scenarios:
1. Custom slash commands: when the user defines a custom slash command
2. Parallel execution: launch multiple agents concurrently to maximize performance
3. Complex multi-step tasks: when you need autonomous task execution

When NOT to use:
- If you want to read a specific file path (use Read instead)
- If you are searching for a specific class definition (use Glob instead)
- If you are searching code within 2-3 specific files (use Read instead)
```

### 5.5 与 Plan 机制对比

| 特性 | Plan 机制 | Task 机制 |
|------|-----------|-----------|
| **本质** | 同一 session 的 agent 切换 | 创建新的 child session |
| **并行** | ❌ 串行 | ✅ 可并行 |
| **会话** | 共享同一个 session | 独立的 child session |
| **权限** | 基于 agent 配置 | 合并 parent + subagent + restrictions |
| **使用方式** | plan_enter / plan_exit | task tool |
| **适用场景** | 先规划后执行 | 并行任务、专用 agent |

---

## 6. Loop 集成

### 6.1 Agent 获取

Loop 从**最后一条用户消息**获取当前 agent：

```typescript
// packages/opencode/src/session/prompt.ts
while (true) {
  let msgs = await MessageV2.filterCompacted(
    MessageV2.stream(sessionID)
  )

  // 从后向前扫描，找到最后一条用户消息
  let lastUser: MessageV2.User | undefined
  for (let i = msgs.length - 1; i >= 0; i--) {
    const msg = msgs[i]
    if (!lastUser && msg.info.role === "user") {
      lastUser = msg.info as MessageV2.User
      break
    }
  }

  // 获取 agent 配置
  const agent = await Agent.get(lastUser.agent)  // ← 关键！
}
```

### 6.2 工具解析

根据当前 agent 的权限解析可用工具：

```typescript
const tools = await resolveTools({
  agent,              // 当前 agent
  session,
  model,
  bypassAgentCheck,   // 是否绕过权限检查（@agent 时）
  messages: msgs,
})

async function resolveTools(input: {
  agent: Agent.Info
  session: Session.Info
  // ...
}) {
  const context = (args: any, options: ToolCallOptions): Tool.Context => ({
    sessionID: input.session.id,
    agent: input.agent.name,  // 当前 agent 名称

    async ask(req) {
      await PermissionNext.ask({
        ...req,
        // 合并 agent + session 权限
        ruleset: PermissionNext.merge(
          input.agent.permission,
          input.session.permission ?? []
        ),
      })
    },
  })

  // 从 registry 获取工具，传入 agent
  for (const item of await ToolRegistry.tools(model, input.agent)) {
    tools[item.id] = tool({
      id: item.id,
      async execute(args, options) {
        const ctx = context(args, options)
        await ctx.ask({ permission: item.id, patterns: ["*"] })
        return await item.execute(args, ctx)
      },
    })
  }
}
```

### 6.3 Agent 切换检测

检测用户是否通过 `@agent` 显式指定 agent：

```typescript
// 检查消息中是否有 agent mention
const lastUserMsg = msgs.findLast((m) => m.info.role === "user")
const bypassAgentCheck = lastUserMsg?.parts.some(
  (p) => p.type === "agent"
) ?? false

// 如果显式指定，绕过权限检查
const tools = await resolveTools({
  agent,
  bypassAgentCheck,  // 传递此标志
  // ...
})
```

### 6.4 Subtask 处理

当检测到 pending subtask 时，创建子会话执行：

```typescript
// 收集待处理任务
const tasks: (MessageV2.CompactionPart | MessageV2.SubtaskPart)[] = []
for (const msg of msgs) {
  const task = msg.parts.filter(
    (p) => p.type === "compaction" || p.type === "subtask"
  )
  tasks.push(...task)
}

// 处理 subtask
const task = tasks.pop()
if (task?.type === "subtask") {
  const taskTool = await TaskTool.init()

  // 创建 assistant message 用于 subagent
  const assistantMessage = await Session.updateMessage({
    role: "assistant",
    agent: task.agent,  // subagent 名称
    mode: task.agent,
    // ...
  })

  // 构建 tool context
  const taskCtx: Tool.Context = {
    agent: task.agent,
    async ask(req) {
      await PermissionNext.ask({
        ...req,
        // 合并 subagent + session 权限
        ruleset: PermissionNext.merge(
          taskAgent.permission,
          session.permission ?? []
        ),
      })
    },
  }

  // 执行 task
  const result = await taskTool.execute(taskArgs, taskCtx)
  continue  // 回到 loop 开头
}
```

---

## 7. 设计原则总结

### 7.1 核心设计原则

| 原则 | 说明 |
|------|------|
| **Agent as Identity** | Agent = 权限 + 行为配置，不是独立进程 |
| **Message-Based Switching** | Agent 切换通过创建 synthetic message 实现 |
| **Last-Match-Wins** | 权限评估采用最后匹配规则 |
| **Hierarchical Sessions** | Subagent 创建 child session，形成层级 |
| **Permission Inheritance** | 权限合并：defaults → agent → session → user approved |
| **Dynamic Tool Resolution** | 每次 loop 根据当前 agent 重新解析工具 |

### 7.2 关键实现技巧

1. **Synthetic Message**：Plan 切换通过 `synthetic: true` 的消息实现，保持消息流清晰

2. **Permission Caching**：用户批准的权限存入 `state.approved`，跨消息持久化

3. **Session ParentID**：Child session 通过 `parentID` 关联 parent，便于追踪层级

4. **Tool Context**：每个工具调用时传入 `ctx.ask()`，实现实时权限检查

5. **Agent Mention Bypass**：显式 `@agent` 时绕过权限检查，允许用户强制使用特定 agent

### 7.3 对 dm_cc 的启示

1. **简化版实现**：可以先实现 Plan/Build 切换，暂不实现 subagent

2. **权限系统**：采用简单的 allow/deny/ask 三态模型

3. **配置驱动**：Agent 配置使用 YAML/JSON，支持用户自定义

4. **Session 管理**：使用 SQLite 存储 session，支持 parent/child 关系

5. **工具过滤**：Loop 启动时根据 agent 权限过滤可用 tools

---

## 参考文件

| 文件 | 说明 |
|------|------|
| `packages/opencode/src/agent/agent.ts` | Agent 定义和配置 |
| `packages/opencode/src/permission/next.ts` | 权限系统 |
| `packages/opencode/src/tool/plan.ts` | Plan 工具实现 |
| `packages/opencode/src/tool/task.ts` | Task 工具实现 |
| `packages/opencode/src/session/prompt.ts` | Loop 集成 |

---

*文档整理于: 2026-02-25*
