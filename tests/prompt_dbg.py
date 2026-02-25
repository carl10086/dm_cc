#!/usr/bin/env python3
"""Prompt 调试脚本 - 用于 IDE 调试

在 IDE 中直接运行，或交互式执行:
    cd /Users/carlyu/soft/projects/coding_agents/dm_cc
    uv run python -i tests/prompt_dbg.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asyncio
from dm_cc.prompt.builder import (
    PROVIDER_TEMPLATE,
    AGENT_TEMPLATE,
    _build_environment_layer,
    _build_custom_layer,
    _build_tools_section,
    PromptBuilder,
)
from dm_cc.tools import ReadTool, EditTool, GlobTool


# 创建工具实例
tools = [ReadTool(), EditTool(), GlobTool()]

# 逐层查看
provider_layer = PROVIDER_TEMPLATE
environment_layer = _build_environment_layer()
custom_layer = _build_custom_layer()
tools_layer = _build_tools_section(tools)
agent_layer = AGENT_TEMPLATE

# 构建完整 prompt
async def build_full():
    builder = PromptBuilder()
    return await builder.build(tools)


full_prompt = asyncio.run(build_full())

# 打印摘要
print(f"Provider layer: {len(provider_layer)} chars")
print(f"Environment layer: {len(environment_layer)} chars")
print(f"Custom layer: {len(custom_layer) if custom_layer else 0} chars")
print(f"Tools layer: {len(tools_layer)} chars")
print(f"Agent layer: {len(agent_layer)} chars")
print(f"Full prompt: {len(full_prompt)} chars")
print("\nVariables available:")
print("  provider_layer, environment_layer, custom_layer")
print("  tools_layer, agent_layer, full_prompt, tools")
