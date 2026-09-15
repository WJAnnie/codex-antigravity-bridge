"""
Google Antigravity Official Headless CLI (agy)
Native CLI runner backed by the official Antigravity engine (Gemini 3.8 Flash).
Authenticates via official Google Antigravity account (OAuth / ~/.gemini/oauth_creds.json).
Zero external API key quota constraints. Full tool execution capabilities.
Features automatic Language Server endpoint discovery for standalone shells & Codex subagents.
"""

import sys
import os
import re
import shutil
import argparse
import asyncio
import time
import json
import uuid
import subprocess
import urllib.request

# 强制标准输入输出为 UTF-8 编码，防止 Windows 终端中文乱码
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Add current directory to path for widget logging & task records
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from antigravity_mcp import log_event, _save_task_record
except Exception:
    def log_event(msg: str):
        pass
    def _save_task_record(record: dict):
        pass

LS_BINARY = r"C:\Users\Administrator\AppData\Local\Programs\Antigravity\resources\bin\language_server.exe"
AGENTAPI_BAT = os.path.expanduser(r"~/.gemini/antigravity/bin/agentapi.bat")
BRAIN_DIR = os.path.expanduser(r"~/.gemini/antigravity/brain")


def discover_antigravity_env() -> dict[str, str]:
    """Auto-discovers running Antigravity Language Server address & CSRF token if not in env."""
    env = dict(os.environ)
    if env.get("ANTIGRAVITY_LS_ADDRESS") and env.get("ANTIGRAVITY_CSRF_TOKEN"):
        return env

    try:
        # Find language_server.exe process
        ps_cmd = "Get-CimInstance Win32_Process -Filter \"Name = 'language_server.exe'\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        if not res.stdout.strip():
            return env

        data = json.loads(res.stdout)
        if isinstance(data, list):
            data = data[0]

        pid = data.get("ProcessId")
        cmdline = data.get("CommandLine", "")
        csrf_match = re.search(r'--csrf_token\s+([a-f0-9\-]+)', cmdline)
        if not csrf_match:
            return env
        csrf = csrf_match.group(1)

        # Query listening ports
        port_cmd = f"Get-NetTCPConnection -OwningProcess {pid} -State Listen | Select-Object -ExpandProperty LocalPort"
        res_port = subprocess.run(["powershell", "-NoProfile", "-Command", port_cmd], capture_output=True, text=True)
        ports = [int(p.strip()) for p in res_port.stdout.strip().splitlines() if p.strip().isdigit()]

        http_port = None
        for port in ports:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"x-csrf-token": csrf})
                with urllib.request.urlopen(req, timeout=1) as resp:
                    if resp.status == 200:
                        http_port = port
                        break
            except Exception:
                pass

        if http_port and csrf:
            env["ANTIGRAVITY_LS_ADDRESS"] = f"localhost:{http_port}"
            env["ANTIGRAVITY_CSRF_TOKEN"] = csrf
    except Exception:
        pass

    return env


def get_agentapi_cmd() -> list[str]:
    """Locate the official Antigravity agentapi binary/script."""
    if os.path.exists(LS_BINARY):
        return [LS_BINARY, "agentapi"]
    if os.path.exists(AGENTAPI_BAT):
        return [AGENTAPI_BAT]
    which_agentapi = shutil.which("agentapi")
    if which_agentapi:
        return [which_agentapi]
    return [LS_BINARY, "agentapi"]


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


