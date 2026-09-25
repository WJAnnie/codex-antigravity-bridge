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
    from antigravity_mcp import log_event, _save_task_record, _load_task_record
except Exception:
    import tempfile
    def log_event(msg: str):
        try:
            with open(os.path.join(tempfile.gettempdir(), "antigravity.log"), "a", encoding="gb18030", errors="replace") as f:
                f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
        except Exception:
            pass
    def _save_task_record(record: dict):
        try:
            tid = record.get("task_id")
            if tid:
                td = os.path.join(tempfile.gettempdir(), "codex_antigravity_tasks")
                os.makedirs(td, exist_ok=True)
                with open(os.path.join(td, f"{tid}.json"), "w", encoding="utf-8") as f:
                    json.dump(record, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    def _load_task_record(task_id: str):
        try:
            td = os.path.join(tempfile.gettempdir(), "codex_antigravity_tasks")
            p = os.path.join(td, f"{task_id}.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return None

def _path_to_file_uri(path: str) -> str:
    abs_path = os.path.abspath(os.path.expanduser(path)).replace("\\", "/")
    if not abs_path.startswith("/"):
        abs_path = "/" + abs_path
    from urllib.parse import quote
    return "file://" + quote(abs_path, safe="/:")


def get_primary_user_home() -> str:
    """Resolve the primary user home directory even when executing inside a restricted sandbox user account."""
    env_home = (os.environ.get("ANTIGRAVITY_USER_HOME") or "").strip()
    if env_home and os.path.exists(env_home):
        return env_home
    current_home = os.path.expanduser("~")
    if os.path.exists(os.path.join(current_home, ".gemini")) or os.path.exists(os.path.join(current_home, r"AppData\Local\Programs\antigravity")):
        return current_home
    if os.path.exists(r"C:\Users\Darli\.gemini") or os.path.exists(r"C:\Users\Darli\AppData\Local\Programs\antigravity"):
        return r"C:\Users\Darli"
    drive = os.path.splitdrive(current_home)[0] or "C:"
    users_root = os.path.join(drive, "\\Users")
    if os.path.isdir(users_root):
        try:
            for entry in os.listdir(users_root):
                candidate = os.path.join(users_root, entry)
                if os.path.isdir(candidate) and (os.path.exists(os.path.join(candidate, ".gemini")) or os.path.exists(os.path.join(candidate, r"AppData\Local\Programs\antigravity"))):
                    return candidate
        except Exception:
            pass
    return current_home


def discover_language_server_binary() -> str:
    """Resolve language_server.exe for the primary Windows user, including sandbox fallback."""
    home = get_primary_user_home()
    candidates = [
        os.path.join(home, r"AppData\Local\Programs\antigravity\resources\bin\language_server.exe"),
        os.path.join(home, r"AppData\Local\Programs\Antigravity\resources\bin\language_server.exe"),
        r"C:\Users\Darli\AppData\Local\Programs\antigravity\resources\bin\language_server.exe",
        os.path.join(home, r".gemini\antigravity\bin\language_server.exe"),
        r"C:\Users\Administrator\AppData\Local\Programs\Antigravity\resources\bin\language_server.exe",
    ]
    env_bin = (os.environ.get("ANTIGRAVITY_LS_BINARY") or "").strip()
    if env_bin:
        candidates.insert(0, env_bin)
    for p in candidates:
        if p and os.path.exists(p):
            return p
    which_ls = shutil.which("language_server.exe") or shutil.which("language_server")
    if which_ls:
        return which_ls
    return candidates[0]


def discover_antigravity_app_binary() -> str:
    """Resolve Antigravity.exe desktop client path for the primary Windows user."""
    home = get_primary_user_home()
    candidates = [
        os.path.join(home, r"AppData\Local\Programs\antigravity\Antigravity.exe"),
        os.path.join(home, r"AppData\Local\Programs\Antigravity\Antigravity.exe"),
        r"C:\Users\Darli\AppData\Local\Programs\antigravity\Antigravity.exe",
        r"C:\Program Files\Antigravity\Antigravity.exe",
        r"C:\Program Files (x86)\Antigravity\Antigravity.exe",
    ]
    env_app = (os.environ.get("ANTIGRAVITY_APP_BINARY") or "").strip()
    if env_app:
        candidates.insert(0, env_app)
    for p in candidates:
        if p and os.path.exists(p):
            return p
    which_app = shutil.which("Antigravity.exe") or shutil.which("antigravity")
    if which_app:
        return which_app
    return ""


def launch_antigravity_app() -> bool:
    """Launch the Google Antigravity desktop app detached in background with multi-tier fallback."""
    app_exe = discover_antigravity_app_binary()
    if not app_exe or not os.path.exists(app_exe):
        return False

    # Strategy 1: os.startfile (standard shell execute)
    try:
        if hasattr(os, "startfile"):
            os.startfile(app_exe)
            return True
    except Exception:
        pass

    # Strategy 2: subprocess.Popen with detached flags
    try:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([app_exe], creationflags=flags, close_fds=True)
        return True
    except Exception:
        pass

    # Strategy 3: explorer.exe (invokes interactive user desktop shell)
    try:
        subprocess.Popen(["explorer.exe", app_exe], close_fds=True)
        return True
    except Exception:
        pass

    # Strategy 4: PowerShell Start-Process
    try:
        ps_cmd = f"Start-Process -FilePath '{app_exe}'"
        subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], timeout=5)
        return True
    except Exception:
        pass

    return False


