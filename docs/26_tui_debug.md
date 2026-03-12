# TUI 调试指南

## 当前状态

### ✅ 已完成
- TUI 界面启动正常
- 双窗口布局正确显示（MainWindow 75%, SideWindow 25%）
- 窗口切换正常（按 1/2 或 Tab）
- Agent 初始化成功
- 输入区域工作正常

### ❌ 已知问题
- **输入提交后 Agent 没有响应** - 消息显示在聊天窗口，但 Agent 不处理

## 诊断步骤

### 1. 检查通知消息

启动 TUI 后，你应该看到：
- "Agent initialized successfully" - 表示 Agent 已就绪
- "Input submitted: ..." - 表示输入已接收
- "Message added to chat" - 表示消息已显示
- "Starting worker..." - 表示 Worker 正在启动

### 2. 测试 CLI 模式（验证 Agent 工作）

```bash
echo "test" | uv run dmcc run --no-tui
```

如果 CLI 模式工作，说明 Agent 本身没问题。

### 3. 运行单元测试

```bash
uv run pytest tests/tui/test_integration.py -v
```

所有测试应该通过。

### 4. 检查 Worker 状态

在 `session.py` 中添加了诊断通知：

```python
worker = self.run_worker(self._process_agent_response(message.text))
self.notify(f"Worker started: {worker}", severity="information")
```

### 5. 常见原因

#### Worker 未启动
- 检查 `run_worker` 是否返回 Worker 对象
- 检查是否有异常被捕获

#### Agent 未响应
- 检查 `_agent` 是否为 None
- 检查 API key 是否设置正确

#### 异步问题
- `run_worker` 可能需要在真实 TUI 模式下不同的处理
- 可能需要使用 `asyncio.create_task` 替代

## 可能的解决方案

### 方案 1: 使用 asyncio.create_task

替换 `run_worker`：

```python
import asyncio

async def _process_agent_response(self, user_input: str) -> None:
    # ... 相同代码

async def on_input_area_submitted(self, message):
    # ... 显示消息
    asyncio.create_task(self._process_agent_response(message.text))
```

### 方案 2: 同步执行

对于快速测试，可以同步执行：

```python
def on_input_area_submitted(self, message):
    # ... 显示消息
    import asyncio
    asyncio.get_event_loop().create_task(
        self._process_agent_response(message.text)
    )
```

### 方案 3: 使用 Textual 的 Worker API

```python
from textual.worker import Worker

@Worker.threaded
def _process_in_thread(self, user_input: str):
    # 在线程中运行
    import asyncio
    asyncio.run(self._process_agent_response(user_input))
```

## 调试技巧

### 启用 Textual 调试模式

```bash
textual run --dev dm_cc.cli:app
```

### 查看日志

添加日志到 `/tmp/dmcc_debug.log`：

```python
import logging
logging.basicConfig(
    filename='/tmp/dmcc_debug.log',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

# 在关键位置添加
logger.debug(f"Input submitted: {message.text}")
```

### 简化测试

创建一个最小测试案例：

```python
from textual.app import App
from textual.widgets import Input, Button

class TestApp(App):
    def compose(self):
        yield Input(id="input")
        yield Button("Submit", id="submit")

    def on_button_pressed(self, event):
        input_widget = self.query_one("#input", Input)
        text = input_widget.value
        self.run_worker(self._process(text))

    async def _process(self, text):
        self.notify(f"Processing: {text}")

if __name__ == "__main__":
    app = TestApp()
    app.run()
```

## 下一步

1. 确认通知消息是否显示
2. 检查 Worker 是否正确启动
3. 尝试方案 1 或方案 2
4. 如果仍有问题，添加日志文件
