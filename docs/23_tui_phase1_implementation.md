# TUI Phase 1 实现总结

## 实现内容

### 1. 双窗口布局

创建了两个独立的窗口组件:

#### MainWindow (主窗口)
- **文件**: `src/dm_cc/tui/windows/main_window.py`
- **用途**: 显示聊天历史
- **快捷键**: `1`
- **宽度**: 75%
- **激活边框**: 绿色 (`$success`)

#### SideWindow (侧边窗口)
- **文件**: `src/dm_cc/tui/windows/side_window.py`
- **用途**: 显示会话信息和 TODO 列表
- **快捷键**: `2`
- **宽度**: 25%
- **激活边框**: 黄色 (`$warning`)

### 2. 窗口切换机制

**快捷键**:
- `1` - 切换到主窗口 (Chat)
- `2` - 切换到侧边窗口 (Info)
- `Tab` - 在窗口间循环切换

**视觉反馈**:
- 当前激活窗口有彩色边框高亮
- 窗口标题栏显示 `[1] Chat` 或 `[2] Info`
- 标题栏背景色随激活状态变化

### 3. 代码变更

#### 新增文件
```
src/dm_cc/tui/windows/
├── __init__.py
├── main_window.py      # 主聊天窗口
└── side_window.py      # 侧边信息窗口
```

#### 修改文件
1. **SessionScreen** (`screens/session.py`)
   - 使用 MainWindow 和 SideWindow 替代原来的布局
   - 添加 `current_window` reactive 状态
   - 实现 `action_switch_window()` 和 `action_next_window()`
   - 添加 `watch_current_window()` 监听状态变化

2. **OutputHandler** (`output_handler.py`)
   - 更新为使用 MainWindow 替代直接的 ChatView
   - 通过 `#main-window` ID 查询主窗口

3. **styles.css**
   - 添加 MainWindow 和 SideWindow 的样式
   - 添加 `.active` 类的样式定义
   - 添加 `.window-header` 的样式

4. **tests**
   - 更新 `test_tui_sanity.py` 包含新窗口导入测试

### 4. 使用方式

#### 启动 TUI (默认)
```bash
uv run dmcc run
```

#### 启动传统 CLI 模式
```bash
uv run dmcc run --no-tui
```

#### 直接执行单次命令 (自动使用 CLI 模式)
```bash
uv run dmcc run "你好"
```

## 效果预览

```
┌─────────────────────────────────────────────────────────────┐
│ dm_cc - DeepClone Coding Agent              [1] Chat [2] Info│
├─────────────────────────────────────────────────────────────┤
│ [1] Chat                    │ [2] Info                      │
│ ┌─────────────────────────┐ │ ┌─────────────────────────┐   │
│ │ Welcome to dm_cc!       │ │ Model: claude-sonnet    │   │
│ │                         │ │ Agent: build            │   │
│ │ User: 你好              │ │                         │   │
│ │                         │ │ TODOs                   │   │
│ │ Assistant: 你好！       │ │ ○ Task 1                │   │
│ │                         │ │ ○ Task 2                │   │
│ └─────────────────────────┘ │ └─────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│ > _                                                           │
└─────────────────────────────────────────────────────────────┘
```

当按 `1` 时，主窗口边框变绿色；
当按 `2` 时，侧边窗口边框变黄色。

## 技术要点

### Reactive 状态
```python
current_window: reactive[int] = reactive(1)

# 当 current_window 改变时自动调用
def watch_current_window(self, window_id: int) -> None:
    self._update_window_states()
```

### 动态 CSS 类
```python
def watch_is_active(self, active: bool) -> None:
    # 添加/移除 active 类
    self.set_class(active, "active")
```

### CSS 样式
```css
MainWindow.active {
    border: solid $success;
}

MainWindow.active .window-header {
    background: $success;
    color: $text;
}
```

## 测试

运行 TUI 基础测试:
```bash
uv run pytest tests/test_tui_sanity.py -v
```

测试包含:
- 导入测试 (通过)
- 组件实例化测试 (通过)
- App 创建测试 (通过)

## 下一步 (Phase 2)

可选的增强功能:
1. **窗口内独立滚动** - 每个窗口支持 `j/k` 或 `↑/↓` 滚动
2. **窗口标题栏信息** - 显示当前会话名称、消息数量等
3. **窗口大小调整** - 支持拖拽调整窗口宽度
4. **更多窗口** - 添加第三个日志窗口 (按 `3` 切换)
5. **快捷键提示** - 在底部显示当前可用的快捷键

## 兼容性

- ✅ CLI 模式 (`--no-tui`) 完全保留
- ✅ 所有原有功能正常工作
- ✅ 新 TUI 模式使用双窗口布局
- ✅ 支持键盘快捷键切换窗口