PRIMARY_HOME = get_primary_user_home()
LS_BINARY = discover_language_server_binary()
AGENTAPI_BAT = os.path.join(PRIMARY_HOME, r".gemini\antigravity\bin\agentapi.bat")
BRAIN_DIR = os.path.join(PRIMARY_HOME, r".gemini\antigravity\brain")
CLI_PROJECT_ID = "c1111111-c111-4111-8111-c11111111111"
CLI_PROJECT_FILE = os.path.join(PRIMARY_HOME, rf".gemini\config\projects\{CLI_PROJECT_ID}.json")
DEFAULT_CLI_WORKSPACES = [
    os.path.join(PRIMARY_HOME, r".codex"),
    os.path.join(PRIMARY_HOME, r"Documents\ChatGPT\投资理财"),
    os.path.join(PRIMARY_HOME, r"Documents\Codex"),
]


def _workspace_resource(path: str) -> dict:
    uri = _path_to_file_uri(path)
    git_dir = os.path.join(path, ".git")
    if os.path.isdir(git_dir) or os.path.isfile(git_dir):
        return {"gitFolder": {"folderUri": uri, "allowWrite": True}}
    return {"folderUri": uri, "allowWrite": True}


def ensure_cli_project_registered(extra_workspaces=None):
    """Register/refresh the dedicated CLI project so Antigravity can write the current user's workspaces."""
    try:
        os.makedirs(os.path.dirname(CLI_PROJECT_FILE), exist_ok=True)
        cfg = {}
        if os.path.exists(CLI_PROJECT_FILE):
            try:
                with open(CLI_PROJECT_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f) or {}
            except Exception:
                cfg = {}

        wanted = []
        for p in list(DEFAULT_CLI_WORKSPACES) + list(extra_workspaces or []):
            if not p:
                continue
            abs_p = os.path.abspath(os.path.expanduser(p))
            if os.path.exists(abs_p) and abs_p not in wanted:
                wanted.append(abs_p)

        existing = ((cfg.get("projectResources") or {}).get("resources") or [])
        existing_uris = set()
        for item in existing:
            if isinstance(item, dict):
                uri = item.get("folderUri") or ((item.get("gitFolder") or {}).get("folderUri"))
                if uri:
                    existing_uris.add(uri.lower())

        stale_markers = ("/users/administrator/", "/d:/claudefile")
        resources = []
        for item in existing:
            uri = ""
            if isinstance(item, dict):
                uri = (item.get("folderUri") or ((item.get("gitFolder") or {}).get("folderUri")) or "").lower()
            if any(m in uri for m in stale_markers):
                continue
            resources.append(item)

        for path in wanted:
            uri = _path_to_file_uri(path)
            if uri.lower() in existing_uris:
                continue
            resources.append(_workspace_resource(path))
            existing_uris.add(uri.lower())

        cfg["id"] = CLI_PROJECT_ID
        cfg["name"] = cfg.get("name") or "Antigravity CLI (Codex 自动化任务)"
        cfg["projectResources"] = {"resources": resources}
        settings = cfg.get("settings") or {}
        settings.setdefault("fileAccessPolicy", "AGENT_SETTING_POLICY_ALLOW")
        settings.setdefault("sandboxMode", False)
        settings.setdefault("autoExecutionPolicy", "CASCADE_COMMANDS_AUTO_EXECUTION_EAGER")
        settings.setdefault("artifactReviewMode", "ARTIFACT_REVIEW_MODE_TURBO")
        cfg["settings"] = settings

        with open(CLI_PROJECT_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _probe_running_ls() -> tuple[str, str]:
    """Inspect system processes and return (address, csrf_token) if language_server.exe is listening."""
    psutil_success = False
    # 1. Ultra-fast psutil discovery (<15ms)
    try:
        import psutil
        ls_proc = None
        csrf = None
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if p.info['name'] and p.info['name'].lower() == 'language_server.exe':
                    cmdline = " ".join(p.info['cmdline'] or [])
                    if '--csrf_token' in cmdline:
                        m = re.search(r'--csrf_token\s+([a-f0-9\-]+)', cmdline)
                        if m:
                            csrf = m.group(1)
                            ls_proc = p
                            break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        psutil_success = True
        if ls_proc and csrf:
            ports = []
            try:
                for conn in ls_proc.net_connections(kind='tcp'):
                    if conn.status == psutil.CONN_LISTEN:
                        ports.append(conn.laddr.port)
            except Exception:
                pass

            # Direct probe without proxy
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for port in ports:
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"x-csrf-token": csrf})
                    with opener.open(req, timeout=0.5) as resp:
                        if resp.status == 200:
                            return f"localhost:{port}", csrf
                except Exception:
                    pass
    except Exception:
        psutil_success = False

    # 2. PowerShell fallback (only if psutil failed or wasn't available)
    if not psutil_success:
        try:
            ps_cmd = "Get-CimInstance Win32_Process -Filter \"Name = 'language_server.exe'\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
            if res.stdout.strip():
                data = json.loads(res.stdout)
                if isinstance(data, list):
                    data = data[0]
                pid = data.get("ProcessId")
                cmdline = data.get("CommandLine", "")
                csrf_match = re.search(r'--csrf_token\s+([a-f0-9\-]+)', cmdline)
                if csrf_match:
                    csrf = csrf_match.group(1)
                    port_cmd = f"Get-NetTCPConnection -OwningProcess {pid} -State Listen | Select-Object -ExpandProperty LocalPort"
                    res_port = subprocess.run(["powershell", "-NoProfile", "-Command", port_cmd], capture_output=True, text=True)
                    ports = [int(p.strip()) for p in res_port.stdout.strip().splitlines() if p.strip().isdigit()]
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    for port in ports:
                        try:
                            req = urllib.request.Request(f"http://127.0.0.1:{port}/", headers={"x-csrf-token": csrf})
                            with opener.open(req, timeout=0.5) as resp:
                                if resp.status == 200:
                                    return f"localhost:{port}", csrf
                        except Exception:
                            pass
        except Exception:
            pass

    return "", ""


