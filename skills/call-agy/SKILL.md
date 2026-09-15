---
name: call-agy
description: "TOP-PRIORITY DEFAULT DELEGATION (Tier 1 via agy CLI). Automatically active by default for all code reviews, security audits, architecture investigations, bulk test generation, and complex multi-file tasks. Uses native CLI 'agy -p' as Tier 1 preferred channel. No need for user to explicitly mention call-agy or antigravity in the prompt."
---

# Call Antigravity (call-agy)

Delegate complex, multi-file, or long-running tasks to Google Antigravity to leverage its deep reasoning and multi-agent capabilities while preserving context window tokens.

## When to Delegate

### ✅ DELEGATE these tasks:
- **Deep codebase investigation**: Multi-file cross-referencing, architecture mapping, dependency auditing.
- **Second-opinion code review**: Independent inspection of security boundaries, data leakage, and regressions.
- **Bulk test & documentation generation**: Writing large test suites or API docs without cluttering context.
- **Web research with Google Search grounding**: Real-time authoritative search and verification.

### ❌ Do NOT delegate:
- Simple 1-line syntax tweaks or straightforward edits.
- Interactive conversational clarifying questions.
- Tasks where you already have the exact solution ready to write.

## Execution Methods

### Method 1: Tier 1 首选通道 - 本地命令行调用 (`agy -p`) (Preferred)
通过原生终端命令直接调用 Antigravity，标准输出直出纯净 Markdown，底层由高可用中继集群（GPT-5.6-Sol / DeepSeek-V4 / GLM-5.3）强力驱动，**彻底根除 Google 原生 API 每日 20 次的极低额度瓶颈**，零等待、零 429 报错：

```bash
agy -p "{{ARGUMENTS}}" --dangerously-skip-permissions --print-timeout 10m
```

**关键参数：**
- `-p "prompt"` / `--print "prompt"`: 非交互式运行，执行完毕直接将纯净 Markdown 结果输出至 stdout 并退出。
- `--dangerously-skip-permissions`: 自动允许文件读写与命令执行权限。
- `--print-timeout 10m`: 设置超时限制（支持 `5m`, `10m`, `300s`）。
- `--add-dir <path>`: 指定工作区绝对路径。

### Method 2: Tier 2 备用通道 - FastMCP 工具 (`ask_antigravity`)
当需要超长任务（>180s）后台异步脱机托管、通过桌面悬浮小组件实时查看进度、或者在 MCP 环境中结构化调用时使用：
- 调用 `ask_antigravity` 或 `antigravity_code_review`；
- 内置 180s 自动脱机保护与网络自愈重试，完整 Markdown 报告自动归档至 `<workspace>/.antigravity_reports/`。

## Prompt Engineering Template for Delegation

Always include:
1. **Target scope**: Absolute workspace and file paths.
2. **Explicit constraints**: "Inspect only, do not modify files" or "Write tests in tests/test_xxx.py".
3. **Output contract**: Request structured Markdown, file:line citations, and severity levels.
