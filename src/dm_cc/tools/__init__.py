"""Tools 包 - Agent 可调用的工具集合"""

from dm_cc.tools.base import Tool
from dm_cc.tools.edit import EditTool
from dm_cc.tools.glob import GlobTool
from dm_cc.tools.read import ReadTool
from dm_cc.tools.write import WriteTool
from dm_cc.tools.plan_enter import PlanEnterTool
from dm_cc.tools.plan_exit import PlanExitTool

__all__ = [
    "Tool",
    "EditTool",
    "GlobTool",
    "ReadTool",
    "WriteTool",
    "PlanEnterTool",
    "PlanExitTool",
    "load_all_tools",
]


def load_all_tools() -> dict[str, Tool]:
    """加载所有可用工具

    Returns:
        工具字典 {name: tool_instance}
    """
    tools = [
        ReadTool(),
        WriteTool(),
        GlobTool(),
        EditTool(),
        PlanEnterTool(),
        PlanExitTool(),
    ]
    return {t.name: t for t in tools}
