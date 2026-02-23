# LSP 集成设计文档

## 概述

opencode 通过完整的 LSP (Language Server Protocol) 客户端实现，为代码编辑提供实时的语法检查和错误提示。编辑文件后，系统会自动触发 LSP 检查，并将发现的错误返回给 LLM，引导其修复。

**核心价值**:
- 编辑后即时发现语法错误
- 支持 30+ 种编程语言
- 自动下载和配置语言服务器
- 零配置启动（自动检测项目类型）

---

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     opencode CLI                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │  EditTool   │    │  WriteTool  │    │  ReadTool   │     │
│  └──────┬──────┘    └──────┬──────┘    └─────────────┘     │
│         │                  │                                │
│         └──────────────────┘                                │
│                    │                                        │
│              LSP.touchFile()                                │
│                    │                                        │
│         ┌──────────▼──────────┐                            │
│         │   LSP Module        │                            │
│         │  ┌───────────────┐  │                            │
│         │  │  LSPClient    │  │ ← vscode-jsonrpc 通信      │
│         │  │  (client.ts)  │  │                            │
│         │  └───────┬───────┘  │                            │
│         │          │          │                            │
│         │  ┌───────▼───────┐  │                            │
│         │  │  LSPServer    │  │ ← 进程管理                 │
│         │  │  (server.ts)  │  │                            │
│         │  └───────────────┘  │                            │
│         └──────────┬──────────┘                            │
└────────────────────┼──────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│ pyright   │ │gopls      │ │rust-      │
│ (Python)  │ │ (Go)      │ │analyzer   │
└───────────┘ └───────────┘ └───────────┘
     ...           ...          ...
```

---

## 核心模块

### 1. LSP Client (`lsp/client.ts`)

负责与语言服务器建立 JSON-RPC 通信，管理诊断信息。

**关键功能**:

```typescript
// 创建与语言服务器的连接
const connection = createMessageConnection(
  new StreamMessageReader(serverProcess.stdout),
  new StreamMessageWriter(serverProcess.stdin)
)

// 监听诊断通知
connection.onNotification("textDocument/publishDiagnostics", (params) => {
  const filePath = fileURLToPath(params.uri)
  diagnostics.set(filePath, params.diagnostics)
  Bus.publish(Event.Diagnostics, { path: filePath, serverID })
})

// 等待诊断结果（带防抖）
async function waitForDiagnostics(input: { path: string }) {
  return new Promise<void>((resolve) => {
    const unsub = Bus.subscribe(Event.Diagnostics, (event) => {
      if (event.properties.path === normalizedPath) {
        if (debounceTimer) clearTimeout(debounceTimer)
        debounceTimer = setTimeout(() => {
          unsub?.()
          resolve()
        }, DIAGNOSTICS_DEBOUNCE_MS)  // 150ms 防抖
      }
    })
  })
}
```

**初始化流程**:
1. 启动语言服务器进程
2. 建立 stdio 通信连接
3. 发送 `initialize` 请求
4. 发送 `initialized` 通知
5. 监听 `textDocument/publishDiagnostics` 通知

### 2. LSP Server (`lsp/server.ts`)

管理各种语言服务器的生命周期，支持自动安装。

**Server 定义结构**:

```typescript
export interface Info {
  id: string                    // 服务器标识
  extensions: string[]          // 支持的文件扩展名
  root: RootFunction            // 项目根目录检测
  spawn(root: string): Promise<Handle>  // 启动进程
}

export interface Handle {
  process: ChildProcess         // 子进程
  initialization?: Record<string, any>  // 初始化配置
}
```

**根目录检测策略**:

```typescript
// 向上查找特定文件确定项目根
const NearestRoot = (includePatterns: string[], excludePatterns?: string[]): RootFunction => {
  return async (file) => {
    const files = Filesystem.up({
      targets: includePatterns,
      start: path.dirname(file),
      stop: Instance.directory,
    })
    const first = await files.next()
    return first.value ? path.dirname(first.value) : Instance.directory
  }
}
}

