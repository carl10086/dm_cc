# dm_cc Compact 系统实现方案

## 1. 设计目标

为 dm_cc 实现上下文压缩（Compact）机制，解决长对话时的 token 限制问题。

## 2. 核心设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **触发方式** | Token 阈值自动触发 | 简单可靠，无需用户干预 |
| **Buffer** | 保留 20% 空间 | 避免频繁 compact |
| **压缩粒度** | 整段历史替换为摘要 | 与 opencode 保持一致 |
| **摘要生成** | 复用现有 Agent 机制 | 无需新建 compaction agent |
| **存储** | Session 消息中标记 | 利用现有 message 系统 |

## 3. 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                     dm_cc Compact 架构                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Agent.run()                                                     │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────────────────────────────┐                        │
│  │ 1. 检查 Token 数                     │                        │
│  │    - 计算 messages 总 token          │                        │
│  │    - 对比模型限制                    │                        │
│  │    - 超过阈值？→ 触发 Compact        │                        │
│  └─────────────────────────────────────┘                        │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────────────────────────────┐                        │
│  │ 2. 生成摘要                          │                        │
│  │    - 构建 compaction prompt          │                        │
│  │    - 调用 LLM 生成摘要               │                        │
│  │    - 解析结构化输出                  │                        │
│  └─────────────────────────────────────┘                        │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────────────────────────────┐                        │
│  │ 3. 更新消息历史                      │                        │
│  │    - 标记旧消息为 compacted          │                        │
│  │    - 插入 summary message            │                        │
│  │    - 继续正常对话                    │                        │
│  └─────────────────────────────────────┘                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 4. 数据模型

### 4.1 Message 扩展

```python
# dm_cc/core/message.py

@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]
    agent: str = "build"
    synthetic: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    # 新增 compact 相关字段
    compacted: bool = False  # 是否已被 compact
    is_summary: bool = False  # 是否是摘要消息
    original_count: int = 0  # 被压缩的消息数量

@dataclass
class SummaryMessage(Message):
    """摘要消息 - 替换 compacted 消息"""
    summary_type: str = "compaction"  # 摘要类型
    goal: str = ""                    # 目标
    instructions: list[str] = field(default_factory=list)  # 指令
    discoveries: list[str] = field(default_factory=list)   # 发现
    accomplished: str = ""            # 已完成的工作
    relevant_files: list[str] = field(default_factory=list)  # 相关文件
```

### 4.2 Token 估算

```python
# dm_cc/core/token.py

class TokenEstimator:
    """Token 估算器 - 简化版"""

    # 粗略估算：1 token ≈ 4 字符（英文）
    # 中文约为 1 token ≈ 1.5-2 字符
    RATIO = 4.0

    @classmethod
    def estimate(cls, text: str) -> int:
        """估算文本的 token 数"""
        if not text:
            return 0
        return int(len(text) / cls.RATIO)

    @classmethod
    def estimate_messages(cls, messages: list[Message]) -> int:
        """估算消息列表的总 token"""
        total = 0
        for msg in messages:
            if isinstance(msg.content, str):
                total += cls.estimate(msg.content)
            elif isinstance(msg.content, list):
                for item in msg.content:
                    if isinstance(item, dict) and "text" in item:
                        total += cls.estimate(item["text"])
        return total
```

## 5. Compact 管理器

