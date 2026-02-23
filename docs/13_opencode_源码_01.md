
## 📖 1：System Prompt 构建 — AI 的"性格"从哪来？

### 1.1 为什么需要 System Prompt？

想象你雇了一个新员工。你不能只说"去干活"，你需要告诉他：
* **你是谁**：你是一个高级软件工程师
* **你的工作环境**：我们用 TypeScript，项目在 `/home/project` 目录
* **公司规范**：代码必须写测试，不能直接改 main 分支
* **你的角色**：你负责代码审查（不是写代码）

System Prompt 就是给 AI 的这份**"入职手册"**。

### 1.2 OpenCode 的 Prompt 是怎么"拼"出来的？

`OpenCode` 不是写一个大字符串就完了。它像搭积木一样，从**4个来源**拼装：

```
最终的 System Prompt = Provider Prompt + 环境信息 + 自定义规则 + Agent Prompt
```

让我用一个生活中的例子来类比：

| 积木块 | 类比 | 例子 |
| :--- | :--- | :--- |
| **Provider Prompt** | 你的"母语和文化背景" | Claude 模型用 `anthropic.txt`，GPT 用 `beast.txt` |
| **环境信息** | 你的"办公室环境" | 工作目录、Git 状态、操作系统、当前日期 |
| **自定义规则** | 公司的"规章制度" | `AGENTS.md`、`CLAUDE.md` 等项目级规则文件 |
| **Agent Prompt** | 你的"岗位职责" | build agent 负责写代码，plan agent 只负责规划 |

### 1.3 具体例子：一个完整的 Prompt 是怎么被拼出来的？

假设你在一个 TypeScript 项目中使用 Claude 模型、build agent：

```
╔══════════════════════════════════════════════════════════╗
║ 第1层：Provider Prompt (anthropic.txt)                    ║
║ "You are Claude, an AI assistant by Anthropic..."        ║
║ "You have tools to read/write files, run commands..."    ║
╠══════════════════════════════════════════════════════════╣
║ 第2层：环境信息 (SystemPrompt.environment)                ║
║ "Working directory: /home/user/my-project"               ║
║ "Git branch: feature/login"                              ║
║ "Platform: linux, Date: 2026-02-09"                      ║
╠══════════════════════════════════════════════════════════╣
║ 第3层：自定义规则 (SystemPrompt.custom)                    ║
║ "项目使用 TypeScript strict mode"                         ║
║ "所有函数必须有 JSDoc 注释"                                ║
║ "测试覆盖率不低于 80%"                                    ║
║ (来自项目根目录的 AGENTS.md)                               ║
╠══════════════════════════════════════════════════════════╣
║ 第4层：Agent Prompt (build agent)                        ║
║ "You are a development agent. You can read, write,       ║
║  edit files, and run commands to complete tasks."         ║
╚══════════════════════════════════════════════════════════╝
```

### 1.4 关键设计思想：为什么要分层？

这里体现了一个很重要的**软件设计思想 — 关注点分离（Separation of Concerns）**：

* **Provider Prompt** 跟着模型走 → 换模型自动切换
* **环境信息** 自动检测 → 不需要手动维护
* **自定义规则** 跟着项目走 → 不同项目不同规范
* **Agent Prompt** 跟着角色走 → 同一项目可以有不同"专家"

> 🔑 **类比**：就像你不会把公司规章制度、部门规范、个人职责全写在一张纸上。分开管理，才能灵活组合。

### 1.5 自定义规则的优先级

OpenCode 会从多个地方收集规则，有清晰的优先级：

```
项目级 AGENTS.md / CLAUDE.md / CONTEXT.md    ← 最高优先级（项目特有）
         ↑
全局级 ~/.claude/CLAUDE.md                    ← 中等优先级（所有项目通用）
         ↑
配置文件 config.instructions                   ← 基础配置
         ↑
URL 远程规则                                   ← 从网络加载的规则
```

> 💡 **实践意义**：如果你想让 AI 在某个项目中"写代码必须用中文注释"，只需在项目根目录创建一个 `AGENTS.md` 文件写上这条规则即可。

