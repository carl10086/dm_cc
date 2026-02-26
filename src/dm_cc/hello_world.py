#!/usr/bin/env python3
"""Hello World 示例模块.

这是一个简单的示例模块，用于展示基本的 Python 代码结构。
"""

from datetime import datetime


def hello(name: str = "World") -> str:
    """返回问候语.

    Args:
        name: 要问候的名字，默认为 "World"

    Returns:
        问候语字符串
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"Hello, {name}! Current time: {current_time}"


def main() -> None:
    """主函数，程序入口."""
    message = hello()
    print(message)


if __name__ == "__main__":
    main()