```python
# dm_cc/core/compact.py

from dataclasses import dataclass
from typing import Optional


@dataclass
class CompactConfig:
    """Compact 配置"""
    enabled: bool = True           # 是否启用
    threshold_ratio: float = 0.8   # 触发阈值（相对于模型限制）
    reserved_ratio: float = 0.2    # 保留空间
    min_messages: int = 4          # 最少消息数才触发（避免早期就 compact）


class CompactManager:
    """Compact 管理器"""

    DEFAULT_CONFIG = CompactConfig()

    def __init__(self, config: Optional[CompactConfig] = None):
        self.config = config or self.DEFAULT_CONFIG

    def should_compact(
        self,
        messages: list[Message],
        model_limit: int
    ) -> bool:
        """判断是否需要 compact"""
        if not self.config.enabled:
            return False

        # 消息数不够
        if len(messages) < self.config.min_messages:
            return False

        # 计算已 compact 的消息（不计入）
        active_messages = [m for m in messages if not m.compacted]

        # 估算 token
        token_count = TokenEstimator.estimate_messages(active_messages)

        # 阈值判断
        threshold = int(model_limit * self.config.threshold_ratio)
        return token_count >= threshold

    def select_messages_to_compact(
        self,
        messages: list[Message]
    ) -> list[Message]:
        """选择需要 compact 的消息"""
        # 策略：保留最近 N 条，compact 前面的
        # 简化：compact 前面 50% 的消息
        active_messages = [m for m in messages if not m.compacted]
        if len(active_messages) < self.config.min_messages:
            return []

        # 保留最近的 2 轮对话（user + assistant）
        to_preserve = 4
        if len(active_messages) <= to_preserve:
            return []

        return active_messages[:-to_preserve]

    def build_compaction_prompt(
        self,
        messages_to_compact: list[Message]
    ) -> str:
        """构建 compaction prompt"""
        # 将消息转为文本
        message_text = "\n\n".join([
            f"{msg.role.upper()}: {msg.content if isinstance(msg.content, str) else str(msg.content)}"
            for msg in messages_to_compact
        ])

        return f"""Please summarize the following conversation for continuation.

Conversation history:
---
{message_text}
---

Provide a structured summary using this format:

## Goal
[What goal(s) is the user trying to accomplish?]

## Instructions
- [Important instructions from the user]
- [Constraints or preferences]

## Discoveries
[Key technical findings and decisions made]

## Accomplished
[Completed work, in-progress work, and remaining work]

## Relevant Files
[List files that were read, edited, or created]

Be concise but comprehensive. The next agent should be able to continue the work based on your summary."""

    def create_summary_message(
        self,
        summary_text: str,
        original_count: int
    ) -> Message:
        """创建摘要消息"""
        return Message(
            role="assistant",
            content=f"[Session Summary]\n\n{summary_text}",
            is_summary=True,
            original_count=original_count,
            agent="system",  # 标记为系统生成
            synthetic=True,
        )

    def compact_messages(
        self,
        messages: list[Message],
        summary_message: Message,
        messages_to_compact: list[Message]
    ) -> list[Message]:
        """整合 compact 后的消息列表"""
        result = []

        # 保留未被 compact 的消息
        compact_ids = {m.id for m in messages_to_compact}
        for msg in messages:
            if msg.id in compact_ids:
                # 标记为 compacted，但不删除（保留历史）
                msg.compacted = True
            result.append(msg)

        # 插入摘要消息
        # 插入位置：第一个 compacted 消息的位置
        if messages_to_compact:
            first_compact_idx = next(
                i for i, m in enumerate(result)
                if m.id == messages_to_compact[0].id
            )
            result.insert(first_compact_idx, summary_message)

        return result
```

## 6. 集成到 Agent Loop

```python
# dm_cc/agent.py - 修改 run() 方法

class Agent:
    async def run(self, user_input: str | None = None) -> str:
        # ... 原有代码 ...

        # 新增：检查是否需要 compact
        if self.compact_manager.should_compact(
            self.ctx.messages,
            model_limit=self._get_model_limit()
        ):
            await self._compact_context()

        # 继续正常流程...

    async def _compact_context(self) -> None:
        """执行上下文压缩"""
        console.print("[dim]Compacting conversation history...[/dim]")

        # 1. 选择要 compact 的消息
        messages_to_compact = self.compact_manager.select_messages_to_compact(
            self.ctx.messages
        )

        if not messages_to_compact:
            return

        # 2. 构建 prompt
        prompt = self.compact_manager.build_compaction_prompt(messages_to_compact)

        # 3. 调用 LLM 生成摘要（简化版，不占用正常消息）
        summary_response = await self.llm.generate(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
        )
        summary_text = summary_response.text

        # 4. 创建摘要消息
        summary_message = self.compact_manager.create_summary_message(
            summary_text=summary_text,
            original_count=len(messages_to_compact)
        )

        # 5. 更新消息列表
        self.ctx.messages = self.compact_manager.compact_messages(
            messages=self.ctx.messages,
            summary_message=summary_message,
            messages_to_compact=messages_to_compact
        )

        console.print(f"[dim]Compacted {len(messages_to_compact)} messages into summary[/dim]")

    def _get_model_limit(self) -> int:
        """获取当前模型的上下文限制"""
        # 简化实现，实际从配置或 provider 获取
        model_limits = {
            "claude-sonnet-4-5-20250929": 200000,
            "claude-3-opus": 200000,
            "claude-3-haiku": 200000,
        }
        return model_limits.get(settings.anthropic_model, 100000)
```

