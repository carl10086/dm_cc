# Edit Tool Diff 确认机制实现文档

本文档记录 dm_cc 中 edit 工具的 diff 确认机制实现细节。

---

## 功能概述

edit 工具在执行文件修改前，会：
1. 生成 diff 显示变更内容
2. 使用 Rich 语法高亮显示
3. 等待用户确认 (y/n)
4. 确认后才真正写入文件

---

## 实现细节

### 1. Diff 生成

使用 Python 标准库 `difflib` 生成 unified diff：

```python
import difflib

def generate_diff(old_content: str, new_content: str, filepath: str) -> str:
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{filepath}",
        tofile=f"b/{filepath}",
        lineterm=""
    )
    return "".join(diff)
```

**输出示例**：
```diff
--- a/hello.py
+++ b/hello.py
@@ -2,7 +2,7 @@ import os
 import sys

 def main():
-    print('Hello, World!')
+    print('Hello, Python!')
     return 0

 if __name__ == '__main__':
```

### 2. 用户确认

使用 Rich 显示 diff 并请求确认：

```python
from rich.panel import Panel
from rich.syntax import Syntax

def confirm_edit(diff: str, filepath: str) -> bool:
    console.print(Panel(
        Syntax(diff, "diff", theme="monokai", line_numbers=True),
        title=f"[yellow]Proposed Edit: {filepath}[/yellow]",
        border_style="yellow"
    ))

    response = input("Apply this edit? (y/n): ").lower().strip()
    return response in ('y', 'yes')
```

### 3. 执行流程

修改后的 `execute()` 流程：

```python
async def execute(self, params: EditParams) -> dict[str, Any]:
    # 1. 验证参数
    # 2. 读取原内容
    # 3. 生成新内容（不写入）
    new_content = replace_content(content, params.oldString, params.newString)

    # 4. 生成 diff
    diff = generate_diff(content, new_content, str(path))

    # 5. 请求用户确认
    if not confirm_edit(diff, str(path)):
        raise UserCancelledError("Edit cancelled by user")

    # 6. 确认后才写入
    path.write_text(new_content, encoding="utf-8")

    return {...}
```

### 4. 异常处理

新增 `UserCancelledError` 异常：

```python
class UserCancelledError(Exception):
    """用户取消编辑操作"""
    pass
```

在 agent.py 中特殊处理：

```python
from dm_cc.tools.edit import UserCancelledError

except UserCancelledError as e:
    # 黄色边框显示取消信息
    console.print(Panel(str(e), title=f"Cancelled", border_style="yellow"))
```

---

## 与 opencode 对比

| 特性 | opencode | dm_cc |
|------|----------|-------|
| Diff 生成 | `diff` 库 (TS) | `difflib` (Python) |
| UI 组件 | 自定义 `<diff>` 组件 | Rich `Syntax` |
| 视图模式 | split/unified | 仅 unified |
| 确认方式 | `ctx.ask()` | `input()` |
| 选项 | Allow once/always/Reject | y/n |

---

## 文件变更

### 修改文件

1. `dm_cc/src/dm_cc/tools/edit.py`
   - 添加 `generate_diff()` 函数
   - 添加 `confirm_edit()` 函数
   - 添加 `UserCancelledError` 异常
   - 修改 `execute()` 流程

2. `dm_cc/src/dm_cc/agent.py`
   - 导入 `UserCancelledError`
   - 添加特殊异常处理

3. `dm_cc/src/dm_cc/tools/edit.txt`
   - 添加 diff 确认说明

---

## 测试

测试使用 `_auto_confirm` 参数跳过确认：

```python
params = EditParams(...)
params._auto_confirm = True  # 测试时自动确认
result = await self.tool.execute(params)
```

---

## 使用示例

用户交互示例：

```
╭────────────────── Proposed Edit: hello.py ──────────────────╮
│   1 --- a/hello.py                                          │
│   2 +++ b/hello.py                                          │
│   3 @@ -1,5 +1,5 @@                                         │
│   4   import os                                             │
│   5                                                           │
│   6   def main():                                           │
│   7 -    print('Hello')                                     │
│   8 +    print('Hello, World!')                             │
│   9       return 0                                          │
│  10                                                           │
╰─────────────────────────────────────────────────────────────╯
Apply this edit? (y/n): y
```

---

## 参考

- opencode edit.ts: `/opencode/packages/opencode/src/tool/edit.ts`
- Python difflib: https://docs.python.org/3/library/difflib.html
- Rich Syntax: https://rich.readthedocs.io/en/latest/syntax.html
