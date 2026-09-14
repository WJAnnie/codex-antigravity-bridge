# 🚀 Codex Antigravity Bridge

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg" alt="Python" />
  <img src="https://img.shields.io/badge/Protocol-FastMCP-orange.svg" alt="MCP" />
  <img src="https://img.shields.io/badge/Platform-Windows-lightgrey.svg" alt="Platform" />
  <img src="https://img.shields.io/badge/Async%20Mode-Supported-blueviolet.svg" alt="Async" />
  <img src="https://img.shields.io/badge/Status-Production%20Ready-success.svg" alt="Status" />
</p>

> **让 OpenAI Codex 无缝调用 Google Antigravity 高级多智能体进行深度代码探索与代码审查，支持“同步即时调用”与“异步长任务（突破 300s 超时限制）”双模式，配备原生桌面悬浮监控小组件。**

---

## 💡 项目背景与解决的痛点

在实际落地 OpenAI Codex 与 Google Antigravity 协同开发时，开发者通常会遭遇三大棘手问题：
1. **Google Gemini 云端 API 受限**：缺少商业 Key 或受地理策略网络限制。
2. **Thinking 模式的 `reasoning_content` 400 校验异常**：部分模型网关在多轮工具链中未回传思维链，导致 API 直接报错中断。
3. **💥 Codex 客户端 300 秒硬性超时限制（`timed out awaiting tools/call after 300s`）**：
   - 当 Antigravity 自主对几十个代码文件进行深度探索、多步重构时，耗时往往需要 10~30+ 分钟。
   - Codex 客户端对任意单次 MCP 工具调用设有 300 秒（5 分钟）硬性截止时间，超时即单方面掐断连接！

**Codex Antigravity Bridge v2.0** 全面攻克上述难题：
- ⚡ **双模式工具体系**：
  - **同步模式**：小任务、单文件审查秒级即时回复。
  - **异步长任务模式**：大重构、全库审查 **< 0.5s 立即返回任务 ID**，Antigravity 后台自主运行，结果自动生成持久化 Markdown 报告，完全突破 300s 限制！
- 🛡️ **免 Key 本地模型网关（LocalOpenAIAgentConfig）**：默认固化高稳定性 `agentrouter/glm-5.3`，实测 40+ 步复杂任务 100% 成功。
- 🖥️ **暗黑悬浮监控小组件**：原生 Tkinter 无边框置顶卡片，支持秒表走字、三色状态指示、历史折叠审计与异步长任务联动。

---

## 🏗️ 异步长任务架构图

```mermaid
flowchart TD
    subgraph Client ["💻 OpenAI Codex 客户端"]
        User["开发者"] --> Codex["Codex 主控 Agent"]
        Codex -->|1. 触发异步长任务\nask_antigravity_async| MCP["FastMCP 服务端"]
        MCP -->|2. 秒级返回 (<0.5s)\ntask_id + 报告路径| Codex
        Codex -->|3. 立即汇报接收| User
        Codex -.->|4. 后续按需查询\ncheck_antigravity_task| MCP
    end

    subgraph Background ["⚙️ 后台自主执行系统"]
        MCP -->|5. 创建后台协程| Worker["Async Worker"]
        Worker -->|6. 状态日志 [START]| Log[("antigravity.log")]
        Worker -->|7. 自主代码探索与重构| AGY["Google Antigravity Agent"]
        AGY <-->|8. 推理链| Gateway["本地网关 (GLM-5.3)"]
        Worker -->|9. 写入独立报告文件| Report[("📄 .antigravity_reports/<task_id>.md")]
        Worker -->|10. 状态日志 [DONE]| Log
    end

    subgraph Monitor ["🎨 桌面状态卡片"]
        Log -.->|实时轮询| Widget["悬浮监控窗\n(动态秒表/三色灯)"]
    end
```

---

## 🛠️ 工具矩阵列表

| 工具名 | 模式 | 说明 | 适用场景 |
|---|---|---|---|
| `ask_antigravity` | 同步 | 同步等待 Antigravity 执行完成 | 单文件分析、简单设计、即时提问（< 3 分钟） |
| `antigravity_code_review` | 同步 | 审查 1~2 个指定文件代码质量 | 小模块代码检查、单函数审查（< 3 分钟） |
| **`ask_antigravity_async`** | **异步** | **立即返回 `task_id`，后台自主执行并保存报告** | **跨文件重构、全库探索、复杂算法（10~60+ 分钟）** |
| **`antigravity_code_review_async`** | **异步** | **立即返回 `task_id`，深度多文件代码质量审查** | **3 个以上文件、全量模块或庞大 PR 审查** |
| **`check_antigravity_task`** | **同步** | **毫秒级查询指定任务的当前状态与进度** | 查看耗时、提取摘要、获取报告路径 |
| **`list_antigravity_tasks`** | **同步** | **列出最近 5 次后台任务的执行概览** | 全局历史任务追踪与状态审计 |

---

## 🚀 快速上手

### 1. 一键自动安装

双击运行 **`install.bat`**，或在 PowerShell 中执行：

```powershell
.\install.ps1
```

> 自动完成依赖安装、脚本拷贝与 `~/.codex/config.toml` 配置注册。

### 2. 启动悬浮监控

双击桌面的 **【启动Antigravity监控窗.bat】**，悬浮小卡片常驻屏幕右上角。

### 3. 在 Codex 中使用

- **对于即时短任务**：
  > *"请让 antigravity 看看这个函数的正则表达式写得对不对"*
- **对于大型耗时任务（推荐异步）**：
  > *"请委派 antigravity 异步审查整个 investment-assistant 项目，重点看数据流异常处理与锁竞争"*

Codex 将调用 `ask_antigravity_async`，秒级返回任务 ID。桌面悬浮窗自动进入秒表计时，执行完成后自动生成专属 Markdown 报告！

---

## ⚙️ 环境变量与配置

| 环境变量 | 默认值 | 作用说明 |
|---|---|---|
| `ANTIGRAVITY_BASE_URL` | `http://127.0.0.1:10100/v1` | 本地模型路由网关地址 |
| `ANTIGRAVITY_MODEL` | `agentrouter/glm-5.3` | 推理模型（实测 GLM-5.3 稳定性最佳） |
| `ANTIGRAVITY_LOG_FILE` | `~/.codex/mcp_servers/antigravity.log` | 桥接通信日志文件路径 |
| `ANTIGRAVITY_WORKSPACE` | 当前执行目录 | Antigravity 默认读取的工作区根路径 |

---

## 📄 License

本项目采用 [MIT License](LICENSE) 开源。
