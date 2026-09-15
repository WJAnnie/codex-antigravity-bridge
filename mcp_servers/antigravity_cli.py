"""
Antigravity CLI (agy) Wrapper
Implements the standard `agy -p` / `agy --print` CLI interface,
backed by the 5-tier self-healing cascade engine (GPT-5.6-Sol / DeepSeek-V4 / GLM-5.3 / Gemini).
Compatible with call-agy, claude-code-agy-CLI-skill, and direct terminal usage.
"""

import sys
import os
import argparse
import asyncio
import time
import uuid
import logging

# 强制标准输入输出为 UTF-8 编码，防止 Windows 终端中文乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from antigravity_mcp import _execute_antigravity_core, log_event, _save_task_record, get_engine_name

# 彻底抑制底层的 RAW WS MSG 与上游警告噪音，保证控制台输出纯净 Markdown
def _silence_loggers():
    logging.root.setLevel(logging.ERROR)
    for h in logging.root.handlers:
        h.setLevel(logging.ERROR)
    for _logger_name in ["google", "google.antigravity", "websockets", "urllib3", "root", "asyncio"]:
        lg = logging.getLogger(_logger_name)
        lg.setLevel(logging.ERROR)
        for h in lg.handlers:
            h.setLevel(logging.ERROR)

_silence_loggers()


def parse_timeout(timeout_str: str) -> float:
    if not timeout_str:
        return 600.0
    timeout_str = timeout_str.strip().lower()
    try:
        if timeout_str.endswith("m") or timeout_str.endswith("m0s"):
            m = float(timeout_str.split("m")[0])
            return m * 60.0
        if timeout_str.endswith("s"):
            return float(timeout_str[:-1])
        return float(timeout_str)
    except Exception:
        return 600.0


async def run_cli(prompt: str, workspace: str, timeout_sec: float) -> int:
    task_id = f"cli-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    start_time = time.time()
    engine_name = get_engine_name()
    
    # Save initial task record for desktop widget display
    record = {
        "task_id": task_id,
        "task_type": "agy_cli",
        "status": "RUNNING",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_path": workspace,
        "prompt": prompt,
        "prompt_summary": prompt.replace("\n", " ").strip()[:60],
        "start_time": start_time,
        "report_file": os.path.join(workspace, ".antigravity_reports", f"{task_id}.md")
    }
    _save_task_record(record)
    log_event(f"[START] [CLI:{task_id}] 触发 agy CLI | 引擎: {engine_name} | 工作区: {workspace} | 任务: {record['prompt_summary']}")

    try:
        # Run with timeout
        result_text = await asyncio.wait_for(
            _execute_antigravity_core(prompt, workspace, task_id=task_id),
            timeout=timeout_sec
        )
        elapsed = time.time() - start_time
        
        # Save report
        os.makedirs(os.path.dirname(record["report_file"]), exist_ok=True)
        with open(record["report_file"], "w", encoding="utf-8") as rf:
            rf.write(f"# 🤖 Antigravity CLI Execution Result\n\n- **Task ID**: `{task_id}`\n- **Time**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n- **Elapsed**: {elapsed:.2f}s\n- **Engine**: {engine_name}\n\n---\n\n## 📝 Prompt\n\n{prompt}\n\n---\n\n## 📋 Output\n\n{result_text}\n")
        
        record["status"] = "COMPLETED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["return_chars"] = len(result_text)
        record["snippet"] = result_text[:500]
        _save_task_record(record)
        log_event(f"[DONE]  [CLI:{task_id}] 执行成功 | 耗时: {elapsed:.2f}s | 字符数: {len(result_text)}")

        # Output to stdout directly (Unicode safe)
        try:
            sys.stdout.write(result_text)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(result_text.encode(sys.stdout.encoding or "utf-8", errors="replace"))
        if not result_text.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
        return 0

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        err_msg = f"Task timed out after {timeout_sec:.0f}s"
        record["status"] = "FAILED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["error"] = err_msg
        _save_task_record(record)
        log_event(f"[TIMEOUT] [CLI:{task_id}] 执行超时 | 耗时: {elapsed:.2f}s")
        sys.stderr.write(f"Error: {err_msg}\n")
        return 1

    except Exception as e:
        elapsed = time.time() - start_time
        err_msg = str(e)
        record["status"] = "FAILED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["error"] = err_msg
        _save_task_record(record)
        log_event(f"[ERROR] [CLI:{task_id}] 执行失败 | 耗时: {elapsed:.2f}s | 异常: {err_msg}")
        sys.stderr.write(f"Error: {err_msg}\n")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Google Antigravity CLI (agy) - 5-Tier Resilient Engine",
        add_help=False
    )
    parser.add_argument("-p", "--print", dest="print_prompt", type=str, default=None,
                        help="Non-interactive mode: run prompt, print response, exit")
    parser.add_argument("--print-timeout", dest="timeout", type=str, default="10m",
                        help="Timeout for print mode (e.g. 5m, 10m, 300s)")
    parser.add_argument("--dangerously-skip-permissions", dest="skip_perm", action="store_true",
                        help="Auto-approve all tool calls (compatibility flag)")
    parser.add_argument("--add-dir", dest="add_dir", action="append", default=[],
                        help="Add directory to workspace")
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")
    parser.add_argument("positional_prompt", nargs="*", help="Positional prompt arguments")

    args, remaining = parser.parse_known_args()

    if args.help:
        parser.print_help()
        sys.exit(0)

    # Resolve prompt
    prompt = args.print_prompt
    if not prompt and args.positional_prompt:
        prompt = " ".join(args.positional_prompt)
    if not prompt and remaining:
        prompt = " ".join(remaining)

    if not prompt:
        if not sys.stdin.isatty():
            prompt = sys.stdin.read().strip()

    if not prompt:
        print("Google Antigravity CLI (agy) v2.5 - 5-Tier Resilient Engine")
        print("Usage: agy -p \"YOUR PROMPT HERE\" [--print-timeout 10m] [--add-dir /path]")
        sys.exit(1)

    workspace = os.getcwd()
    if args.add_dir:
        workspace = os.path.abspath(args.add_dir[0])

    timeout_sec = parse_timeout(args.timeout)
    code = asyncio.run(run_cli(prompt, workspace, timeout_sec))
    sys.exit(code)


if __name__ == "__main__":
    main()
