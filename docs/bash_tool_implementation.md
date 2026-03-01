# Bash Tool 实现文档

## 概述

Bash Tool 是 dm_cc 的核心工具之一，用于执行 shell 命令。它使 Agent 能够运行 git 命令、构建命令、检查系统状态等，同时提供多层安全防护机制。

## 参考实现

- **opencode**: `packages/opencode/src/tool/bash.ts`

## 文件位置

```
dm_cc/src/dm_cc/tools/bash.py       # 主实现
dm_cc/src/dm_cc/tools/bash.txt      # LLM 描述文本
```

## 核心特性

| 特性 | 说明 |
|------|------|
| 异步执行 | 使用 `asyncio.create_subprocess_shell` |
| 命令解析 | 使用 tree-sitter 解析 bash 语法 |
| 安全检查 | 危险命令检测、目录访问限制 |
| 超时控制 | 默认 2 分钟，最大 10 分钟 |
| 输出限制 | 50KB 上限，自动截断 |

---

## 架构设计

### 类结构

```
BashTool(Tool)
├── parameters: BashParams
├── execute(params) -> dict
├── _resolve_workdir(workdir) -> Path
├── _security_check(command, workdir)
├── _parse_command(command) -> list[dict]
├── _extract_commands(node, source, commands)
└── _run_command(command, workdir, timeout) -> dict
```

### 参数模型 (BashParams)

```python
class BashParams(BaseModel):
    command: str      # 要执行的命令
    description: str  # 命令描述（用于日志）
    timeout: int      # 超时秒数（默认 120）
    workdir: str      # 工作目录（默认项目根目录）
```

---

## 安全机制

### 1. 危险命令列表

以下命令被完全禁止执行：

```python
DANGEROUS_COMMANDS = frozenset([
    "rm",       # 删除文件
    "mv",       # 移动文件
    "cp",       # 复制文件（可能覆盖）
    "chmod",    # 修改权限
    "chown",    # 修改所有者
    "dd",       # 磁盘操作
    "mkfs",     # 格式化
    "fdisk",    # 分区
    "mount",    # 挂载
    "umount",   # 卸载
    "reboot",   # 重启
    "shutdown", # 关机
    "poweroff", # 关机
    "kill",     # 杀死进程
    "killall",  # 杀死所有进程
    "pkill",    # 按名称杀死进程
    "sudo",     # 提权
    "su",       # 切换用户
])
```

### 2. 可疑模式检测

使用正则表达式检测危险模式：

```python
SUSPICIOUS_PATTERNS = [
    r">\s*/dev/null",  # 重定向到 /dev/null
    r";\s*rm",         # 分号后接 rm
    r"&&\s*rm",        # && 后接 rm
    r"\|\s*rm",        # 管道后接 rm
]
```

### 3. 目录访问限制

- 工作目录必须存在且是有效目录
- 命令通过 `cd <workdir> && <command>` 方式执行
- 未来可扩展：限制在项目目录范围内

### 4. 命令解析

使用 tree-sitter 解析 bash 命令结构：

```python
def _parse_command(self, command: str) -> list[dict]:
    parser = get_parser("bash")
    tree = parser.parse(command.encode())
    # 提取命令名和参数
    commands = []
    self._extract_commands(tree.root_node, command, commands)
    return commands
```

解析结果示例：

```python
# 输入: "git status --short"
# 输出: [{"command": "git", "args": ["status", "--short"]}]
```

---

## 执行流程

```
用户请求 -> execute(params)
    │
    ├── 1. 解析工作目录
    │   └── _resolve_workdir(params.workdir)
    │
    ├── 2. 安全检查
    │   └── _security_check(command, workdir)
    │       ├── 检查目录有效性
    │       ├── tree-sitter 解析命令
    │       └── 检查危险命令/模式
    │
    ├── 3. 执行命令
    │   └── _run_command(command, workdir, timeout)
    │       ├── 创建子进程
    │       ├── 等待输出（带超时）
    │       ├── 解码输出
    │       └── 截断超长输出
    │
    └── 4. 返回结果
        └── {"title", "output", "metadata"}
```

---

## 权限控制

### Agent 配置

```python
# Build Agent - 允许使用 bash
build_agent = AgentConfig(
    allowed_tools=["*"],
    denied_tools=["plan_exit"],  # 但不能使用 plan_exit
)

# Plan Agent - 禁止使用 bash
plan_agent = AgentConfig(
    allowed_tools=["read", "glob", "write", "edit", "plan_exit"],
    denied_tools=["bash"],  # 明确禁用
)
```

