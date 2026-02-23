# Session Logger 设计文档

## 概述

Session Logger 用于记录每次对话会话的完整交互历史，帮助开发者理解 Agent 的工作流程、调试问题和优化性能。

**核心价值**:
- 完整追溯会话流程（LOOP 结构清晰）
- 调试 Agent 决策过程
- 分析 LLM 调用链
- 问题复现和排查

---

## 文件结构

```
dm_cc/
├── logs/                              # 日志目录（自动创建）
│   └── session_20250223_201530_a1b2c3d4.log
├── src/dm_cc/
│   ├── session_logger.py              # SessionLogger 实现
│   └── agent.py                       # 集成点
└── docs/
    └── session_logger_design.md       # 本文档
```

---

## 架构设计

```
┌──────────────────────────────────────────────────────────────┐
│                          User Input                          │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────┐
│                        Agent.run()                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              SessionLogger (上下文管理器)               │  │
│  │                                                        │  │
│  │  ┌──────────────┐    ┌──────────────┐                 │  │
│  │  │ log_user_    │    │ start_loop() │                 │  │
│  │  │ input()      │    │              │                 │  │
│  │  └──────────────┘    └──────────────┘                 │  │
│  │         │                   │                         │  │
│  │         ▼                   ▼                         │  │
│  │  ┌────────────────────────────────────────────┐      │  │
│  │  │            LOOP 1                          │      │  │
│  │  │  ┌──────────────┐  ┌──────────────┐       │      │  │
│  │  │  │ log_llm_     │  │ log_llm_     │       │      │  │
│  │  │  │ request()    │  │ response()   │       │      │  │
│  │  │  └──────────────┘  └──────────────┘       │      │  │
│  │  │         │                   │             │      │  │
│  │  │         ▼                   ▼             │      │  │
│  │  │  ┌──────────────────────────────────┐    │      │  │
│  │  │  │   log_tool_execution()           │    │      │  │
│  │  │  │   (多次工具调用)                  │    │      │  │
│  │  │  └──────────────────────────────────┘    │      │  │
│  │  └────────────────────────────────────────────┘      │  │
│  │                    │                                  │  │
│  │                    ▼                                  │  │
│  │  ┌────────────────────────────────────────────┐      │  │
│  │  │            LOOP 2 ...                       │      │  │
│  │  └────────────────────────────────────────────┘      │  │
│  │                                                        │  │
│  │  close()  ← 上下文退出时自动调用                       │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## SessionLogger 类

### 核心方法

| 方法 | 职责 | 调用时机 |
|------|------|----------|
| `__init__()` | 生成 session_id，创建日志文件 | Agent.run() 开始时 |
| `start_loop()` | 标记新循环开始，记录时间戳 | 每个 loop 开始时 |
| `log_user_input()` | 记录用户原始输入 | Agent.run() 初始化后 |
| `log_llm_request()` | 记录给 LLM 的消息和可用工具 | 调用 LLM 前 |
| `log_llm_response()` | 记录 LLM 响应（文本/工具调用） | LLM 返回后 |
| `log_tool_execution()` | 记录工具执行（输入/结果/错误） | 工具执行后 |
| `log_assistant_text()` | 记录最终文本回复 | 任务完成时 |
| `close()` | 写入会话统计信息 | 会话结束时 |

### 会话ID生成

```python
def _generate_session_id(self) -> str:
    """格式: YYYYMMDD_HHMMSS_随机8位"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = uuid.uuid4().hex[:8]
    return f"{timestamp}_{random_suffix}"

# 示例: 20250223_201530_a1b2c3d4
```

---

## 日志格式

### 文件命名

```
session_YYYYMMDD_HHMMSS_xxxxxxx.log
```

### 日志内容示例

```log
================================================================================
SESSION START: 2026-02-23 20:15:30
SESSION ID: 20250223_201530_a1b2c3d4
================================================================================

================================================================================
[LOOP 1]
Timestamp: 2026-02-23 20:15:30
================================================================================

--- USER INPUT ---
帮我读取 README.md 文件

--- LLM REQUEST ---
Messages:
[
  {
    "role": "user",
    "content": "帮我读取 README.md 文件"
  }
]

Available Tools (3):
[
  {
    "name": "read",
    "description": "读取文件内容..."
  },
  {
    "name": "edit",
    "description": "编辑文件内容..."
  },
  {
    "name": "glob",
    "description": "查找文件..."
  }
]

--- LLM RESPONSE ---
{
  "text": "我来帮您读取 README.md 文件。",
  "has_tool_calls": true,
  "tool_calls": [
    {
      "id": "tool_01ABCD",
      "name": "read",
      "input": {
        "filePath": "/path/to/README.md"
      }
    }
  ]
}

--- TOOL EXECUTION: read [SUCCESS] ---
Input:
{
  "filePath": "/path/to/README.md"
}

Result:
{
  "title": "README.md",
  "output": "# Project Name\n\n这是一个示例项目...",
  "metadata": {
    "truncated": false
  }
}

================================================================================
[LOOP 2]
Timestamp: 2026-02-23 20:15:31
================================================================================

--- LLM REQUEST ---
Messages:
[
  ...
]

--- LLM RESPONSE ---
{
  "text": "文件内容如下...",
  "has_tool_calls": false
}

--- ASSISTANT RESPONSE ---
文件内容如下：

# Project Name

这是一个示例项目...

================================================================================
SESSION END: 2026-02-23 20:15:32
Duration: 0:00:02
Total Loops: 2
================================================================================

Log file: /path/to/dm_cc/logs/session_20250223_201530_a1b2c3d4.log
```

---

## 与 Agent 的集成

### 修改点

**1. 导入 SessionLogger**

```python
from dm_cc.session_logger import SessionLogger
```

**2. Agent.run() 中使用上下文管理器**

```python
async def run(self, user_input: str) -> str:
    ctx = AgentContext()

    # 初始化会话日志
    with SessionLogger() as logger:
        # 记录用户输入
        ctx.messages.append({"role": "user", "content": user_input})
        logger.log_user_input(user_input)

        while ctx.step < ctx.max_steps:
            ctx.step += 1

            # 开始新循环日志
            logger.start_loop()

            # 记录 LLM 请求
            logger.log_llm_request(ctx.messages, self.tool_list)

            # 调用 LLM
            llm = await get_llm()
            response = await llm.complete(ctx.messages, self.tool_list)

            # 记录 LLM 响应
            logger.log_llm_response(response)

            # ... 处理工具调用 ...

            # 执行工具时传递 logger
            tool_results = await self._execute_tools(response.tool_calls, logger)

        # 任务完成时记录最终回复
        logger.log_assistant_text(response.text)
        return response.text
```

**3. _execute_tools() 接收 logger 参数**

```python
async def _execute_tools(
    self, tool_calls: list[Any], logger: SessionLogger
) -> list[dict[str, Any]]:
    for call in tool_calls:
        try:
            result = await tool.execute(params)
            # 记录成功
            logger.log_tool_execution(tool_name, tool_input, result, is_error=False)
        except Exception as e:
            # 记录错误
            logger.log_tool_execution(tool_name, tool_input, {"error": str(e)}, is_error=True)
```

---

## 使用方式

### 方式 1: 上下文管理器（推荐）

```python
with SessionLogger() as logger:
    # 会话代码
    ...
# 自动调用 close()
```

### 方式 2: 手动管理

```python
logger = SessionLogger()
try:
    # 会话代码
    ...
finally:
    logger.close()
```

---

## 日志目录管理

### 自动创建

```python
LOG_DIR = Path(__file__).parent.parent.parent / "logs"

# 确保目录存在
self.LOG_DIR.mkdir(parents=True, exist_ok=True)
```

### 清理策略（可选扩展）

```python
# 删除7天前的日志
import shutil
from datetime import datetime, timedelta

def cleanup_old_logs(days: int = 7):
    log_dir = Path("dm_cc/logs")
    cutoff = datetime.now() - timedelta(days=days)

    for log_file in log_dir.glob("session_*.log"):
        # 从文件名解析时间
        # session_YYYYMMDD_HHMMSS_xxxxxx.log
        try:
            timestamp_str = log_file.stem.split('_')[1:3]
            file_time = datetime.strptime('_'.join(timestamp_str), "%Y%m%d_%H%M%S")
            if file_time < cutoff:
                log_file.unlink()
        except (ValueError, IndexError):
            continue
```

---

## 扩展建议

### 1. 结构化日志（JSON 格式）

```python
import json
from dataclasses import asdict

class StructuredSessionLogger:
    def log_event(self, event_type: str, data: dict):
        event = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "event_type": event_type,
            "data": data
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
```

### 2. 日志级别控制

```python
from enum import Enum

class LogLevel(Enum):
    DEBUG = "debug"      # 所有细节
    INFO = "info"        # 默认
    ERROR = "error"      # 仅错误

class SessionLogger:
    def __init__(self, level: LogLevel = LogLevel.INFO):
        self.level = level
```

### 3. 异步日志写入

```python
import asyncio
from asyncio import Queue

class AsyncSessionLogger:
    def __init__(self):
        self.queue = Queue()
        self.writer_task = asyncio.create_task(self._writer_loop())

    async def _writer_loop(self):
        while True:
            message = await self.queue.get()
            await self._async_write(message)
```

### 4. 远程日志上传

```python
import httpx

class RemoteSessionLogger(SessionLogger):
    async def upload_to_server(self, server_url: str):
        async with httpx.AsyncClient() as client:
            with open(self.log_file, "rb") as f:
                await client.post(
                    f"{server_url}/logs",
                    files={"log": f},
                    data={"session_id": self.session_id}
                )
```

---

## 总结

Session Logger 是一个轻量级但功能完整的会话记录系统：

1. **使用简单**: 上下文管理器自动管理生命周期
2. **信息完整**: 记录用户输入、LLM 请求/响应、工具执行
3. **格式清晰**: LOOP 结构便于追溯执行流程
4. **易于扩展**: 支持结构化日志、异步写入等增强

---

*文档版本: 1.0*
*最后更新: 2026-02-23*
