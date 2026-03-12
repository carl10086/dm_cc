# TUI 双窗口设计 - Lazygit 风格

## 1. 核心概念

### 1.1 什么是 Lazygit 风格？

Lazygit 是一个终端 UI 工具，它的设计理念是：
- **多窗口独立**: 不同功能区域用独立窗口展示
- **数字快捷键切换**: 按数字键 `1`, `2`, `3` 等快速切换窗口
- **每个窗口有自己的状态**: 比如滚动位置、选中项等
- **窗口间有联动**: 一个窗口的操作影响另一个窗口的显示

### 1.2 我们的双窗口设计

```
┌─────────────────────────────────────────────────────────────┐
│ Header: dm_cc - DeepClone Coding Agent           [1] [2] [Q] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  MainWindow (Window 1)         SideWindow (Window 2)       │
│  ┌──────────────────────┐     ┌──────────────────────┐     │
│  │                      │     │                      │     │
│  │   Chat History       │     │   Session Info       │     │
│  │   - User messages    │     │   - Model: claude    │     │
│  │   - Assistant        │     │   - Agent: build     │     │
│  │   - Tool results     │     │                      │     │
│  │                      │     │   TODO List          │     │
│  │   [Scrollable]       │     │   ○ Task 1           │     │
│  │                      │     │   ○ Task 2           │     │
│  └──────────────────────┘     └──────────────────────┘     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Input Area (Fixed at bottom)                                │
│ > _                                                         │
└─────────────────────────────────────────────────────────────┘
```

## 2. 窗口定义

### Window 1: MainWindow (主窗口)
- **用途**: 显示对话历史
- **快捷键**: `1`
- **包含组件**:
  - ChatView (消息列表)
  - 用户输入消息
  - Agent 回复
  - Tool 执行结果

### Window 2: SideWindow (侧边窗口)
- **用途**: 显示会话信息和任务
- **快捷键**: `2`
- **包含组件**:
  - Session 信息 (模型、agent 类型)
  - TODO 列表
  - 工具执行统计

### Window 3: LogWindow (日志窗口) - 可选
- **用途**: 显示系统日志
- **快捷键**: `3`
- **包含组件**:
  - 执行日志
  - 错误信息

## 3. 交互设计

### 3.1 窗口切换

```python
# 全局快捷键绑定
BINDINGS = [
    ("1", "switch_window(1)", "Chat"),
    ("2", "switch_window(2)", "Info"),
    ("3", "switch_window(3)", "Logs"),
    ("tab", "next_window", "Next"),
    ("shift+tab", "prev_window", "Prev"),
]
```

### 3.2 当前窗口的视觉反馈

```
当前窗口 1 时:
┌──────────────────────┐     ┌──────────────────────┐
│ [1] Chat        ***  │     │ [2] Info             │
│                      │     │                      │
│  当前窗口有边框高亮   │     │  非当前窗口正常显示   │
│  标题栏显示 [1]      │     │  标题栏显示 [2]      │
└──────────────────────┘     └──────────────────────┘

当前窗口 2 时:
┌──────────────────────┐     ┌──────────────────────┐
│ [1] Chat             │     │ [2] Info        ***  │
│                      │     │                      │
│                      │     │  当前窗口有边框高亮   │
└──────────────────────┘     └──────────────────────┘
```

### 3.3 窗口内的操作

每个窗口有自己的操作快捷键，只在窗口激活时生效:

**MainWindow (Chat)**:
- `↑/↓` or `j/k` - 滚动消息
- `G` - 跳到最后
- `gg` - 跳到开头
- `enter` - 查看消息详情

**SideWindow (Info)**:
- `↑/↓` or `j/k` - 滚动 TODO 列表
- `space` - 切换 TODO 状态
- `n` - 新建 TODO

## 4. 实现逻辑

### 4.1 核心类设计

