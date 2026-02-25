"""LSP (Language Server Protocol) 支持模块

Phase 1: 仅支持 Python，使用 pyright CLI 进行类型检查
"""

import json
import subprocess
from pathlib import Path
from typing import Any


class LSPChecker:
    """简化版 LSP 检查器 - CLI 调用方式"""

    def check_python(self, filepath: Path) -> list[dict[str, Any]]:
        """使用 pyright CLI 检查 Python 文件

        Args:
            filepath: 要检查的 Python 文件路径

        Returns:
            诊断信息列表，每个诊断包含 severity, message, range 等
        """
        try:
            result = subprocess.run(
                ["pyright", str(filepath), "--outputjson"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # pyright 返回非零退出码表示有错误，但输出仍在 stdout
            output = json.loads(result.stdout)
            return output.get("generalDiagnostics", [])

        except FileNotFoundError:
            # pyright 未安装，给出安装提示
            return [{
                "severity": "info",
                "message": "pyright not found. Install: pip install pyright",
                "range": {"start": {"line": 0, "character": 0}},
            }]
        except json.JSONDecodeError:
            return [{
                "severity": "error",
                "message": "Failed to parse pyright output",
                "range": {"start": {"line": 0, "character": 0}},
            }]
        except Exception as e:
            return [{"severity": "error", "message": str(e), "range": {"start": {"line": 0, "character": 0}}}]

    def format_diagnostics(
        self, errors: list[dict[str, Any]], filepath: Path, max_errors: int = 10
    ) -> str:
        """格式化诊断信息为可读字符串

        Args:
            errors: 诊断信息列表
            filepath: 文件路径
            max_errors: 最多显示的错误数

        Returns:
            格式化后的错误信息字符串
        """
        if not errors:
            return ""

        severity_map = {
            "error": "ERROR",
            "warning": "WARN",
            "info": "INFO",
        }

        lines = ["\n\nLSP errors detected in this file, please fix:"]
        lines.append(f'<diagnostics file="{filepath}">')

        for error in errors[:max_errors]:
            severity = severity_map.get(error.get("severity", "error"), "ERROR")
            range_info = error.get("range", {})
            start = range_info.get("start", {})
            line = start.get("line", 0) + 1
            col = start.get("character", 0) + 1
            message = error.get("message", "Unknown error")
            lines.append(f"{severity} [{line}:{col}] {message}")

        if len(errors) > max_errors:
            lines.append(f"... and {len(errors) - max_errors} more")

        lines.append("</diagnostics>")
        return "\n".join(lines)
