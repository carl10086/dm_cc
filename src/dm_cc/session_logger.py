"""Session Logger - 会话历史记录器

记录每次会话的完整交互历史，包括：
- 用户输入
- 给 LLM 的消息
- LLM 的响应
- 工具调用和执行结果
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionLogger:
    """会话日志记录器"""

    LOG_DIR = Path(__file__).parent.parent.parent / "logs"

    def __init__(self):
        """初始化会话日志"""
        self.session_id = self._generate_session_id()
        self.log_file = self.LOG_DIR / f"session_{self.session_id}.log"
        self.loop_count = 0
        self.start_time = datetime.now()

        # 确保日志目录存在
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)

        # 写入会话开始标记
        self._write_header()

    def _generate_session_id(self) -> str:
        """生成唯一的会话ID: 时间戳_随机后缀"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]
        return f"{timestamp}_{random_suffix}"

    def _write_header(self) -> None:
        """写入会话头部信息"""
        header = f"""{'=' * 80}
SESSION START: {self.start_time.strftime("%Y-%m-%d %H:%M:%S")}
SESSION ID: {self.session_id}
{'=' * 80}

"""
        self._append(header)

    def _append(self, content: str) -> None:
        """追加内容到日志文件"""
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(content)

    def start_loop(self) -> int:
        """开始一个新的循环，返回循环编号"""
        self.loop_count += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        loop_header = f"""
{'=' * 80}
[LOOP {self.loop_count}]
Timestamp: {timestamp}
{'=' * 80}

"""
        self._append(loop_header)
        return self.loop_count

    def log_user_input(self, user_input: str) -> None:
        """记录用户输入"""
        content = f"""--- USER INPUT ---
{user_input}

"""
        self._append(content)

    def log_llm_request(self, messages: list[dict[str, Any]], tools: list[Any]) -> None:
        """记录给 LLM 的请求（消息和工具）"""
        # 格式化消息
        messages_str = json.dumps(messages, indent=2, ensure_ascii=False)

        # 格式化工具列表
        tools_info = []
        for tool in tools:
            tools_info.append({
                "name": tool.name,
                "description": tool.description[:100] + "..." if len(tool.description) > 100 else tool.description,
            })
        tools_str = json.dumps(tools_info, indent=2, ensure_ascii=False)

        content = f"""--- LLM REQUEST ---
Messages:
{messages_str}

Available Tools ({len(tools)}):
{tools_str}

"""
        self._append(content)

    def log_llm_response(self, response: Any) -> None:
        """记录 LLM 的响应"""
        response_info = {
            "text": response.text if hasattr(response, 'text') else None,
            "has_tool_calls": response.has_tool_calls if hasattr(response, 'has_tool_calls') else False,
        }

        # 记录工具调用
        if hasattr(response, 'tool_calls') and response.tool_calls:
            tool_calls_info = []
            for tc in response.tool_calls:
                tool_calls_info.append({
                    "id": tc.id if hasattr(tc, 'id') else None,
                    "name": tc.name if hasattr(tc, 'name') else None,
                    "input": tc.input if hasattr(tc, 'input') else None,
                })
            response_info["tool_calls"] = tool_calls_info

        response_str = json.dumps(response_info, indent=2, ensure_ascii=False)

        content = f"""--- LLM RESPONSE ---
{response_str}

"""
        self._append(content)

    def log_tool_execution(self, tool_name: str, tool_input: dict[str, Any], result: dict[str, Any], is_error: bool = False) -> None:
        """记录工具执行"""
        status = "ERROR" if is_error else "SUCCESS"

        content = f"""--- TOOL EXECUTION: {tool_name} [{status}] ---
Input:
{json.dumps(tool_input, indent=2, ensure_ascii=False)}

Result:
{json.dumps(result, indent=2, ensure_ascii=False)}

"""
        self._append(content)

    def log_assistant_text(self, text: str) -> None:
        """记录助手的纯文本回复（无工具调用时）"""
        content = f"""--- ASSISTANT RESPONSE ---
{text}

"""
        self._append(content)

    def log_error(self, error: Exception) -> None:
        """记录错误信息"""
        content = f"""--- ERROR ---
Type: {type(error).__name__}
Message: {str(error)}

"""
        self._append(content)

    def close(self) -> None:
        """结束会话，写入尾部信息"""
        end_time = datetime.now()
        duration = end_time - self.start_time

        footer = f"""{'=' * 80}
SESSION END: {end_time.strftime("%Y-%m-%d %H:%M:%S")}
Duration: {duration}
Total Loops: {self.loop_count}
{'=' * 80}

Log file: {self.log_file}
"""
        self._append(footer)

    def __enter__(self) -> "SessionLogger":
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """上下文管理器出口，自动关闭"""
        self.close()
