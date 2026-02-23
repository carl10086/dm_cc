# Edit Tool 设计文档

## 概述

Edit Tool 用于精准替换文件中的特定内容，是 coding agent 的核心工具之一。

**设计对齐**: 参考 opencode TypeScript 实现，保持核心算法一致，简化部分复杂功能

**与 Write Tool 的区别**:

| 特性 | Write Tool | Edit Tool |
|------|-----------|-----------|
| 作用 | 完全覆盖整个文件 | 精准替换特定内容 |
| 匹配策略 | 无（直接覆盖） | 3 种智能匹配算法 |
| 安全性 | 较低 | 较高（只改需要改的地方）|
| 首选原则 | 尽量避免 | **优先使用** |

---

## 文件结构

```
tools/
├── base.py        # Tool 基类
├── edit.py        # EditTool 实现（430 行）
└── edit.txt       # Tool description（独立文件）
```

---

## 功能特性

### 1. 核心功能

- **字符串替换**: 使用 `oldString` 匹配并替换为 `newString`
- **模糊匹配**: 3 级匹配策略处理不精确的匹配
- **Diff 预览**: 应用前显示 unified diff，需用户确认
- **批量替换**: 支持 `replaceAll` 参数替换所有匹配

### 2. 参数设计（camelCase）

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| filePath | string | 是 | - | 文件的绝对路径 |
| oldString | string | 是 | - | 要替换的文本 |
| newString | string | 是 | - | 新文本（必须与 oldString 不同）|
| replaceAll | boolean | 否 | false | 是否替换所有匹配 |

### 3. 返回值结构

```python
{
    "title": "hello.py",           # 相对路径标题
    "output": "Edit applied successfully.",
    "metadata": {
        "replacements": 1,         # 替换次数
    }
}
```

### 4. 执行流程

```
1. 参数验证（oldString != newString）
2. 路径解析（支持相对路径转为绝对路径）
3. 文件验证（存在性、非二进制、非目录）
4. 读取原内容
5. 生成新内容（通过 replace_content，不写入）
6. 生成 unified diff
7. 显示 diff 并请求用户确认
8. 用户确认后才写入文件
9. 返回执行结果
```

---

## 核心算法详解

### 1. Levenshtein 距离计算

使用动态规划计算两个字符串的编辑距离（插入、删除、替换的最少操作次数）。

```python
def levenshtein_distance(a: str, b: str) -> int:
    # 初始化矩阵
    matrix = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]

    # 初始化边界
    for i in range(len(a) + 1):
        matrix[i][0] = i
    for j in range(len(b) + 1):
        matrix[0][j] = j

    # 填充矩阵
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            cost = 0 if a[i-1] == b[j-1] else 1
            matrix[i][j] = min(
                matrix[i-1][j] + 1,      # 删除
                matrix[i][j-1] + 1,      # 插入
                matrix[i-1][j-1] + cost  # 替换
            )

    return matrix[len(a)][len(b)]
```

**相似度计算**:

```python
def similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0

    max_len = max(len(a), len(b))
    distance = levenshtein_distance(a, b)
    return 1.0 - (distance / max_len)
```

### 2. 三级匹配策略

Edit 工具按优先级尝试以下匹配策略：

#### 2.1 Simple Replacer - 精确匹配

```python
def simple_replacer(content: str, find: str) -> Replacer:
    """简单替换器 - 精确匹配"""
    yield find
```

直接尝试精确匹配，适用于 LLM 提供的文本与文件内容完全一致的情况。

#### 2.2 Line Trimmed Replacer - 行级匹配

```python
def line_trimmed_replacer(content: str, find: str) -> Replacer:
    """行修剪替换器 - 去除行首尾空格后匹配"""
    original_lines = content.split("\n")
    search_lines = find.split("\n")

    # 移除末尾的空行
    if search_lines and search_lines[-1] == "":
        search_lines.pop()

    for i in range(len(original_lines) - len(search_lines) + 1):
        matches = True
        for j in range(len(search_lines)):
            if original_lines[i + j].strip() != search_lines[j].strip():
                matches = False
                break

        if matches:
            # 计算匹配的起始和结束索引
            match_start = sum(len(original_lines[k]) + 1 for k in range(i))
            match_end = match_start + sum(
                len(original_lines[i + k]) + (1 if k < len(search_lines) - 1 else 0)
                for k in range(len(search_lines))
            )
            yield content[match_start:match_end]
```

去除每行首尾空格后匹配，适用于缩进可能有差异的场景。

#### 2.3 Block Anchor Replacer - 块锚点匹配

**核心思想**: 使用代码块的首行和末行作为锚点，即使中间行有差异也能匹配。

