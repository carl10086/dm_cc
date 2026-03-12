# Opencode Compact 系统源码深度分析

## 关键发现速览

| 问题 | 答案 |
|------|------|
| **Compact 是 Subagent 吗？** | ❌ **不是！** 是 `hidden: true` 的 Primary Agent |
| **Prompt 机制** | 双层 Prompt：System（角色定义）+ User（任务模板）|
| **工具权限** | `"*": "deny"` - 禁止所有工具，纯文本生成 |
| **触发方式** | Token 超过阈值（默认保留 20K buffer）|
| **双层优化** | Prune（懒删除旧工具输出）+ Compact（生成摘要）|
| **删除机制** | **懒删除（Soft Delete）** - 标记时间戳，数据保留但过滤 |

---

## 0. 两个关键设计细节

### 0.1 Hidden Primary Agent 详解

**问题：什么是 `hidden: true`？**

```typescript
// packages/opencode/src/agent/agent.ts L157-170
compaction: {
  name: "compaction",
  mode: "primary",      // ✅ 是 Primary，不是 subagent
  native: true,
  hidden: true,         // ✅ 关键：对用户隐藏
  prompt: PROMPT_COMPACTION,
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      "*": "deny",      // 禁止所有工具
    }),
  ),
}
```

**`hidden: true` 的含义**：

| 维度 | Hidden Agent | 普通 Primary Agent |
|------|-------------|-------------------|
| **代码中可访问** | ✅ `Agent.get("compaction")` | ✅ `Agent.get("build")` |
| **TUI 显示** | ❌ **不显示** | ✅ 显示在列表中 |
| **用户可选择** | ❌ **无法手动选择** | ✅ 用户可以切换 |
| **自动触发** | ✅ 系统内部调用 | ❌ 用户主动使用 |
| **用途** | 内部专用（摘要、标题生成） | 用户交互 |

**代码证据**（`local.tsx` L38）：

```typescript
// UI 中过滤掉 hidden agents
const agents = createMemo(() =>
  sync.data.agent.filter((x) => x.mode !== "subagent" && !x.hidden)
)
```

**设计意图**：

```
用户看到的 Agent 列表          实际所有 Agent
--------------------          ----------------
Build  (primary)              Build  (primary, visible)
Plan   (primary)              Plan   (primary, visible)
                              Compaction (primary, hidden) ← 用户看不到
                              Title      (primary, hidden) ← 用户看不到
General (subagent)            General (subagent)
Explore (subagent)            Explore (subagent)
```

1. **避免混淆**：用户不需要知道 compaction 的存在
2. **自动触发**：由系统在后台自动调用
3. **专职专用**：只做一件事（生成摘要），不需要用户干预
4. **安全**：`"*": "deny"` 禁止所有工具，防止误操作

### 0.2 懒删除（Soft Delete）机制

**问题：Prune 为什么不真删除？**

```typescript
// 不是删除，而是标记时间戳
part.state.time.compacted = Date.now()
```

**数据对比**：

正常 Tool 输出：
```typescript
{
  type: "tool",
  state: {
    status: "completed",
    output: "文件内容...",
    time: {
      start: 1700000000000,
      end: 1700000001000
      // ❌ 没有 compacted 字段
    }
  }
}
```

被 Prune 的 Tool 输出：
```typescript
{
  type: "tool",
  state: {
    status: "completed",
    output: "文件内容...",  // ✅ 数据还在！
    time: {
      start: 1700000000000,
      end: 1700000001000,
      compacted: 1700005000000  // ✅ 只是加了时间戳标记
    }
  }
}
```

**使用时的过滤**：

```typescript
// 构建发送给 LLM 的消息时过滤
function buildMessagesForLLM(allMessages) {
  return allMessages.filter(msg => {
    // 被标记 compacted 的消息不发送给 LLM
    if (msg.state?.time?.compacted) {
      return false;  // ❌ 过滤掉
    }
    return true;  // ✅ 发送
  })
}
```

**懒删除的优势**：