---

## 📖 2：权限系统 — 怎么防止 AI 干坏事？

### 2.1 为什么需要权限系统？

AI 有能力读写文件、执行命令。但你肯定不希望：
* AI 偷偷读你的 `.env` 文件（里面有数据库密码）
* AI 在未经确认的情况下执行 `rm -rf /`
* AI 随意访问项目外的目录

权限系统就是给 AI 加的**"安全围栏"**。

### 2.2 三种权限动作

OpenCode 的权限只有3种状态，非常简洁：

```
allow → 直接允许，不用问我
deny  → 直接拒绝，想都别想
ask   → 先问我，我来决定
```

当用户被"问"的时候，有3种回答：

```
once   → 这次允许，下次还要问我
always → 永远允许，别再烦我了
reject → 拒绝
```

### 2.3 权限流程：用一个真实场景来理解

假设 AI 想执行 `npm install axios`：

```
AI 调用 bash 工具: "npm install axios"
    │
    ▼
系统检查权限规则：bash 的权限是什么？
    │
    ├─ 如果 bash 规则是 "allow" → ✅ 直接执行
    │
    ├─ 如果 bash 规则是 "deny"  → ❌ 直接拒绝
    │
    └─ 如果 bash 规则是 "ask"   → 🤔 弹窗问用户
                                      │
                                ┌─────┼─────┐
                                ▼     ▼     ▼
                              Once  Always  Reject
```

### 2.4 权限配置的精细度：模式匹配

OpenCode 的权限不是简单的"全开/全关"，它支持**通配符模式匹配**：

```typescript
read: {
  "*": "allow",           // 默认允许读取所有文件
  "*.env": "deny",        // 但禁止读取 .env 文件
  "*.env.*": "deny",      // 禁止读取 .env.production 等
  "*.env.example": "allow" // 但 .env.example 可以读（它只是模板）
}
```

> 🔑 **这就像公司的门禁系统**：员工可以进大楼（`*: allow`），但不能进机房（`*.env: deny`），除非是参观模型机房（`*.env.example: allow`）。

### 2.5 不同 Agent 有不同权限

这是一个很巧妙的设计：

| Agent | 关键权限 | 为什么？ |
| :--- | :--- | :--- |
| **build** | 几乎全部 allow | 它是"干活的"，需要完整能力 |
| **plan** | edit: deny | 它只负责"想"，不负责"改" |
| **explore** | 只允许读操作 | 它只负责"看"，不能改任何东西 |

```typescript
// plan agent - 只读模式
plan: {
  permission: {
    edit: { "*": "deny" }  // 禁止所有编辑操作
  }
}

// explore agent - 白名单模式（默认全禁，显式开放）
explore: {
  permission: {
    "*": "deny",        // 先禁止一切
    grep: "allow",      // 显式允许搜索
    glob: "allow",      // 显式允许文件匹配
    read: "allow",      // 显式允许读取
    // ... 其他只读操作
  }
}
```

> 💡 **设计思想**：这叫**最小权限原则（Principle of Least Privilege）**。每个角色只给它完成任务所需的最小权限，不多给。

---

## 📖 3：Agent 与 Tool 系统 — AI 的"角色"和"技能"

### 3.1 什么是 Agent？

Agent 不是一个新的 AI 模型，而是**同一个 AI 戴不同的"帽子"**。

```
┌──────────────────────────────────────────────┐
│              同一个 LLM（如 Claude）           │
│                                              │
│   🎩 build    📋 plan    🔍 explore           │
│   写代码      做规划      看代码               │
│   改文件      不能改      不能改               │
│   跑命令      只能看      只能搜               │
└──────────────────────────────────────────────┘
```

### 3.2 Agent 的两种模式

```
primary  → 直接与用户对话的"主角"
subagent → 被主角调用的"助手"
```

举个例子：用户问 build agent "帮我重构这个模块"

