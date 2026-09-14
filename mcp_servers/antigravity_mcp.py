"""
Antigravity MCP Server for OpenAI Codex / Claude / Cursor
Allows AI assistants (like OpenAI Codex) to delegate complex coding, refactoring, research, 
and code review tasks to Google Antigravity.

Features:
- Synchronous tools (ask_antigravity, antigravity_code_review) for short queries (<300s).
- Asynchronous tools (ask_antigravity_async, antigravity_code_review_async) for long-running
  exploration, multi-file refactoring, and extensive reviews (10~60+ mins), completely 
  bypassing the client 300s timeout constraint.
- Task status inquiry (check_antigravity_task, list_antigravity_tasks) with auto-generated
  markdown reports saved directly in the project workspace.
- Configured with LocalOpenAIAgentConfig to bridge seamlessly to local model gateway (http://127.0.0.1:10100/v1).
- Keyless, reliable execution using local agentrouter/glm-5.3.
"""

import sys
import asyncio
import os
import time
import json
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP
from google.antigravity import Agent, LocalOpenAIAgentConfig, CapabilitiesConfig

# Initialize FastMCP server
mcp = FastMCP(
    "Antigravity",
    dependencies=["google-antigravity", "mcp"]
)

# Configuration with environment variable overrides
LOG_FILE = os.environ.get(
    "ANTIGRAVITY_LOG_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "antigravity.log")
)
BASE_URL = os.environ.get("ANTIGRAVITY_BASE_URL", "http://127.0.0.1:10100/v1")
DEFAULT_MODEL = os.environ.get("ANTIGRAVITY_MODEL", "agentrouter/glm-5.3")
TASKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tasks")
os.makedirs(TASKS_DIR, exist_ok=True)

# In-memory background tasks tracker
_background_tasks: Dict[str, asyncio.Task] = {}