| 优势 | 说明 |
|------|------|
| **数据安全** | 不真正删除，避免误操作 |
| **可审计** | 可以查看完整历史记录 |
| **灵活性** | 可以清除标记恢复数据 |
| **多模型支持** | 根据模型大小动态决定是否过滤 |
| **容错性** | 错误的 compact 决策可以回滚 |

---

## 1. 核心发现：Compaction Agent 的本质

### 1.1 不是 Subagent！

**文件**: `packages/opencode/src/agent/agent.ts` (L157-170)

```typescript
compaction: {
  name: "compaction",
  mode: "primary",      // ✅ 是 Primary，不是 subagent
  native: true,
  hidden: true,         // ✅ 隐藏的，用户不可见
  prompt: PROMPT_COMPACTION,  // 加载 prompt/compaction.txt
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      "*": "deny",      // ✅ 禁止所有工具！
    }),
    user,
  ),
  options: {},
}
```

**关键特性**：

| 特性 | 值 | 说明 |
|------|-----|------|
| `mode` | `"primary"` | 主 Agent，不是 subagent |
| `hidden` | `true` | 不在 UI 中显示，用户无法直接选择 |
| `prompt` | `PROMPT_COMPACTION` | 专门的 system prompt |
| `permission` | `"*": "deny"` | **禁用所有工具**，只能生成文本 |

**设计意图**：
- **专职专用**：只做摘要生成，不执行任何操作
- **无工具权限**：防止误操作，确保安全
- **隐藏**：用户不需要知道它的存在，自动触发

---

## 2. 双层 Prompt 机制（核心细节）

opencode 使用了 **两个层级的 Prompt**，这是我之前没有强调的关键细节：

### 2.1 第一层：System Prompt（角色定义）

**文件**: `packages/opencode/src/agent/prompt/compaction.txt`

```
You are a helpful AI assistant tasked with summarizing conversations.

When asked to summarize, provide a detailed but concise summary of the conversation.
Focus on information that would be helpful for continuing the conversation, including:
- What was done
- What is currently being worked on
- Which files are being modified
- What needs to be done next
- Key user requests, constraints, or preferences that should persist
- Important technical decisions and why they were made

Your summary should be comprehensive enough to provide context but concise enough to be quickly understood.

Do not respond to any questions in the conversation, only output the summary.
```

**作用**：
- 定义 compaction agent 的角色
- 规定摘要的风格和内容要求
- 禁止回答具体问题（只输出摘要）

### 2.2 第二层：User Prompt（任务模板）

**文件**: `packages/opencode/src/session/compaction.ts` (L80-110)

```typescript
const defaultPrompt = `Provide a detailed prompt for continuing our conversation above.
Focus on information that would be helpful for continuing the conversation, including what we did, what we're doing, which files we're working on, and what we're going to do next.
The summary that you construct will be used so that another agent can read it and continue the work.

When constructing the summary, try to stick to this template:
---
## Goal

[What goal(s) is the user trying to accomplish?]

## Instructions

- [What important instructions did you user give you that are relevant]
- [If there is a plan or spec, include information about it so next agent can continue using it]

## Discoveries

[What notable things were learned during this conversation that would be useful for the next agent to know when continuing the work]

## Accomplished

[What work has been completed, what work is still in progress, and what work is left?]

## Relevant files / directories

[Construct a structured list of relevant files that have been read, edited, or created that pertain to the task at hand. If all the files in a directory are relevant, include the path to the directory.]
---`
```

**作用**：
- 具体的任务指令
- **强制结构化输出模板**（Goal/Instructions/Discoveries/Accomplished/Files）
- 指导如何提取和组织信息

### 2.3 Prompt 组合方式

```typescript
// compaction.ts
const promptText = compacting.prompt ?? [defaultPrompt, ...compacting.context].join("\n\n")

// 最终发送给 LLM 的消息结构：
[
  // 1. System Message (来自 compaction.txt)
  { role: "system", content: PROMPT_COMPACTION },

  // 2. 历史消息（要被 compact 的消息）
  ...messagesToCompact,

  // 3. User Message（defaultPrompt，含结构化模板）
  { role: "user", content: defaultPrompt }
]
```

