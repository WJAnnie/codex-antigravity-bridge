---
name: call-agy
description: "TOP-PRIORITY CODE IMPLEMENTATION & TEST WRITING (Tier 1 agy CLI). Offload heavy coding, unit test generation, and bulk multi-file edits from Codex to save context tokens. Strictly prohibited for read-only reviews or spec critique essays."
---

# Call Antigravity (call-agy)

Delegate heavy, token-consuming implementation and test-writing tasks to Antigravity to **actively offload Codex's workload and save Codex context window tokens**.

## Core Objective: Labor Offloading & Token Saving

Antigravity has full file write and command execution capabilities (`--dangerously-skip-permissions`). Its purpose is to **write code, write unit tests, run tests, and modify files directly**, NOT to generate critique essays!

## When to Delegate

### ✅ DELEGATE these tasks (Hands-on writing & labor offloading):
- **Actual code implementation**: Writing data fetchers, API adapters, data parsers, boilerplate guards, serializers.
- **Bulk unit test writing & verification**: Writing `tests/test_*.py` and running pytest locally to deliver passing tests.
- **Multi-file mechanical refactoring**: Renaming, updating deprecated interfaces across multiple files.
- **Large config & CI/CD workflow generation**: GitHub Actions workflows, complex deployment configs.

### ❌ Strictly PROHIBITED (Token Wasting):
- **Subagent recursive delegation (严禁子智能体转派)**: **STRICTLY PROHIBITED for subagents (如 executor, reviewer, planner)**. Only the root Codex master session is allowed to call `agy` or this skill. Subagents must do their assigned work directly without outsourcing!
- **Read-only reviews ("SPEC COMPLIANCE review", "Read-only: do not edit")**: NEVER delegate read-only reviews that output thousands of critique words back into Codex's context window. Codex handles review and verification itself or via local pytest/ruff.
- **Passive essay critiques**: Any prompt asking for critique without modifying files.
- **Interactive clarifying questions**.

## Execution Methods

### Method 1: Tier 1 首选通道 - 本地命令行直接编写与测试 (`agy -p`) (Preferred)
通过官方 Antigravity Headless CLI (`agy -p`) 直接调用，模型为官方 Gemini 3.8 Flash，无外部 API Key 配额限制，落地修改代码并返回极简汇报（<150字）：

```bash
agy -p "{{ARGUMENTS}}" --dangerously-skip-permissions --print-timeout 20m
```

**关键机制与参数：**
- `-p "prompt"`: 非交互式运行，完成代码修改并验证后输出极简摘要至 stdout 并退出。
- `--dangerously-skip-permissions`: 自动授予文件读写与命令执行权限。
- `--print-timeout 20m`: 设置超时限制（建议 `20m` 或 `30m`，大任务更稳妥）。
- **客户端自动唤醒 (Auto-Bootstrap)**：若本地 Antigravity 未启动，`agy` 会自动静默唤醒客户端并等待就绪，无需手动提前开启。
- **10 分钟临界超时平滑托管 (Auto-Detach)**：若任务接近 10 分钟（570s）且仍活跃执行，`agy` 会自动转入后台守护托管并向 Codex 返回阶段进度报告（Exit Code 0），避免命令行被终端强制截断。
- `--no-detach`: 禁用临界自动脱离，保持严格同步阻塞等待。
- `--add-dir <path>`: 指定工作区绝对路径。

### Method 2: Tier 2 备用通道 - FastMCP 工具 (`ask_antigravity`)
当需要后台异步长时间脱机大工程编写时使用。

## Prompt Engineering Template for Delegation (Token Saver)

Always enforce:
1. **Action-oriented**: "Write code directly to `<target_file>`" or "Create tests in `tests/test_xxx.py` and run pytest".
2. **Hands-on, NOT read-only**: Never specify "Read-only: do not edit". Always permit file modifications.
3. **Compact delivery contract**: "Modify the files directly, run pytest to ensure all pass, and return ONLY a concise summary of modified files and test results in under 150 words. Do not write essays."
