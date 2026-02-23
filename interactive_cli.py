#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行交互程序
功能：
1. 打印当前时间
2. 打印用户输入
3. 支持退出命令（退出、quit、exit）
"""

from datetime import datetime


def get_current_time():
    """获取当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    """主函数：命令行交互循环"""
    print("=" * 50)
    print("命令行交互程序")
    print("功能：输入任意内容，程序会显示时间和输入内容")
    print("退出命令：'退出', 'quit', 'exit', 'q'")
    print("=" * 50)
    print()
    
    # 退出命令列表
    exit_commands = ['退出', 'quit', 'exit', 'q', 'Q']
    
    while True:
        try:
            # 获取用户输入
            user_input = input("请输入: ").strip()
            
            # 检查是否为空输入
            if not user_input:
                continue
            
            # 检查是否为退出命令
            if user_input in exit_commands:
                print(f"\n[{get_current_time()}] 程序已退出")
                break
            
            # 打印时间和用户输入
            print(f"[{get_current_time()}] 输入内容: {user_input}")
            print()
            
        except KeyboardInterrupt:
            # 处理 Ctrl+C
            print(f"\n[{get_current_time()}] 程序被中断")
            break
        except EOFError:
            # 处理 EOF (Ctrl+D)
            print(f"\n[{get_current_time()}] 程序已退出")
            break


if __name__ == "__main__":
    main()