**为什么分层？**

| 层级 | 内容 | 稳定性 | 作用 |
|------|------|--------|------|
| System | 角色定义 | 固定 | 让 LLM 进入"摘要模式" |
| User | 任务模板 | 固定 | 指导结构化输出 |
| Context | 历史消息 | 动态变化 | 被摘要的原始内容 |

---

## 3. Compact 完整流程

### 3.1 触发阶段

```typescript
// 检查是否溢出
export async function isOverflow(input: { tokens; model }) {
  const context = input.model.limit.context
  const count = tokens.total || (input + output + cache)

  // 保留 20K buffer，超过则触发
  const reserved = config.compaction?.reserved ?? 20_000
  const usable = context - reserved
  return count >= usable
}
```

### 3.2 执行阶段

```typescript
export async function process(input: {
  parentID: string
  messages: MessageV2.WithParts[]
  sessionID: string
  auto: boolean
  overflow?: boolean
}) {
  // 1. 创建 compaction message（标记为 summary）
  const msg = await Session.updateMessage({
    id: Identifier.ascending("message"),
    role: "assistant",
    parentID: input.parentID,
    sessionID: input.sessionID,
    mode: "compaction",
    agent: "compaction",
    summary: true,  // ✅ 关键标记
    // ...
  })

  // 2. 获取 compaction agent（隐藏、无工具权限）
  const agent = await Agent.get("compaction")

  // 3. 构建双层 prompt
  // System: PROMPT_COMPACTION (角色定义)
  // User: defaultPrompt (结构化模板)
  const promptText = [defaultPrompt, ...compacting.context].join("\n\n")

  // 4. 调用 LLM 生成摘要
  const processor = SessionProcessor.create({...})
  const result = await processor.process({
    messages: [
      ...MessageV2.toModelMessages(messages, model),
      { role: "user", content: promptText }
    ],
    model,
    tools: {},  // ✅ 无工具
  })

  // 5. 发布事件通知 UI
  Bus.publish(Event.Compacted, { sessionID: input.sessionID })
}
```

---

## 4. Prune 机制（第一层优化）

**文件**: `packages/opencode/src/session/compaction.ts` (L65-100)

在 Compact 之前，先执行 Prune 删除旧的 tool 输出：

```typescript
export async function prune(input: { sessionID: string }) {
  const PRUNE_PROTECT = 40_000  // 保留最近 40K tokens
  const PRUNE_MINIMUM = 20_000  // 至少删除 20K 才生效

  let total = 0
  const toPrune = []

  // 从后向前遍历（从最新的消息开始）
  for (const msg of msgs.reverse()) {
    for (const part of msg.parts) {
      if (part.type === "tool" && part.state.status === "completed") {
        total += estimateTokens(part.state.output)

        // 超过保护阈值，标记为可删除
        if (total > PRUNE_PROTECT) {
          part.state.time.compacted = Date.now()
          toPrune.push(part)
        }
      }
    }
  }

  // 只有删除量足够大时才执行
  if (pruned > PRUNE_MINIMUM) {
    for (const part of toPrune) {
      part.state.time.compacted = Date.now()
      await Session.updatePart(part)
    }
  }
}
```

### 4.1 关键设计：懒删除（Soft Delete）

**不是真删除，而是"标记删除"**

| 操作 | 实际行为 | 数据是否保留 |
|------|---------|-------------|
| **Prune** | 标记 `time.compacted = Date.now()` | ✅ 数据还在，只是不发送给 LLM |
| **Compact** | 标记 `compacted: true` + 插入摘要 | ✅ 原消息还在，只是被跳过 |

**为什么用懒删除？**