```python
from textual.app import App
from textual.containers import Horizontal, Vertical
from textual.widgets import Header, Footer, Static
from textual.reactive import reactive
from textual.screen import Screen

class MainWindow(Vertical):
    """主窗口 - 显示聊天历史"""

    DEFAULT_CSS = """
    MainWindow {
        width: 70%;
        height: 100%;
        border: solid $primary;
    }
    MainWindow.active {
        border: solid $success;
    }
    """

    is_active: reactive[bool] = reactive(False)

    def watch_is_active(self, active: bool) -> None:
        """当激活状态改变时更新样式"""
        self.set_class(active, "active")

class SideWindow(Vertical):
    """侧边窗口 - 显示会话信息"""

    DEFAULT_CSS = """
    SideWindow {
        width: 30%;
        height: 100%;
        border: solid $primary-darken-2;
    }
    SideWindow.active {
        border: solid $success;
    }
    """

    is_active: reactive[bool] = reactive(False)

    def watch_is_active(self, active: bool) -> None:
        self.set_class(active, "active")

class DualPaneScreen(Screen):
    """双窗口主屏幕"""

    BINDINGS = [
        ("1", "switch_window(1)", "Chat"),
        ("2", "switch_window(2)", "Info"),
        ("tab", "next_window", "Next"),
        ("q", "quit", "Quit"),
    ]

    current_window: reactive[int] = reactive(1)

    def compose(self) -> ComposeResult:
        with Horizontal(id="main-container"):
            yield MainWindow(id="main-window")
            yield SideWindow(id="side-window")
        yield InputArea(id="input-area")

    def watch_current_window(self, window_id: int) -> None:
        """当当前窗口改变时更新"""
        main_window = self.query_one("#main-window", MainWindow)
        side_window = self.query_one("#side-window", SideWindow)

        main_window.is_active = (window_id == 1)
        side_window.is_active = (window_id == 2)

    def action_switch_window(self, window_id: int) -> None:
        """切换到指定窗口"""
        self.current_window = window_id
```

### 4.2 窗口内聚焦管理

每个窗口内部可以有子组件聚焦:

```python
class MainWindow(Vertical):
    """主窗口 - 支持内部聚焦"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._chat_view = None
        self._focus_index = 0
        self._focusable_widgets = []

    def compose(self) -> ComposeResult:
        yield ChatHeader()
        yield ChatView(id="chat-view")  # 可聚焦
        yield ChatFooter()

    def on_mount(self) -> None:
        """初始化可聚焦组件列表"""
        self._focusable_widgets = [
            self.query_one("#chat-view", ChatView),
        ]

    def focus_next(self) -> None:
        """聚焦下一个组件"""
        self._focus_index = (self._focus_index + 1) % len(self._focusable_widgets)
        self._focusable_widgets[self._focus_index].focus()

    def on_key(self, event) -> None:
        """处理键盘事件 - 只在窗口激活时"""
        if not self.is_active:
            return

        if event.key == "j":
            self._focusable_widgets[0].scroll_down()
        elif event.key == "k":
            self._focusable_widgets[0].scroll_up()
        elif event.key == "g":
            self._focusable_widgets[0].scroll_home()
        elif event.key == "G":
            self._focusable_widgets[0].scroll_end()
```

### 4.3 输入区域的设计

输入区域固定在底部，不受窗口切换影响:

```python
class InputArea(Horizontal):
    """底部输入区域 - 始终可见"""

    DEFAULT_CSS = """
    InputArea {
        dock: bottom;
        height: 3;
        background: $surface;
        border-top: solid $primary;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(">", id="prompt")
        yield TextArea(id="input-text")
        yield Button("Send", id="send-btn")
```

## 5. 具体实现建议

### 5.1 最简单的实现 (Phase 1)

先实现基础的双窗口 + 数字切换:

```python
class SimpleDualPane(Screen):
    """最简单的双窗口实现"""

    BINDINGS = [
        ("1", "focus_main", "Main"),
        ("2", "focus_side", "Side"),
    ]

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(id="main-pane") as main:
                yield ChatView()
            with Vertical(id="side-pane") as side:
                yield SessionInfo()
                yield TodoList()
        yield InputArea()

    def action_focus_main(self) -> None:
        self.query_one("#main-pane", Vertical).focus()

    def action_focus_side(self) -> None:
        self.query_one("#side-pane", Vertical).focus()
```

### 5.2 增加视觉反馈 (Phase 2)

添加边框高亮和标题栏:

