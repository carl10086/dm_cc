"""Tool 基类定义"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel


@dataclass
class ToolResult:
    """工具执行结果"""

    success: bool
    content: str
    error: str | None = None

    @classmethod
    def ok(cls, content: str) -> "ToolResult":
        return cls(success=True, content=content)

    @classmethod
    def error(cls, message: str) -> "ToolResult":
        return cls(success=False, content=message, error=message)


class Tool(ABC):
    """工具基类"""

    # 工具元信息 (子类覆盖)
    name: str = ""
    description: str = ""
    parameters: type[BaseModel] | None = None

    @abstractmethod
    async def execute(self, params: BaseModel) -> ToolResult:
        """执行工具逻辑"""
        pass

    def to_anthropic_schema(self) -> dict[str, Any]:
        """转换为 Anthropic Tools API 格式"""
        schema: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        if self.parameters:
            schema["input_schema"] = self.parameters.model_json_schema()
        return schema


# 便捷装饰器
T = TypeVar("T", bound=BaseModel)


def tool(name: str, description: str, params_model: type[T]) -> Callable:
    """工具装饰器，快速创建 Tool 类"""

    def decorator(func: Callable[[T], ToolResult]) -> type[Tool]:
        class DynamicTool(Tool):
            name = name
            description = description
            parameters = params_model

            async def execute(self, params: BaseModel) -> ToolResult:
                return func(params)  # type: ignore

        DynamicTool.__name__ = f"{name.title()}Tool"
        return DynamicTool

    return decorator
