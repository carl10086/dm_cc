
## 🚀 第一部分：动态组装 System Prompt

传统做法是写一个静态的 System Prompt 文本文件，OpenCode 的创新在于：

```
System Prompt = 
    Provider 特定模板 (适配不同 AI 模型)
  + 环境信息 (当前目录、日期、平台)
  + 自定义规则 (项目规范、团队约定)
  + Agent 特定指令 (不同 Agent 的专属任务)
```

**为什么这样设计？**
- ✅ **灵活性**：不同模型用不同模板
- ✅ **上下文感知**：自动注入当前环境
- ✅ **可扩展性**：轻松添加新规则
- ✅ **维护性**：各部分独立修改

---

## 🏗️ 第二部分：四层架构深度解析

`OpenCode` 的 `System Prompt` 由四层组成，每一层都有特定职责。

### Layer 1: Provider 特定提示 (模型适配层)

#### 核心问题
不同的 AI 模型就像说不同方言的人：
- **Claude (Anthropic)**：喜欢散文式、详细的解释
- **GPT-4 (OpenAI)**：偏好指令化、强调自主性
- **Gemini (Google)**：适合列表式、规则清单

#### 源码解析

```typescript
// packages/opencode/src/session/system.ts
export function provider(model: Provider.Model) {
  if (model.api.id.includes("gpt-5")) return [PROMPT_CODEX]
  if (model.api.id.includes("gpt-") || model.api.id.includes("o1")) 
    return [PROMPT_BEAST]
  if (model.api.id.includes("gemini-")) return [PROMPT_GEMINI]
  if (model.api.id.includes("claude")) return [PROMPT_ANTHROPIC]
  return [PROMPT_ANTHROPIC_WITHOUT_TODO]
}
```

**设计思路**：通过模型 ID 的字符串匹配，动态选择最适合的提示模板。

#### 实际例子

**Claude 模板 (anthropic.txt)** - 散文风格
```
You are OpenCode, the best coding agent on the planet.

You are an interactive CLI tool that helps users with 
software engineering tasks. Use the instructions below...

IMPORTANT: You must NEVER generate or guess URLs...
```

**GPT-4 模板 (beast.txt)** - 指令风格
```
You are opencode, an agent - please keep going until 
the user's query is completely resolved.

You MUST iterate and keep going until the problem is solved.

THE PROBLEM CAN NOT BE SOLVED WITHOUT EXTENSIVE INTERNET RESEARCH.
```

**关键区别**：

| 维度 | Claude | GPT-4 |
|:---|:---|:---|
| 风格 | 友好、解释性强 | 命令式、强调持续性 |
| 长度 | 较短 (~106 行) | 较长 (~148 行) |
| 重点 | 安全规范 | 自主迭代、深度研究 |

#### 🎓 深层理解

这不是简单的"翻译"，而是**针对模型特性的优化**：

- Claude 更擅长理解上下文 → 提示更简洁
- GPT-4 需要明确的持续指令 → 强调"keep going"
- Gemini 偏好结构化 → 使用列表和规则

---

### Layer 2: 环境信息 (上下文感知层)

#### 核心问题

AI 需要知道它在"哪里"工作：

- 当前目录是什么？
- 是否是 Git 仓库？
- 运行在什么操作系统？
- 今天是几号？

#### 源码解析

```typescript
// packages/opencode/src/session/system.ts
export async function environment() {
  const project = Instance.project
  return [
    [
      `Here is some useful information about the environment:`,
      `<env>`,
      `  Working directory: ${Instance.directory}`,
      `  Is directory a git repo: ${project.vcs === "git" ? "yes" : "no"}`,
      `  Platform: ${process.platform}`,
      `  Today's date: ${new Date().toDateString()}`,
      `</env>`,
    ].join("\n"),
  ]
}
```

#### 实际输出示例

```xml
<env>
  Working directory: /Users/felix/learningspace/opencode
  Is directory a git repo: yes
  Platform: darwin
  Today's date: Wed Feb 10 2026
</env>
```

#### 🎓 为什么需要这些信息？

**例子：路径解析:**

用户: "读取 `src/main.ts` 文件"

AI 内部思考:
  - 工作目录: `/Users/felix/project`
  - 完整路径: `/Users/felix/project/src/main.ts`
  - 调用 `read` 工具

**例子：平台适配:**

```
用户: "列出所有进程"