```python
class Pane(Vertical):
    """带标题栏的窗口"""

    def __init__(self, title: str, pane_id: str, **kwargs):
        super().__init__(**kwargs)
        self.pane_title = title
        self.pane_id = pane_id

    def compose(self) -> ComposeResult:
        yield Static(f"[{self.pane_id}] {self.pane_title}", classes="pane-header")
        yield self.content()

    def watch_is_active(self, active: bool) -> None:
        header = self.query_one(".pane-header", Static)
        if active:
            header.styles.background = "$success"
            self.styles.border = "solid $success"
        else:
            header.styles.background = "$surface"
            self.styles.border = "solid $primary-darken-2"
```

### 5.3 完整的 Lazygit 风格 (Phase 3)

实现完整的窗口管理和快捷键系统:

```python
class WindowManager:
    """窗口管理器 - 管理多个窗口的状态和切换"""

    def __init__(self, app: App):
        self.app = app
        self.windows = {}
        self.current = 0
        self._key_map = {}

    def register_window(self, window_id: int, window: Widget, key: str):
        """注册窗口"""
        self.windows[window_id] = window
        self._key_map[key] = window_id

    def switch_to(self, window_id: int) -> None:
        """切换到指定窗口"""
        if window_id in self.windows:
            # 失活当前窗口
            if self.current in self.windows:
                self.windows[self.current].is_active = False

            # 激活新窗口
            self.current = window_id
            self.windows[self.current].is_active = True
            self.windows[self.current].focus()

    def next_window(self) -> None:
        """切换到下一个窗口"""
        window_ids = sorted(self.windows.keys())
        if not window_ids:
            return

        current_idx = window_ids.index(self.current) if self.current in window_ids else -1
        next_idx = (current_idx + 1) % len(window_ids)
        self.switch_to(window_ids[next_idx])
```

## 6. 关键技术点

### 6.1 reactive 状态

Textual 的 reactive 可以自动触发 UI 更新:

```python
from textual.reactive import reactive

class MyWidget(Widget):
    is_active: reactive[bool] = reactive(False)

    def watch_is_active(self, active: bool) -> None:
        """当 is_active 改变时自动调用"""
        self.set_class(active, "active")
```

### 6.2 焦点管理

Textual 有内建的焦点系统:

```python
# 让组件可聚焦
class MyWidget(Widget, can_focus=True):
    pass

# 设置焦点
def action_focus_main(self):
    self.query_one("#main", MyWidget).focus()

# 检查是否有焦点
def on_key(self, event) -> None:
    if not self.has_focus:
        return
```

### 6.3 CSS 类切换

根据状态改变样式:

```python
# 添加/移除 CSS 类
self.set_class(True, "active")   # 添加 active 类
self.set_class(False, "active")  # 移除 active 类

# 或者在 CSS 中定义
Widget.active {
    border: solid $success;
}
```

## 7. 推荐实现路线

### Phase 1: 基础双窗口 (今天就能用)
- 两个 Vertical 容器并排
- 数字键 1/2 切换焦点
- 简单的边框颜色变化

### Phase 2: 完善功能 (下周)
- 添加窗口标题栏
- 窗口内独立滚动
- 不同窗口的不同快捷键

### Phase 3: Lazygit 风格 (可选)
- 3-4 个窗口
- 完整的窗口管理器
- 窗口间联动

## 8. 示例代码位置

建议创建以下文件:

```
dm_cc/tui/
├── __init__.py
├── app.py              # 已有，需要修改
├── screens/
│   ├── __init__.py
│   ├── base.py         # 基础 Screen 类
│   └── dual_pane.py    # 双窗口屏幕 (新)
├── windows/            # 窗口组件 (新目录)
│   ├── __init__.py
│   ├── base.py         # Window 基类
│   ├── main_window.py  # 主聊天窗口
│   └── side_window.py  # 侧边信息窗口
└── widgets/            # 已有
```

## 9. 参考资源

- Textual 文档: https://textual.textualize.io/
- Lazygit 快捷键: https://github.com/jesseduffield/lazygit/blob/master/docs/keybindings/Keybindings_en.md
- Textual 示例: https://github.com/Textualize/textual/tree/main/examples
