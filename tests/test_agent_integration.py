"""Agent 类集成测试 - 测试 AgentConfig 与 Agent 类的集成"""

import pytest

from dm_cc.agent import Agent
from dm_cc.tools import load_all_tools


class TestAgentInitialization:
    """Agent 初始化测试"""

    def test_default_build_agent(self):
        """测试默认 Build Agent 创建"""
        agent = Agent()

        assert agent.agent_name == "build"
        assert agent.config.name == "build"
        # Build agent 应该有所有工具
        assert "read" in agent.tools
        assert "write" in agent.tools
        assert "edit" in agent.tools
        assert "glob" in agent.tools

    def test_build_agent_explicit(self):
        """测试显式创建 Build Agent"""
        agent = Agent(agent_name="build")

        assert agent.agent_name == "build"
        # Build agent 允许所有工具，除了 plan_exit
        all_tools = load_all_tools()
        expected_tools = set(all_tools.keys()) - {"plan_exit"}
        assert set(agent.tools.keys()) == expected_tools

    def test_plan_agent(self):
        """测试 Plan Agent 创建"""
        agent = Agent(agent_name="plan")

        assert agent.agent_name == "plan"
        assert agent.config.name == "plan"
        # Plan agent 有 read, glob, write, edit, plan_exit (但不能用 bash)
        assert "read" in agent.tools
        assert "glob" in agent.tools
        assert "write" in agent.tools  # Plan agent 可以编辑 plan 文件
        assert "edit" in agent.tools   # Plan agent 可以编辑 plan 文件
        assert "plan_exit" in agent.tools  # Plan agent 可以退出 plan 模式
        assert "bash" not in agent.tools  # Plan agent 不能用 bash

    def test_plan_agent_tool_count(self):
        """测试 Plan Agent 工具数量"""
        agent = Agent(agent_name="plan")

        # Plan agent 有 5 个工具：read, glob, write, edit, plan_exit
        assert len(agent.tools) == 5
        assert len(agent.tool_list) == 5

    def test_unknown_agent_raises(self):
        """测试未知 Agent 名称报错"""
        with pytest.raises(ValueError) as exc_info:
            Agent(agent_name="unknown_agent")
        assert "Unknown agent" in str(exc_info.value)


class TestAgentWithCustomTools:
    """Agent 自定义工具测试"""

    def test_custom_tools_dict(self):
        """测试传入自定义工具字典"""
        all_tools = load_all_tools()
        # 只传入部分工具
        custom_tools = {"read": all_tools["read"], "glob": all_tools["glob"]}

        # 使用 build config，但传入部分工具
        agent = Agent(tools=custom_tools, agent_name="build")

        # 虽然 build 允许所有工具，但只传入的部分可用
        assert "read" in agent.tools
        assert "glob" in agent.tools
        assert "write" not in agent.tools
        assert "edit" not in agent.tools

    def test_custom_tools_list(self):
        """测试传入自定义工具列表"""
        all_tools = load_all_tools()
        custom_tools = [all_tools["read"], all_tools["glob"]]

        agent = Agent(tools=custom_tools, agent_name="build")

        assert len(agent.tools) == 2
        assert "read" in agent.tools
        assert "glob" in agent.tools

    def test_tools_filtered_by_config(self):
        """测试工具按配置过滤"""
        all_tools = load_all_tools()

        # Plan agent 配置允许 read, glob, write, edit, plan_exit
        agent = Agent(tools=all_tools, agent_name="plan")

        # 虽然传入了所有工具，但配置过滤后只有 5 个
        assert len(agent.tools) == 5
        assert set(agent.tools.keys()) == {"read", "glob", "write", "edit", "plan_exit"}


class TestAgentBackwardCompatibility:
    """Agent 向后兼容性测试"""

    def test_tools_parameter_optional(self):
        """测试 tools 参数可选"""
        # 不传 tools 参数也能工作
        agent = Agent(agent_name="build")
        # Build agent 有所有工具，除了 plan_exit
        assert len(agent.tools) == 6  # read, write, edit, glob, plan_enter, bash

    def test_default_agent_name(self):
        """测试默认 agent_name 为 build"""
        agent = Agent()
        assert agent.agent_name == "build"