## 7. Prompt 传递给 LLM 的修改

```python
# dm_cc/agent.py - 修改 _build_messages()

def _build_messages(self) -> list[dict]:
    """构建消息列表（过滤 compacted 消息，但保留 summary）"""
    messages = []

    for msg in self.ctx.messages:
        # 跳过已 compact 的普通消息
        if msg.compacted and not msg.is_summary:
            continue

        # 摘要消息和正常消息都保留
        messages.append({
            "role": msg.role,
            "content": msg.content if isinstance(msg.content, str)
                      else json.dumps(msg.content)
        })

    return messages
```

## 8. 配置选项

```python
# dm_cc/config.py - 添加 compact 配置

class Settings(BaseSettings):
    # ... 原有配置 ...

    # Compact 配置
    compact_enabled: bool = True
    compact_threshold_ratio: float = 0.8  # 80% 时触发
    compact_reserved_ratio: float = 0.2   # 保留 20%
    compact_min_messages: int = 6         # 最少 6 条消息才触发
```

## 9. CLI 支持

```python
# dm_cc/cli.py - 添加 compact 命令

@app.command()
def compact(
    session_id: str = typer.Argument(..., help="Session ID to compact"),
):
    """手动触发会话压缩"""
    # 加载 session
    # 执行 compact
    # 保存结果
    pass
```

## 10. 测试策略

```python
# tests/test_compact.py

class TestCompactManager:
    def test_should_compact_when_over_threshold(self):
        config = CompactConfig(threshold_ratio=0.8)
        manager = CompactManager(config)

        # 创建超过阈值的消息
        messages = [create_large_message() for _ in range(10)]

        assert manager.should_compact(messages, model_limit=10000) is True

    def test_select_messages_preserve_recent(self):
        manager = CompactManager()
        messages = [Message(role="user", content=f"msg{i}") for i in range(10)]

        to_compact = manager.select_messages_to_compact(messages)

        # 应该保留最近的 4 条
        assert len(to_compact) == 6
        assert messages[-1] not in to_compact
        assert messages[-2] not in to_compact

    def test_compact_messages_structure(self):
        manager = CompactManager()
        messages = create_test_messages(6)
        summary = Message(role="assistant", content="summary", is_summary=True)
        to_compact = messages[:2]

        result = manager.compact_messages(messages, summary, to_compact)

        # 验证摘要消息插入
        assert any(m.is_summary for m in result)
        # 验证原消息标记为 compacted
        assert all(m.compacted for m in to_compact)
```

## 11. 实现阶段

### Phase 1: 基础框架
- [ ] TokenEstimator 实现
- [ ] CompactManager 基础类
- [ ] Message 模型扩展

### Phase 2: 集成
- [ ] Agent.run() 集成 compact 检查
- [ ] _compact_context() 实现
- [ ] 配置项添加

### Phase 3: 优化
- [ ] 更精确的 token 计算
- [ ] 增量 compact（多次 compact）
- [ ] 手动 compact CLI 命令

### Phase 4: 测试
- [ ] 单元测试
- [ ] 集成测试
- [ ] 长对话场景测试

## 12. 与 opencode 的对比

| 特性 | opencode | dm_cc (本方案) |
|------|----------|----------------|
| **专用 Agent** | ✅ compaction agent | ❌ 复用现有 Agent |
| **Prune** | ✅ 两层优化 | ❌ 暂不实现 |
| **Token 估算** | 精确计算 | 粗略估算（简化） |
| **配置** | 详细配置项 | 简化配置 |
| **事件系统** | Bus 发布 | 暂不实现 |
| **手动触发** | ✅ API 支持 | ✅ CLI 支持 |

---

*设计方案日期: 2026-03-05*