[在 macOS 上]
AI: 使用 `ps aux` 命令

[在 Windows 上]
AI: 使用 `tasklist` 命令
```

**例子：时间感知:**

```
用户: "生成今天的日志文件名"
AI: 基于环境中的日期 → log_2026-02-10.txt
```

---

### Layer 3: 自定义规则 (项目规范层)

#### 核心问题
每个项目/团队都有自己的规范：
- 代码风格（用 2 空格还是 4 空格？）
- Git 提交规范（Conventional Commits？）
- 技术栈约定（用 Vue 还是 React？）

#### 加载策略：三层级优先级

```
优先级（高→低）:
1. 项目级规则 (AGENTS.md / CLAUDE.md)
2. 全局用户级规则 (~/.claude/CLAUDE.md)
3. 配置指令 (config.instructions)
```

#### 源码解析

```typescript
// packages/opencode/src/session/system.ts
export async function custom() {
  const paths = new Set<string>()
  const urls: string[] = []

  // 1. 查找本地项目规则 (向上遍历)
  for (const localRuleFile of LOCAL_RULE_FILES) {
    const matches = await Filesystem.findUp(
      localRuleFile, 
      Instance.directory, 
      Instance.worktree
    )
    if (matches.length > 0) {
      paths.add(matches[0])
      break  // ← 找到第一个就停止！
    }
  }

  // 2. 查找全局规则
  for (const globalRuleFile of GLOBAL_RULE_FILES) {
    if (await Filesystem.exists(globalRuleFile)) {
      paths.add(globalRuleFile)
      break  // ← 也是首个匹配即停
    }
  }

  // 3. 处理配置指令
  for (const instruction of config.instructions || []) {
    if (instruction.startsWith("http")) {
      urls.push(instruction)
    } else {
      // 处理文件路径和 glob 模式
    }
  }

  // 并行加载所有内容
  return await Promise.all([
    ...Array.from(paths).map(p => 
      fs.readFile(p, "utf-8").catch(() => "")
    ),
    ...urls.map(url => 
      fetch(url).then(r => r.text()).catch(() => "")
    )
  ]).filter(Boolean)
}
```

#### 🎓 设计哲学："首个匹配即停"

**为什么不加载所有找到的文件？**

```
假设项目结构:
/project/
  ├── AGENTS.md        ← 项目规范
  └── .claude/
      └── AGENTS.md    ← 个人设置
```

如果两个都加载 → **可能冲突**！
- 项目规范说："用 2 空格"
- 个人设置说："用 4 空格"

OpenCode 的选择：**只加载第一个**（项目级优先）

#### 实际例子：AGENTS.md

```markdown
# 项目开发规范

## 代码风格
- 使用 TypeScript strict 模式
- 函数名采用 camelCase
- 类名采用 PascalCase

## Git 提交规范
- 使用 Conventional Commits
- 格式: `type(scope): description`
- 类型: feat/fix/docs/refactor

## 技术栈
- 前端: React + TypeScript
- 状态管理: Zustand
- 样式: Tailwind CSS
```

这些规则会被自动注入到 System Prompt 中，AI 会遵循这些约定。

---

### Layer 4: Agent 特定提示 (角色定位层)

#### 核心问题

不同的 `Agent` 有不同的"人格"和职责：

- **build Agent**：全能开发者，可以读写代码
- **plan Agent**：规划师，只能阅读和制定计划
- **explore Agent**：探索者，专注代码理解

#### 源码解析：Agent 配置

```typescript
// packages/opencode/src/agent/agent.ts
export const builtInAgents: Record<string, Agent> = {
  build: {
    name: "build",
    mode: "primary",
    // 没有 prompt 属性 → 使用 provider() 提供的模板
    permission: {
      // 完整权限
    }
  },
  
  plan: {
    name: "plan",
    mode: "primary",
    // 通过 insertReminders 动态注入
    permission: {
      edit: "deny",  // ← 禁止编辑！
      create: {
        allow: ".opencode/plans/*.md"  // 只能创建计划文件
      }
    }
  },
  
  explore: {
    name: "explore",
    mode: "subagent",  // ← 只能被调用
    prompt: PROMPT_EXPLORE,  // ← 专属提示
    permission: {
      allow: ["grep", "glob", "list", "read"],  // 只读工具
      bash: "deny",
      edit: "deny"
    }
  }
}
```

#### 🎓 模式设计：Primary vs Subagent

**形象比喻**：
- **Primary Agent** = 项目经理
  - 直接响应用户请求
  - 可以调用其他 Agent
  - 一个会话只有一个活跃的 Primary Agent

- **Subagent** = 专家顾问
  - 不能独立工作
  - 只能被 Primary Agent 通过 `Task` 工具调用
  - 专注特定领域任务

#### 实际例子：explore Agent 的提示

```typescript
// packages/opencode/src/session/prompt/explore.txt
You are a code exploration agent. Your task is to:

