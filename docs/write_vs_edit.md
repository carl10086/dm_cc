# Write vs Edit 工具对比

本文档记录了 opencode 中 Write 和 Edit 两个工具的区别，用于 dm_cc 项目参考实现。

---

## 概述

| 特性 | Write Tool | Edit Tool |
|------|-----------|-----------|
| **作用** | 完全覆盖整个文件 | 精准替换特定内容 |
| **范围** | 整个文件 | 文件中特定位置 |
| **匹配策略** | 无（直接覆盖） | 9 种智能匹配算法 |
| **安全性** | 较低（容易丢失原有内容） | 较高（只改需要改的地方） |
| **首选原则** | 尽量避免 | **优先使用** |

---

## Write Tool（写入工具）

### 参数
- `filePath`: 文件绝对路径
- `content`: 要写入的完整内容

### 行为
- 不管文件原来有什么，直接全部覆盖
- 如果文件不存在则创建新文件
- 保留旧内容用于生成 diff 预览

### 适用场景
1. **创建新文件** - 文件不存在时
2. **完全重写** - 整个内容都需要改变
3. **文件生成** - 从模板生成代码/配置
4. **重新开始** - 旧内容完全无关

### 代码示例
```typescript
const file = Bun.file(filepath)
const exists = await file.exists()
const contentOld = exists ? await file.text() : ""
await Bun.write(filepath, params.content)
```

---

## Edit Tool（编辑工具）

### 参数
- `filePath`: 文件绝对路径
- `oldString`: 要替换的文本（必须精确匹配）
- `newString`: 新文本（必须与 oldString 不同）
- `replaceAll`: 是否替换所有匹配（默认 false）

### 行为
- 使用 9 种匹配算法在文件中查找指定文本
- 只替换匹配的部分，保留文件其余内容
- 如果找不到匹配或有多处匹配（无 replaceAll），抛出错误

### 适用场景
1. **修改现有文件** - 只改特定部分
2. **重构** - 重命名变量、更新函数调用
3. **Bug 修复** - 修改特定行
4. **批量替换** - 使用 replaceAll 替换多处

### 9 种匹配算法

Edit 工具按顺序尝试以下匹配策略：

| 算法 | 描述 |
|------|------|
| `SimpleReplacer` | 精确字符串匹配 |
| `LineTrimmedReplacer` | 去除行首尾空格后匹配 |
| `BlockAnchorReplacer` | 使用首尾行作为锚点，相似度阈值匹配 |
| `WhitespaceNormalizedReplacer` | 标准化空白字符后匹配 |
| `IndentationFlexibleReplacer` | 忽略缩进差异匹配 |
| `EscapeNormalizedReplacer` | 处理转义字符后匹配 |
| `TrimmedBoundaryReplacer` | 边界修剪后匹配 |
| `ContextAwareReplacer` | 上下文感知匹配（50% 相似度启发式） |
| `MultiOccurrenceReplacer` | 处理多处匹配的情况 |

### 代码示例
```typescript
// 核心替换逻辑
export function replace(content: string, oldString: string, newString: string, replaceAll = false): string {
  if (oldString === newString) {
    throw new Error("No changes to apply: oldString and newString are identical.")
  }

  for (const replacer of [
    SimpleReplacer,
    LineTrimmedReplacer,
    BlockAnchorReplacer,
    WhitespaceNormalizedReplacer,
    IndentationFlexibleReplacer,
    EscapeNormalizedReplacer,
    TrimmedBoundaryReplacer,
    ContextAwareReplacer,
    MultiOccurrenceReplacer,
  ]) {
    for (const search of replacer(content, oldString)) {
      const index = content.indexOf(search)
      if (index === -1) continue
      // 找到匹配，执行替换
      if (replaceAll) {
        return content.replaceAll(search, newString)
      }
      // 检查是否唯一匹配
      const lastIndex = content.lastIndexOf(search)
      if (index !== lastIndex) continue
      return content.substring(0, index) + newString + content.substring(index + search.length)
    }
  }
  throw new Error("Could not find oldString in the file...")
}
```

---

## 设计原则

来自 opencode 的 description 文件：

> "ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required."
> （始终优先编辑现有文件，除非明确要求，否则不要写入新文件。）

**核心原则**：
- **优先使用 Edit** - 保留文件结构，只改必要部分
- **谨慎使用 Write** - 只在创建新文件或完全重写时使用
- **Read 优先** - 两个工具都要求先读取文件（安全检查）

---

## dm_cc 实现参考

### Python 实现要点

1. **Write Tool**
   - 使用 `path.write_text(content)` 直接写入
   - 保留旧内容用于生成 diff
   - 检查文件是否存在，不存在则创建

2. **Edit Tool**
   - 实现多种匹配策略（可从简单开始）
   - 必须验证 `oldString != newString`
   - 处理唯一性检查（非 replaceAll 时）
   - 提供清晰的错误信息

### 简化版本（MVP）

```python
# 简化版 Edit Tool - 从精确匹配开始
def replace_simple(content: str, old_string: str, new_string: str) -> str:
    if old_string == new_string:
        raise ValueError("old_string and new_string are identical")

    if old_string not in content:
        raise ValueError("Could not find old_string in content")

    count = content.count(old_string)
    if count > 1:
        raise ValueError(f"Found {count} matches, provide more context")

    return content.replace(old_string, new_string)
```

---

## 参考文件

- opencode Write: `/opencode/packages/opencode/src/tool/write.ts`
- opencode Edit: `/opencode/packages/opencode/src/tool/edit.ts`
- opencode Write Desc: `/opencode/packages/opencode/src/tool/write.txt`
- opencode Edit Desc: `/opencode/packages/opencode/src/tool/edit.txt`