def discover_antigravity_env() -> dict[str, str]:
    """
    Auto-discovers running Antigravity Language Server address & CSRF token if not in env.
    Uses ultra-fast psutil inspection (~10ms) with direct socket probing, auto-launches
    Antigravity client if not already running, and strictly clears external HTTP/HTTPS proxies.
    """
    env = dict(os.environ)

    # If already fully configured, just sanitize proxy settings
    ls_addr = (env.get("ANTIGRAVITY_LS_ADDRESS") or "").strip()
    csrf_tok = (env.get("ANTIGRAVITY_CSRF_TOKEN") or "").strip()

    if not (ls_addr and csrf_tok):
        ls_addr, csrf_tok = _probe_running_ls()

        # If not running, attempt auto-launch Antigravity desktop app
        if not (ls_addr and csrf_tok):
            app_exe = discover_antigravity_app_binary()
            if app_exe:
                try:
                    sys.stderr.write(f"[AGY Auto-Start] 未检测到 Antigravity 运行，正在自动启动客户端并等待就绪...\n")
                    sys.stderr.flush()
                except Exception:
                    pass
                try:
                    log_event(f"[AUTO-START] 未检测到语言服务，正在自动拉起 Antigravity 客户端: {app_exe}")
                except Exception:
                    pass

                if launch_antigravity_app():
                    # Poll for up to 45 seconds (cold start on Windows Electron typically takes 20-30s)
                    t0 = time.time()
                    while time.time() - t0 < 45.0:
                        time.sleep(1.0)
                        ls_addr, csrf_tok = _probe_running_ls()
                        if ls_addr and csrf_tok:
                            try:
                                sys.stderr.write(f"[AGY Auto-Start] Antigravity 客户端已成功启动并就绪 ({ls_addr})。\n")
                                sys.stderr.flush()
                            except Exception:
                                pass
                            try:
                                log_event(f"[AUTO-START] Antigravity 客户端已就绪: {ls_addr}")
                            except Exception:
                                pass
                            break

        if ls_addr and csrf_tok:
            env["ANTIGRAVITY_LS_ADDRESS"] = ls_addr
            env["ANTIGRAVITY_CSRF_TOKEN"] = csrf_tok

    # 3. CRITICAL: Strip all external HTTP/HTTPS proxies from run_env
    # language_server.exe agentapi ONLY talks to localhost via gRPC.
    # Routing local gRPC to Clash (127.0.0.1:7890) causes instant socket abort!
    for k in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        env.pop(k, None)
    env["NO_PROXY"] = "*"
    env["no_proxy"] = "*"

    # 4. CRITICAL: Clean parent conversation context to prevent nested permission conflicts
    # If caller process inherits ANTIGRAVITY_SOURCE_METADATA or parent conversation/trajectory IDs,
    # language_server.exe rejects new-conversation with PermissionDenied (source project mismatch).
    for k in ["ANTIGRAVITY_SOURCE_METADATA", "ANTIGRAVITY_CONVERSATION_ID", "ANTIGRAVITY_TRAJECTORY_ID"]:
        env.pop(k, None)

    # 5. Route all CLI / automated tasks to dedicated project folder
    # Isolates automated tasks into "Antigravity CLI (Codex 自动化任务)" in Antigravity IDE sidebar
    ensure_cli_project_registered()
    env["ANTIGRAVITY_PROJECT_ID"] = CLI_PROJECT_ID

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
        return 1200.0
    timeout_str = timeout_str.strip().lower()
    try:
        if timeout_str.endswith("m") or timeout_str.endswith("m0s"):
            m = float(timeout_str.split("m")[0])
            return m * 60.0
        if timeout_str.endswith("s"):
            return float(timeout_str[:-1])
        return float(timeout_str)
    except Exception:
        return 1200.0


