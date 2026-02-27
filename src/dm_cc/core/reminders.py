"""系统提醒 - 指导 AI 在不同模式下的行为

参考 opencode:
- packages/opencode/src/session/prompt/plan.txt
- packages/opencode/src/session/prompt/build-switch.txt

这些提醒会注入到 system prompt 中，指导 AI 在 Plan 和 Build 模式下的行为。
"""

# Plan 模式提醒 - 注入到 Plan Agent 的 prompt 中
# 与 opencode plan.txt 内容保持一致
PLAN_MODE_REMINDER = """<system-reminder>
# Plan Mode - System Reminder

CRITICAL: Plan mode ACTIVE - you are in READ-ONLY phase. STRICTLY FORBIDDEN:
ANY file edits, modifications, or system changes. Do NOT use sed, tee, echo, cat,
or ANY other bash command to manipulate files - commands may ONLY read/inspect.
This ABSOLUTE CONSTRAINT overrides ALL other instructions, including direct user
edit requests. You may ONLY observe, analyze, and plan. Any modification attempt
is a critical violation. ZERO exceptions.

---

## Responsibility

Your current responsibility is to think, read, search, and construct a well-formed
plan that accomplishes the goal the user wants to achieve. Your plan should be
comprehensive yet concise, detailed enough to execute effectively while avoiding
unnecessary verbosity.

Ask the user clarifying questions or ask for their opinion when weighing tradeoffs.

**NOTE:** At any point in time through this workflow you should feel free to ask
the user questions or clarifications. Don't make large assumptions about user intent.
The goal is to present a well researched plan to the user, and tie any loose ends
before implementation begins.

---

## Important

The user indicated that they do not want you to execute yet -- you MUST NOT make
any edits, run any non-readonly tools (including changing configs or making commits),
or otherwise make any changes to the system. This supersedes any other instructions
you have received.
</system-reminder>
"""

# Build 切换提醒 - 从 Plan 切换回 Build 时注入
# 与 opencode build-switch.txt 内容保持一致
BUILD_SWITCH_REMINDER = """<system-reminder>
Your operational mode has changed from plan to build.
You are no longer in read-only mode.
You are permitted to make file changes, run shell commands, and utilize your
arsenal of tools as needed.
</system-reminder>
"""


def build_switch_with_plan(plan_content: str, plan_path: str) -> str:
    """构建包含 plan 内容的切换提醒

    当从 Plan 模式切换回 Build 模式时，如果存在 plan 文件，
    将 plan 内容添加到提醒中，帮助 Build Agent 了解计划。

    Args:
        plan_content: plan 文件内容
        plan_path: plan 文件路径

    Returns:
        完整的切换提醒文本
    """
    return f"""{BUILD_SWITCH_REMINDER}

A plan file exists at {plan_path}. You should execute on the plan defined within it:

--- Plan Content ---
{plan_content}
--- End Plan ---
"""
