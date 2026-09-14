---
name: codex-antigravity-bridge
description: Seamlessly bridge OpenAI Codex / Claude / Cursor with Google Antigravity expert subagents via FastMCP, featuring an Auto-Detaching Hybrid Engine that permanently eliminates client 300s timeouts without requiring users to specify async mode, with a floating real-time desktop monitor widget.
---

# Codex Antigravity Bridge

`codex-antigravity-bridge` 是一个将 **OpenAI Codex** 与 **Google Antigravity** 双向打通的协同 Skill 与工具网关。

它最大的特色是内置了 **全自动防超时自愈引擎 (Auto-Detaching Hybrid Engine)**：
- **用户与 Codex 无需每次强调“异步”**：直接调用 `ask_antigravity` 或 `antigravity_code_review` 即可。
- **大任务瞬间秒转（$\ge 3$ 文件）**：0.1 秒内直接以托管模式返回凭据，Codex 零等待。
- **安全时限熔断托管（180 秒）**：任务若在 180 秒内完成，直接返回结果；若超过 180 秒，在 Codex 的 300 秒极限前自动转入后台继续运行，**从物理上彻底根除 300s 超时中断**！
- **自动持久化 Markdown 报告**：后台任务完成后，自动生成标准 Markdown 报告至 `<workspace>/.antigravity_reports/<task_id>.md`。

---

## 🌟 核心工具矩阵

| 工具名称 | 模式 | 特性 |
|---|---|---|
| `ask_antigravity` | 智能混合 | 180 秒自愈熔断，小任务同步直出，大任务自动转入后台报告 |
| `antigravity_code_review` | 智能混合 | $\ge 3$ 个文件 0.1 秒秒转后台；1~2 个文件 180 秒自愈熔断 |
| `ask_antigravity_async` | 显式异步 | 立即返回任务 ID，适合显式长任务指令 |
| `antigravity_code_review_async` | 显式异步 | 立即返回任务 ID，适合显式长代码审查 |
| `check_antigravity_task` | 同步查询 | 查询后台任务当前状态、耗时、执行摘要及报告文件路径（支持 `wait_seconds` 等待） |
| `list_antigravity_tasks` | 同步列表 | 列出最近 5 次后台任务的执行概览与状态矩阵 |

---

## 🛠️ 安装与部署

运行根目录下的 `install.bat` 或在 PowerShell 中执行 `.\install.ps1` 即可全自动完成配置注册与桌面快捷方式生成。
