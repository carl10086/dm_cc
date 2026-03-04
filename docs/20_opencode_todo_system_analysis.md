# Opencode Todo 系统源码深度分析

## 目录

1. [架构概览](#1-架构概览)
2. [数据模型](#2-数据模型)
3. [存储层实现](#3-存储层实现)
4. [工具层实现](#4-工具层实现)
   - 4.0 [Todo vs Plan：关键区别](#40-todo-vs-plan关键区别)
   - 4.1 [工具定义](#41-工具定义)
   - 4.2 [工具参数对比](#42-工具参数对比)
   - 4.3 [工具描述文件](#43-工具描述文件)
   - 4.4 [触发条件分析](#44-触发条件分析)
5. [实际使用示例](#5-实际使用示例)
6. [UI 展示](#6-ui-展示)
7. [与 dm_cc 的对比](#7-与-dm_cc-的对比)
8. [设计要点总结](#8-设计要点总结)
   - 8.1 [关键设计决策](#81-关键设计决策)
   - 8.2 [Agent 权限配置](#82-agent-权限配置)
   - 8.3 [Todo 与 Plan 的完整对比](#83-todo-与-plan-的完整对比)

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     opencode Todo 系统架构                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   AI Agent                                                       │
│      │                                                           │
│      ▼                                                           │
│   ┌─────────────┐     ┌─────────────┐                           │
│   │ todoread    │     │ todowrite   │  ← 两个极简工具           │
│   │ (无参数)    │     │ (todos[])   │                           │
│   └──────┬──────┘     └──────┬──────┘                           │
│          │                   │                                   │
│          └─────────┬─────────┘                                   │
│                    ▼                                             │
│            ┌───────────────┐                                     │
│            │  Todo Module  │                                     │
│            │  (todo.ts)    │                                     │
│            └───────┬───────┘                                     │
│                    │                                             │
│         ┌─────────┼─────────┐                                   │
│         ▼         ▼         ▼                                   │
│      ┌─────┐  ┌─────┐  ┌────────┐                              │
│      │ get │  │update│  │ Event  │  ← Bus 事件发布              │
│      └─────┘  └─────┘  └────────┘                              │
│         │        │          │                                    │
│         └────────┼──────────┘                                    │
│                  ▼                                               │
│         ┌───────────────┐                                        │
│         │  SQLite       │                                        │
│         │  TodoTable    │                                        │
│         └───────────────┘                                        │
│                  │                                               │
│                  ▼                                               │
│         ┌───────────────┐                                        │
│         │   TUI Sidebar │  ← 实时订阅显示                        │
│         │  (sidebar.tsx)│                                        │
│         └───────────────┘                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**核心设计原则**：
- **极简接口**：仅两个工具（read/write），无增量更新
- **全量替换**：每次更新传入完整列表，简化并发控制
- **Session 隔离**：每个会话独立存储，天然支持多会话
- **事件驱动**：通过 Bus 事件实现 UI 实时同步

> **⚠️ 重要区别：Todo 工具 vs Plan 模式**
>
> | 特性 | Todo 工具 | Plan 模式 |
> |------|----------|-----------|
> | **触发方式** | `todowrite` 工具调用 | `plan_enter` 工具调用 |
> | **Agent 切换** | ❌ **不切换**，当前 agent 继续使用 | ✅ **会切换** build → plan |
> | **工具权限变化** | 无变化 | Plan agent 限制编辑权限 |
> | **系统提醒** | 无 | 注入 `PLAN_MODE_REMINDER` |
> | **目的** | 任务跟踪管理 | 进入只读规划阶段 |
>
> **关键理解**：Todo 是同一 Agent 内的任务管理工具，Plan 是不同 Agent 之间的模式切换。

---

## 2. 数据模型

### 2.1 TypeScript 定义

**文件**: `packages/opencode/src/session/todo.ts`

```typescript
export namespace Todo {
  // 核心数据模型 - 只有 3 个字段
  export const Info = z
    .object({
      content: z.string().describe("Brief description of the task"),
      status: z.string().describe("Current status: pending, in_progress, completed, cancelled"),
      priority: z.string().describe("Priority level: high, medium, low"),
    })
    .meta({ ref: "Todo" })

  export type Info = z.infer<typeof Info>
}
```

### 2.2 字段说明

| 字段 | 类型 | 说明 | 示例值 |
|------|------|------|--------|
| `content` | string | 任务描述 | "Implement user authentication" |
| `status` | string | 任务状态 | `"pending"`, `"in_progress"`, `"completed"`, `"cancelled"` |
| `priority` | string | 优先级 | `"high"`, `"medium"`, `"low"` |

**为什么没有更多字段？**
- 没有 `id`：用数组索引（position）标识
- 没有 `created_at`/`updated_at`：简化设计，不需要时间追踪
- 没有 `assignee`：单用户场景，无需分配

---

## 3. 存储层实现

### 3.1 数据库表结构

**文件**: `packages/opencode/src/session/session.sql.ts`

```typescript
export const TodoTable = sqliteTable(
  "todo",
  {
    session_id: text()
      .notNull()
      .references(() => SessionTable.id, { onDelete: "cascade" }),
    content: text().notNull(),
    status: text().notNull(),     // pending | in_progress | completed | cancelled
    priority: text().notNull(),   // high | medium | low
    position: integer().notNull(), // 用于排序
  },
  (table) => [
    // 复合主键：(session_id, position)
    primaryKey({ columns: [table.session_id, table.position] }),
    // 索引加速查询
    index("todo_session_idx").on(table.session_id),
  ],
)
```

**设计特点**：

| 特性 | 说明 | 优势 |
|------|------|------|
| Session 级联删除 | `onDelete: "cascade"` | 删除 session 自动清理 todos |
| 复合主键 | `(session_id, position)` | 确保每个 session 内顺序唯一 |
| position 字段 | 数组索引 | 支持排序，无需额外的 order 字段 |

### 3.2 存储操作

**文件**: `packages/opencode/src/session/todo.ts`

```typescript
export namespace Todo {
  // 全量替换更新 - 关键设计！
  export function update(input: { sessionID: string; todos: Info[] }) {
    Database.transaction((db) => {
      // 1. 删除该 session 的所有 todos
      db.delete(TodoTable)
        .where(eq(TodoTable.session_id, input.sessionID))
        .run()

      if (input.todos.length === 0) return

      // 2. 插入新列表（position 字段控制顺序）
      db.insert(TodoTable)
        .values(
          input.todos.map((todo, position) => ({
            session_id: input.sessionID,
            content: todo.content,
            status: todo.status,
            priority: todo.priority,
            position,
          })),
        )
        .run()
    })

    // 3. 发布更新事件，TUI 订阅此事件
    Bus.publish(Event.Updated, input)
  }

  // 查询 - 按 position 排序
  export function get(sessionID: string) {
    const rows = Database.use((db) =>
      db.select()
        .from(TodoTable)
        .where(eq(TodoTable.session_id, sessionID))
        .orderBy(asc(TodoTable.position))
        .all(),
    )
    return rows.map((row) => ({
      content: row.content,
      status: row.status,
      priority: row.priority,
    }))
  }
}
```

**为什么用全量替换？**
1. **简化并发**：避免复杂的 merge 逻辑
2. **AI 友好**：LLM 生成完整列表比计算 diff 更容易
3. **幂等性**：多次执行相同请求结果一致
4. **事务安全**：单次事务完成，不会部分更新

---

## 4. 工具层实现

### 4.0 Todo vs Plan：关键区别

很多开发者容易混淆 **Todo 工具** 和 **Plan 模式**，它们是完全不同的机制：

```
┌─────────────────────────────────────────────────────────────────┐
│                    两种复杂度管理方式对比                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Plan 模式 (Agent 切换)                                  │   │
│  │  ─────────────────────                                   │   │
│  │  • 触发：调用 plan_enter 工具                            │   │
│  │  • 结果：切换到 Plan Agent                               │   │
│  │  • 权限：进入只读模式，不能编辑代码文件                  │   │
│  │  • 目的：调研分析，制定规划，写入 .dm_cc/plans/*.md      │   │
│  │  • 退出：调用 plan_exit 切换回 Build Agent               │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Todo 工具 (同一 Agent 内)                               │   │
│  │  ────────────────────────                                │   │
│  │  • 触发：调用 todowrite 工具                             │   │
│  │  • 结果：当前 Agent 继续执行（不切换）                   │   │
│  │  • 权限：无变化，Build Agent 仍可使用所有工具            │   │
│  │  • 目的：跟踪任务进度，标记完成状态                      │   │
│  │  • 存储：.dm_cc/todos/{session_id}.json                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**决策流程**：

```
用户请求复杂任务
       │
       ├── 需要先调研/规划？───► 调用 plan_enter ──► 进入 Plan Agent
       │                         (制定整体方案)
       │
       └── 直接执行多步骤任务？──► 调用 todowrite ──► 保持 Build Agent
                                   (跟踪执行进度)
```

### 4.1 工具定义

**文件**: `packages/opencode/src/tool/todo.ts`

```typescript
export const TodoWriteTool = Tool.define("todowrite", {
  description: DESCRIPTION_WRITE,  // 详细的 few-shot 描述
  parameters: z.object({
    todos: z.array(z.object(Todo.Info.shape))
      .describe("The updated todo list"),
  }),
  async execute(params, ctx) {
    // 权限检查（可选，因为 always: ["*"]）
    await ctx.ask({
      permission: "todowrite",
      patterns: ["*"],
      always: ["*"],
      metadata: {},
    })

    await Todo.update({
      sessionID: ctx.sessionID,
      todos: params.todos,
    })

    return {
      title: `${params.todos.filter((x) => x.status !== "completed").length} todos`,
      output: JSON.stringify(params.todos, null, 2),
      metadata: { todos: params.todos },
    }
  },
})

export const TodoReadTool = Tool.define("todoread", {
  description: "Use this tool to read your todo list",
  parameters: z.object({}),  // 无参数
  async execute(_params, ctx) {
    await ctx.ask({
      permission: "todoread",
      patterns: ["*"],
      always: ["*"],
      metadata: {},
    })

    const todos = await Todo.get(ctx.sessionID)
    return {
      title: `${todos.filter((x) => x.status !== "completed").length} todos`,
      metadata: { todos },
      output: JSON.stringify(todos, null, 2),
    }
  },
})
```

### 4.2 工具参数对比

| 工具 | 参数 | 返回值 |
|------|------|--------|
| `todoread` | 无（空对象） | `{ title, output, metadata: { todos } }` |
| `todowrite` | `{ todos: Todo.Info[] }` | `{ title, output, metadata: { todos } }` |

**title 的计算**：`pending` 状态的任务数量
```typescript
title: `${todos.filter((x) => x.status !== "completed").length} todos`
```

### 4.3 工具描述文件

**文件**: `packages/opencode/src/tool/todowrite.txt`（节选）

```
Use this tool to create and manage a structured task list for your current coding session.
This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.

## When to Use This Tool

Use this tool proactively in these scenarios:

1. Complex multistep tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done
5. After receiving new instructions - Immediately capture user requirements as todos
6. After completing a task - Mark it complete and add any new follow-up tasks
7. When you start working on a new task, mark the todo as in_progress

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

## Task States and Management

1. **Task States**:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully
   - cancelled: Task no longer needed

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing
   - Only have ONE task in_progress at any time
   - Complete current tasks before starting new ones
```

### 4.4 触发条件分析（从 Prompt 提取）

**什么时候调用 todowrite？** —— 完全由 Prompt 规则决定，不是代码硬编码：

| 场景 | 触发条件 | 示例 |
|------|----------|------|
| ✅ **复杂多步骤** | 任务需要 **3+ 个不同步骤** | 实现暗黑模式（UI + 状态管理 + 样式） |
| ✅ **用户明确要求** | 用户说 "create a todo list" | "帮我创建一个任务列表跟踪进度" |
| ✅ **多个任务** | 用户提供列表（逗号/编号分隔） | "实现 A, B, C 三个功能" |
| ✅ **新指令** | 收到新需求时立即捕获 | 用户中途追加需求 |
| ✅ **开始新任务** | 将新任务标记为 `in_progress` | 完成第一步，开始第二步 |
| ❌ **简单任务** | < 3 个步骤，直接完成 | "print Hello World" |
| ❌ **纯对话** | 信息查询，无实际操作 | "git status 是做什么的？" |

**关键理解**：
- 使用 Todo **不会触发任何状态变化或 Agent 切换**
- 只是普通的工具调用，执行后返回结果，继续当前 Agent 的循环
- 与 Plan 模式的区别：Plan 会切换 Agent 并改变系统 prompt

---

## 5. 实际使用示例

### 5.1 示例 1: 添加暗黑模式

**用户**: "I want to add a dark mode toggle to the application settings. Make sure you run the tests and build when you're done!"

**AI 执行流程**:

```typescript
// Step 1: 创建 todo 列表
await todowrite({
  todos: [
    { content: "Create dark mode toggle component in Settings page", status: "pending", priority: "high" },
    { content: "Add dark mode state management (context/store)", status: "pending", priority: "high" },
    { content: "Implement CSS-in-JS styles for dark theme", status: "pending", priority: "medium" },
    { content: "Update existing components to support theme switching", status: "pending", priority: "medium" },
    { content: "Run tests and build process", status: "pending", priority: "high" },
  ]
})

// Step 2: 开始第一个任务
await todowrite({
  todos: [
    { content: "Create dark mode toggle component in Settings page", status: "in_progress", priority: "high" },
    // ... 其他保持不变
  ]
})

// Step 3: 完成第一个任务，开始第二个
await todowrite({
  todos: [
    { content: "Create dark mode toggle component in Settings page", status: "completed", priority: "high" },
    { content: "Add dark mode state management (context/store)", status: "in_progress", priority: "high" },
    // ... 其他保持不变
  ]
})
```

### 5.2 示例 2: 重构函数名

**用户**: "Help me rename the function getCwd to getCurrentWorkingDirectory across my project"

**AI 执行流程**:

```typescript
// Step 1: 先搜索了解情况
const results = await search({ pattern: "getCwd" })
// 发现 15 处调用，分布在 8 个文件中

// Step 2: 创建 todo 列表
await todowrite({
  todos: [
    { content: "Update getCwd in src/utils/path.ts", status: "pending", priority: "high" },
    { content: "Update getCwd in src/config/loader.ts", status: "pending", priority: "high" },
    { content: "Update getCwd in src/cli/commands.ts", status: "pending", priority: "high" },
    { content: "Update getCwd in tests/path.test.ts", status: "pending", priority: "medium" },
    // ... 其他文件
  ]
})

// Step 3: 逐个处理...
```

### 5.3 示例 3: 读取并更新

```typescript
// 读取当前列表
const { metadata } = await todoread({})
const currentTodos = metadata.todos

// 添加新任务
await todowrite({
  todos: [
    ...currentTodos,
    { content: "New follow-up task", status: "pending", priority: "medium" }
  ]
})
```

---

## 6. UI 展示

### 6.1 TUI 侧边栏展示

**文件**: `packages/opencode/src/cli/cmd/tui/routes/session/sidebar.tsx`

```tsx
<Show when={todo().length > 0 && todo().some((t) => t.status !== "completed")}>
  <box>
    <box flexDirection="row">
      <text><b>Todo</b></text>
    </box>
    <For each={todo()}>
      {(todo) => <TodoItem status={todo.status} content={todo.content} />}
    </For>
  </box>
</Show>
```

**显示条件**：
1. 有 todo 项
2. 至少有一个未完成的任务

### 6.2 Todo 项组件

**文件**: `packages/opencode/src/cli/cmd/tui/component/todo-item.tsx`

```tsx
export function TodoItem(props: { status: string; content: string }) {
  return (
    <box flexDirection="row">
      {/* 状态图标 */}
      <text style={{
        fg: props.status === "in_progress" ? theme.warning : theme.textMuted,
      }}>
        [{props.status === "completed" ? "✓" :
           props.status === "in_progress" ? "•" : " "}] {" "}
      </text>

      {/* 任务内容 */}
      <text style={{
        fg: props.status === "in_progress" ? theme.warning : theme.textMuted,
      }}>
        {props.content}
      </text>
    </box>
  )
}
```

### 6.3 UI 效果

```
┌─────────────────────────────────────────┐
│  Session: 实现电商网站                  │
│                                         │
│  Todo                                   │
│  [•] 设计商品展示页面  ← in_progress    │
│  [ ] 实现购物车功能    ← pending        │
│  [ ] 开发订单管理系统                   │
│  [✓] 初始化项目结构   ← completed       │
│                                         │
│  ─────────────────────                  │
│  Cost: $0.023                           │
└─────────────────────────────────────────┘
```

**视觉设计**：
- `✓` - 已完成（灰色/柔和）
- `•` - 进行中（黄色/警告色，突出显示）
- ` ` - 待处理（灰色）

---

## 7. 与 dm_cc 的对比

### 7.1 架构对比

| 特性 | opencode (TypeScript) | dm_cc 建议 (Python) |
|------|----------------------|---------------------|
| **存储** | SQLite + Drizzle | JSON 文件 / SQLite |
| **事件总线** | 自定义 Bus | 无需（无 TUI） |
| **UI 框架** | Ink (React-like) | 无 / Rich Console |
| **权限** | PermissionNext 规则 | AgentConfig 工具过滤 |
| **更新策略** | 全量替换 | 全量替换（保持一致） |

### 7.2 代码对比

**数据模型**:

```typescript
// opencode - TypeScript
export const Info = z.object({
  content: z.string(),
  status: z.string(),   // pending | in_progress | completed | cancelled
  priority: z.string(), // high | medium | low
})
```

```python
# dm_cc - Python 建议
@dataclass
class TodoItem:
    content: str
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    priority: Literal["high", "medium", "low"]
```

**存储**:

```typescript
// opencode - SQLite
export function update(input: { sessionID: string; todos: Info[] }) {
  Database.transaction((db) => {
    db.delete(TodoTable).where(eq(TodoTable.session_id, input.sessionID)).run()
    if (input.todos.length === 0) return
    db.insert(TodoTable).values(...).run()
  })
  Bus.publish(Event.Updated, input)
}
```

```python
# dm_cc - JSON 文件建议
class TodoStore:
    def update(self, todos: list[TodoItem]) -> None:
        """全量替换更新"""
        data = [todo.to_dict() for todo in todos]
        self._file_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )
```

---

## 8. 设计要点总结

### 8.1 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **更新策略** | 全量替换 | 避免复杂并发控制，AI 友好 |

### 8.2 Agent 权限配置

**文件**: `packages/opencode/src/agent/agent.ts`

```typescript
const result: Record<string, Info> = {
  build: {
    name: "build",
    // Build agent 默认可用所有工具，包括 todowrite/todoread
    permission: PermissionNext.merge(defaults, {
      question: "allow",
      plan_enter: "allow",
      // todowrite/todoread 默认可用（在 defaults 中 "*": "allow"）
    }),
    mode: "primary",
  },
  plan: {
    name: "plan",
    // Plan agent 也可以使用 todo 工具
    permission: PermissionNext.merge(defaults, {
      plan_exit: "allow",
      // 没有禁用 todo，规划时也需要任务管理
    }),
    mode: "primary",
  },
  general: {
    name: "general",
    // Subagent - 显式禁用 todo！
    permission: PermissionNext.merge(defaults, {
      todoread: "deny",   // ❌ 禁止
      todowrite: "deny",  // ❌ 禁止
    }),
    mode: "subagent",
  },
  explore: {
    name: "explore",
    // Explore subagent 也禁用 todo
    permission: PermissionNext.merge(defaults, {
      todoread: "deny",
      todowrite: "deny",
    }),
    mode: "subagent",
  },
}
```

**为什么 Subagent 禁用 Todo？**
- Subagent（general/explore）只执行单一任务
- 不应访问或修改父会话的 todo 列表
- 保持关注点分离，避免子任务干扰主任务跟踪

### 8.3 Todo 与 Plan 的完整对比

| 维度 | Todo 工具 | Plan 模式 |
|------|----------|-----------|
| **触发方式** | `todowrite` 工具调用 | `plan_enter` 工具调用 |
| **Agent 切换** | ❌ 否，保持当前 Agent | ✅ 是，build → plan |
| **权限变化** | 无 | Plan agent 限制编辑权限 |
| **系统 Prompt** | 不变 | 注入 `PLAN_MODE_REMINDER` |
| **目的** | 跟踪任务执行进度 | 进入只读规划阶段 |
| **存储位置** | `.dm_cc/todos/{session_id}.json` | `.dm_cc/plans/*.md` |
| **适用 Agent** | Build, Plan | Build 调用，Plan 执行 |
| **Subagent 权限** | ❌ general/explore 禁用 | ❌ general/explore 禁用 |
| **参数设计** | 极简（todos 数组） | LLM 容易生成完整列表 |
| **存储** | SQLite + ORM | 轻量、事务支持、易于查询 |
| **作用域** | Session 级别 | 自然隔离，多会话不冲突 |
| **同步机制** | Bus 事件发布 | 实时 UI 更新，松耦合 |

### 8.2 权限控制

opencode 中 Todo 工具使用标准权限系统，**Subagent 禁止使用**：

```typescript
// general/explore subagent 配置
{
  name: "general",
  permission: PermissionNext.merge(
    defaults,
    PermissionNext.fromConfig({
      todoread: "deny",   // 禁止读取 todo
      todowrite: "deny",  // 禁止修改 todo
    }),
  ),
}
```

**为什么限制 Subagent？**
- Subagent（如 general、explore）只执行单一任务
- 不应访问或修改父会话的 todo 列表
- 保持关注点分离

### 8.3 AI 使用场景

| 场景 | 触发条件 | AI 操作 |
|------|----------|---------|
| 创建 | 多步骤任务（3+ 步骤） | 调用 todowrite 创建初始列表 |
| 更新 | 开始新任务 | 标记为 in_progress |
| 完成 | 任务完成 | 标记为 completed |
| 添加 | 发现新任务 | 读取当前列表，追加新任务 |
| 检查 | 每隔 3-5 轮对话 | 调用 todoread 确认进度 |

### 8.4 实现建议（dm_cc）

```python
# ============ 存储层 ============
class TodoStore:
    """Session 级别的 Todo 存储"""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.file_path = TODOS_DIR / f"{session_id}.json"

    def get_all(self) -> list[TodoItem]:
        if not self.file_path.exists():
            return []
        data = json.loads(self.file_path.read_text())
        return [TodoItem(**item) for item in data]

    def update(self, todos: list[TodoItem]):
        """全量替换更新"""
        data = [asdict(todo) for todo in todos]
        self.file_path.write_text(json.dumps(data, indent=2))


# ============ 工具层 ============
class TodoReadTool(Tool):
    name = "todo_read"
    parameters = None  # 无参数

    async def execute(self, params) -> dict:
        session_id = get_current_session_id()
        store = TodoStore(session_id)
        todos = store.get_all()
        return {
            "title": f"{len([t for t in todos if t.status != 'completed'])} todos",
            "output": format_todos(todos),
            "metadata": {"todos": todos},
        }


class TodoWriteTool(Tool):
    name = "todo_write"

    class Parameters(BaseModel):
        todos: list[TodoItem]

    async def execute(self, params: Parameters) -> dict:
        session_id = get_current_session_id()
        store = TodoStore(session_id)
        store.update(params.todos)
        return {"title": "Updated", "output": "Todo list updated"}
```

---

## 附录：完整文件清单

| 文件 | 说明 |
|------|------|
| `packages/opencode/src/session/todo.ts` | 数据模型和存储操作 |
| `packages/opencode/src/session/session.sql.ts` | 数据库表定义 |
| `packages/opencode/src/tool/todo.ts` | 工具定义 |
| `packages/opencode/src/tool/todoread.txt` | 读取工具描述 |
| `packages/opencode/src/tool/todowrite.txt` | 写入工具描述（含触发条件） |
| `packages/opencode/src/agent/agent.ts` | Agent 权限配置（todo 禁用规则） |
| `packages/opencode/src/cli/cmd/tui/component/todo-item.tsx` | UI 组件 |
| `packages/opencode/src/cli/cmd/tui/routes/session/sidebar.tsx` | 侧边栏展示 |

---

*文档生成日期: 2026-03-04*
