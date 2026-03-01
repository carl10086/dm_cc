"""Agent 配置系统单元测试"""

import pytest

from dm_cc.agents.config import AgentConfig, AGENTS, get_agent_config, list_agents, register_agent


class TestAgentConfig:
    """AgentConfig 测试类"""

    def test_basic_config(self):
        """测试基本配置创建"""
        config = AgentConfig(
            name="test",
            description="Test agent",
            system_prompt="You are a test agent.",
            allowed_tools=["*"],
            denied_tools=[],
        )
        assert config.name == "test"
        assert config.description == "Test agent"
        assert config.allowed_tools == ["*"]
        assert config.denied_tools == []

    def test_filter_tools_wildcard(self):
        """测试通配符允许所有工具"""
        config = AgentConfig(
            name="test",
            description="Test agent",
            system_prompt="Test",
            allowed_tools=["*"],
            denied_tools=[],
        )
        all_tools = {"read": object(), "write": object(), "edit": object()}
        filtered = config.filter_tools(all_tools)

        assert set(filtered.keys()) == {"read", "write", "edit"}

    def test_filter_tools_specific(self):
        """测试指定允许工具列表"""
        config = AgentConfig(
            name="readonly",
            description="Read-only agent",
            system_prompt="Test",
            allowed_tools=["read", "glob"],
            denied_tools=[],
        )
        all_tools = {"read": object(), "write": object(), "edit": object(), "glob": object()}
        filtered = config.filter_tools(all_tools)

        assert set(filtered.keys()) == {"read", "glob"}

    def test_filter_tools_denied_priority(self):
        """测试 denied_tools 优先级高于 allowed_tools"""
        config = AgentConfig(
            name="restricted",
            description="Restricted agent",
            system_prompt="Test",
            allowed_tools=["*"],
            denied_tools=["write", "edit"],
        )
        all_tools = {"read": object(), "write": object(), "edit": object(), "glob": object()}
        filtered = config.filter_tools(all_tools)

        assert set(filtered.keys()) == {"read", "glob"}
        assert "write" not in filtered
        assert "edit" not in filtered

    def test_filter_tools_specific_with_denied(self):
        """测试指定允许列表同时有排除项"""
        config = AgentConfig(
            name="custom",
            description="Custom agent",
            system_prompt="Test",
            allowed_tools=["read", "write", "edit"],
            denied_tools=["edit"],
        )
        all_tools = {"read": object(), "write": object(), "edit": object(), "glob": object()}
        filtered = config.filter_tools(all_tools)

        assert set(filtered.keys()) == {"read", "write"}
        assert "edit" not in filtered
        assert "glob" not in filtered

    def test_filter_tools_empty_allowed(self):
        """测试空允许列表返回空工具集"""
        config = AgentConfig(
            name="no_tools",
            description="No tools agent",
            system_prompt="Test",
            allowed_tools=[],
            denied_tools=[],
        )
        all_tools = {"read": object(), "write": object()}
        filtered = config.filter_tools(all_tools)

        assert filtered == {}


class TestPredefinedAgents:
    """预定义 Agent 配置测试"""

    def test_build_agent_exists(self):
        """测试 build agent 存在且配置正确"""
        assert "build" in AGENTS
        config = AGENTS["build"]
        assert config.name == "build"
        assert "*" in config.allowed_tools
        assert "plan_exit" in config.denied_tools  # Build agent 不能用 plan_exit

    def test_plan_agent_exists(self):
        """测试 plan agent 存在且配置正确"""
        assert "plan" in AGENTS
        config = AGENTS["plan"]
        assert config.name == "plan"
        # Plan agent 允许 read, glob, write, edit, plan_exit
        assert set(config.allowed_tools) == {"read", "glob", "write", "edit", "plan_exit"}
        # Plan agent 不能用 bash
        assert "bash" in config.denied_tools

    def test_get_agent_config_success(self):
        """测试获取已知 agent 配置"""
        config = get_agent_config("build")
        assert config.name == "build"

        config = get_agent_config("plan")
        assert config.name == "plan"

    def test_get_agent_config_failure(self):
        """测试获取未知 agent 配置报错"""
        with pytest.raises(ValueError) as exc_info:
            get_agent_config("unknown")
        assert "Unknown agent" in str(exc_info.value)
        assert "build" in str(exc_info.value)
        assert "plan" in str(exc_info.value)

    def test_list_agents(self):
        """测试列出所有 agent"""
        agents = list_agents()
        assert "build" in agents
        assert "plan" in agents


class TestRegisterAgent:
    """Agent 注册测试"""

    def test_register_new_agent(self):
        """测试注册新 agent"""
        new_config = AgentConfig(
            name="custom_agent",
            description="Custom test agent",
            system_prompt="Test prompt",
            allowed_tools=["read"],
            denied_tools=[],
        )
        register_agent(new_config)

        assert "custom_agent" in AGENTS
        assert AGENTS["custom_agent"].name == "custom_agent"

        # Clean up
        del AGENTS["custom_agent"]

    def test_register_overwrite_existing(self):
        """测试注册覆盖已有 agent"""
        original_config = AGENTS["build"]

        new_config = AgentConfig(
            name="build",
            description="Overridden",
            system_prompt="New prompt",
            allowed_tools=["read"],
            denied_tools=["write"],
        )
        register_agent(new_config)

        assert AGENTS["build"].description == "Overridden"
        assert AGENTS["build"].allowed_tools == ["read"]

        # Restore original
        AGENTS["build"] = original_config