// 示例：Python 项目
export const Pyright: Info = {
  id: "pyright",
  extensions: [".py", ".pyi"],
  root: NearestRoot([
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    ...
  ]),
  async spawn(root) { ... }
}
```

---

## 支持的语言（30+）

| 语言 | Server | 自动安装 | 检测文件 |
|------|--------|----------|----------|
| **Python** | pyright / ty | ✅ npm install | pyproject.toml, requirements.txt |
| **TypeScript** | typescript-language-server | ✅ bun x | package.json, tsconfig.json |
| **Go** | gopls | ✅ go install | go.mod |
| **Rust** | rust-analyzer | ❌ 手动 | Cargo.toml |
| **Java** | jdtls | ✅ 下载 tar.gz | pom.xml, build.gradle |
| **C/C++** | clangd | ✅ GitHub Release | compile_commands.json |
| **Vue** | vue-language-server | ✅ npm install | *.vue |
| **Ruby** | ruby-lsp | ✅ gem install | Gemfile |
| **PHP** | intelephense | ✅ npm install | composer.json |
| **Lua** | lua-language-server | ✅ GitHub Release | .luarc.json |
| **Zig** | zls | ✅ GitHub Release | build.zig |
| **Elixir** | elixir-ls | ✅ 下载/编译 | mix.exs |
| **C#** | csharp-ls | ✅ dotnet tool | .csproj, .sln |
| **F#** | fsautocomplete | ✅ dotnet tool | .fsproj |
| **Kotlin** | kotlin-lsp | ✅ GitHub Release | build.gradle.kts |
| **Swift** | sourcekit-lsp | ❌ Xcode 自带 | Package.swift |
| **Dart** | dart | ❌ SDK 自带 | pubspec.yaml |
| **Haskell** | haskell-language-server | ❌ 手动 | stack.yaml |
| **OCaml** | ocamllsp | ❌ 手动 | dune-project |
| **Nix** | nixd | ❌ 手动 | flake.nix |
| **Terraform** | terraform-ls | ✅ GitHub Release | *.tf |
| **LaTeX** | texlab | ✅ GitHub Release | *.tex |
| **Docker** | dockerfile-language-server | ✅ npm install | Dockerfile |
| **YAML** | yaml-language-server | ✅ npm install | *.yml |
| **Bash** | bash-language-server | ✅ npm install | *.sh |
| **Prisma** | prisma language-server | ❌ CLI 自带 | schema.prisma |
| **Gleam** | gleam | ❌ 自带 | gleam.toml |
| **Clojure** | clojure-lsp | ❌ 手动 | deps.edn |
| **Svelte** | svelte-language-server | ✅ npm install | *.svelte |
| **Astro** | @astrojs/language-server | ✅ npm install | *.astro |
| **Typst** | tinymist | ✅ GitHub Release | *.typ |

---

## 自动安装机制

opencode 能自动检测和安装缺失的语言服务器。

### 安装策略

**1. npm 包（Node.js 语言服务器）**

```typescript
async spawn(root) {
  const js = path.join(Global.Path.bin, "node_modules", "pyright", "dist", "pyright-langserver.js")
  if (!(await Bun.file(js).exists())) {
    await Bun.spawn([BunProc.which(), "install", "pyright"], {
      cwd: Global.Path.bin,
    }).exited
  }
  return {
    process: spawn(BunProc.which(), ["run", js, "--stdio"], { cwd: root })
  }
}
```

**2. GitHub Release（二进制工具）**

```typescript
async spawn(root) {
  let bin = Bun.which("zls")
  if (!bin) {
    // 1. 获取最新 release
    const release = await fetch("https://api.github.com/repos/zigtools/zls/releases/latest")
    // 2. 匹配平台架构
    const assetName = `zls-${arch}-${platform}.${ext}`
    // 3. 下载并解压
    await download(asset.browser_download_url, tempPath)
    await extract(tempPath, Global.Path.bin)
    // 4. 设置可执行权限
    await $`chmod +x ${bin}`
  }
}
```

**3. 包管理器安装**

```typescript
// Go: go install
const proc = Bun.spawn({
  cmd: ["go", "install", "golang.org/x/tools/gopls@latest"],
  env: { ...process.env, GOBIN: Global.Path.bin }
})

// Ruby: gem install
const proc = Bun.spawn({
  cmd: ["gem", "install", "rubocop", "--bindir", Global.Path.bin]
})

// .NET: dotnet tool
const proc = Bun.spawn({
  cmd: ["dotnet", "tool", "install", "csharp-ls", "--tool-path", Global.Path.bin]
})
```

---

## 与 Edit Tool 的集成

编辑文件后自动触发 LSP 检查：

```typescript
// edit.ts: 写入文件后
await file.write(contentNew)

// 1. 触发 LSP 检查
await LSP.touchFile(filePath, true)  // true = 等待诊断结果

// 2. 获取所有诊断
const diagnostics = await LSP.diagnostics()
const normalizedFilePath = Filesystem.normalizePath(filePath)
const issues = diagnostics[normalizedFilePath] ?? []

// 3. 过滤错误级别（severity 1 = Error）
const errors = issues.filter((item) => item.severity === 1)