```python
def block_anchor_replacer(content: str, find: str) -> Replacer:
    """块锚点替换器 - 使用首行和末行作为锚点匹配"""
    original_lines = content.split("\n")
    search_lines = find.split("\n")

    if len(search_lines) < 3:
        return

    # 移除末尾的空行
    if search_lines[-1] == "":
        search_lines.pop()

    first_line_search = search_lines[0].strip()
    last_line_search = search_lines[-1].strip()
    search_block_size = len(search_lines)

    # 阶段 1: 收集所有候选位置
    candidates: list[tuple[int, int]] = []
    for i in range(len(original_lines)):
        if original_lines[i].strip() != first_line_search:
            continue

        # 寻找匹配的末行
        for j in range(i + 2, len(original_lines)):
            if original_lines[j].strip() == last_line_search:
                candidates.append((i, j))
                break

    if not candidates:
        return

    # 阶段 2: 单一候选场景
    if len(candidates) == 1:
        start_line, end_line = candidates[0]
        actual_block_size = end_line - start_line + 1

        # 计算相似度（只比较中间行）
        sim = 0.0
        lines_to_check = min(search_block_size - 2, actual_block_size - 2)

        if lines_to_check > 0:
            for j in range(1, search_block_size - 1):
                if start_line + j >= end_line:
                    break
                orig_line = original_lines[start_line + j].strip()
                search_line = search_lines[j].strip()
                sim += similarity(orig_line, search_line) / lines_to_check

            if sim >= 0.3:  # 单候选阈值 0.3
                yield matched_block
        else:
            # 没有中间行，直接接受
            yield matched_block
        return

    # 阶段 3: 多个候选场景 - 选择相似度最高的
    best_match = None
    max_sim = -1.0

    for start_line, end_line in candidates:
        # 计算该候选的相似度...
        if sim > max_sim:
            max_sim = sim
            best_match = (start_line, end_line)

    if max_sim >= 0.5 and best_match:  # 多候选阈值 0.5
        yield best_matched_block
```

**阈值策略**:

| 场景 | 阈值 | 说明 |
|------|------|------|
| 单一候选 | 0.3 | 更宽松，允许更多差异 |
| 多候选 | 0.5 | 更严格，确保选择最匹配的 |

### 3. 主替换逻辑

```python
def replace_content(content: str, old_string: str, new_string: str,
                   replace_all: bool = False) -> str:
    """执行内容替换

    按优先级尝试不同的匹配策略，直到成功。
    """
    if old_string == new_string:
        raise ValueError("No changes to apply: oldString and newString are identical.")

    not_found = True

    # 按优先级尝试各种替换器
    replacers = [
        simple_replacer,
        line_trimmed_replacer,
        block_anchor_replacer,
    ]

    for replacer in replacers:
        for search in replacer(content, old_string):
            index = content.find(search)
            if index == -1:
                continue

            not_found = False

            if replace_all:
                return content.replace(search, new_string)

            # 检查是否唯一匹配
            last_index = content.rfind(search)
            if index != last_index:
                continue  # 有多处匹配，尝试下一个替换器

            # 执行替换
            return content[:index] + new_string + content[index + len(search):]

    if not_found:
        raise ValueError("Could not find oldString in the file...")

    raise ValueError("Found multiple matches for oldString...")
```

### 4. Diff 生成

使用 Python 标准库 `difflib` 生成 unified diff：

```python
def generate_diff(old_content: str, new_content: str, filepath: str) -> str:
    """生成 unified diff"""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # 确保每行都以换行符结尾
    if old_lines and not old_lines[-1].endswith('\n'):
        old_lines[-1] += '\n'
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm=""
    )
    return "".join(diff)
```

### 5. 用户确认流程

```python
def confirm_edit(diff: str, filepath: str) -> bool:
    """显示 diff 并请求用户确认"""
    # 计算相对路径显示
    try:
        display_path = str(Path(filepath).relative_to(Path.cwd()))
    except ValueError:
        display_path = filepath

    # 使用 Rich 显示带语法高亮的 diff
    console.print(Panel(
        Syntax(diff, "diff", theme="monokai", line_numbers=True),
        title=f"[yellow]Proposed Edit: {display_path}[/yellow]",
        border_style="yellow"
    ))

    # 请求确认
    console.print("[dim]Apply this edit? (y/n): [/dim]", end="")
    try:
        response = input().lower().strip()
        return response in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        return False
```

---

## 错误处理设计

### 设计原则

**所有错误通过抛出异常表示**。