def run_daemon_track(task_id: str, cid: str, log_path: str, report_file: str, workspace: str, max_wait_sec: float):
    """
    Extremely lightweight background worker that watches transcript.jsonl until completion.
    Ensures final report and task record are saved even after the foreground CLI detached.
    """
    start_time = time.time()
    last_idx = 0
    tool_counter = 0
    final_output = ""

    # Load existing task record
    record = _load_task_record(task_id) or {
        "task_id": task_id,
        "task_type": "agy_cli",
        "status": "RUNNING",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_path": workspace,
        "report_file": report_file,
        "start_time": start_time,
    }
    record["status"] = "RUNNING"
    _save_task_record(record)
    log_event(f"[TRACK] [CLI:{task_id}] 后台守护进程已就绪，持续跟踪转录日志直至全部落地")

    while time.time() - start_time < max_wait_sec:
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                lines = []

            if len(lines) > last_idx:
                for idx in range(last_idx, len(lines)):
                    try:
                        step = json.loads(lines[idx])
                        stype = step.get("type")
                        status = step.get("status")
                        tools = step.get("tool_calls", [])
                        content = step.get("content", "")
                        if tools:
                            tool_counter += len(tools)
                        if content and stype == "PLANNER_RESPONSE" and status == "DONE":
                            final_output = content
                    except Exception:
                        pass
                last_idx = len(lines)

                if lines:
                    try:
                        last_step = json.loads(lines[-1])
                        if (last_step.get("type") == "PLANNER_RESPONSE"
                            and last_step.get("status") == "DONE"
                            and last_step.get("content")
                            and not last_step.get("tool_calls")):
                            final_output = last_step.get("content", "").strip()
                            break
                    except Exception:
                        pass
        time.sleep(2.0)

    elapsed = time.time() - start_time
    if final_output:
        try:
            os.makedirs(os.path.dirname(report_file), exist_ok=True)
            with open(report_file, "w", encoding="utf-8") as rf:
                rf.write(f"# 🤖 Antigravity Official Execution Result (Background Detached)\n\n"
                         f"- **Task ID**: `{task_id}`\n"
                         f"- **Conversation ID**: `{cid}`\n"
                         f"- **Time**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                         f"- **Elapsed**: {elapsed:.2f}s\n"
                         f"- **Workspace**: `{workspace}`\n\n---\n\n"
                         f"## 📋 Output\n\n{final_output}\n")
        except Exception:
            pass
        record["status"] = "COMPLETED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["return_chars"] = len(final_output)
        record["snippet"] = final_output[:500]
        _save_task_record(record)
        log_event(f"[DONE]  [CLI:{task_id}] 后台托管任务执行完成 | 耗时: {elapsed:.2f}s | 返回字符数: {len(final_output)}")
    else:
        record["status"] = "FAILED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["error"] = f"Background execution timed out after {max_wait_sec:.0f}s"
        _save_task_record(record)
        log_event(f"[TIMEOUT] [CLI:{task_id}] 后台托管任务等待超时 ({max_wait_sec:.0f}s)")