1. Systematically explore the codebase
2. Understand the project structure
3. Identify key components and their relationships
4. Report findings in a structured format

You have access to:
- grep: search for patterns
- glob: find files matching patterns
- list: list directory contents
- read: read file contents
- codesearch: semantic code search

You CANNOT modify files. Focus on understanding.
```

**注意**：explore Agent 的提示明确说明了它**不能修改文件**，这与权限配置一致。

---

## 🔄 第三部分：动态组装流程

现在我们理解了四层架构，让我们看看这些层如何在运行时组装成完整的 System Prompt。

### 完整流程图

```
用户发送消息
    ↓
[prompt.ts] 主循环启动
    ↓
1. 确定当前 Agent (build/plan/explore...)
    ↓
2. 调用 SystemPrompt.environment()
   → 收集环境信息
    ↓
3. 调用 SystemPrompt.custom()
   → 加载自定义规则
    ↓
4. 调用 resolveTools(agent)
   → 根据 Agent 权限过滤工具
    ↓
5. 创建 SessionProcessor
    ↓
6. 调用 processor.process({
     system: [...environment, ...custom],  ← 组装！
     messages: [...],
     tools: [...],
     model: {...}
   })
    ↓
7. [SessionProcessor] 构造最终请求
   → 根据 Agent 是否有 prompt 属性决定：
      - 有 → 使用 Agent.prompt
      - 无 → 使用 SystemPrompt.provider(model)
    ↓
8. 发送给 LLM Provider
```

### 源码深度解析

#### Step 1: 主循环入口

```typescript
// packages/opencode/src/session/prompt.ts:553-560
const tools = await resolveTools({
  agent,
  session,
  model,
  tools: lastUser.tools,
  processor,
  bypassAgentCheck,
})
```

#### Step 2: 组装 System 参数

```typescript
// packages/opencode/src/session/prompt.ts:592-611
const result = await processor.process({
  user: lastUser,
  agent,
  abort,
  sessionID,
  system: [
    ...(await SystemPrompt.environment()),  // ← Layer 2
    ...(await SystemPrompt.custom())        // ← Layer 3
  ],
  messages: [
    ...MessageV2.toModelMessage(sessionMessages),
    ...(isLastStep ? [{ role: "assistant", content: MAX_STEPS }] : []),
  ],
  tools,
  model,
})
```

**注意**：这里只包含 `environment` 和 `custom`，`Provider` 和 `Agent` 提示在哪里？

#### Step 3: SessionProcessor 处理

```typescript
// packages/opencode/src/session/processor.ts (简化版)
class SessionProcessor {
  async process(input) {
    // 构造完整的 system messages
    const systemMessages = [
      ...SystemPrompt.header(this.model.providerID),  // ← Layer 0
      ...(input.agent.prompt 
           ? [input.agent.prompt]                      // ← Layer 4 (Agent)
           : SystemPrompt.provider(this.model)),       // ← Layer 1 (Provider)
      ...input.system  // ← Layer 2 + 3 (environment + custom)
    ]
    
    // 发送给 LLM
    return await this.sendToLLM({
      system: systemMessages,
      messages: input.messages,
      tools: input.tools
    })
  }
}
```

### 🎓 关键洞察

#### Insight 1: 互斥关系

```
Agent.prompt 存在？
  ├─ 是 → 使用 Agent.prompt (如 explore Agent)
  └─ 否 → 使用 SystemPrompt.provider(model) (如 build Agent)
