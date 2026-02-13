"""配置管理"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""

    # Anthropic API
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    anthropic_max_tokens: int = 4096

    # 应用
    working_dir: Path = Path.cwd()
    debug: bool = False

    class Config:
        env_file = ".env"
        env_prefix = "DMCC_"


# 全局配置实例
settings = Settings()


def get_api_key() -> str:
    """获取 API Key，优先级: 环境变量 > .env 文件"""
    key = settings.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise ValueError(
            "未找到 Anthropic API Key.\n"
            "请设置环境变量: export DMCC_ANTHROPIC_API_KEY='your-key'\n"
            "或创建 .env 文件: echo 'DMCC_ANTHROPIC_API_KEY=your-key' > .env"
        )
    return key
