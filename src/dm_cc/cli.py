"""CLI 入口"""

import asyncio
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from dm_cc.agent import Agent
from dm_cc.tools import EditTool, GlobTool, ReadTool, WriteTool
from dm_cc.config import get_api_key, settings

app = typer.Typer(name="dmcc", help="dm_cc - DeepClone Coding Agent")
console = Console()


@app.callback()
def callback():
    """dm_cc - 一个极简的 Python Coding Agent"""
    pass


@app.command()
def run(
    prompt: Annotated[str | None, typer.Argument(help="初始提示，不提供则进入交互模式")] = None,
):
    """启动 Agent"""
    # 检查 API Key
    try:
        get_api_key()
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    # 初始化 Agent（read, write, glob, edit 工具）
    tools = [ReadTool(), WriteTool(), GlobTool(), EditTool()]
    agent = Agent(tools)

    console.print(Panel(
        "[bold]dm_cc[/bold] - DeepClone Coding Agent\n"
        f"Model: {settings.anthropic_model}\n"
        f"Tools: {', '.join(agent.tools.keys())}",
        border_style="blue"
    ))

    # 运行
    if prompt:
        # 单次模式
        asyncio.run(_run_once(agent, prompt))
    else:
        # 交互模式
        asyncio.run(_run_interactive(agent))


async def _run_once(agent: Agent, prompt: str) -> None:
    """单次运行"""
    await agent.run(prompt)


async def _run_interactive(agent: Agent) -> None:
    """交互模式"""
    console.print("\n[dim]Enter your request (q/exit to quit):[/dim]\n")

    while True:
        try:
            # 获取用户输入
            user_input = typer.prompt("You")
            if not user_input.strip():
                continue

            # 检查退出命令
            if user_input.strip().lower() in ("q", "exit"):
                console.print("\n[dim]Goodbye![/dim]")
                break

            console.print()
            await agent.run(user_input)
            console.print()

        except KeyboardInterrupt:
            console.print("\n\n[dim]Goodbye![/dim]")
            break


if __name__ == "__main__":
    app()
