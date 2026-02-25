# LSP 实现参考文档

基于 opencode 的 LSP 集成实现分析，为 dm_cc 提供实现参考。

---

## 1. opencode 的 LSP 架构

### 1.1 核心策略：多独立 Server

opencode 采用**每种语言各自启动独立的 LSP Server 进程**的策略：

```
opencode
├── TypeScript 文件 → typescript-language-server 进程
├── Python 文件     → pyright-langserver 进程
├── Go 文件         → gopls 进程
├── Rust 文件       → rust-analyzer 进程
└── ...每种语言独立的进程
```

**为什么选择多独立 Server？**
- 每种语言有官方推荐的 LSP 实现
- 专业化：pyright 专注 Python，gopls 专注 Go
- 隔离性：一个 server 崩溃不影响其他语言

### 1.2 工作流程

```
编辑 test.py
    ↓
匹配到 .py 扩展名 → 启动 pyright-langserver 进程
    ↓
通过 stdin/stdout JSON-RPC 通信
    ↓
获取诊断结果
    ↓
关闭文件后可选关闭进程（或保持运行）
```

---

## 2. 支持的语言分类（35+ 种）

### 2.1 Node.js/npm 安装（最简单）

| 语言 | 包名 | 安装方式 |
|------|------|----------|
| TypeScript | typescript-language-server | `bun install` |
| Python | pyright | `bun install pyright` |
| Vue | @vue/language-server | `bun install` |
| ESLint | vscode-eslint | 下载 zip + npm install |
| Svelte | svelte-language-server | `bun install` |
| Astro | @astrojs/language-server | `bun install` |
| YAML | yaml-language-server | `bun install` |
| PHP | intelephense | `bun install` |
| Bash | bash-language-server | `bun install` |
| Dockerfile | dockerfile-language-server-nodejs | `bun install` |
| Prisma | prisma | 内置 CLI 支持 |

### 2.2 包管理器安装

| 语言 | 工具 | 命令 |
|------|------|------|
| Go | gopls | `go install golang.org/x/tools/gopls@latest` |
| Ruby | rubocop | `gem install rubocop` |
| C# | csharp-ls | `dotnet tool install csharp-ls` |
| F# | fsautocomplete | `dotnet tool install fsautocomplete` |

### 2.3 GitHub Release 下载（二进制）

| 语言 | 下载源 |
|------|--------|
| Zig | zigtools/zls |
| C/C++ | clangd/clangd |
| Lua | LuaLS/lua-language-server |
| Terraform | hashicorp/terraform-ls |
| Kotlin | JetBrains/kotlin-lsp |
| TeX | latex-lsp/texlab |
| Tinymist | Myriad-Dreamin/tinymist |

### 2.4 手动安装（不自动下载）

| 语言 | 说明 |
|------|------|
| Rust | rust-analyzer（需手动安装）|
| Swift | sourcekit-lsp（Xcode 自带）|
| Dart | dart language-server（SDK 自带）|
| Haskell | haskell-language-server（需手动安装）|
| OCaml | ocamllsp（需手动安装）|
| Gleam | gleam lsp（gleam 自带）|
| Clojure | clojure-lsp（需手动安装）|
| Nix | nixd（需手动安装）|
| Deno | deno lsp（deno 自带）|

---

## 3. 自动安装策略

### 3.1 核心逻辑

```typescript
export const Pyright: Info = {
  id: "pyright",
  extensions: [".py", ".pyi"],
  async spawn(root) {
    // 1. 检查是否已安装
    let binary = Bun.which("pyright-langserver")

    if (!binary) {
      // 2. 检查是否禁止自动安装
      if (Flag.OPENCODE_DISABLE_LSP_DOWNLOAD) return

      // 3. 自动安装到固定目录
      await Bun.spawn([BunProc.which(), "install", "pyright"], {
        cwd: Global.Path.bin,  // ~/.opencode/bin
      })

      // 4. 再次检查
      binary = BunProc.which()
    }

    // 5. 启动进程
    const proc = spawn(binary, ["--stdio"], { cwd: root })
    return { process: proc }
  }
}
```

### 3.2 关键原则

1. **按需安装**：不是一次性装所有，而是编辑 `.py` 时才装 pyright
2. **自动检测**：先检查系统 PATH，找不到才安装
3. **安装到固定目录**：`Global.Path.bin`（类似 `~/.dm_cc/bin`）
4. **优雅降级**：装不上或禁用下载时，静默跳过
5. **版本控制**：通过 GitHub API 获取 latest release

### 3.3 配置开关

```typescript
// 通过环境变量/配置禁用自动下载
if (Flag.OPENCODE_DISABLE_LSP_DOWNLOAD) return
```

---

## 4. LSP Server 定义结构

```typescript
export interface Info {
  id: string                    // 服务器标识
  extensions: string[]          // 支持的文件扩展名
  global?: boolean              // 是否全局安装
  root: RootFunction            // 项目根目录检测
  spawn(root: string): Promise<Handle | undefined>  // 启动进程
}

export interface Handle {
  process: ChildProcess         // 子进程
  initialization?: Record<string, any>  // 初始化配置
}

type RootFunction = (file: string) => Promise<string | undefined>
```

### 4.1 根目录检测