```python
# 成功 - 返回 dict
return {
    "title": "...",
    "output": "Edit applied successfully.",
    "metadata": {"replacements": 1}
}

# 失败 - 抛出异常
raise ValueError("No changes to apply: oldString and newString are identical.")
raise FileNotFoundError(f"File not found: {filepath}")
raise UserCancelledError("Edit cancelled by user")
```

### 异常类型

| 错误场景 | 异常类型 | 消息示例 |
|----------|----------|----------|
| 无变化 | `ValueError` | `No changes to apply: oldString and newString are identical.` |
| 文件不存在 | `FileNotFoundError` | `File not found: {filepath}` |
| 是目录 | `IsADirectoryError` | `Path is a directory, not a file: {filepath}` |
| 二进制文件 | `ValueError` | `Cannot edit binary file: {path}` |
| 未找到匹配 | `ValueError` | `Could not find oldString in the file...` |
| 多处匹配 | `ValueError` | `Found multiple matches for oldString...` |
| 用户取消 | `UserCancelledError` | `Edit cancelled by user` |

---

## 与 opencode 的差异对比

### 1. Replacer 策略

| Replacer | dm_cc | opencode | 用途 |
|----------|-------|----------|------|
| Simple | ✅ | ✅ | 精确匹配 |
| LineTrimmed | ✅ | ✅ | 忽略行首尾空格 |
| BlockAnchor | ✅ | ✅ | 代码块锚点匹配 |
| WhitespaceNormalized | ❌ | ✅ | 空白字符归一化 |
| IndentationFlexible | ❌ | ✅ | 忽略缩进差异 |
| EscapeNormalized | ❌ | ✅ | 处理转义序列 |
| MultiOccurrence | ❌ | ✅ | 多出现优化 |
| TrimmedBoundary | ❌ | ✅ | 边界 trim |
| ContextAware | ❌ | ✅ | 上下文感知 |

### 2. 相似度阈值

| 场景 | dm_cc | opencode |
|------|-------|----------|
| 单一候选 | 0.3 | 0.0 |
| 多候选 | 0.5 | 0.3 |

### 3. 其他差异

| 特性 | dm_cc | opencode |
|------|-------|----------|
| LSP 集成 | 无 | 有（编辑后检查语法错误）|
| 文件锁 | 无 | FileTime.withLock |
| 快照系统 | 无 | Snapshot.FileDiff |
| 权限系统 | 简单 input 确认 | ctx.ask 权限框架 |
| Diff 修剪 | 无 | trimDiff 去除公共缩进 |
| 架构风格 | OOP + Pydantic | 函数式 + Zod |

### 4. 总结

dm_cc 的 Edit 工具实现了核心功能，采用 3 层 replacer 策略，能够满足基本的代码编辑需求。与 opencode 相比，主要差距在于匹配策略的丰富度和工程化特性（LSP、文件锁、快照等）。dm_cc 的设计更简洁，适合学习和定制；opencode 更完善，适合生产环境直接使用。

---

## 使用示例

### Python API

```python
from dm_cc.tools.edit import EditTool, EditParams

tool = EditTool()

# 基本替换
params = EditParams(
    filePath="/path/to/hello.py",
    oldString="def hello():",
    newString="def hello(name):"
)
result = await tool.execute(params)

# 批量替换
params = EditParams(
    filePath="/path/to/config.py",
    oldString="DEBUG = True",
    newString="DEBUG = False",
    replaceAll=True
)
result = await tool.execute(params)
```

### 错误处理

```python
from dm_cc.tools.edit import UserCancelledError

try:
    result = await tool.execute(params)
except FileNotFoundError as e:
    print(f"文件不存在: {e}")
except ValueError as e:
    print(f"编辑错误: {e}")
except UserCancelledError as e:
    print(f"用户取消: {e}")
```

### 测试模式（自动确认）

```python
# 测试时可以跳过用户确认
params = EditParams(
    filePath="/path/to/file.py",
    oldString="old",
    newString="new",
    _auto_confirm=True  # 内部参数，仅用于测试
)
result = await tool.execute(params)
```

---

## 测试覆盖

主要测试场景：

1. ✅ 正常替换（精确匹配）
2. ✅ 行 trim 匹配（缩进差异）
3. ✅ 块锚点匹配（代码块替换）
4. ✅ 批量替换（replaceAll）
5. ✅ 文件不存在（抛出异常）
6. ✅ 二进制文件（抛出异常）
7. ✅ 无变化（oldString == newString）
8. ✅ 未找到匹配（抛出异常）
9. ✅ 多处匹配（抛出异常）
10. ✅ Diff 正确生成
11. ✅ 用户确认流程
12. ✅ 用户取消行为

---

*文档版本: 1.0*
*最后更新: 2026-02-23*