### 运行时检查

```python
# 在 agent.py 中通过 filter_tools 过滤
self.tools = self.config.filter_tools(all_tools)
```

---

## 关键实现细节

### 1. 异步执行

```python
async def _run_command(self, command, workdir, timeout):
    cd_command = f"cd {shlex_quote(str(workdir))} && {command}"

    process = await asyncio.create_subprocess_shell(
        cd_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    stdout, _ = await asyncio.wait_for(
        process.communicate(),
        timeout=timeout
    )
```

### 2. 输出截断

```python
MAX_OUTPUT_SIZE = 50 * 1024  # 50KB

if len(output) > self.MAX_OUTPUT_SIZE:
    output = output[:self.MAX_OUTPUT_SIZE] + (
        f"\n\n[Output truncated: {len(output)} chars, "
        f"showing first {self.MAX_OUTPUT_SIZE}]"
    )
```

### 3. Shell 安全引用

```python
def shlex_quote(s: str) -> str:
    """安全地引用字符串用于 shell"""
    if re.match(r"^[a-zA-Z0-9_./-]+$", s):
        return s
    # 使用单引号包裹，处理内部单引号
    return "'" + s.replace("'", "'\"'\"'") + "'"
```

---

## 使用示例

### 基本命令

```python
from dm_cc.tools.bash import BashTool, BashParams

tool = BashTool()
params = BashParams(command="pwd", description="Show current directory")
result = await tool.execute(params)
# 输出: /Users/carlyu/soft/projects/coding_agents/dm_cc
```

### Git 命令

```python
params = BashParams(
    command="git status --short",
    description="Check git status"
)
result = await tool.execute(params)
```

### 指定工作目录

```python
params = BashParams(
    command="ls -la",
    description="List files in temp",
    workdir="/tmp"
)
result = await tool.execute(params)
```

### 危险命令拦截

```python
params = BashParams(command="rm -rf /", description="Dangerous")
# 抛出 PermissionError: Dangerous command detected: 'rm'
```

---

## 错误处理

| 错误类型 | 场景 | 处理 |
|----------|------|------|
| `PermissionError` | 危险命令/模式 | 拒绝执行，返回错误信息 |
| `FileNotFoundError` | 工作目录不存在 | 拒绝执行 |
| `NotADirectoryError` | workdir 不是目录 | 拒绝执行 |
| `TimeoutError` | 命令超时 | 终止进程，返回超时错误 |
| `RuntimeError` | 执行失败 | 返回错误信息 |

---

## 测试用例

```python
# Test 1: 简单命令
params = BashParams(command="pwd")
result = await tool.execute(params)
assert result["metadata"]["exit_code"] == 0

# Test 2: Git 命令
params = BashParams(command="git status")
result = await tool.execute(params)
assert "exit_code" in result["metadata"]

# Test 3: 危险命令拦截
try:
    params = BashParams(command="rm -rf /")
    await tool.execute(params)
    assert False, "Should raise PermissionError"
except PermissionError:
    pass

# Test 4: 目录切换
params = BashParams(command="pwd", workdir="/tmp")
result = await tool.execute(params)
assert "/tmp" in result["output"]
```

---

## 与 opencode 的差异

| 方面 | opencode (TypeScript) | dm_cc (Python) |
|------|----------------------|----------------|
| 执行方式 | `child_process.spawn` | `asyncio.create_subprocess_shell` |
| 命令解析 | tree-sitter | tree-sitter-languages |
| 超时处理 | 内置超时 | `asyncio.wait_for` |
| 输出限制 | 50KB | 50KB |
| 权限控制 | 基于 Agent 配置 | 相同的 Agent 配置机制 |

---

## 未来扩展

1. **项目目录限制**: 确保命令只能在项目目录内执行
2. **交互式命令**: 支持需要用户输入的命令
3. **环境变量**: 允许设置自定义环境变量
4. **管道处理**: 更复杂的管道命令安全检查
5. **白名单模式**: 可选的只允许特定命令模式

---

## 相关文件

- `dm_cc/src/dm_cc/tools/bash.py` - 主实现
- `dm_cc/src/dm_cc/tools/bash.txt` - LLM 描述
- `dm_cc/src/dm_cc/tools/base.py` - Tool 基类
- `dm_cc/src/dm_cc/agents/config.py` - Agent 配置
- `dm_cc/tests/test_bash_tool.py` - 单元测试（待创建）

---

*创建日期: 2026-03-01*