```
用户 ──→ build agent（primary）
              │
              ├─ "我先看看代码结构" → 调用 explore agent（subagent）
              │                         → explore 返回代码结构信息
              │
              ├─ "现在我知道怎么改了" → 直接使用 edit 工具修改文件
              │
              └─ "改完了，跑下测试" → 使用 bash 工具执行 npm test
```

### 3.3 Tool（工具）系统

Tool 是 Agent 的"手"和"脚"。每个工具的定义非常清晰：

```typescript
export const ReadTool = Tool.define("read", async (ctx) => {
  return {
    description: "Read a file...",     // 告诉 LLM 这个工具干什么
    parameters: z.object({             // 需要什么参数（用 Zod 做类型校验）
      filePath: z.string(),
    }),
    async execute(params, ctx) {       // 具体执行逻辑
      // 读取文件并返回内容
    },
  }
})
```

> 🔑 **这个模式的精髓**：工具对 LLM 来说只是一个"函数签名"（名字 + 描述 + 参数），LLM 决定什么时候调用哪个工具，execute 部分是真正执行的代码。

### 3.4 OpenCode 提供的工具清单

| 工具           | 作用        | 类比                  |
| :----------- | :-------- | :------------------ |
| `read`       | 读取文件内容    | 打开文件看看              |
| `edit`       | 编辑文件      | 用编辑器改代码             |
| `glob`       | 按模式匹配文件   | `ls *.ts`           |
| `grep`       | 搜索代码内容    | `grep -r "keyword"` |
| `bash`       | 执行命令      | 在终端敲命令              |
| `list`       | 列出目录      | `ls -la`            |
| `task`       | 调用子 Agent | 喊同事帮忙               |
| `webfetch`   | 抓取网页      | 打开浏览器看文档            |
| `websearch`  | 搜索网络      | Google 搜索           |
| `codesearch` | 代码搜索      | 语义级代码搜索             |

---

## 📖 4：迭代决策循环 — AI 的"灵魂"

### 4.1 这是 OpenCode 最核心的部分

一般人以为 AI 助手就是："收到问题 → 回答" 一步完成。

**错！** 真实的 AI agent 是这样工作的：

```
收到问题 → 想想需要什么信息 → 用工具获取信息 → 
  → 信息够了吗？
    → 不够 → 再获取更多信息 → 再判断...（循环）
    → 够了 → 执行最终行动 → 返回结果
```

### 4.2 用一个真实场景来理解

用户问：**"帮我修复 login 功能的 bug"**

```
🤖 第1轮思考：
   "login 功能？我先看看项目结构"
   → 调用 glob("**/*.ts")
   → 得到文件列表

🤖 第2轮思考：
   "找到了很多文件，我先搜搜哪些涉及 login"
   → 调用 grep("login", "**/*.ts")
   → 发现 src/auth/login.ts, src/api/auth.ts

🤖 第3轮思考：
   "让我看看这两个文件的具体内容"
   → 调用 read("src/auth/login.ts")
   → 调用 read("src/api/auth.ts")
   → 看到了具体代码

🤖 第4轮思考：
   "我找到 bug 了！login.ts 第 42 行的条件判断反了"
   "现在信息足够了，直接修复"
   → 调用 edit("src/auth/login.ts", ...)
   → 修复完成

🤖 第5轮思考：
   "改完了，跑下测试确认"
   → 调用 bash("npm test")
   → 测试通过 ✅

🤖 最终回答：
   "bug 已修复，问题出在 login.ts 第42行..."
```

### 4.3 代码层面怎么实现的？

核心是一个**双层循环**：

```typescript
async process(streamInput) {
  while (true) {                          // ← 外层循环：迭代决策
    const stream = await LLM.stream(streamInput)  // 调用 LLM

    for await (const value of stream.fullStream) { // ← 内层循环：处理流式响应
      switch (value.type) {
        case "tool-call":
          // LLM 决定调用工具 → 执行工具
          break
        case "tool-result":
          // 工具返回结果 → 加入上下文
          break
      }
    }
    
    // LLM 没有再调用工具 → 说明它觉得信息够了 → 跳出循环
    // LLM 还在调用工具 → 继续循环
  }
}
```

