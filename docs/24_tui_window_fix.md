# TUI Window Bug 修复

## 问题

运行 `dmcc run` 时出现错误：
```
MountError: Can't mount <class 'generator'>; expected a Widget instance.
```

## 原因

用户创建了 `base.py` 作为 Window 基类，但 `content()` 方法默认返回 `None`，而 `compose()` 方法中使用了 `yield self.content()`，这会导致：
1. 如果 `content()` 返回 `None`，`yield None` 会出错
2. 如果子类的 `content()` 使用 `yield`，它会返回 generator 而不是 Widget

## 解决方案

### 1. 修复 `base.py`

- 将 `content()` 重命名为 `compose_content()`
- 使用 `yield from self.compose_content()` 正确展开生成器
- `compose_content()` 应该返回 `ComposeResult` (使用 `yield` 生成 widgets)

```python
def compose(self) -> ComposeResult:
    """Compose window with header and content"""
    yield Static(f"[{self.window_id}] {self.window_title}", classes="window-header")
    with Vertical(classes="window-content"):
        # Call compose_content which should be overridden by subclasses
        yield from self.compose_content()

def compose_content(self) -> ComposeResult:
    """Override this to provide window content. Should yield widgets."""
    return
    yield  # Makes this a generator
```

### 2. 更新子类

`MainWindow` 和 `SideWindow` 现在：
- 继承自 `Window` 基类
- 覆盖 `compose_content()` 而不是 `compose()`
- 使用 `yield` 生成内容 widgets

示例：
```python
class MainWindow(Window):
    def __init__(self, **kwargs):
        super().__init__(window_id="1", window_title="Chat", **kwargs)

    def compose_content(self) -> ComposeResult:
        yield ChatView(id="chat-view")
```

## 关键概念

### `yield from`  vs `yield`

- `yield self.content()` - 如果 `content()` 返回 generator，这只会 yield generator 对象本身
- `yield from self.content()` - 展开 generator，yield 其中的每个值

### `ComposeResult`

Textual 的 `compose()` 方法应该返回 `ComposeResult`，实际上就是使用 `yield` 生成 widgets。为了让类型检查器满意，可以写成：

```python
def compose_content(self) -> ComposeResult:
    yield Widget1()
    yield Widget2()
```

## 文件变更

1. **`src/dm_cc/tui/windows/base.py`** - 修复基类实现
2. **`src/dm_cc/tui/windows/main_window.py`** - 继承 Window 基类
3. **`src/dm_cc/tui/windows/side_window.py`** - 继承 Window 基类
4. **`src/dm_cc/tui/windows/__init__.py`** - 导出 Window 基类
5. **`tests/test_tui_sanity.py`** - 添加 Window 导入测试

## 验证

```bash
# 运行测试
uv run pytest tests/test_tui_sanity.py -v

# 测试 TUI 启动
uv run dmcc run

# 测试 CLI 模式
uv run dmcc run --no-tui
```

所有测试通过，TUI 和 CLI 模式均正常工作。