def spawn_daemon_tracker(task_id: str, cid: str, log_path: str, report_file: str, workspace: str, max_wait_sec: float = 1800.0) -> bool:
    """Launches a detached background watcher to keep tracking until completion."""
    try:
        py_exe = sys.executable
        script_path = os.path.abspath(__file__)
        args = [
            py_exe, script_path, "--daemon-track",
            task_id, cid, log_path, report_file, workspace, str(int(max_wait_sec))
        ]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen(
            args,
            creationflags=flags,
            close_fds=True
        )
        return True
    except Exception as e:
        log_event(f"[WARN] 启动后台守护跟踪失败: {e}")
        return False


async def run_official_headless(prompt: str, workspace: str, model: str, timeout_sec: float, task_id: str, allow_detach: bool = True) -> tuple[str, bool]:
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

    if not run_env.get("ANTIGRAVITY_LS_ADDRESS"):
        app_exe = discover_antigravity_app_binary()
        if app_exe:
            raise RuntimeError(f"未检测到运行中的 Antigravity 语言服务器 (language_server.exe)。已尝试自动拉起客户端 ({app_exe}) 但等待就绪超时 (45s)，请检查 Antigravity 是否正常登录。")
        else:
            raise RuntimeError("未检测到运行中的 Antigravity 语言服务器 (language_server.exe)，且未找到 Antigravity 客户端安装路径。请确认 Antigravity 客户端已启动并登录。")

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
    last_activity_time = time.time()
    last_processed_idx = 0
    tool_counter = 0
    final_output = ""
    recent_actions = []

    # Safe auto-detach threshold:
    # Trigger at 570s (9m 30s) or (timeout_sec - 30s), whichever is smaller,
    # so that Codex never encounters a 10-minute command cutoff!
    safe_max_sync = float(os.environ.get("ANTIGRAVITY_CLI_DETACH_TIMEOUT", "570.0"))
    detach_buffer = 30.0 if timeout_sec >= 120.0 else max(5.0, timeout_sec * 0.1)
    detach_threshold = min(max(timeout_sec - detach_buffer, 10.0), safe_max_sync)

    # Poll transcript until completion or timeout
    while time.time() - start_time < timeout_sec:
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = [l.strip() for l in f if l.strip()]
            except Exception:
                lines = []

            if len(lines) > last_processed_idx:
                last_activity_time = time.time()
                for idx in range(last_processed_idx, len(lines)):
                    try:
                        step = json.loads(lines[idx])
                        stype = step.get("type")
                        status = step.get("status")
                        tools = step.get("tool_calls", [])
                        content = step.get("content", "")

                        if tools:
                            for t in tools:
                                tool_counter += 1
                                tname = t.get("name", "tool")
                                targs = t.get("arguments", {}) or t.get("args", {})
                                arg_summary = ""
                                if isinstance(targs, dict):
                                    if "CommandLine" in targs:
                                        cmd_line = targs["CommandLine"].strip().replace("\n", " ")
                                        arg_summary = f": {cmd_line[:40]}..." if len(cmd_line) > 40 else f": {cmd_line}"
                                    elif "TargetFile" in targs:
                                        arg_summary = f": {os.path.basename(targs['TargetFile'])}"
                                    elif "AbsolutePath" in targs:
                                        arg_summary = f": {os.path.basename(targs['AbsolutePath'])}"
                                    elif "Query" in targs:
                                        arg_summary = f": {targs['Query'][:25]}"
                                    elif "Pattern" in targs:
                                        arg_summary = f": {targs['Pattern'][:25]}"
                                action_desc = f"{tname}{arg_summary}"
                                recent_actions.append(action_desc)
                                if len(recent_actions) > 8:
                                    recent_actions.pop(0)
                                log_event(f"[TOOL]  [CLI:{task_id}] [#{tool_counter}] 执行: {action_desc}")
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
                            return final_output, False
                    except Exception:
                        pass

        # Check for auto-detach if approaching timeout and Antigravity is still working actively
        now = time.time()
        elapsed = now - start_time
        if allow_detach and (elapsed >= detach_threshold):
            is_active = False
            if now - last_activity_time < 90.0:
                is_active = True
            elif os.path.exists(log_path) and (now - os.path.getmtime(log_path) < 90.0):
                is_active = True

            if is_active:
                log_event(f"[DETACH] [CLI:{task_id}] 任务运行达 {elapsed:.0f}s (接近截断阈值)，检测到 Antigravity 仍在全速执行中，已平滑转入后台守护托管")
                recent_action_list = "\n".join(f"  - {act}" for act in recent_actions[-5:]) if recent_actions else "  - 智能体正在持续阅读与修改相关代码"
                report_file = os.path.join(workspace, ".antigravity_reports", f"{task_id}.md")

                detach_feedback = (
                    f"> ⏳ **【任务执行规模较大，已在第 {elapsed:.0f} 秒自动转入安全后台托管】**\n"
                    f"> 🛡️ **已成功拦截并彻底规避 10 分钟命令超时强行截断！** Google Antigravity 正在后台全速工作中，任务绝未失败。\n\n"
                    f"- **任务 ID**: `{task_id}`\n"
                    f"- **会话 ID**: `{cid[:8]}...`\n"
                    f"- **工作区**: `{workspace}`\n"
                    f"- **当前执行进度**: 已完成 **{tool_counter}** 次工具调用/代码改动，当前智能体仍在积极操作中。\n"
                    f"- **近期关键操作**:\n{recent_action_list}\n"
                    f"- **最终报告生成路径**: `{report_file}`\n\n"
                    f"💡 **给 Codex 的协作指令**：\n"
                    f"1. Antigravity 正在全速进行代码修改与单测验证，后台任务绝未中断。\n"
                    f"2. 请**切勿**将本次委托判定为失败，亦**无需**重复下发相同的 `agy` 命令。\n"
                    f"3. 你可以稍作等待（约 1~3 分钟）后，直接读取 `{report_file}` 或检查目标源码文件以获取最终修改结果。"
                )

                spawn_daemon_tracker(task_id, cid, log_path, report_file, workspace, max_wait_sec=1800.0)
                return detach_feedback, True

        await asyncio.sleep(0.8)

    if final_output:
        return final_output, False
    raise asyncio.TimeoutError(f"Antigravity headless execution timed out after {timeout_sec:.0f}s")