```typescript
const NearestRoot = (includePatterns: string[], excludePatterns?: string[]): RootFunction => {
  return async (file) => {
    // 向上查找特定文件确定项目根
    const files = Filesystem.up({
      targets: includePatterns,      // 如 ["pyproject.toml", "requirements.txt"]
      start: path.dirname(file),
      stop: Instance.directory,
    })
    const first = await files.next()
    return first.value ? path.dirname(first.value) : Instance.directory
  }
}

// Python 项目检测
export const Pyright: Info = {
  root: NearestRoot([
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "Pipfile",
    "pyrightconfig.json"
  ]),
  // ...
}
```

---

## 5. 与 Edit/Write 工具的集成

### 5.1 编辑后触发检查

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
  const limited = errors.slice(0, MAX_DIAGNOSTICS_PER_FILE]
  output += `\n\nLSP errors detected in this file, please fix:
<diagnostics file="${filePath}">
${limited.map(LSP.Diagnostic.pretty).join("\n")}${suffix}
</diagnostics>`
}
```

### 5.2 诊断格式化输出

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

### 5.3 输出示例

```
LSP errors detected in this file, please fix:
<diagnostics file="/path/to/file.py">
ERROR [15:23] Argument of type "str" cannot be assigned to parameter "count" of type "int"
WARN [42:5] Variable "unused" is not accessed
</diagnostics>
```

---

## 6. 对 dm_cc 的实现建议

### 6.1 三种方案对比

| 方案 | 说明 | 复杂度 | 性能 |
|------|------|--------|------|
| **CLI 调用** | 每次检查启动新进程 | 低 | 慢（进程启动开销）|
| **多独立 Server** | 每种语言各自进程（opencode 方式）| 中 | 快 |
| **单一 Server** | 一个进程处理所有语言 | 高 | 中（需自行实现）|

### 6.2 推荐实现路径

#### Phase 1: CLI 调用（Python 优先）

**目标**：快速验证价值，支持 Python

```python
import subprocess
import json
from pathlib import Path

class LSPChecker:
    def check_python(self, filepath: Path) -> list[dict]:
        """使用 pyright CLI 检查 Python 文件"""
        try:
            result = subprocess.run(
                ["pyright", str(filepath), "--outputjson"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                return []  # 无错误

            output = json.loads(result.stdout)
            return output.get("generalDiagnostics", [])
        except FileNotFoundError:
            # 未安装，给出提示
            return [{
                "severity": "info",
                "message": "pyright not found. Install: pip install pyright"
            }]
        except Exception as e:
            return [{"severity": "error", "message": str(e)}]
```

**集成到 edit.py**：
```python
async def execute(self, params: EditParams) -> dict[str, Any]:
    # ... 写入文件 ...

    output = f"Applied edit to {file_path}"

    # 只对 Python 文件进行 LSP 检查
    if file_path.suffix == ".py":
        checker = LSPChecker()
        errors = checker.check_python(file_path)
        if errors:
            output += self._format_diagnostics(errors, file_path)

    return {"title": f"Edit {file_path.name}", "output": output}
```

#### Phase 2: 简化版 LSP Client（3-5 种语言）

**目标**：支持 Python、TypeScript、Go

- Python: pyright (CLI)
- TypeScript: tsc --noEmit 或 typescript-language-server
- Go: gopls (通过 stdio 通信)

**架构**：
```
dm_cc/lsp/
├── __init__.py      # 主入口
├── client.py        # LSP 客户端（JSON-RPC）
├── server.py        # Server 配置（Python/TS/Go）
└── diagnostics.py   # 诊断信息收集
```

#### Phase 3: 完整 LSP 支持（10+ 语言）

**目标**：类似 opencode，支持 30+ 语言，按需自动安装

- 实现完整的 LSP Client（JSON-RPC 通信）
- 支持多种安装方式（npm/pip/go install/GitHub Release）
- 根目录自动检测
- 诊断防抖（150ms）

### 6.3 依赖管理建议

| 阶段 | Python 依赖 | 用户安装方式 |
|------|------------|-------------|
| Phase 1 | pyright | `pip install pyright` 或 `npm install -g pyright` |
| Phase 2 | pyright + typescript | 同上 |
| Phase 3 | 按需自动安装 | 工具自动处理 |

### 6.4 配置设计

```python
# config.py
class Settings(BaseSettings):
    # ... 现有配置 ...

    # LSP 配置
    lsp_enabled: bool = True
    lsp_auto_install: bool = False  # Phase 1/2 先禁用，Phase 3 开启
    lsp_pyright_path: str = ""      # 自定义路径

# opencode.json（可选）
{
  "lsp": {
    "enabled": true,
    "pyright": {
      "disabled": false,
      "pythonPath": "/path/to/python"
    }
  }
}
```

---

## 7. 参考资源

- **opencode LSP 实现**: `/Users/carlyu/soft/projects/coding_agents/opencode/packages/opencode/src/lsp/`
- **server.ts**: 35+ 语言的 LSP Server 配置
- **client.ts**: JSON-RPC 通信实现
- **index.ts**: 诊断收集和格式化

---

*文档版本: 1.0*
*参考: opencode v0.3.x*
*最后更新: 2026-02-25*