```
┌─────────────────────────────────────────────────────────────┐
│                      懒删除的优势                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 数据安全                                                  │
│     - 不真正删除，避免误操作导致数据丢失                          │
│     - 可以事后查看完整历史                                      │
│     - 支持审计和调试                                           │
│                                                              │
│  2. 灵活性                                                    │
│     - 可以随时清除 compacted 标记恢复数据                         │
│     - 支持不同的上下文窗口策略（小模型需要过滤，大模型可以保留）       │
│     - 便于排查问题（可以看到哪些数据被 compact 了）                │
│                                                              │
│  3. 多模型支持                                                 │
│     - 不同模型有不同的上下文限制                                    │
│     - 根据模型动态决定是否过滤（运行时决策）                         │
│                                                              │
│  4. 容错性                                                    │
│     - 如果 compact 决策错误，可以回滚                              │
│     - 数据是宝贵的，绝不轻易删除                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**使用时的过滤逻辑**：

```typescript
// 构建发送给 LLM 的消息时过滤
function buildMessagesForLLM(allMessages) {
  return allMessages.filter(msg => {
    // 跳过被 prune 的消息
    if (msg.type === "tool" && msg.state?.time?.compacted) {
      return false;  // ❌ 不发送给 LLM，但数据还在数据库
    }
    // 跳过被 compact 的消息
    if (msg.compacted && !msg.is_summary) {
      return false;  // ❌ 不发送给 LLM，但数据还在数据库
    }
    return true;  // ✅ 正常发送
  })
}
```

**Prune vs Compact 对比**：

| 维度 | Prune | Compact |
|------|-------|---------|
| **粒度** | 单个 tool 输出 | 整个消息历史 |
| **方式** | 标记 `compacted` 时间戳 | 生成新的 summary message |
| **触发** | 自动（在 compact 之前） | 自动/手动 |
| **数据保留** | 还在数据库，只是不发送给 LLM | 替换为摘要 |
| **保护策略** | 保留最近 40K | 保留最近 2-4 条消息 |

---

## 5. 消息标记策略

**如何区分被 compact 的消息？**

```typescript
// 1. Summary Message（摘要消息）
{
  role: "assistant",
  mode: "compaction",    // ✅ 标记为 compaction 模式
  agent: "compaction",   // ✅ agent 为 compaction
  summary: true,         // ✅ 关键标记
  content: "## Goal\n...",
}

// 2. 被 Prune 的 Tool 输出
{
  type: "tool",
  state: {
    status: "completed",
    time: {
      compacted: 1700000000000  // ✅ 标记时间戳
    }
  }
}

// 3. 构建发送给 LLM 的消息时过滤
function buildMessagesForLLM(allMessages) {
  return allMessages.filter(msg => {
    // 跳过被 prune 的消息
    if (msg.type === "tool" && msg.state?.time?.compacted) {
      return false
    }
    // 保留 summary message
    return true
  })
}
```

---

## 6. 与 dm_cc 的对比

| 特性 | opencode | dm_cc 建议 |
|------|----------|------------|
| **Agent 类型** | Hidden Primary | 复用现有 Agent 或新建 |
| **Prompt 层数** | 双层（System + User）| 可简化为单层 |
| **工具权限** | `"*": "deny"` | 直接不传入 tools |
| **Prune** | ✅ 两层优化 | 可先只实现 Compact |
| **事件系统** | Bus 发布 | 可省略 |
| **结构化模板** | 强制 5 部分 | 可简化 |

---

## 7. 关键文件清单

| 文件 | 说明 |
|------|------|
| `packages/opencode/src/agent/agent.ts` | Compaction agent 定义（L157-170）|
| `packages/opencode/src/agent/prompt/compaction.txt` | System Prompt（角色定义）|
| `packages/opencode/src/session/compaction.ts` | Compact 核心逻辑 + User Prompt 模板 |
| `packages/opencode/src/session/compaction.ts` | Prune 逻辑（L65-100）|
| `packages/opencode/src/server/routes/session.ts` | Compact API 路由 |

---

## 8. 核心结论

1. **Compaction 是 Hidden Primary Agent**，不是 subagent
2. **双层 Prompt**：System 定义角色，User 定义任务模板
3. **无工具权限**：`"*": "deny"`，确保安全
4. **双层优化**：Prune（删除旧 tool）+ Compact（生成摘要）
5. **结构化输出**：强制模板确保可解析性

---

*分析更新日期: 2026-03-05*