> 🔑 **精髓理解**：LLM 自己决定"够不够"。如果 LLM 的响应中没有工具调用（只有文本），就说明它认为信息已经足够，可以给出最终答案了。

### 4.4 死循环检测（DoomLoop）

如果 AI 一直重复做同样的事怎么办？

```typescript
const DOOM_LOOP_THRESHOLD = 3

// 检查最近3次工具调用是否完全相同
if (lastThree.length === DOOM_LOOP_THRESHOLD &&
    all_same_tool_calls &&   // 调用的工具和参数都一样
    no_errors) {             // 而且没有报错（不是在重试）
  throw new DoomLoopError()  // 强制中断！
}
```

> 💡 **为什么需要这个？** 想象 AI 一直在 `grep("bug")` → 没找到 → `grep("bug")` → 没找到... 无限循环。DoomLoop 检测就是"安全阀"。

### 4.5 Tool Chaining — 工具链

AI 不是随机调用工具的，有一个典型的**探索模式**：

```
glob("**/*.ts")          → 第1步：发现有哪些文件
       ↓
grep("API|export")       → 第2步：在文件中搜索关键词
       ↓
read("src/api/main.ts")  → 第3步：读取感兴趣的文件
       ↓
bash("npm test")         → 第4步：验证理解是否正确
```

这就像一个**侦探破案的过程**：
1. 先看看犯罪现场有什么（glob）
2. 搜索线索（grep）
3. 仔细检查可疑物品（read）
4. 验证推理（bash）

---

## 📖 5：Skill 系统 — 可复用的"技能包"

### 5.1 什么是 Skill？

Skill 就是一份**结构化的操作指南**，让 AI 在面对特定任务时知道该怎么做。

```markdown
<!-- .opencode/skill/test-skill/SKILL.md -->
---
name: test-skill
description: use this when asked to test skill
---
# 如何运行测试
1. 先检查 package.json 中的 test script
2. 运行 npm test
3. 如果失败，检查 jest.config.ts
```

> 🔑 **Skill vs Prompt 的区别**：Prompt 是"你是谁"，Skill 是"遇到特定情况该怎么做"。就像员工手册 vs SOP（标准操作流程）。

### 5.2 Skill 的存放位置

```
.opencode/skill/           ← 项目级 Skill（推荐）
.claude/skills/            ← 兼容 Claude Code 的 Skill
```

### 5.3 Skill 是怎么被发现和使用的？

```
用户问："帮我跑测试"
    │
    ▼
LLM 分析问题 → 发现有 test-skill 的描述匹配
    │
    ▼
自动加载 SKILL.md 的内容作为工具的指引
    │
    ▼
按照 Skill 中的步骤执行
```

---

## 🎯 总结：OpenCode 的整体架构一图看懂

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────┐               │
│  │         System Prompt 组装               │               │
│  │  Provider + 环境 + 规则 + Agent Prompt    │               │
│  └──────────────────────────────────────────┘               │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────┐               │
│  │         Agent（build/plan/explore）       │               │
│  │         ↕ 迭代决策循环                    │               │
│  │         ↕ Tool Chaining                  │               │
│  └──────────────────────────────────────────┘               │
│                    │           │                              │
│              ┌─────┘           └─────┐                       │
│              ▼                       ▼                        │
│  ┌────────────────┐     ┌────────────────────┐              │
│  │  权限系统检查    │     │   Skill 技能加载    │              │
│  │  allow/deny/ask │     │   操作指南注入       │              │
│  └────────────────┘     └────────────────────┘              │
│              │                       │                        │
│              └───────────┬───────────┘                        │
│                          ▼                                   │
│  ┌──────────────────────────────────────────┐               │
│  │       Tool 执行（read/edit/bash...）      │               │
│  └──────────────────────────────────────────┘               │
│                          │                                   │
│                          ▼                                   │
│                    最终输出给用户                              │
└─────────────────────────────────────────────────────────────┘
```