async def run_official_headless(prompt: str, workspace: str, model: str, timeout_sec: float, task_id: str) -> str:
    """
    Spawns an official Antigravity conversation in headless mode using Gemini 3.8 Flash,
    streams tool events to the desktop widget, and returns the final result.
    """
    # Prepend explicit workspace anchor so Antigravity agent immediately resolves relative paths
    if workspace and os.path.exists(workspace):
        full_prompt = f"【执行工作区根目录绝对路径】：{workspace}\n所有相对文件路径与测试命令均严格在此工作区下执行。\n\n{prompt}"
    else:
        full_prompt = prompt

    cmd_prefix = get_agentapi_cmd()
    launch_cmd = cmd_prefix + ["new-conversation", f"--model={model}", full_prompt]
    run_env = discover_antigravity_env()

    log_event(f"[START] [CLI:{task_id}] 启动官方 Antigravity Headless 引擎 (模型: {model}) | 工作区: {workspace}")

    # Run agentapi new-conversation in the target workspace directory with auto-discovered environment
    proc = await asyncio.to_thread(
        subprocess.run,
        launch_cmd,
        cwd=workspace,
        env=run_env,
        capture_output=True,
        text=True,
        encoding="utf-8"
    )

    if proc.returncode != 0:
        err_detail = proc.stderr.strip() or proc.stdout.strip()
        raise RuntimeError(f"agentapi new-conversation failed (code {proc.returncode}): {err_detail}")

    try:
        data = json.loads(proc.stdout)
        cid = data["response"]["newConversation"]["conversationId"]
    except Exception as e:
        raise RuntimeError(f"Failed to parse newConversation response: {proc.stdout} (err: {e})")

    log_path = os.path.join(BRAIN_DIR, cid, ".system_generated", "logs", "transcript.jsonl")
    log_event(f"[TRACK] [CLI:{task_id}] 会话已创建: {cid[:8]}... | 跟踪转录日志")

    start_time = time.time()
    last_processed_idx = 0
    final_output = ""
    seen_tools = set()

    # Poll transcript until completion or timeout
    while time.time() - start_time < timeout_sec:
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                lines = []

            if len(lines) > last_processed_idx:
                for idx in range(last_processed_idx, len(lines)):
                    try:
                        step = json.loads(lines[idx])
                        stype = step.get("type")
                        status = step.get("status")
                        tools = step.get("tool_calls", [])
                        content = step.get("content", "")

                        if tools:
                            for t in tools:
                                tname = t.get("name", "tool")
                                if tname not in seen_tools:
                                    seen_tools.add(tname)
                                    log_event(f"[TOOL]  [CLI:{task_id}] 执行工具: {tname}")
                        elif content and stype == "PLANNER_RESPONSE" and status == "DONE":
                            final_output = content
                    except Exception:
                        pass
                last_processed_idx = len(lines)

                # Check if last step indicates turn completion
                if lines:
                    try:
                        last_step = json.loads(lines[-1])
                        if (last_step.get("type") == "PLANNER_RESPONSE"
                            and last_step.get("status") == "DONE"
                            and last_step.get("content")
                            and not last_step.get("tool_calls")):
                            # Let it stabilize for 0.5s
                            await asyncio.sleep(0.5)
                            final_output = last_step.get("content", "").strip()
                            return final_output
                    except Exception:
                        pass

        await asyncio.sleep(0.8)

    if final_output:
        return final_output
    raise asyncio.TimeoutError(f"Antigravity headless execution timed out after {timeout_sec:.0f}s")


async def run_cli(prompt: str, workspace: str, model: str, timeout_sec: float) -> int:
    task_id = f"cli-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    start_time = time.time()

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
        "model": model,
        "report_file": os.path.join(workspace, ".antigravity_reports", f"{task_id}.md")
    }
    _save_task_record(record)

    try:
        result_text = await run_official_headless(
            prompt=prompt,
            workspace=workspace,
            model=model,
            timeout_sec=timeout_sec,
            task_id=task_id
        )
        elapsed = time.time() - start_time

        # Save markdown report
        try:
            os.makedirs(os.path.dirname(record["report_file"]), exist_ok=True)
            with open(record["report_file"], "w", encoding="utf-8") as rf:
                rf.write(f"# 🤖 Antigravity Official CLI Execution Result\n\n"
                         f"- **Task ID**: `{task_id}`\n"
                         f"- **Time**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                         f"- **Elapsed**: {elapsed:.2f}s\n"
                         f"- **Engine**: Google Antigravity Headless (Model: `{model}`)\n"
                         f"- **Workspace**: `{workspace}`\n\n---\n\n"
                         f"## 📝 Prompt\n\n{prompt}\n\n---\n\n"
                         f"## 📋 Output\n\n{result_text}\n")
        except Exception:
            pass

        record["status"] = "COMPLETED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["return_chars"] = len(result_text)
        record["snippet"] = result_text[:500]
        _save_task_record(record)
        log_event(f"[DONE]  [CLI:{task_id}] 官方 CLI 执行成功 | 耗时: {elapsed:.2f}s | 返回字符数: {len(result_text)}")

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
        log_event(f"[ERROR] [CLI:{task_id}] 执行异常 | 耗时: {elapsed:.2f}s | 异常: {err_msg}")
        sys.stderr.write(f"Error: {err_msg}\n")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Google Antigravity Official Headless CLI (agy) - Gemini 3.8 Flash",
        add_help=False
    )
    parser.add_argument("-p", "--print", dest="print_prompt", type=str, default=None,
                        help="Non-interactive mode: run prompt, print response, exit")
    parser.add_argument("--print-timeout", dest="timeout", type=str, default="10m",
                        help="Timeout for print mode (e.g. 5m, 10m, 300s)")
    parser.add_argument("--model", dest="model", type=str, default="flash",
                        help="Antigravity model tier: flash (Gemini 3.8 Flash), pro, or flash_lite")
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
        print("Google Antigravity Official Headless CLI (agy) v3.0 - Gemini 3.8 Flash")
        print("Usage: agy -p \"YOUR PROMPT HERE\" [--print-timeout 10m] [--model flash] [--add-dir /path]")
        sys.exit(1)

    workspace = os.getcwd()
    if args.add_dir:
        workspace = os.path.abspath(args.add_dir[0])

    timeout_sec = parse_timeout(args.timeout)
    code = asyncio.run(run_cli(prompt, workspace, args.model, timeout_sec))
    sys.exit(code)


if __name__ == "__main__":
    main()
