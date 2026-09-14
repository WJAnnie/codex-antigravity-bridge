---
name: codex-antigravity-bridge
description: Seamlessly bridge OpenAI Codex / Claude / Cursor with Google Antigravity expert subagents via FastMCP, supporting both sync calls and async long-running tasks (bypassing 300s client timeouts), with a floating real-time desktop monitor widget.
---

# Codex Antigravity Bridge

`codex-antigravity-bridge` 是一个将 **OpenAI Codex** 与 **Google Antigravity** 双向打通的协同 Skill 与工具网关。

它通过 **FastMCP** 协议对外暴露两大维度的工具矩阵：
1. **同步工具 (`ask_antigravity`, `antigravity_code_review`)**：适用于 3 分钟以内的快速问答、单文件微调与即时审查。
2. **异步长任务工具 (`ask_antigravity_async`, `antigravity_code_review_async`, `check_antigravity_task`, `list_antigravity_tasks`)**：适用于 10~60+ 分钟的全库探索、多模块深度重构与全量安全审查，**彻底解除 Codex 客户端 300 秒硬性超时限制**，任务完成后自动生成标准 Markdown 报告并持久化存储。

底层深度绑定 `LocalOpenAIAgentConfig` 桥接本地模型网关（默认采用高稳定的 `agentrouter/glm-5.3`），彻底规避云端 API Key 失效及 `reasoning_content` 思维链回传 400 异常。

配套提供现代暗色风格的 **桌面悬浮小组件（Desktop Mini-Widget）**，提供实时秒表、三色状态指示与历史折叠审计。

---

## 🌟 核心工具矩阵

| 工具名称 | 模式 | 典型耗时 | 适用场景 |
|---|---|---|---|
| `ask_antigravity` | 同步 | < 3 分钟 | 单文件代码探索、定位具体 Bug、简单模块设计 |
| `antigravity_code_review` | 同步 | < 3 分钟 | 1~2 个关键文件的快速代码安全与规范审查 |
| `ask_antigravity_async` | 异步 | **10~60+ 分钟** | 全工程架构调研、跨模块重构、复杂算法实现（**秒级返回任务 ID**） |
| `antigravity_code_review_async` | 异步 | **10~60+ 分钟** | 3 个以上文件、全量模块或庞大 PR 的深度审查（自动输出报告文件） |
| `check_antigravity_task` | 同步 | < 0.1 秒 | 查询后台任务当前状态、耗时、执行摘要及报告文件路径 |
| `list_antigravity_tasks` | 同步 | < 0.1 秒 | 列出最近 5 次后台任务的执行概览与状态矩阵 |

---

## 🛠️ 安装与部署

### 一键自动安装（推荐）

双击项目根目录下的 **`install.bat`**，或在 PowerShell 中执行：

```powershell
.\install.ps1
```

脚本将自动完成依赖安装、脚本拷贝与 `~/.codex/config.toml` 配置注册。

---

## 📖 异步长任务使用范例

### 1. 发起大型跨模块重构（异步）
在 Codex 中输入：
> *"请让 antigravity 异步重构整个投资分析模块，并把方案写进文档"*

Codex 触发 `ask_antigravity_async`，**0.5 秒内即刻收到确认**：
```markdown
🚀 【Antigravity 后台长任务已创建成功】
- 任务 ID: `ag-20260914-083015-a1b2`
- 报告生成路径: `E:\项目路径\.antigravity_reports\ag-20260914-083015-a1b2.md`
- 不受 300s 超时限制: 任务正在后台全速运转，桌面悬浮监控窗已启动秒表。
```

### 2. 查询任务状态
在 Codex 中输入：
> *"查一下刚才 antigravity 任务的进度"*

Codex 触发 `check_antigravity_task(task_id="ag-20260914-083015-a1b2")`：
- 若在执行中：返回已运行秒数与当前进度；
- 若已完成：返回总耗时、输出字符数与完整报告文件的路径。

---

## ⚙️ 环境变量配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `ANTIGRAVITY_BASE_URL` | `http://127.0.0.1:10100/v1` | 本地模型路由网关地址 |
| `ANTIGRAVITY_MODEL` | `agentrouter/glm-5.3` | 推理引擎（推荐 GLM-5.3，零 400 报错） |
| `ANTIGRAVITY_LOG_FILE` | `~/.codex/mcp_servers/antigravity.log` | 通信与审计日志路径 |
| `ANTIGRAVITY_WORKSPACE`| 当前工作目录 | 默认分析的工作区根路径 |