// 4. 有错误时添加到输出，提示 LLM 修复
if (errors.length > 0) {
  const limited = errors.slice(0, MAX_DIAGNOSTICS_PER_FILE)
  output += `\n\nLSP errors detected in this file, please fix:
<diagnostics file="${filePath}">
${limited.map(LSP.Diagnostic.pretty).join("\n")}${suffix}
</diagnostics>`
}
```

**诊断格式化输出**:

```typescript
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
```

输出示例：
```
LSP errors detected in this file, please fix:
<diagnostics file="/path/to/file.py">
ERROR [15:23] Argument of type "str" cannot be assigned to parameter "count" of type "int"
WARN [42:5] Variable "unused" is not accessed
</diagnostics>
```

---

## LSP 通信流程

```
┌─────────┐                           ┌──────────────┐
│ opencode │                           │ Language     │
│          │                           │ Server       │
├─────────┤                           ├──────────────┤
│         │ ─── 1. initialize ───────▶ │              │
│         │ ◀── 2. initialize result ─ │              │
│         │ ─── 3. initialized ──────▶ │              │
│         │                           │              │
│  Edit   │ ─── 4. textDocument/       │              │
│  Tool   │      didOpen/didChange ──▶ │              │
│         │                           │              │
│         │ ◀── 5. textDocument/       │              │
│         │      publishDiagnostics ── │              │
│         │                           │              │
│         │ ─── 6. shutdown ─────────▶ │              │
│         │ ◀── 7. shutdown result ─── │              │
│         │ ─── 8. exit ─────────────▶ │              │
└─────────┘                           └──────────────┘
```

---

## 配置系统

用户可通过配置文件禁用或自定义 LSP：

```typescript
// opencode.json
{
  "lsp": {
    // 禁用所有 LSP
    false,

    // 或单独配置
    "pyright": {
      "disabled": false,
      "command": ["pyright-langserver", "--stdio"],
      "extensions": [".py"],
      "env": { "PYTHONPATH": "/custom/path" },
      "initialization": {
        "pythonPath": "/path/to/python"
      }
    }
  }
}
```

---

## Python 实现参考

对于 dm_cc，可以参考以下简化实现：

### 方案 1: 直接调用 CLI（最简单）

```python
import subprocess
import json
from pathlib import Path

class LSPChecker:
    def check_file(self, filepath: Path) -> list[dict]:
        """使用 pyright CLI 检查 Python 文件"""
        result = subprocess.run(
            ["pyright", str(filepath), "--outputjson"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            return []  # 无错误

        output = json.loads(result.stdout)
        return output.get("generalDiagnostics", [])

# 使用
errors = checker.check_file(Path("hello.py"))
for error in errors:
    print(f"{error['severity']} [{error['range']['start']['line']}]: {error['message']}")
```

### 方案 2: 使用 python-lsp-server

```python
from pylsp.python_lsp import PythonLSPServer
from pylsp.lsp import TextDocumentItem

class LSPServer:
    def __init__(self):
        self.server = PythonLSPServer()

    def open_file(self, uri: str, content: str):
        self.server.lsp.text_document_did_open({
            "textDocument": TextDocumentItem(
                uri=uri,
                languageId="python",
                version=0,
                text=content
            )
        })

    def get_diagnostics(self, uri: str) -> list:
        # 获取诊断信息
        return self.server.workspace.documents[uri].diagnostics
```

### 方案 3: 完整的 LSP 客户端

```python
import subprocess
import json
from typing import Any

class LSPClient:
    """简化版 LSP 客户端，通过 stdio 与语言服务器通信"""

    def __init__(self, command: list[str]):
        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        self.request_id = 0

    def send_request(self, method: str, params: dict) -> Any:
        """发送 JSON-RPC 请求"""
        self.request_id += 1
        message = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params
        }

        # 发送消息
        content = json.dumps(message)
        header = f"Content-Length: {len(content)}\r\n\r\n"
        self.proc.stdin.write(header + content)
        self.proc.stdin.flush()

        # 读取响应（简化版，实际需要处理分块）
        response = self._read_response()
        return json.loads(response)

    def _read_response(self) -> str:
        """读取 JSON-RPC 响应"""
        # 读取 header
        header = ""
        while True:
            char = self.proc.stdout.read(1)
            header += char
            if header.endswith("\r\n\r\n"):
                break

        # 解析 Content-Length
        length = int(header.split("Content-Length: ")[1].split("\r\n")[0])

        # 读取 body
        return self.proc.stdout.read(length)
```

---

## 总结

opencode 的 LSP 集成展示了如何在 CLI 工具中实现完整的语言服务器客户端：

1. **架构清晰**: 分离 Client（通信）和 Server（进程管理）职责
2. **多语言支持**: 30+ 语言，统一接口
3. **零配置**: 自动检测项目类型，自动安装语言服务器
4. **实时反馈**: 编辑后立即检查，错误信息直接反馈给 LLM

对于 dm_cc 的 MVP 版本，建议：
- **Phase 1**: 方案 1（CLI 调用），快速验证价值
- **Phase 2**: 方案 3（完整 LSP 客户端），支持多语言

---

*文档版本: 1.0*
*参考: opencode v0.3.x*
*最后更新: 2026-02-23*