def log_event(message: str) -> None:
    """写入运行日志（GB18030 兼容 Windows 终端与桌面监控窗），便于实时跟踪与审计"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"
    try:
        with open(LOG_FILE, "a", encoding="gb18030", errors="replace") as f:
            f.write(log_line)
    except Exception as e:
        sys.stderr.write(f"[Log Error] {e}\n")


def _get_task_file(task_id: str) -> str:
    return os.path.join(TASKS_DIR, f"{task_id}.json")


def _save_task_record(record: Dict[str, Any]) -> None:
    task_id = record["task_id"]
    try:
        with open(_get_task_file(task_id), "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)
    except Exception as e:
        sys.stderr.write(f"[Task Save Error] {e}\n")


def _load_task_record(task_id: str) -> Optional[Dict[str, Any]]:
    path = _get_task_file(task_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


async def _execute_antigravity_core(
    prompt: str,
    ws: str,
    system_instructions: Optional[str] = None
) -> str:
    """底层的 Antigravity 智能体调用逻辑"""
    sys_inst = system_instructions or (
        f"你是由 OpenAI Codex 调用的 Google Antigravity 高级专家智能体。\n"
        f"当前工作区路径为：{ws}。\n"
        f"请结合工作区文件和最佳实践，高质量执行用户委托的任务，并输出清晰详尽的中文执行汇报与结果。"
    )

    workspaces = [ws] if os.path.exists(ws) else None

    config = LocalOpenAIAgentConfig(
        base_url=BASE_URL,
        model=DEFAULT_MODEL,
        system_instructions=sys_inst,
        capabilities=CapabilitiesConfig(
            file_reads=True,
            file_writes=True,
            command_execution=True,
            subagents=True,
            mcp=True,
        ),
        workspaces=workspaces,
    )

    response_chunks = []
    async with Agent(config) as agent:
        response = await agent.chat(prompt)
        async for token in response:
            response_chunks.append(token)

    return "".join(response_chunks).strip()


async def _run_async_worker(
    task_id: str,
    task_type: str,
    prompt: str,
    ws: str,
    report_file: str,
    system_instructions: Optional[str] = None
) -> None:
    """后台异步任务 Worker"""
    start_time = time.time()
    record = _load_task_record(task_id) or {}
    record["status"] = "RUNNING"
    record["start_time"] = start_time
    _save_task_record(record)

    prompt_summary = prompt.replace("\n", " ").strip()
    if len(prompt_summary) > 50:
        prompt_summary = prompt_summary[:50] + "..."

    log_event(f"[START] [ASYNC:{task_id}] 触发后台任务: {task_type} | 引擎: {DEFAULT_MODEL} | 工作区: {ws} | 任务: {prompt_summary}")

    try:
        result_text = await _execute_antigravity_core(prompt, ws, system_instructions)
        elapsed = time.time() - start_time
        
        # 写入完整的 Markdown 报告文件
        os.makedirs(os.path.dirname(os.path.abspath(report_file)), exist_ok=True)
        report_content = (
            f"# 🤖 Google Antigravity 任务执行报告\n\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **任务类型**: `{task_type}`\n"
            f"- **执行耗时**: {elapsed:.2f} 秒 (约 {elapsed/60:.1f} 分钟)\n"
            f"- **完成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- **工作区**: `{ws}`\n"
            f"- **模型引擎**: `{DEFAULT_MODEL}`\n\n"
            f"---\n\n"
            f"## 📋 任务描述\n\n"
            f"{prompt}\n\n"
            f"---\n\n"
            f"## 📝 执行成果汇报\n\n"
            f"{result_text}\n"
        )
        with open(report_file, "w", encoding="utf-8") as rf:
            rf.write(report_content)

        record["status"] = "COMPLETED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["return_chars"] = len(result_text)
        record["report_file"] = report_file
        record["snippet"] = result_text[:400] + ("..." if len(result_text) > 400 else "")
        _save_task_record(record)

        log_event(f"[DONE]  [ASYNC:{task_id}] 执行成功 | 耗时: {elapsed:.2f}s | 字符数: {len(result_text)} | 报告: {os.path.basename(report_file)}")

    except Exception as e:
        elapsed = time.time() - start_time
        record["status"] = "FAILED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["error"] = str(e)
        _save_task_record(record)
        log_event(f"[ERROR] [ASYNC:{task_id}] 执行失败 | 耗时: {elapsed:.2f}s | 异常: {str(e)}")


# ---------------------------------------------------------------------------
# 同步工具 (适用于短任务 < 3 分钟)
# ---------------------------------------------------------------------------

@mcp.tool()
async def ask_antigravity(
    prompt: str,
    workspace_path: Optional[str] = None,
    system_instructions: Optional[str] = None,
) -> str:
    """
    Delegate a fast coding, refactoring, or research task to Google Antigravity Agent (Synchronous).
    NOTE: If the task is large, involves 3+ files, or is expected to take over 3 minutes,
    please use `ask_antigravity_async` instead to avoid Codex client 300s timeout.

    :param prompt: The specific task, questions, or instructions for Antigravity.
    :param workspace_path: Root directory of the workspace to operate on.
    :param system_instructions: Optional custom persona or system guidance for Antigravity.
    :return: The full response and findings from Antigravity.
    """
    start_time = time.time()
    ws = workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd())
    
    prompt_summary = prompt.replace("\n", " ").strip()
    if len(prompt_summary) > 60:
        prompt_summary = prompt_summary[:60] + "..."

    log_event(f"[START] 触发工具: ask_antigravity | 引擎: {DEFAULT_MODEL} | 工作区: {ws} | 任务: {prompt_summary}")

    try:
        result_text = await _execute_antigravity_core(prompt, ws, system_instructions)
        elapsed = time.time() - start_time
        log_event(f"[DONE]  执行成功 | 引擎: {DEFAULT_MODEL} | 耗时: {elapsed:.2f}s | 返回字符数: {len(result_text)}")

        header = (
            f"> 🤖 **【Google Antigravity 专家子智能体执行汇报】**\n"
            f"> ⏱️ **执行耗时**: {elapsed:.2f}s | 📁 **工作区**: `{ws}` | 🧠 **引擎**: `{DEFAULT_MODEL}`\n\n"
        )
        return header + result_text

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"[Antigravity Error] 调用执行失败: {str(e)}"
        log_event(f"[ERROR] 执行失败 | 引擎: {DEFAULT_MODEL} | 耗时: {elapsed:.2f}s | 异常: {str(e)}")
        return error_msg


@mcp.tool()
async def antigravity_code_review(
    files: List[str],
    instructions: str = "审查代码安全性、异常处理、性能瓶颈与架构合理性，并给出具体的重构建议。",
    workspace_path: Optional[str] = None,
) -> str:
    """
    Request a quick multi-perspective code review from Google Antigravity for small sets of files (Synchronous).
    NOTE: If reviewing more than 3 files or complex architectures, use `antigravity_code_review_async`
    to avoid the client 300s timeout.

    :param files: List of relative or absolute file paths to be reviewed.
    :param instructions: Specific focus areas or guidelines for the review.
    :param workspace_path: Workspace directory path.
    :return: Detailed code review report with findings and suggested diffs/improvements.
    """
    start_time = time.time()
    ws = workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd())
    
    log_event(f"[START] 触发工具: antigravity_code_review | 引擎: {DEFAULT_MODEL} | 文件数: {len(files)} | 列表: {', '.join(files[:3])}{'...' if len(files) > 3 else ''}")

    file_list_str = "\n".join(f"- {f}" for f in files)
    prompt = (
        f"请对以下文件进行深度代码审查：\n"
        f"{file_list_str}\n\n"
        f"审查重点与要求：\n"
        f"{instructions}\n\n"
        f"请按照问题严重等级（严重/中等/建议）结构化输出审查报告，并提供具体的代码改进建议。"
    )

    sys_inst = (
        f"你是由 OpenAI Codex 调用的 Google Antigravity 首席代码审查专家。\n"
        f"当前工作区路径为：{ws}。\n"
        f"请对用户指定的代码进行深入的质量与安全审计，并提供具体的重构与优化方案。"
    )

    try:
        result_text = await _execute_antigravity_core(prompt, ws, sys_inst)
        elapsed = time.time() - start_time
        log_event(f"[DONE]  审查成功 | 引擎: {DEFAULT_MODEL} | 耗时: {elapsed:.2f}s | 返回字符数: {len(result_text)}")

        header = (
            f"> 🔍 **【Google Antigravity 深度代码审查报告】**\n"
            f"> ⏱️ **审查耗时**: {elapsed:.2f}s | 📄 **审查文件数**: {len(files)} 个 | 🧠 **引擎**: `{DEFAULT_MODEL}`\n\n"
        )
        return header + result_text

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"[Antigravity Error] 代码审查执行失败: {str(e)}"
        log_event(f"[ERROR] 审查失败 | 引擎: {DEFAULT_MODEL} | 耗时: {elapsed:.2f}s | 异常: {str(e)}")
        return error_msg


# ---------------------------------------------------------------------------
# 异步长任务工具 (突破 300s 限制，支持 10~60+ 分钟长任务)
# ---------------------------------------------------------------------------

@mcp.tool()
async def ask_antigravity_async(
    prompt: str,
    workspace_path: Optional[str] = None,
    report_file: Optional[str] = None,
    system_instructions: Optional[str] = None,
) -> str:
    """
    Launch a long-running coding, exploration, or refactoring task in the background (Asynchronous).
    Returns immediately (< 0.5s) with a task ID, completely immune to Codex 300s timeout!
    Antigravity will run autonomously in the background and write a comprehensive markdown report.

    :param prompt: Detailed instructions for the task.
    :param workspace_path: Root directory of the workspace.
    :param report_file: Path to save the final markdown report. Defaults to `<workspace>/.antigravity_reports/<task_id>.md`.
    :param system_instructions: Optional custom persona or system guidance.
    :return: Immediate confirmation with task_id and tracking instructions.
    """
    ws = workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd())
    task_id = f"ag-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    
    if not report_file:
        report_file = os.path.join(ws, ".antigravity_reports", f"{task_id}.md")

    # Record initial task state
    record = {
        "task_id": task_id,
        "task_type": "ask_antigravity",
        "status": "PENDING",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_path": ws,
        "report_file": report_file,
        "prompt": prompt,
        "prompt_summary": prompt.replace("\n", " ").strip()[:80],
    }
    _save_task_record(record)

    # Spawn background task
    bg_task = asyncio.create_task(
        _run_async_worker(task_id, "ask_antigravity", prompt, ws, report_file, system_instructions)
    )
    _background_tasks[task_id] = bg_task

    return (
        f"🚀 **【Antigravity 后台长任务已创建成功】**\n\n"
        f"- **任务 ID**: `{task_id}`\n"
        f"- **工作区**: `{ws}`\n"
        f"- **报告生成路径**: `{report_file}`\n"
        f"- **不受 300s 超时限制**: 任务正在后台全速运转，桌面悬浮监控窗已启动秒表。\n\n"
        f"💡 **后续操作指南**：\n"
        f"1. 你可以随时调用 `check_antigravity_task(task_id=\"{task_id}\")` 查看当前进度与耗时。\n"
        f"2. 任务完成后，可直接查看或读取 `{report_file}` 获取完整的执行结论与代码建议。"
    )


@mcp.tool()
async def antigravity_code_review_async(
    files: List[str],
    instructions: str = "审查代码安全性、异常处理、性能瓶颈与架构合理性，并给出具体的重构建议。",
    workspace_path: Optional[str] = None,
    report_file: Optional[str] = None,
) -> str:
    """
    Launch a comprehensive multi-file code review in the background (Asynchronous).
    Returns immediately (< 0.5s) with a task ID. Ideal for reviewing 5~30+ files or entire architectures.

    :param files: List of file paths to review.
    :param instructions: Review guidelines and focus areas.
    :param workspace_path: Root directory of the workspace.
    :param report_file: Path to save the final review report.
    :return: Immediate confirmation with task_id and tracking instructions.
    """
    ws = workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd())
    task_id = f"cr-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"

    if not report_file:
        report_file = os.path.join(ws, ".antigravity_reports", f"{task_id}.md")

    file_list_str = "\n".join(f"- {f}" for f in files)
    prompt = (
        f"请对以下文件进行深度代码审查：\n"
        f"{file_list_str}\n\n"
        f"审查重点与要求：\n"
        f"{instructions}\n\n"
        f"请按照问题严重等级（严重/中等/建议）结构化输出审查报告，并提供具体的代码改进建议与重构方案。"
    )

    sys_inst = (
        f"你是由 OpenAI Codex 调用的 Google Antigravity 首席代码审查专家。\n"
        f"当前工作区路径为：{ws}。\n"
        f"请对用户指定的代码进行深入的质量与安全审计，并提供具体的重构与优化方案。"
    )

    record = {
        "task_id": task_id,
        "task_type": "antigravity_code_review",
        "status": "PENDING",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_path": ws,
        "report_file": report_file,
        "files": files,
        "prompt": prompt,
        "prompt_summary": f"深度审查 {len(files)} 个文件",
    }
    _save_task_record(record)

    bg_task = asyncio.create_task(
        _run_async_worker(task_id, "antigravity_code_review", prompt, ws, report_file, sys_inst)
    )
    _background_tasks[task_id] = bg_task

    return (
        f"🔍 **【Antigravity 深度代码审查长任务已创建】**\n\n"
        f"- **任务 ID**: `{task_id}`\n"
        f"- **审查文件数**: {len(files)} 个文件\n"
        f"- **报告生成路径**: `{report_file}`\n"
        f"- **不受 300s 超时限制**: 任务正在后台深度逐行审计中，桌面小组件已同步开启计时。\n\n"
        f"💡 可随时通过 `check_antigravity_task(task_id=\"{task_id}\")` 获取审查进度。"
    )


@mcp.tool()
async def check_antigravity_task(task_id: str) -> str:
    """
    Check the current status, progress, and results of a background Antigravity task.

    :param task_id: The unique task ID returned by `ask_antigravity_async` or `antigravity_code_review_async`.
    :return: Current status, elapsed time, and report file location if finished.
    """
    record = _load_task_record(task_id)
    if not record:
        return f"❌ 未找到任务 ID 为 `{task_id}` 的记录。请核实 ID 是否正确。"

    status = record.get("status", "UNKNOWN")
    created_at = record.get("created_at", "未知")
    report_file = record.get("report_file", "")
    summary = record.get("prompt_summary", "")

    if status == "RUNNING" or status == "PENDING":
        start_time = record.get("start_time", time.time())
        running_sec = time.time() - start_time
        return (
            f"⏳ **【任务执行中】**\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **任务内容**: {summary}\n"
            f"- **开始时间**: {created_at}\n"
            f"- **当前已运行**: {running_sec:.1f} 秒 (约 {running_sec/60:.1f} 分钟)\n"
            f"- **目标报告**: `{report_file}`\n"
            f"- **状态**: Antigravity 智能体正在后台深入处理，请耐心等候。"
        )

    elif status == "COMPLETED":
        elapsed = record.get("elapsed_sec", 0.0)
        chars = record.get("return_chars", 0)
        snippet = record.get("snippet", "")
        return (
            f"✅ **【任务执行完毕】**\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **总耗时**: {elapsed:.2f} 秒 (约 {elapsed/60:.1f} 分钟)\n"
            f"- **返回字符数**: {chars} 字\n"
            f"- **完整报告路径**: `{report_file}`\n\n"
            f"📄 **成果摘要**：\n"
            f"{snippet}\n\n"
            f"💡 你可以直接读取 `{report_file}` 获取完整的分析与代码建议。"
        )

    elif status == "FAILED":
        elapsed = record.get("elapsed_sec", 0.0)
        error = record.get("error", "未知错误")
        return (
            f"❌ **【任务执行失败】**\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **耗时**: {elapsed:.2f} 秒\n"
            f"- **异常原因**: `{error}`\n"
            f"- 请检查本地网关连接或日志文件了解详情。"
        )

    return f"ℹ️ **任务状态**: `{status}`"


@mcp.tool()
async def list_antigravity_tasks(limit: int = 5) -> str:
    """
    List recent background Antigravity tasks and their execution status.

    :param limit: Maximum number of recent tasks to return. Defaults to 5.
    :return: Summary table of recent tasks.
    """
    if not os.path.exists(TASKS_DIR):
        return "暂无后台任务记录。"

    files = [os.path.join(TASKS_DIR, f) for f in os.listdir(TASKS_DIR) if f.endswith(".json")]
    if not files:
        return "暂无后台任务记录。"

    # Sort by mtime desc
    files.sort(key=os.path.getmtime, reverse=True)
    recent_files = files[:limit]

    lines = [
        "### 📋 最近 Antigravity 任务概览",
        "| 任务 ID | 类型 | 状态 | 耗时 | 摘要 |",
        "|---|---|---|---|---|"
    ]

    for pf in recent_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                rec = json.load(f)
            tid = rec.get("task_id", "")
            ttype = rec.get("task_type", "")
            st = rec.get("status", "")
            el = f"{rec.get('elapsed_sec', 0):.1f}s" if "elapsed_sec" in rec else "-"
            sm = rec.get("prompt_summary", "")[:25]
            status_icon = "⏳" if st in ("RUNNING", "PENDING") else ("✅" if st == "COMPLETED" else "❌")
            lines.append(f"| `{tid}` | {ttype} | {status_icon} {st} | {el} | {sm} |")
        except Exception:
            continue

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