```

这意味着：
- `build` Agent → 使用 `anthropic.txt` / `beast.txt`
- `explore` Agent → 使用 `explore.txt`

#### Insight 2: header() 的特殊作用

```typescript
export function header(providerID: string) {
  if (providerID.includes("anthropic")) {
    return [ANTHROPIC_SPOOF]  // "假装你不是 Claude"
  }
  return []
}
```

这是一个**身份伪装 hack**！
- 告诉 Claude："你不是 Claude，你是通用 AI"
- 为什么？可能是为了绕过某些限制或改变模型行为

#### Insight 3: 消息转换

```typescript
// MessageV2.toModelMessage() 的作用
// 内部格式 → LLM API 格式
MessageV2 {
  role: "user",
  parts: [
    { type: "text", text: "..." },
    { type: "file", path: "..." },
    { type: "tool", result: "..." }
  ]
}
    ↓ 转换
{
  role: "user",
  content: [
    { type: "text", text: "..." },
    { type: "image_file", file: "..." },
    { type: "tool-use", ... }
  ]
}
```

---

## 🎭 第四部分：Agent 模式设计哲学

现在让我们深入理解 Agent 的设计思想。

### Agent 的三种模式

```typescript
type AgentMode = "primary" | "subagent" | "all"
```

| 模式           | 能力             | 使用场景                 |
| :----------- | :------------- | :------------------- |
| **primary**  | 可以独立响应用户请求     | `build`, `plan`      |
| **subagent** | 只能被其他 Agent 调用 | `explore`, `general` |
| **all**      | 两种能力都有         | 自定义 Agent 默认模式       |

### 设计案例分析：plan Agent

#### 需求
创建一个"规划模式"，让 AI 只能：
- ✅ 阅读代码
- ✅ 创建计划文档
- ❌ 修改代码

#### 实现策略

```typescript
plan: {
  name: "plan",
  mode: "primary",
  permission: {
    // 禁止所有编辑操作
    edit: "deny",
    bash: "deny",
    
    // 只允许创建计划文件
    create: {
      allow: ".opencode/plans/*.md",
      deny: "*"
    }
  }
}
```

#### 提示注入方式

```typescript
// packages/opencode/src/session/prompt.ts
function insertReminders(input) {
  const userMessage = findLastUserMessage(input.messages)
  
  if (input.agent.name === "plan") {
    userMessage.parts.push({
      type: "text",
      text: PROMPT_PLAN,
      synthetic: true  // ← 标记为"合成"
    })
  }
}
```

**为什么用 insertReminders 而不是 Agent.prompt？**
- `insertReminders` → 注入到**用户消息末尾**
- 好处：可以参与**上下文压缩** (compaction)
- 当对话很长时，旧消息会被压缩，但提示会保留

### 权限系统与 System Prompt 的关系

```
┌─────────────────────────────────────────┐
│         两层防护机制                      │
├─────────────────────────────────────────┤
│                                         │
│  1. System Prompt (指导)                │
│     "你应该只读取代码，不要修改"          │
│                 ↓                       │
│  2. Permission (强制)                   │
│     edit: "deny"  ← 硬性拒绝            │
│                                         │
└─────────────────────────────────────────┘
```

**即使 AI 试图调用 edit，权限系统也会拒绝**。

#### 例子：plan Agent 尝试编辑

```
AI 思考: "我需要修改这个文件"
AI 行动: toolCall("edit", {file: "src/main.ts", ...})
          ↓
[权限检查] edit 被 deny
          ↓
返回错误: "Permission denied: edit is not allowed"
```

---

## 🛠️ 第五部分：实战应用与扩展

现在让我们把学到的知识应用到实际场景中。

### 场景 1：创建自定义 Agent

**需求**：创建一个"文档审查 Agent"，只能：
- 读取 Markdown 文件
- 检查拼写和语法
- 提出改进建议
- **不能**修改文件

#### 实现步骤

**Step 1: 创建提示文件**

```typescript
// prompts/doc-reviewer.txt
You are a documentation review agent.

Your responsibilities:
1. Read markdown files
2. Check for:
   - Spelling errors
   - Grammar issues
   - Unclear explanations
   - Missing examples
3. Suggest improvements
4. DO NOT modify files directly

Output format:
## File: [filename]
### Issues Found:
- [issue 1]
- [issue 2]

