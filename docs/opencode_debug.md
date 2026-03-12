# OpenCode 源码 Debug

两种方案，选一种就行。

---

## 方案一：Cursor + Bun（推荐，最简单）

Cursor = VS Code + AI，对 Bun 支持最好。

### 配置步骤

1. 用 Cursor 打开 `opencode` 文件夹
2. 创建 `.vscode/launch.json`：

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Debug OpenCode",
      "type": "node",
      "request": "launch",
      "runtimeExecutable": "bun",
      "runtimeArgs": ["run", "--conditions=browser", "src/index.ts"],
      "cwd": "${workspaceFolder}/packages/opencode",
      "console": "integratedTerminal"
    }
  ]
}
```

3. 在 `packages/opencode/src/agent/agent.ts` 打个断点
4. 按 `F5` 启动调试
5. Terminal 里输入命令，断点停下

---

## 方案二：WebStorm + Node.js + tsx

不想用 Bun，就用 Node.js + tsx 跑 TypeScript。

### 配置步骤

**Run** → **Edit Configurations** → **+** → **Node.js**

| 字段 | 值 |
|-----|---|
| Name | Debug OpenCode |
| Node interpreter | 你的 node 路径 |
| Working directory | `/Users/carlyu/soft/projects/coding_agents/opencode/packages/opencode` |
| JavaScript file | `src/index.ts` |
| Node parameters | `--import tsx` |
| Environment | 需要的话加 `ANTHROPIC_API_KEY=xxx` |

点虫子图标启动。

### 命令行验证

```bash
cd /Users/carlyu/soft/projects/coding_agents/opencode/packages/opencode
node --import tsx src/index.ts
```

能跑起来再去配 WebStorm。

---

## 关键断点位置（两种方案都一样）

1. **Agent 入口**：`packages/opencode/src/agent/agent.ts` → `execute()`
2. **API 调用**：`packages/opencode/src/provider/anthropic.ts` → `send()`
3. **Tool 执行**：`packages/opencode/src/tool/edit.ts` → `execute()`

---

## 触发流程

1. Debug 启动（跑 src/index.ts）
2. Terminal 里看到 opencode 启动
3. 输入任意命令如"创建一个文件"
4. 断点停下，观察变量

---

## TS → Python 速查

| TypeScript | Python |
|-----------|--------|
| `interface X { y: string }` | `class X(BaseModel): y: str` |
| `async function foo(): Promise<T>` | `async def foo() -> T:` |
| `x?.y` | `x.y if x else None` |
| `type X = A \| B` | `X = Union[A, B]` |
| `string[]` | `list[str]` |
| `Record<string, T>` | `dict[str, T]` |

---

## 验证成功

在 `src/agent/agent.ts` 的 `execute()` 第一行插入：
```typescript
console.log("🚀 源码跑起来了！输入:", request);
```

Debug 启动后输入命令，看到 🚀 日志 = 成功。
