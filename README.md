# dm_cc - DeepClone Coding Agent

一个用 Python 实现的轻量级 AI 编程助手，深入理解 Coding Agent 的核心原理。

## 特性

- **Multi-Agent 架构**: Plan Agent（规划模式）+ Build Agent（执行模式）
- **工具系统**: 文件读写、代码编辑、Glob 搜索、Bash 执行
- **权限控制**: 基于 Agent 角色的工具访问控制
- **安全机制**: 危险命令拦截、目录访问限制

## 技术栈

| 组件 | 选择 |
|------|------|
| CLI | Typer |
| 数据校验 | Pydantic |
| HTTP Client | httpx |
| LLM SDK | Anthropic |
| 测试 | pytest |

## 快速开始

### 1. 环境准备

本项目使用 [uv](https://docs.astral.sh/uv/) 作为 Python 包管理器。

```bash
# 安装 uv (如果还没有安装)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. 克隆项目

```bash
git clone <repository-url>
cd dm_cc
```

### 3. 安装依赖

```bash
# 创建虚拟环境并安装所有依赖
uv sync

# 安装开发依赖（包含 pytest）
uv sync --dev
```

### 4. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，添加你的 Anthropic API Key
# ANTHROPIC_API_KEY=your_api_key_here
```

### 5. 运行项目

```bash
# 启动交互式 CLI
uv run dmcc

# 或者直接运行模块
uv run python -m dm_cc

# 使用交互式脚本
uv run python interactive_cli.py
```

## 常用命令

### 开发命令

```bash
# 运行测试
uv run pytest

# 运行特定测试文件
uv run pytest tests/test_agent_integration.py -v

# 代码类型检查
uv run pyright src/

# 运行 CLI 帮助
uv run dmcc --help
```

### 工具测试

```bash
# 测试 Bash Tool
uv run python -c "
import asyncio
from dm_cc.tools.bash import BashTool, BashParams

tool = BashTool()
params = BashParams(command='pwd')
result = asyncio.run(tool.execute(params))
print(result['output'])
"
```

## 项目结构

```
dm_cc/
├── src/dm_cc/
│   ├── agent.py           # Agent 主实现
│   ├── agents/
│   │   └── config.py      # Agent 配置
│   ├── tools/             # 工具实现
│   │   ├── bash.py        # Bash 工具
│   │   ├── read.py        # 文件读取
│   │   ├── write.py       # 文件写入
│   │   ├── edit.py        # 代码编辑
│   │   ├── glob.py        # 文件搜索
│   │   ├── plan_enter.py  # 切换到 Plan 模式
│   │   └── plan_exit.py   # 切换到 Build 模式
│   ├── core/              # 核心模块
│   │   ├── message.py     # 消息模型
│   │   ├── reminders.py   # 系统提醒
│   │   └── plan.py        # Plan 文件管理
│   └── cli.py             # CLI 入口
├── tests/                 # 测试文件
├── docs/                  # 文档
└── pyproject.toml         # 项目配置
```

## Agent 模式

### Build Agent（默认）

- 可编辑文件、执行命令
- 可以调用 `plan_enter` 切换到 Plan 模式

### Plan Agent

- 只读模式，用于研究和规划
- 只能编辑 `.dm_cc/plans/` 目录下的 plan 文件
- 完成后调用 `plan_exit` 切换回 Build 模式

## uv 使用参考

### 包管理

```bash
# 添加依赖
uv add package-name

# 添加开发依赖
uv add --dev package-name

# 更新依赖
uv sync --upgrade

# 锁定依赖版本
uv lock
```

### 虚拟环境

```bash
# uv 会自动管理虚拟环境，无需手动激活
# 所有命令通过 uv run 执行，自动使用项目虚拟环境

# 查看虚拟环境信息
uv venv

# 运行 Python 解释器
uv run python

# 运行 IPython（如果安装）
uv run ipython
```

### 更多命令

```bash
# 查看依赖树
uv tree

# 检查依赖更新
uv outdated

# 清理缓存
uv cache clean
```

## 配置说明

创建 `.env` 文件配置以下选项：

```bash
# 必需
ANTHROPIC_API_KEY=your_api_key

# 可选
ANTHROPIC_MODEL=claude-sonnet-4-6  # 默认模型
DMCC_HOME=.dm_cc                   # 数据存储目录
```

## 许可证

MIT

## 参考

- [opencode](https://github.com/sst/opencode) - 参考的 TypeScript 实现
- [uv 文档](https://docs.astral.sh/uv/)