### Suggestions:
- [suggestion 1]
```

**Step 2: 配置 Agent**

```json
// config.json
{
  "agent": {
    "doc-reviewer": {
      "mode": "primary",
      "prompt": "./prompts/doc-reviewer.txt",
      "description": "Review documentation for quality",
      "permission": {
        "allow": ["read", "glob", "grep"],
        "edit": "deny",
        "bash": "deny",
        "create": "deny"
      },
      "steps": 20
    }
  }
}
```

**Step 3: 使用**

```bash
$ opencode --agent doc-reviewer
> 审查 docs/ 目录下的所有文档
```

### 场景 2：适配新的 LLM Provider

**需求**：添加对 "DeepSeek" 模型的支持

#### 实现步骤

**Step 1: 创建提示模板**

```typescript
// packages/opencode/src/session/prompt/deepseek.txt
You are OpenCode, powered by DeepSeek.

Core Principles:
- Reasoning-first: Think deeply before acting
- Efficiency: Minimize token usage
- Precision: Be exact in code generation

[...具体指令...]
```

**Step 2: 修改 provider() 函数**

```typescript
// packages/opencode/src/session/system.ts
export function provider(model: Provider.Model) {
  if (model.api.id.includes("deepseek")) return [PROMPT_DEEPSEEK]  // ← 新增
  if (model.api.id.includes("gpt-5")) return [PROMPT_CODEX]
  // ...
}
```

**Step 3: 测试**

```bash
$ opencode --model deepseek-coder
```

### 场景 3：动态环境信息扩展

**需求**：添加"当前 Git 分支"到环境信息

#### 实现步骤

```typescript
// packages/opencode/src/session/system.ts
export async function environment() {
  const project = Instance.project
  
  // 新增：获取 Git 分支
  let gitBranch = "N/A"
  if (project.vcs === "git") {
    try {
      const result = await exec("git branch --show-current", {
        cwd: Instance.directory
      })
      gitBranch = result.stdout.trim()
    } catch {}
  }
  
  return [
    [
      `<env>`,
      `  Working directory: ${Instance.directory}`,
      `  Is directory a git repo: ${project.vcs === "git" ? "yes" : "no"}`,
      `  Git branch: ${gitBranch}`,  // ← 新增
      `  Platform: ${process.platform}`,
      `  Today's date: ${new Date().toDateString()}`,
      `</env>`,
    ].join("\n"),
  ]
}
```

### 场景 4：项目规范自动化

**需求**：让 AI 自动遵循项目的 ESLint 配置

#### 实现步骤

**Step 1: 创建 AGENTS.md**

```markdown
<!-- .opencode/AGENTS.md -->
# Project Coding Standards

## ESLint Configuration
The project uses ESLint with the following key rules:
- `semi`: ["error", "always"] - Always use semicolons
- `quotes`: ["error", "double"] - Use double quotes
- `indent`: ["error", 2] - 2 spaces indentation
- `comma-dangle`: ["error", "always-multiline"]

When generating or modifying code:
1. Read .eslintrc.js first
2. Follow the configured rules
3. Run `npm run lint` after changes
```

**Step 2: AI 自动读取**

当 AI 启动时，`SystemPrompt.custom()` 会自动加载这个文件，AI 就会遵循这些规范。

---

## 📝 总结：核心设计原则

通过这篇教程，我们学到了 OpenCode System Prompt 系统的核心设计原则：

### 1. 分层架构 (Layered Architecture)
```
Provider → 适配不同模型
Environment → 感知运行环境
Custom → 加载项目规范
Agent → 定义角色职责
```

### 2. 职责分离 (Separation of Concerns)
```
System Prompt → "应该怎么做"
Permission → "能不能做"
Tools → "可以做什么"
```

### 3. 动态组装 (Dynamic Composition)
```
运行时根据:
- 模型类型
- 当前环境
- 项目配置
- Agent 选择

→ 动态生成最优的 System Prompt
```

### 4. 首个匹配 (First Match)
```
避免规则冲突 → 只加载第一个匹配的配置
本地优先 → 项目规范优先于全局设置
```

### 5. 防御性设计 (Defensive Design)
```
System Prompt (软指导) + Permission (硬约束)
= 双重保护机制
```

---

## 🤔 思考

1. **为什么 `header()` 只针对 Anthropic？**
   - 提示：考虑 Claude 的特殊限制

2. **为什么 plan Agent 用 insertReminders 而不是 Agent.prompt？**
   - 提示：考虑长对话的上下文管理

3. **如果你要设计一个"测试 Agent"，它应该有哪些权限和提示？**

4. **在多租户系统中，如何隔离不同用户的自定义规则？**

---

