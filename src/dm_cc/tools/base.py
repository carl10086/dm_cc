"""Tool 基类定义 - 对齐 opencode 设计"""

from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel


class Tool(ABC):
    """工具基类 - 对齐 opencode 设计

    子类需要定义:
    - name: str
    - description: str
    - parameters: type[BaseModel]
    - execute(params) -> dict[str, Any]  # 抛出异常表示错误
    """

    # 工具元信息 (子类覆盖)
    name: str = ""
    description: str = ""
    parameters: type[BaseModel] | None = None

    @abstractmethod
    async def execute(self, params: BaseModel) -> dict[str, Any]:
        """执行工具逻辑

        Returns:
            dict with keys: title, output, metadata (optional)

        Raises:
            Exception: 执行失败时抛出
        """
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
