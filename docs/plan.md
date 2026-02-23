# dm_cc 实现计划

## 项目定位

MCP 精简版 Coding Agent - 仅支持 Claude，专注代码编写，去除 Skills 和 MCP 插件系统。

---

## 阶段规划

### Phase 1: 最小可用产品 (MVP)

**目标**: 能对话 + 能读写文件 + 能执行命令

**核心模块**:
- `cli.py` - 入口命令 `dmcc run`
- `agent.py` - Agent 核心循环 (从 opencode 学到的 loop 模式)
- `llm.py` - Anthropic 接口封装
- `tools/` - 4 个核心工具 (read, edit, bash, glob)
- `config.py` - API Key 和基础配置
- `session.py` - 简单内存会话管理

**技术栈**:
- Python 3.12+
- `anthropic` - 官方 SDK
- `pydantic` - 类型校验
- `rich` - 终端美化
- `typer` - CLI 框架

---

### Phase 2: 基础增强

- [ ] System Prompt 分层 (Provider + 环境 + 项目规则)
- [ ] 权限系统 (allow/ask/deny)
- [ ] 会话持久化 (JSON 存储)

---

### Phase 3: 体验优化

- [ ] 流式输出
- [ ] 代码块渲染
- [ ] 死循环检测 (DoomLoop)
- [ ] 多 Agent (build/plan)

---

## 当前任务

1. [x] 创建 plan.md (本文档)
2. [x] 项目骨架 - `dm_cc/` 目录 + `pyproject.toml`
3. [x] 核心循环 - `agent.py` + `llm.py`
4. [x] 第一个 Tool - `read`

---

## 完成情况

### 已创建文件

```
dm_cc/
├── src/dm_cc/
│   ├── __init__.py      # 版本信息
│   ├── cli.py           # CLI 入口 (typer)
│   ├── config.py        # 配置管理 (pydantic-settings)
│   ├── agent.py         # Agent 核心循环
│   ├── llm.py           # Anthropic 封装
│   └── tools/
│       ├── __init__.py
│       ├── base.py      # Tool 基类
│       └── read.py      # 文件读取工具
├── pyproject.toml       # 项目配置
├── .env.example         # 环境变量模板
└── README.md
```

### 功能验证

```bash
# 安装依赖
uv sync

# 运行 CLI
uv run dmcc --help

# 启动 Agent
uv run dmcc run
```

### 当前能力

- ✅ CLI 框架 (typer)
- ✅ 配置管理 (环境变量 / .env 文件)
- ✅ Agent 核心循环 (支持工具调用)
- ✅ Anthropic 集成 (Claude 3.5 Sonnet)
- ✅ Read 工具 (带行号和范围限制)
- ✅ Rich 终端美化

---

## 下一步

建议继续实现:

1. **edit 工具** - 文件编辑/创建
2. **bash 工具** - 命令执行
3. **glob 工具** - 文件搜索

这三个工具配合 read 可以完成基本的代码编写任务。

---

## 核心循环设计

基于 opencode 的 loop 架构，简化版：

```python
async def loop(user_input: str, tools: list[Tool]):
    messages = [{"role": "user", "content": user_input}]

    while True:
        response = await llm.complete(messages, tools)

        if response.has_tool_calls:
            results = await execute_tools(response.tool_calls)
            messages.extend(format_tool_results(results))
            continue  # 继续循环

        return response.text  # 文本回复，结束
```

---

*创建时间: 2026-02-13*
