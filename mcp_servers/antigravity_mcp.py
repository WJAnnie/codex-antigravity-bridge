"""
Antigravity MCP Server for OpenAI Codex / Claude / Cursor
Allows AI assistants (like OpenAI Codex) to delegate complex coding, refactoring, research, 
and code review tasks to Google Antigravity.
Configured with LocalOpenAIAgentConfig to bridge seamlessly to local model gateway (http://127.0.0.1:10100/v1).
Completely keyless and uses local agentrouter/glm-5.3 for reliable multi-turn tool calling.
"""

import sys
import asyncio
import os
import time
from datetime import datetime
from typing import List, Optional
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


def log_event(message: str) -> None:
    """写入运行日志（GB18030 兼容 Windows 终端与监控窗），便于实时跟踪与审计"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] {message}\n"
    try:
        with open(LOG_FILE, "a", encoding="gb18030", errors="replace") as f:
            f.write(log_line)
    except Exception as e:
        sys.stderr.write(f"[Log Error] {e}\n")


@mcp.tool()
async def ask_antigravity(
    prompt: str,
    workspace_path: Optional[str] = None,
    system_instructions: Optional[str] = None,
) -> str:
    """
    Delegate a complex coding, refactoring, or research task to Google Antigravity Agent.
    Use this when you need deep codebase exploration, multi-agent reasoning, complex refactoring,
    or a second opinion from Antigravity.

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

    try:
        response_chunks = []
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            async for token in response:
                response_chunks.append(token)

        elapsed = time.time() - start_time
        result_text = "".join(response_chunks).strip()
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
    Request a comprehensive multi-perspective code review from Google Antigravity for specific files.

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

    try:
        response_chunks = []
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            async for token in response:
                response_chunks.append(token)

        elapsed = time.time() - start_time
        result_text = "".join(response_chunks).strip()
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


if __name__ == "__main__":
    mcp.run()
