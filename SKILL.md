---
name: codex-antigravity-bridge
description: Seamlessly bridge OpenAI Codex / Claude / Cursor with Google Antigravity expert subagents via MCP and LocalOpenAIAgentConfig, featuring a floating real-time desktop monitor widget.
---

# Codex Antigravity Bridge

`codex-antigravity-bridge` 是一个将 **OpenAI Codex** 与 **Google Antigravity** 双向打通的协同 Skill 与工具网关。

它通过 **FastMCP** 协议对外暴露 `ask_antigravity` 和 `antigravity_code_review` 两大标准工具，并在底层使用 `LocalOpenAIAgentConfig` 桥接本地模型网关（默认使用 `agentrouter/glm-5.3`），彻底规避云端 API Key 失效及 `reasoning_content` 思维链回传 400 异常，实现真正免 Key、低延迟、高可靠的深度推理与代码审查。

同时，配套提供了一个现代暗色风格的 **桌面悬浮小组件（Desktop Mini-Widget）**，在 AI 思考与多工具调用过程中提供实时秒表、三色状态指示与历史折叠审计。

---

## 🌟 核心功能

1. **MCP 桥梁 (`antigravity_mcp.py`)**：
   - `ask_antigravity(prompt, workspace_path, system_instructions)`：将复杂探索、跨模块重构、架构调研直接委托给 Antigravity 智能体。
   - `antigravity_code_review(files, instructions, workspace_path)`：多文件安全与质量代码审查，输出按严重等级分类的改进建议与 diff。
2. **桌面悬浮小组件 (`antigravity_widget.py`)**：
   - 无边框置顶、半透明暗黑极简设计，支持鼠标任意拖动。
   - 实时秒表走字（精确记录复杂多步推理耗时）。
   - 绿色（待命）、黄色（思考中）、红色（异常）三色状态指示灯。
   - 支持一键展开/折叠最近 5 次调用的耗时与返回字数明细。
3. **子角色协议 (`antigravity.toml` & `AGENTS.md`)**：
   - 支持 oh-my-codex 标准子角色定义，可在 Codex 中使用 `@antigravity` 直接委派。
   - 支持在工作区 `AGENTS.md` 中配置默认分流规则，自动化触发 Antigravity 专家。

---

## 🛠️ 安装与部署

### 方法一：一键自动安装（推荐）

双击项目根目录下的 **`install.bat`**，或在 PowerShell 中执行：

```powershell
.\install.ps1
```

脚本将自动：
- 校验并安装 Python 依赖（`google-antigravity`, `mcp`）。
- 将 MCP 服务与监控脚本安装至 `~/.codex/mcp_servers/`。
- 将子角色定义安装至 `~/.codex/agents/`。
- 将 MCP 服务注册至 `~/.codex/config.toml`。
- 在桌面创建【启动Antigravity监控窗.bat】快捷方式。

### 方法二：手动安装

1. **安装依赖**：
   ```bash
   pip install google-antigravity mcp
   ```

2. **复制文件**：
   - 将 `mcp_servers/antigravity_mcp.py` 放入 `~/.codex/mcp_servers/`
   - 将 `widget/antigravity_widget.py` 放入 `~/.codex/mcp_servers/`
   - 将 `agents/antigravity.toml` 放入 `~/.codex/agents/`

3. **配置 `~/.codex/config.toml`**：
   ```toml
   [mcp_servers.antigravity]
   command = "python"
   args = ["-u", "C:/Users/<你的用户名>/.codex/mcp_servers/antigravity_mcp.py"]
   ```

---

## 📖 使用指南

### 1. 启动桌面监控窗
双击桌面的 **`启动Antigravity监控窗.bat`**（或直接运行 `pythonw widget/antigravity_widget.py`）。
悬浮窗将静默驻留在屏幕右上角，随时等待 Codex 触发调用。

### 2. 在 Codex 中调用 Antigravity
在 Codex 对话中，你可以直接输入：
- *"请让 antigravity 深度阅读此项目架构并总结核心流向"*
- *"请委派 antigravity 审查 app/engine.py 和 risk.py 的并发安全性"*
- *"@antigravity 重构此模块并给出优化建议"*

Codex 会自动调用 MCP 工具，此时桌面监控窗会即时点亮黄灯并启动动态秒表，完成后绿灯常亮并展示耗时与输出字数。

---

## ⚙️ 环境变量与模型配置

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `ANTIGRAVITY_BASE_URL` | `http://127.0.0.1:10100/v1` | 本地模型路由网关地址 |
| `ANTIGRAVITY_MODEL` | `agentrouter/glm-5.3` | 推理引擎（推荐 GLM-5.3，完美支持多步工具链） |
| `ANTIGRAVITY_LOG_FILE` | `~/.codex/mcp_servers/antigravity.log` | 通信与审计日志路径 |
| `ANTIGRAVITY_WORKSPACE`| 当前工作目录 | 默认分析的工作区根路径 |
