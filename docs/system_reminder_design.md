# System Reminder 设计原理

## 概述

System Reminder 是 dm_cc Multi-Agent 系统的关键机制，用于在对话过程中动态注入当前模式的约束条件，确保 AI 始终遵守当前 Agent 角色的限制。

## 为什么需要 Reminder

### 核心问题：AI 的"遗忘"现象

大语言模型在长对话中会逐渐"遗忘"早期的系统指令：

- **初始状态**：AI 被告知 "你是 Plan Agent，只能读取不能编辑"
- **10 轮对话后**：AI 可能开始尝试编辑文件，因为它已忘记自己在 Plan 模式
- **根本原因**：上下文长度限制 + 注意力分散

### 解决方案：每轮动态提醒

不是一次性在 system prompt 中告知限制，而是在**每轮对话的最后**动态注入当前模式的约束。

---

## 为什么放在 Prompt 末尾效果好

### 1. 近因效应 (Recency Bias)

大语言模型对序列**末尾**的信息更敏感：

```
[系统指令...很长...] [Reminder: 记住！你现在不能编辑文件！]
                            ↑
                        模型更关注这里
```

| 位置 | 效果 |
|------|------|
| 开头 | 模型看了 3000 token 后已遗忘 |
| 中间 | 被前后文淹没 |
| 末尾 | 记忆新鲜，马上要生成回复 |

### 2. 上下文结构分层

```
┌─────────────────────────────────────────┐
│  System Prompt (背景/身份定义)           │  ← "你是谁"
│  "你是 Plan Agent，用于规划..."          │
├─────────────────────────────────────────┤
│  Message History (对话历史)              │  ← "你们聊了什么"
│  user: 帮我做个功能                      │
│  assistant: 让我看看...                  │
├─────────────────────────────────────────┤
│  System Reminder (当前约束)              │  ← "现在记住这个"
│  "CRITICAL: 你现在在 PLAN 模式..."       │
└─────────────────────────────────────────┘
```

Reminder 是对**当前状态**的约束，应该最接近决策点。

---

## Opencode 实现参考

### 核心代码

**文件**: `packages/opencode/src/session/prompt.ts:1323`

```typescript
async function insertReminders(input: {
  messages: MessageV2.WithParts[];
  agent: Agent.Info;
  session: Session.Info
}) {
  // 找到最后一条用户消息
  const userMessage = input.messages.findLast((msg) => msg.info.role === "user")
  if (!userMessage) return input.messages

  // Plan Agent 模式：插入 PLAN reminder
  if (input.agent.name === "plan") {
    userMessage.parts.push({
      type: "text",
      text: PROMPT_PLAN,  // 加载自 plan.txt
      synthetic: true,     // 标记为系统生成
    })
  }

  // 从 Plan 切换回 Build：插入 BUILD_SWITCH reminder
  const wasPlan = input.messages.some((msg) =>
    msg.info.role === "assistant" && msg.info.agent === "plan"
  )
  if (wasPlan && input.agent.name === "build") {
    userMessage.parts.push({
      type: "text",
      text: BUILD_SWITCH,  // 加载自 build-switch.txt
      synthetic: true,
    })
  }
}
```

### 实际调用流程

```
用户输入 -> opencode 处理
              │
              ▼
    ┌─────────────────────┐
    │  1. 确定当前 Agent   │  (build or plan)
    │  2. 加载对话历史      │
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  insertReminders()  │  <-- 关键：在最后一条 user message
    │                     │       的 parts 中插入 reminder
    │  userMessage.parts  │
    │    ├── [原始文本]    │
    │    └── [reminder]   │  <-- 追加到末尾
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  发送给 LLM         │  <-- reminder 在 message 序列靠后位置
    │  (system + history  │
    │   + user + reminder)│
    └─────────────────────┘
```

### 为什么放在 user message 的 parts 中

对比两种方案：

**方案 A：放在 system role（不推荐）**
```javascript
[
  { role: "system", content: "你是助手..." },           // 开头
  { role: "system", content: "记住：你在 plan 模式" },  // 容易被忽略
  ... // 很长的对话
  { role: "user", content: "执行吧" }
]
```

**方案 B：放在 user message parts（opencode 做法）**
```javascript
[
  { role: "system", content: "你是助手..." },
  ... // 很长的对话
  {
    role: "user",
    content: "执行吧",
    parts: [
      { text: "执行吧" },
      { text: "记住：你在 plan 模式", synthetic: true }  // 紧贴决策点
    ]
  }
]
```