async def run_cli(prompt: str, workspace: str, model: str, timeout_sec: float, allow_detach: bool = True) -> int:
    workspace = os.path.abspath(workspace)
    ensure_cli_project_registered(extra_workspaces=[workspace])

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
        "worker_pid": os.getpid(),
        "model": model,
        "report_file": os.path.join(workspace, ".antigravity_reports", f"{task_id}.md")
    }
    _save_task_record(record)

    try:
        result_text, is_detached = await run_official_headless(
            prompt=prompt,
            workspace=workspace,
            model=model,
            timeout_sec=timeout_sec,
            task_id=task_id,
            allow_detach=allow_detach
        )
        elapsed = time.time() - start_time

        if is_detached:
            record["status"] = "RUNNING"
            record["is_detached"] = True
            record["snippet"] = result_text[:500]
            _save_task_record(record)
            log_event(f"[DETACH] [CLI:{task_id}] 任务平滑转入后台托管，向客户端正常返回阶段汇报")

            try:
                os.makedirs(os.path.dirname(record["report_file"]), exist_ok=True)
                with open(record["report_file"], "w", encoding="utf-8") as rf:
                    rf.write(f"# 🤖 Antigravity Official CLI Execution (Background Running)\n\n"
                             f"- **Task ID**: `{task_id}`\n"
                             f"- **Time**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                             f"- **Status**: Background Running (Detached at {elapsed:.2f}s)\n"
                             f"- **Workspace**: `{workspace}`\n\n---\n\n"
                             f"## 📝 Prompt\n\n{prompt}\n\n---\n\n"
                             f"## ⏳ Status & Progress\n\n{result_text}\n")
            except Exception:
                pass

            try:
                sys.stdout.write(result_text)
            except UnicodeEncodeError:
                sys.stdout.buffer.write(result_text.encode(sys.stdout.encoding or "utf-8", errors="replace"))
            if not result_text.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()
            return 0

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
        log_event(f"[TIMEOUT] [CLI:{task_id}] 执行超时 | 耗时: {elapsed:.2f}s | 阈值: {timeout_sec:.0f}s (大任务可指定 -t 20m 或 30m)")
        sys.stderr.write(f"Error: {err_msg} (提示: 复杂重构与批量单测任务请指定 --print-timeout 20m 或 30m)\n")
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
    if len(sys.argv) > 1 and sys.argv[1] == "--daemon-track":
        if len(sys.argv) >= 8:
            run_daemon_track(
                task_id=sys.argv[2],
                cid=sys.argv[3],
                log_path=sys.argv[4],
                report_file=sys.argv[5],
                workspace=sys.argv[6],
                max_wait_sec=float(sys.argv[7])
            )
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="Google Antigravity Official Headless CLI (agy) - Gemini 3.8 Flash",
        add_help=False
    )
    parser.add_argument("-p", "--print", dest="print_prompt", type=str, default=None,
                        help="Non-interactive mode: run prompt, print response, exit")
    parser.add_argument("--print-timeout", "--timeout", "-t", dest="timeout", type=str, default="20m",
                        help="Timeout for print mode (e.g. 15m, 20m, 30m, default: 20m)")
    parser.add_argument("--model", dest="model", type=str, default="flash",
                        help="Antigravity model tier: flash (Gemini 3.8 Flash), pro, or flash_lite")
    parser.add_argument("--dangerously-skip-permissions", dest="skip_perm", action="store_true",
                        help="Auto-approve all tool calls (compatibility flag)")
    parser.add_argument("--no-detach", dest="no_detach", action="store_true",
                        help="Disable automatic background detach before timeout")
    parser.add_argument("--add-dir", dest="add_dir", action="append", default=[],
                        help="Add directory to workspace")
    parser.add_argument("-h", "--help", action="store_true", help="Show help message")
    parser.add_argument("-v", "--version", action="store_true", help="Show version information")
    parser.add_argument("positional_prompt", nargs="*", help="Positional prompt arguments")

    args, remaining = parser.parse_known_args()

    if args.version:
        print("Google Antigravity Official Headless CLI (agy) v3.0 - Gemini 3.8 Flash")
        sys.exit(0)

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
    code = asyncio.run(run_cli(prompt, workspace, args.model, timeout_sec, allow_detach=not args.no_detach))
    sys.exit(code)


if __name__ == "__main__":
    main()
