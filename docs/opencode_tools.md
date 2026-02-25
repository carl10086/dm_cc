# OpenCode 工具参考文档

本文档详细整理了 OpenCode 的全部 23 个工具，包括参数定义、返回值和特殊功能。

---

## 目录

- [工具总览](#工具总览)
- [文件系统工具](#文件系统工具)
- [命令执行工具](#命令执行工具)
- [Web 工具](#web-工具)
- [LSP 工具](#lsp-工具)
- [任务管理工具](#任务管理工具)
- [规划工具](#规划工具)
- [实用工具](#实用工具)

---

## 工具总览

| 分类 | 数量 | 工具 |
|------|------|------|
| 文件系统 | 8 | read, write, edit, multiedit, apply_patch, glob, grep, ls |
| 命令执行 | 1 | bash |
| Web | 3 | websearch, webfetch, codesearch |
| LSP | 1 | lsp |
| 任务管理 | 2 | task, todo |
| 规划 | 2 | plan_enter, plan_exit |
| 实用工具 | 5 | batch, question, skill, invalid |
| **总计** | **23** | |

---

## 文件系统工具

### 1. read

读取文件或目录内容。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `filePath` | string | 是 | 文件或目录的绝对路径 |
| `offset` | number | 否 | 起始行号（1-indexed） |
| `limit` | number | 否 | 最大读取行数（默认：2000） |

**返回值：**
- 文件内容（带行号前缀）
- 目录列表（子目录带 `/` 后缀）
- 图片/PDF 作为附件返回

**特殊功能：**
- 支持图片和 PDF 附件
- 二进制文件检测（排除常见二进制扩展名）
- 超过 2000 字符的行会被截断
- 单次读取最大 50KB 输出

---

### 2. write

写入文件（覆盖现有文件）。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `filePath` | string | 是 | 文件的绝对路径 |
| `content` | string | 是 | 写入的内容 |

**返回值：**
- 成功消息
- LSP 诊断信息（如果检测到错误）

**特殊功能：**
- 如果文件已存在，需要先读取文件
- 发布文件编辑事件
- 返回写入文件及其他文件的错误（每文件最多 20 个错误，最多 5 个文件）

---

### 3. edit

执行精确的字符串替换编辑。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `filePath` | string | 是 | 文件的绝对路径 |
| `oldString` | string | 是 | 要替换的文本 |
| `newString` | string | 是 | 替换后的文本（必须不同） |
| `replaceAll` | boolean | 否 | 替换所有匹配项（默认：false） |

**返回值：**
- 成功消息
- diff 对比
- LSP 诊断信息

**特殊功能：**
- **9 种匹配策略**：
  1. Simple - 精确匹配
  2. LineTrimmed - 行首尾去空格匹配
  3. BlockAnchor - 块锚点匹配
  4. WhitespaceNormalized - 空白字符规范化匹配
  5. IndentationFlexible - 缩进灵活匹配
  6. EscapeNormalized - 转义字符规范化匹配
  7. TrimmedBoundary - 边界去空格匹配
  8. ContextAware - 上下文感知匹配
  9. MultiOccurrence - 多出现匹配
- 使用 Levenshtein 距离进行模糊匹配
- 编辑期间文件锁定

---

### 4. multiedit

对单个文件进行批量编辑（基于 edit 工具）。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `filePath` | string | 是 | 文件的绝对路径 |
| `edits` | array | 是 | 编辑对象数组 |

**edits 数组项结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `filePath` | string | 文件路径 |
| `oldString` | string | 要替换的文本 |
| `newString` | string | 替换后的文本 |
| `replaceAll` | boolean | 是否替换所有（可选） |

**返回值：**
- 所有编辑的合并结果

**特殊功能：**
- 原子操作：要么全部成功，要么全部不应用
- 按顺序依次应用编辑

---

### 5. apply_patch

应用 diff patch 进行文件操作。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `patchText` | string | 是 | 完整的 patch 文本 |

**Patch 格式：**

```
*** Begin Patch
*** Add File: <path>
<content>
*** Update File: <path>
<content>
*** Delete File: <path>
*** Move File: <old_path>
*** Move to: <new_path>
*** End Patch
```

**返回值：**
- 文件变更摘要（A/M/D 表示添加/修改/删除）

**特殊功能：**
- 支持添加、更新、删除、移动操作
- 应用前验证 patch
- 返回变更文件的 LSP 诊断

---

### 6. glob

快速文件模式匹配。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pattern` | string | 是 | Glob 模式（如 `"**/*.js"`, `"src/**/*.ts"`） |
| `path` | string | 否 | 搜索目录（默认：当前工作目录） |

**返回值：**
- 匹配的文件路径列表（按修改时间排序）

**特殊功能：**
- 最多 100 个结果（超出会截断并警告）
- 按修改时间排序（最新的在前）

---

### 7. grep

使用正则表达式进行内容搜索。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pattern` | string | 是 | 正则表达式模式 |
| `path` | string | 否 | 搜索目录（默认：当前目录） |
| `include` | string | 否 | 文件包含模式（如 `"*.js"`, `"*.{ts,tsx}"`） |

**返回值：**
- 匹配的文件路径和行号

**特殊功能：**
- 内部使用 ripgrep
- 最多 100 个匹配（超出会截断并警告）
- 按文件修改时间排序
- 处理 Unix 和 Windows 换行符

---

### 8. ls (list)

以树形结构列出文件和目录。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `path` | string | 否 | 目录绝对路径（默认：工作区） |
| `ignore` | string[] | 否 | 忽略的 glob 模式列表 |

**返回值：**
- 层级目录列表

**特殊功能：**
- 最多 100 个文件
- 内置忽略模式（node_modules, .git 等）
- 树形结构渲染

---

## 命令执行工具

### 9. bash

在持久化的 shell 会话中执行 bash 命令。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `command` | string | 是 | 要执行的命令 |
| `description` | string | 是 | 5-10 字的命令描述 |
| `timeout` | number | 否 | 超时时间（毫秒，默认：120000 = 2分钟） |
| `workdir` | string | 否 | 工作目录（默认：项目目录） |

**返回值：**
- 命令输出和退出码

**特殊功能：**
- 使用 tree-sitter bash 解析器解析命令
- 追踪文件系统访问用于权限检查
- 支持外部目录访问
- 支持超时和中止
- 元数据中输出截断于 30KB
- Git 集成与安全协议

---

## Web 工具

### 10. websearch

使用 Exa AI 进行网页搜索。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 搜索查询 |
| `numResults` | number | 否 | 结果数量（默认：8） |
| `livecrawl` | enum | 否 | 实时爬取模式（"fallback" \| "preferred"） |
| `type` | enum | 否 | 搜索类型（"auto" \| "fast" \| "deep"，默认："auto"） |
| `contextMaxCharacters` | number | 否 | 最大上下文长度（默认：10000） |

**返回值：**
- 搜索结果及相关网站内容

**特殊功能：**
- 日期感知（描述中使用当前日期）
- 25 秒超时
- SSE 响应解析

---

### 11. webfetch

从 URL 获取内容并转换为指定格式。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 要获取的 URL |
| `format` | enum | 否 | 输出格式（"text" \| "markdown" \| "html"，默认："markdown"） |
| `timeout` | number | 否 | 超时时间（秒，最大：120） |

**返回值：**
- 指定格式的内容

**特殊功能：**
- HTTP 自动升级为 HTTPS
- 5MB 响应大小限制
- 支持图片获取作为附件
- 使用 Turndown 进行 HTML 到 Markdown 转换
- Cloudflare 机器人检测处理
- 基于格式的 Accept 头协商

---

### 12. codesearch

使用 Exa Code API 搜索编程相关内容。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | 是 | API、库、SDK 的搜索查询 |
| `tokensNum` | number | 否 | 返回的 token 数量（1000-50000，默认：5000） |

**返回值：**
- 代码片段和文档

**特殊功能：**
- 针对编程查询优化
- 30 秒超时
- MCP（Model Context Protocol）API 集成

---

## LSP 工具

### 13. lsp

与 Language Server Protocol 服务器交互获取代码智能。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `operation` | enum | 是 | 操作类型 |
| `filePath` | string | 是 | 文件路径 |
| `line` | number | 是 | 行号（1-based） |
| `character` | number | 是 | 字符偏移（1-based） |

**operation 可选值：**

| 值 | 说明 |
|----|------|
| `goToDefinition` | 查找符号定义 |
| `findReferences` | 查找所有引用 |
| `hover` | 获取悬停信息 |
| `documentSymbol` | 获取文档符号 |
| `workspaceSymbol` | 搜索工作区符号 |
| `goToImplementation` | 查找实现 |
| `prepareCallHierarchy` | 获取调用层次项 |
| `incomingCalls` | 查找调用者 |
| `outgoingCalls` | 查找被调用者 |

**返回值：**
- LSP 服务器的 JSON 结果

**特殊功能：**
- 检查 LSP 服务器可用性
- 内部将 1-based 坐标转换为 0-based

---

## 任务管理工具

### 14. task

启动子代理处理复杂的多步骤任务。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `description` | string | 是 | 3-5 字的简短任务描述 |
| `prompt` | string | 是 | 给代理的详细任务 |
| `subagent_type` | string | 是 | 专业代理类型 |
| `task_id` | string | 否 | 恢复之前的任务会话 |
| `command` | string | 否 | 触发此任务的命令 |

**返回值：**
- 任务结果和会话 ID（用于恢复）

**特殊功能：**
- 创建带权限的隔离会话
- 支持任务恢复
- 根据权限过滤可访问的代理
- 默认禁用子代理的 todo 工具

---

### 15. todo (todowrite / todoread)

创建和管理结构化任务列表。

**todowrite 参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `todos` | array | 是 | 待办事项对象数组 |

**todos 数组项结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 唯一标识符 |
| `content` | string | 任务描述 |
| `status` | enum | 状态："pending" \| "in_progress" \| "completed" |
| `priority` | enum | 优先级："low" \| "medium" \| "high" |

**todoread 参数：**
- 无参数

**返回值：**
- 当前待办列表和计数

**特殊功能：**
- 状态：pending, in_progress, completed, cancelled
- 一次只能有一个任务处于 in_progress
- 主动管理复杂多步骤任务

---

## 规划工具

### 16. plan_enter

切换到计划代理模式。

**参数：**
- 无

**返回值：**
- 确认消息并切换到计划代理

**特殊功能：**
- 请求用户确认
- 创建合成用户消息触发计划代理
- 计划文件位置由会话决定

---

### 17. plan_exit

完成规划阶段，切换到构建代理。

**参数：**
- 无

**返回值：**
- 确认消息并切换到构建代理

**特殊功能：**
- 询问用户是否切换到构建代理
- 创建合成用户消息触发构建代理
- 仅在计划完成并澄清后调用

---

## 实用工具

### 18. batch

并发执行多个独立的工具调用以减少延迟。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `tool_calls` | array | 是 | 1-25 个工具调用对象 |

**tool_calls 数组项结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool` | string | 工具名称 |
| `parameters` | object | 工具参数 |

**返回值：**
- 成功/失败工具执行的摘要

**特殊功能：**
- 2-5 倍效率提升
- 每次 batch 最多 25 个工具调用
- 部分失败不会停止其他调用
- 不能嵌套 batch 工具
- 排除某些工具（batch 自身、invalid、patch）
- 返回成功调用的附件

---

### 19. question

执行期间向用户提问。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `questions` | array | 是 | 问题对象数组 |

**questions 数组项结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `question` | string | 问题文本 |
| `header` | string | 头部文本（可选） |
| `options` | array | 可用选项（含 label 和 description） |
| `multiple` | boolean | 允许多选 |
| `custom` | boolean | 允许自定义文本输入 |

**返回值：**
- 用户答案

**特殊功能：**
- 支持多选和自定义答案
- 可用 "(Recommended)" 标签推荐特定选项

---

### 20. skill

加载提供专业指令的专项技能。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 可用技能中的技能名称 |

**返回值：**
- 技能内容及文件和指令

**特殊功能：**
- 根据代理权限过滤可访问技能
- 加载 SKILL.md 内容
- 列出捆绑资源（脚本、参考）
- 显示技能文件（最多 10 个文件）

---

### 21. invalid

无效工具占位符（内部使用）。

**参数：**

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `tool` | string | 是 | 无效的工具名称 |
| `error` | string | 是 | 错误消息 |

**返回值：**
- 解释无效参数的错误消息

**特殊功能：**
- 工具验证失败时内部使用

---

## 设计特点

所有工具遵循一致的设计模式：

1. **参数验证** - 使用 Zod schema 进行参数校验
2. **权限检查** - 通过 `ctx.ask()` 进行权限验证
3. **结构化返回** - 包含 `title`、`output` 和 `metadata` 的结构化对象
4. **附件支持** - 支持文件附件（图片、PDF 等）
5. **中止处理** - 支持中止信号处理以取消操作
6. **事件发布** - 发布文件系统变更事件

---

## 权限模型

工具访问通过权限系统控制：

- **Agent** 通过 `permissions` 配置定义可访问的工具
- **Skill** 通过权限过滤可访问的技能
- **Subagent** 通过 `subagent_type` 过滤可用的代理类型

---

*文档生成时间: 2026-02-25*
*基于 OpenCode 源码分析*
