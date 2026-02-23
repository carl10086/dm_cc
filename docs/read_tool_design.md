# Read Tool 设计文档

## 概述

Read Tool 用于读取文件或目录内容，是 coding agent 最基础的工具之一。

**设计对齐**: 完全对齐 opencode TypeScript 实现

## 文件结构

```
tools/
├── base.py        # Tool 基类
├── read.py        # ReadTool 实现
└── read.txt       # Tool description (独立文件)
```

## 功能特性

### 1. 核心功能

- **读取文件**: 支持文本文件，带行号和范围限制
- **读取目录**: 列出目录内容（子目录带 `/` 后缀）
- **范围控制**: 通过 `offset` 和 `limit` 参数控制读取范围
- **智能截断**: 大文件自动截断，并提示如何继续读取

### 2. 参数设计 (camelCase)

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| filePath | string | 是 | - | 文件或目录路径 |
| offset | integer | 否 | 1 | 起始行号（1-indexed） |
| limit | integer | 否 | 2000 | 最大读取行数 |

### 3. 返回值结构

```python
{
    "title": "hello.py",           # 相对路径标题
    "output": "<path>...</path>",  # XML 格式输出
    "metadata": {
        "preview": "...",          # 前20行预览
        "truncated": False,        # 是否被截断
    }
}
```

### 4. 输出格式 (XML)

**文件输出：**
```xml
<path>/Users/.../file.py</path>
<type>file</type>
<content>
1: import os
2: import sys
3: def main():
...
</content>
```

**目录输出：**
```xml
<path>/Users/.../src</path>
<type>directory</type>
<entries>
subdir/
file1.py
file2.txt
...
</entries>
```

## 错误处理设计

### 设计原则

**所有错误通过抛出异常表示**，这是 opencode 的设计风格。

```python
# 成功 - 返回 dict
return {
    "title": "...",
    "output": "...",
    "metadata": {...}
}

# 失败 - 抛出异常
raise FileNotFoundError(f"File not found: {filepath}")
raise ValueError(f"Cannot read binary file: {filepath}")
```

### 异常类型

| 错误场景 | 异常类型 | 消息示例 |
|----------|----------|----------|
| 文件不存在 | `FileNotFoundError` | `File not found: {filepath}` |
| 二进制文件 | `ValueError` | `Cannot read binary file: {filepath}` |
| offset 越界 | `ValueError` | `Offset {n} is out of range...` |
| offset < 1 | `ValueError` | `offset must be >= 1` |

### 智能提示 (文件不存在)

opencode 的特色功能：推荐相似文件名

```python
File not found: /path/to/config.ts

Did you mean one of these?
/path/to/config.tsx
/path/to/config.js
/path/to/config.json
```

## 限制与边界

| 限制项 | 值 | 说明 |
|--------|-----|------|
| 默认读取行数 | 2000 行 | `DEFAULT_READ_LIMIT` |
| 单行最大长度 | 2000 字符 | `MAX_LINE_LENGTH` |
| 单次最大字节 | 50KB | `MAX_BYTES` |

## 二进制文件检测

### 检测策略

**双保险策略**：扩展名 + 内容检测

```python
# 1. 扩展名黑名单
_BINARY_EXTENSIONS = {
    ".zip", ".tar", ".gz", ".exe", ".so",
    ".class", ".jar", ".pyc", ".bin",
    # ... 更多
}

# 2. 内容检测（读取前 min(4096, file_size) 字节）
# - null byte 存在 → 肯定是二进制
# - >30% 不可打印字符 → 认为是二进制
```

## 目录读取设计

### 条目排序

按字母顺序排序（不区分大小写）：

```python
entries.sort(key=str.lower)
```

### 目录标识

子目录添加 `/` 后缀：

```
subdir/          ← 目录
file.txt         ← 文件
```

### 分页支持

和文件一样支持 `offset` 和 `limit`。

## 截断提示设计

### 三种截断情况

1. **字节限制截断** (50KB)
   ```
   (Output truncated at 51200 bytes. Use 'offset' parameter to read beyond line 1600)
   ```

2. **行数限制截断** (> 2000 行)
   ```
   (File has more lines. Use 'offset' parameter to read beyond line 2000)
   ```

3. **完整读取**
   ```
   (End of file - total 123 lines)
   ```

**关键原则**: 必须告知 LLM 内容不完整，否则它会基于不完整信息做决策。

## 与 opencode 的对齐

| 方面 | opencode (TS) | dm_cc (Python) |
|------|--------------|----------------|
| 参数命名 | `filePath`, `offset`, `limit` | ✅ 完全一致 |
| 参数类型 | `string`, `number?` | ✅ `str`, `int \| None` |
| description | 独立 `.txt` 文件 | ✅ 独立 `.txt` 文件 |
| 错误处理 | 抛出 Error | ✅ 抛出 Exception |
| 返回值 | `{title, output, metadata}` | ✅ 完全一致 |
| 输出格式 | XML 标签 | ✅ 完全一致 |
| 截断提示 | "Use 'offset' parameter..." | ✅ 完全一致 |

## 使用示例

### Python API

```python
from dm_cc.tools.read import ReadTool, ReadParams

tool = ReadTool()

# 读取文件
params = ReadParams(filePath="hello.py")
result = await tool.execute(params)
print(result["output"])

# 读取范围
params = ReadParams(filePath="large.txt", offset=100, limit=50)
result = await tool.execute(params)

# 读取目录
params = ReadParams(filePath="src/")
result = await tool.execute(params)
```

### 错误处理

```python
try:
    result = await tool.execute(params)
except FileNotFoundError as e:
    print(f"文件不存在: {e}")
except ValueError as e:
    print(f"读取错误: {e}")
```

## 测试覆盖

10 个测试场景全部通过：

1. ✅ 正常读取文件
2. ✅ 读取目录
3. ✅ offset 和 limit 参数
4. ✅ 文件不存在（抛出异常）
5. ✅ 二进制文件（抛出异常）
6. ✅ 超长行截断
7. ✅ 大文件截断提示
8. ✅ 相对路径
9. ✅ 绝对路径
10. ✅ offset 超出范围（抛出异常）
