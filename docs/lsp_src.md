# opencode LSP 源码分析

详细分析 opencode 从文件修改到 LSP 诊断的完整流程。

---

## 目录

1. [整体架构](#整体架构)
2. [核心流程](#核心流程)
3. [源码详解](#源码详解)
4. [数据流向](#数据流向)

---

## 整体架构

opencode 采用**每种语言各自启动独立的 LSP Server 进程**的策略：

```
opencode
├── TypeScript 文件 → typescript-language-server 进程
├── Python 文件     → pyright-langserver 进程
├── Go 文件         → gopls 进程
├── Rust 文件       → rust-analyzer 进程
└── ...每种语言独立的进程
```

### 为什么选择多独立 Server？

- **官方推荐**：每种语言有官方推荐的 LSP 实现
- **专业化**：pyright 专注 Python，gopls 专注 Go
- **隔离性**：一个 server 崩溃不影响其他语言

---

## 核心流程

```
编辑 test.py
    ↓
匹配到 .py 扩展名 → 启动 pyright-langserver 进程
    ↓
通过 stdin/stdout JSON-RPC 通信
    ↓
获取诊断结果
    ↓
格式化错误信息 → 返回给 Agent
```

---

## 源码详解

### 1. 发现语言（文件扩展名）

**文件**: `lsp/index.ts:179`

```typescript
const extension = path.parse(file).ext || file  // ".py"
```

**扩展名映射**: `lsp/language.ts`

```typescript
export const LANGUAGE_EXTENSIONS: Record<string, string> = {
  ".py": "python",
  ".ts": "typescript",
  ".tsx": "typescriptreact",
  ".go": "go",
  ".rs": "rust",
  // ... 更多扩展名
}
```

### 2. 找到对应 LSP（getClients）

**文件**: `lsp/index.ts:177-262`

```typescript
async function getClients(file: string) {
  const s = await state()
  const extension = path.parse(file).ext || file
  const result: LSPClient.Info[] = []

  for (const server of Object.values(s.servers)) {
    // 2.1 检查扩展名是否匹配
    if (server.extensions.length && !server.extensions.includes(extension))
      continue

    // 2.2 确定项目根目录
    const root = await server.root(file)  // 找 pyproject.toml
    if (!root) continue

    // 2.3 检查是否已有运行中的 client
    const match = s.clients.find((x) => x.root === root && x.serverID === server.id)
    if (match) {
      result.push(match)
      continue
    }

    // 2.4 启动新的 LSP Server 进程
    const handle = await server.spawn(root)  // 启动 pyright-langserver
    if (!handle) continue

    // 2.5 创建 LSP Client（JSON-RPC 连接）
    const client = await LSPClient.create({
      serverID: server.id,
      server: handle,
      root,
    })

    s.clients.push(client)
    result.push(client)
  }

  return result
}
```

### 3. Edit 触发校验

**文件**: `tool/edit.ts:132-153`

```typescript
async execute(params, ctx) {
  // 3.1 写入文件
  await file.write(contentNew)

  // 3.2 通知 LSP 文件已更改
  await LSP.touchFile(filePath, true)  // true = 等待诊断

  // 3.3 获取诊断信息
  const diagnostics = await LSP.diagnostics()

  // 3.4 处理结果
  let output = "Edit applied successfully."
  const normalizedFilePath = Filesystem.normalizePath(filePath)
  const issues = diagnostics[normalizedFilePath] ?? []

  // 只筛选 Error 级别（severity === 1）
  const errors = issues.filter((item) => item.severity === 1)

  // 格式化错误信息
  if (errors.length > 0) {
    const limited = errors.slice(0, MAX_DIAGNOSTICS_PER_FILE)
    output += `\n\nLSP errors detected in this file, please fix:
<diagnostics file="${filePath}">
${limited.map(LSP.Diagnostic.pretty).join("\n")}
</diagnostics>`
  }

  // 3.5 返回给 Agent
  return { title: path.relative(Instance.worktree, filePath), output }
}
```

### 4. touchFile 内部流程

**文件**: `lsp/index.ts:277-289`

```typescript
export async function touchFile(input: string, waitForDiagnostics?: boolean) {
  log.info("touching file", { file: input })

  // 4.1 获取/启动 LSP clients
  const clients = await getClients(input)

  await Promise.all(
    clients.map(async (client) => {
      // 4.2 等待诊断完成
      const wait = waitForDiagnostics
        ? client.waitForDiagnostics({ path: input })
        : Promise.resolve()

      // 4.3 通知 LSP 文件已打开/更改
      await client.notify.open({ path: input })

      return wait
    })
  )
}
```

### 5. 等待诊断（防抖）

**文件**: `lsp/client.ts:210-238`

```typescript
async waitForDiagnostics(input: { path: string }) {
  const normalizedPath = Filesystem.normalizePath(input.path)

  return new Promise<void>((resolve) => {
    const unsub = Bus.subscribe(Event.Diagnostics, (event) => {
      // 检查是否是当前文件的诊断
      if (event.properties.path === normalizedPath) {
        // 防抖：等待 150ms 确保 LSP 完成所有分析
        if (debounceTimer) clearTimeout(debounceTimer)
        debounceTimer = setTimeout(() => {
          unsub?.()
          resolve()
        }, DIAGNOSTICS_DEBOUNCE_MS)  // 150ms
      }
    })
  })
}
```

### 6. 获取诊断

**文件**: `lsp/index.ts:291-301`

```typescript
export async function diagnostics() {
  const results: Record<string, LSPClient.Diagnostic[]> = {}

  // 从所有 clients 收集诊断
  for (const result of await runAll(async (client) => client.diagnostics)) {
    for (const [path, diagnostics] of result.entries()) {
      const arr = results[path] || []
      arr.push(...diagnostics)
      results[path] = arr
    }
  }

  return results
}
```

### 7. 诊断格式化

**文件**: `lsp/index.ts:469-484`

```typescript
export namespace Diagnostic {
  export function pretty(diagnostic: LSPClient.Diagnostic) {
    const severityMap = {
      1: "ERROR",
      2: "WARN",
      3: "INFO",
      4: "HINT",
    }

    const severity = severityMap[diagnostic.severity || 1]
    const line = diagnostic.range.start.line + 1
    const col = diagnostic.range.start.character + 1

    return `${severity} [${line}:${col}] ${diagnostic.message}`
  }
}
```

**输出示例**:

```
ERROR [15:23] Argument of type "str" cannot be assigned to parameter "count" of type "int"
WARN [42:5] Variable "unused" is not accessed
```

---

## 数据流向

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────┐
│  Edit   │────▶│   touchFile │────▶│  LSP Client │────▶│ pyright │
│  Tool   │     │             │     │ (JSON-RPC)  │     │ Server  │
└─────────┘     └─────────────┘     └─────────────┘     └─────────┘
                                              │                │
                                              │◄───────────────┘
                                              │  发送诊断通知
                                              ▼
                                       ┌─────────────┐
                                       │  diagnostics │
                                       │  收集所有错误  │
                                       └──────┬──────┘
                                              │
                                              ▼
                                       ┌─────────────┐
                                       │    Agent    │
                                       │  (LLM 看到)  │
                                       │ "LSP errors  │
                                       │ detected..." │
                                       └─────────────┘
```

---

## 关键步骤总结

| 步骤 | 函数/文件 | 核心逻辑 |
|------|----------|----------|
| **1. 发现语言** | `getClients()` | 根据文件扩展名 `.py` 匹配 |
| **2. 找到 LSP** | `server.extensions` | `Pyright.extensions = [".py", ".pyi"]` |
| **3. 启动 Server** | `server.spawn(root)` | 启动 `pyright-langserver --stdio` |
| **4. 创建 Client** | `LSPClient.create()` | 建立 JSON-RPC 连接 |
| **5. 触发校验** | `LSP.touchFile()` | 通知 LSP 文件已更改 |
| **6. 等待诊断** | `waitForDiagnostics()` | 等待 150ms 防抖 |
| **7. 获取结果** | `LSP.diagnostics()` | 收集所有 client 的诊断 |
| **8. 返回 Agent** | `return { output }` | 格式化错误信息给 LLM |

---

## 对 dm_cc 的启示

### 简化版实现（Phase 1）

```python
# 1. 发现语言
if file_path.suffix == ".py":
    # 2. 调用 pyright CLI
    result = subprocess.run(
        ["pyright", str(file_path), "--outputjson"],
        capture_output=True,
        text=True
    )

    # 3. 解析诊断
    diagnostics = json.loads(result.stdout)

    # 4. 格式化并返回给 Agent
    if diagnostics.get("generalDiagnostics"):
        output += "\n\nLSP errors detected:\n"
        for error in diagnostics["generalDiagnostics"]:
            line = error["range"]["start"]["line"]
            message = error["message"]
            output += f"ERROR [{line}] {message}\n"
```

### 完整版实现（Phase 3）

参考 opencode 的实现，需要：

1. **LSP 管理器**: 管理多个 LSP Server 进程
2. **Client 类**: 处理 JSON-RPC 通信
3. **Server 配置**: 定义每种语言的启动方式
4. **诊断收集**: 聚合多个 server 的诊断
5. **防抖机制**: 避免过早返回不完整的诊断

---

*文档版本: 1.0*
*参考: opencode v0.3.x*
*最后更新: 2026-02-25*
