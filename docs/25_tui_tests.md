# TUI 测试总结

## 测试覆盖

创建了完整的 TUI 测试套件，共 **15 个测试**，全部通过。

### 测试文件

```
tests/
├── test_tui_sanity.py              # 4 个基础测试
└── tui/
    ├── test_windows.py             # 5 个窗口组件测试
    ├── test_session_screen.py      # 3 个会话屏幕测试
    └── test_integration.py         # 3 个集成测试
```

## 测试详情

### 1. 基础测试 (test_tui_sanity.py)

| 测试 | 描述 |
|------|------|
| `test_tui_imports` | 验证所有 TUI 模块可以导入 |
| `test_css_syntax` | 验证 CSS 文件语法正确 |
| `test_widget_instantiation` | 验证组件可以实例化 |
| `test_app_creation` | 验证 TUI App 可以创建 |

### 2. 窗口组件测试 (test_windows.py)

| 测试 | 描述 |
|------|------|
| `test_window_creation` | 窗口可以被创建 |
| `test_window_inheritance` | MainWindow/SideWindow 正确继承 Window |
| `test_window_reactive_state` | reactive 状态正常工作 |
| `test_window_compose_content` | compose_content 生成器正常工作 |
| `test_window_in_app` | 窗口在 App 中正常工作 |

### 3. 会话屏幕测试 (test_session_screen.py)

| 测试 | 描述 |
|------|------|
| `test_session_screen_creation` | SessionScreen 可以创建 |
| `test_window_switching` | 窗口切换 (1/2) 正常工作 |
| `test_window_query` | 可以通过 ID 查询窗口 |

### 4. 集成测试 (test_integration.py)

| 测试 | 描述 |
|------|------|
| `test_app_startup` | TUI App 启动正常 |
| `test_home_to_session_navigation` | Home -> Session 导航正常 |
| `test_window_navigation` | 窗口切换集成测试 |

## 运行测试

```bash
# 运行所有 TUI 测试
uv run pytest tests/tui/ tests/test_tui_sanity.py -v

# 运行特定测试文件
uv run pytest tests/tui/test_windows.py -v
uv run pytest tests/tui/test_session_screen.py -v
uv run pytest tests/tui/test_integration.py -v

# 运行基础测试
uv run pytest tests/test_tui_sanity.py -v
```

## 关键技术点

### 1. 使用 `pytest-anyio`

Textual 测试需要异步支持，使用 `@pytest.mark.anyio` 装饰器：

```python
@pytest.mark.anyio
async def test_window_in_app():
    app = WindowTestApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # 测试代码
```

### 2. 测试模式下的 App

使用 `app.run_test()` 在测试模式下运行 App，不会占用终端：

```python
async with app.run_test() as pilot:
    await pilot.pause()
    # 执行操作
    await pilot.click("#button")
```

### 3. 查询组件

使用 `query_one` 查询特定组件：

```python
# 通过 ID 查询
main = app.query_one("#main-window", MainWindow)

# 通过类型查询
side = app.query_one(SideWindow)
```

### 4. 测试 Reactive 状态

直接设置 reactive 属性，Textual 会自动更新：

```python
main_window.is_active = True
await pilot.pause()  # 让事件循环处理更新
```

## 测试发现的问题

1. **Window 基类问题** - `compose()` 使用 `yield self.content()` 导致 generator 错误
   - **修复**: 使用 `yield from self.compose_content()`

2. **CSS 解析 API 变化** - `parse()` 函数签名变化
   - **修复**: 使用 App 加载 CSS 的方式测试

3. **SessionScreen 查询问题** - 窗口 ID 查询需要在 screen 上执行
   - **修复**: `screen.query_one()` 替代 `app.query_one()`

## 持续集成

建议在 CI 中运行：

```bash
uv run pytest tests/tui/ tests/test_tui_sanity.py -v --tb=short
```

## 下一步

可以添加的测试：

1. **输入处理测试** - 测试 InputArea 提交消息
2. **Agent 集成测试** - 测试与 Agent 的交互（使用 mock）
3. **TODO 功能测试** - 测试 TODO 列表更新
4. **快捷键测试** - 测试键盘快捷键
5. **窗口大小调整测试** - 测试布局变化

## 总结

- ✅ 15 个测试全部通过
- ✅ 覆盖窗口组件、会话屏幕、集成测试
- ✅ 使用 mock App 方式测试，无需真实终端
- ✅ 快速反馈（全部测试 < 2秒）
