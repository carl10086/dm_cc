# TUI 完整实现计划（简化版）

## 设计参考
基于 opencode 的 TUI 设计，采用单窗口+可选侧边栏模式。

## 界面布局

```
┌─────────────────────────────────────────────────────────────┐
│ Header: dm_cc - DeepClone Coding Agent          [New] [Quit]│
├─────────────────────────────────────────────────────────────┤
│ Chat History (Scrollable)                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ User: hello                                             │ │
│ │                                                         │ │
│ │ Claude: Hi! How can I help you today?                   │ │
│ │                                                         │ │
│ │ [Tool: read_file] ✓ /path/to/file.txt                   │ │
│ │ ┌─────────────────────────────────────────────────────┐ │ │
│ │ │ file content here...                                │ │ │
│ │ └─────────────────────────────────────────────────────┘ │ │
│ │                                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│ Status Bar: build agent | claude-sonnet | 8 tools           │
├─────────────────────────────────────────────────────────────┤
│ Input Area                                                  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Type your message...                             [Send] │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## 阶段 1: 基础框架

### 1.1 最简 App
- [ ] 创建 `tui/app.py` - 主应用入口
- [ ] 创建 `tui/styles.css` - 基础样式
- [ ] 实现启动和退出（按 Q）
- **验收**: `uv run dmcc run` 显示窗口，按 Q 退出

### 1.2 屏幕管理
- [ ] 创建 `screens/home.py` - 首页（New Session 按钮）
- [ ] 创建 `screens/session.py` - 聊天主界面
- [ ] 实现屏幕切换（Home -> Session）
- **验收**: 按 'n' 或点击按钮进入 Session 界面

### 1.3 输入组件
- [ ] 创建 `widgets/input_area.py`
  - TextArea 多行输入
  - Send 按钮
  - Enter 发送，Shift+Enter 换行
- [ ] 实现输入提交事件
- **验收**: 输入文字，按 Enter，输入框清空，日志显示输入内容

### 1.4 消息显示
- [ ] 创建 `widgets/chat_view.py` - 滚动消息区域
- [ ] 创建 `widgets/message.py`
  - UserMessage（用户消息，右对齐，蓝色）
  - AssistantMessage（助手消息，左对齐，绿色）
- [ ] 实现消息追加到 ChatView
- **验收**: 用户输入后能在 ChatView 看到自己的消息

## 阶段 2: Agent 集成

### 2.1 连接 Agent
- [ ] SessionScreen 初始化 Agent
- [ ] 调用 Agent.run() 处理用户输入
- [ ] 显示 Agent 响应到 ChatView
- **验收**: 输入消息，能看到 Agent 回复

### 2.2 异步处理
- [ ] 使用 asyncio.create_task() 非阻塞调用
- [ ] 添加 loading 状态（转圈或"Thinking..."）
- [ ] 防止重复提交（发送后禁用按钮）
- **验收**: Agent 处理时 UI 不卡，有 loading 提示

### 2.3 输出处理
- [ ] 实现 TUIOutputHandler
  - 将 Agent 输出重定向到 ChatView
  - 处理工具调用结果
  - 格式化错误信息
- **验收**: Agent 工具调用结果正确显示

## 阶段 3: 增强功能

### 3.1 工具结果显示
- [ ] 创建 ToolResultMessage 组件
- [ ] 支持展开/折叠工具输出
- [ ] 显示工具执行状态（成功/失败）
- **验收**: 工具调用结果可折叠查看

### 3.2 侧边栏（可选）
- [ ] 创建 Sidebar 组件
- [ ] 显示 TODO 列表
- [ ] 显示会话信息（模型、Agent 类型）
- [ ] 快捷键 'o' 打开/关闭侧边栏
- **验收**: 按 'o' 显示/隐藏侧边栏，信息正确

### 3.3 消息操作
- [ ] 支持消息复制
- [ ] 代码块语法高亮
- [ ] 长消息折叠
- **验收**: 消息可操作，代码可读

## 阶段 4: 完善

### 4.1 导航和快捷键
- [ ] '1'/'2' 切换主区域和侧边栏焦点
- [ ] j/k 或 ↑/↓ 滚动消息历史
- [ ] Ctrl+L 清空聊天
- **验收**: 所有快捷键工作正常

### 4.2 Home Screen 完善
- [ ] 显示最近会话列表
- [ ] 快速开始新会话
- [ ] 显示版本信息
- **验收**: Home Screen 美观实用

### 4.3 测试和优化
- [ ] 单元测试覆盖 > 80%
- [ ] 性能测试（大文件处理）
- [ ] 错误边界处理
- **验收**: 无崩溃，错误有提示

## 当前进行: 阶段 1.1

从最简单的开始，每一步都要可验证。

## 文件结构

```
src/dm_cc/tui/
├── __init__.py
├── app.py              # 主应用入口
├── styles.css          # 全局样式
├── screens/
│   ├── __init__.py
│   ├── home.py         # 首页
│   └── session.py      # 聊天主界面
└── widgets/
    ├── __init__.py
    ├── input_area.py   # 输入区域
    ├── chat_view.py    # 聊天显示区域
    ├── message.py      # 消息组件
    └── sidebar.py      # 侧边栏（阶段3）
```

## 成功标准

每个阶段完成后必须满足：
1. 所有测试通过
2. CLI 模式 `--no-tui` 仍然正常工作
3. 用户可以直观操作，无需看代码
4. 错误有清晰提示

## 参考资源

- opencode TUI: `/Users/carlyu/soft/projects/coding_agents/opencode/packages/opencode/src/cli/cmd/tui/`
- Textual 文档: https://textual.textualize.io/
