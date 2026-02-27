"""Agent 配置系统 - 支持多 Agent 和权限控制"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dm_cc.tools.base import Tool


@dataclass
class AgentConfig:
    """Agent 配置类

    定义 Agent 的基本信息和工具权限。

    Attributes:
        name: Agent 标识名
        description: Agent 功能描述
        system_prompt: 系统提示词
        allowed_tools: 允许使用的工具列表，["*"] 表示全部允许
        denied_tools: 禁止使用的工具列表，优先级高于 allowed_tools
    """

    name: str
    description: str
    system_prompt: str
    allowed_tools: list[str]  # ["*"] 表示全部
    denied_tools: list[str]  # 优先级高于 allowed

    def filter_tools(self, all_tools: dict[str, "Tool"]) -> dict[str, "Tool"]:
        """根据配置过滤可用工具

        Args:
            all_tools: 所有可用工具的字典 {name: tool}

        Returns:
            过滤后的工具字典
        """
        # 确定允许的工具集合
        if "*" in self.allowed_tools:
            allowed = set(all_tools.keys())
        else:
            allowed = set(self.allowed_tools)

        # denied_tools 优先级更高，从允许集合中移除
        for denied in self.denied_tools:
            allowed.discard(denied)

        return {name: tool for name, tool in all_tools.items() if name in allowed}


# 预定义 Agent 配置
AGENTS: dict[str, AgentConfig] = {
    "build": AgentConfig(
        name="build",
        description="默认执行 Agent，可编辑文件和执行命令",
        system_prompt="""你是 dm_cc，一个专业的编程助手。

你的任务是帮助用户完成软件开发任务，包括：
- 读取和理解代码库结构
- 编辑、修改和创建文件
- 分析代码问题并提供解决方案
- 完成软件工程任务

请遵循以下原则：
1. 先理解需求，再动手修改
2. 读取相关文件，确保理解上下文
3. 使用工具完成任务，必要时询问用户确认
4. 提供清晰、有用的响应
5. 复杂任务先调用 plan_enter 切换到 Plan Agent 进行规划

你有权限使用文件编辑工具（read, write, edit, glob）。
不能直接使用 plan_exit（这是 Plan Agent 的权限）。""",
        allowed_tools=["*"],
        denied_tools=["plan_exit"],  # Build agent 不能使用 plan_exit
    ),
    "plan": AgentConfig(
        name="plan",
        description="规划 Agent，只读模式，用于分析和规划",
        system_prompt="""你是 dm_cc 的规划模式 Agent。

你的任务是帮助用户分析和规划：
- 读取代码库理解结构
- 分析问题和需求
- 制定执行计划
- 将计划写入 plan 文件
- 提供建议和方案

限制：
- 只能读取代码文件，不能编辑代码文件
- 只能编辑 .dm_cc/plans/ 目录下的 plan 文件
- 专注于分析和规划
- 完成后调用 plan_exit 切换回 Build Agent 执行

你有权限使用只读工具（read, glob）和 plan 文件编辑工具（write, edit）。""",
        allowed_tools=["read", "glob", "write", "edit", "plan_exit"],
        denied_tools=[],  # 权限控制在 agent.py 的 _execute_tools 中实现
    ),
}


def get_agent_config(name: str) -> AgentConfig:
    """获取指定 Agent 的配置

    Args:
        name: Agent 名称

    Returns:
        AgentConfig 实例

    Raises:
        ValueError: 如果 Agent 不存在
    """
    if name not in AGENTS:
        available = ", ".join(AGENTS.keys())
        raise ValueError(f"Unknown agent: {name}. Available: {available}")
    return AGENTS[name]


def register_agent(config: AgentConfig) -> None:
    """注册新的 Agent 配置

    Args:
        config: Agent 配置实例
    """
    AGENTS[config.name] = config


def list_agents() -> list[str]:
    """获取所有注册的 Agent 名称

    Returns:
        Agent 名称列表
    """
    return list(AGENTS.keys())