**方案 B 的优势**：
- Reminder 紧贴着当前决策的上下文
- 不受历史消息长度影响，永远在最后
- 可以动态变化（每轮都可以不同）

---

## dm_cc 的实现

### 文件结构

```
dm_cc/src/dm_cc/core/
├── reminders.py       # Reminder 文本定义
├── message.py         # Message 模型支持 synthetic 标记
└── plan.py           # Plan 文件管理
```

### Reminder 定义

**文件**: `dm_cc/src/dm_cc/core/reminders.py`

```python
# Plan 模式提醒 - 注入到 Plan Agent 的 prompt 中
PLAN_MODE_REMINDER = """<system-reminder>
# Plan Mode - System Reminder

CRITICAL: Plan mode ACTIVE - you are in READ-ONLY phase. STRICTLY FORBIDDEN:
ANY file edits, modifications, or system changes. Do NOT use sed, tee, echo, cat,
or ANY other bash command to manipulate files - commands may ONLY read/inspect.

...
</system-reminder>
"""

# Build 切换提醒 - 从 Plan 切换回 Build 时注入
BUILD_SWITCH_REMINDER = """<system-reminder>
Your operational mode has changed from plan to build.
You are no longer in read-only mode.
You are permitted to make file changes, run shell commands, and utilize your
arsenal of tools as needed.
</system-reminder>
"""
```

### Agent Loop 注入

**文件**: `dm_cc/src/dm_cc/agent.py`

```python
def _build_system_prompt(self) -> str:
    """构建系统提示 - 包含 agent-specific reminder"""
    base_prompt = self.config.system_prompt
    reminders = []

    # Plan 模式提醒
    if self.agent_name == "plan":
        reminders.append(PLAN_MODE_REMINDER)

    # 从 Plan 切换回 Build 的提醒
    elif self._was_plan_mode:
        # 读取 plan 文件内容
        plan_result = read_latest_plan()
        if plan_result:
            plan_path, plan_content = plan_result
            reminders.append(build_switch_with_plan(plan_content, plan_path))
        else:
            reminders.append(BUILD_SWITCH_REMINDER)
        self._was_plan_mode = False

    if reminders:
        base_prompt = base_prompt + "\n\n" + "\n\n".join(reminders)

    return base_prompt
```

---

## 实际效果示例

### 场景 1：Plan Agent 防止误操作

**对话历史（10轮后）**：
```
user: 帮我做个登录功能
assistant: 让我先了解一下项目结构...
[10轮对话后]
user: 直接改吧，把登录代码写进去
```

**不加 Reminder 的结果**：
```
assistant: 好的，我现在修改文件...
→ 错误！Plan Agent 不应该编辑文件
```

**加了 Reminder 的结果**：
```
assistant: 我现在处于 Plan 模式，只能读取不能编辑。
让我先调用 plan_exit 切换回 Build Agent 再执行...
→ 正确！先切换模式再执行
```

### 场景 2：Build Agent 读取 Plan 内容

**切换时自动注入**：
```
<system-reminder>
Your operational mode has changed from plan to build.
You are no longer in read-only mode.

A plan file exists at .dm_cc/plans/20260302-plan.md.
You should execute on the plan defined within it:

--- Plan Content ---
1. 创建用户模型
2. 实现登录接口
3. 添加 JWT 验证
--- End Plan ---
</system-reminder>
```

**效果**：Build Agent 立即知道要执行什么计划，无需重新询问用户。

---

## 关键设计要点

| 要点 | 说明 |
|------|------|
| **动态注入** | 每轮对话都重新注入，不是一次性 |
| **位置靠后** | 放在 user message 或 prompt 末尾 |
| **synthetic 标记** | 标记为系统生成，不混淆真实用户输入 |
| **模式感知** | 根据当前 Agent 类型注入不同 reminder |
| **状态切换** | 切换 Agent 时注入切换提醒 + 上下文 |

---

## 相关文件

- `dm_cc/src/dm_cc/core/reminders.py` - Reminder 文本定义
- `dm_cc/src/dm_cc/agent.py` - Agent Loop 注入逻辑
- `dm_cc/src/dm_cc/core/message.py` - Message 模型

---

## 参考

- [opencode prompt.ts](https://github.com/sst/opencode/blob/main/packages/opencode/src/session/prompt.ts)
- [Anthropic: System Prompts Guide](https://docs.anthropic.com/claude/docs/system-prompts)

---

*创建日期: 2026-03-04*
