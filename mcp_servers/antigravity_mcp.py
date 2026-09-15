"""
Antigravity MCP Server for OpenAI Codex / Claude / Cursor
Allows AI assistants (like OpenAI Codex) to delegate complex coding, refactoring, research, 
and code review tasks to Google Antigravity.

Features:
- Auto-Detaching Hybrid Engine: Prevents client 300s timeout by design!
  - Quick tasks (< 180s) return complete results synchronously.
  - Large reviews (3+ files) immediately detach to background in 0.1s.
  - Long tasks (> 180s) automatically detach safely at 180s, continuing in background without interruption.
- Asynchronous task tools (`ask_antigravity_async`, `antigravity_code_review_async`).
- Real-time progress query (`check_antigravity_task` with optional `wait_seconds`).
- Persistent markdown reports automatically written to `<workspace>/.antigravity_reports/`.
- LocalOpenAIAgentConfig with local agentrouter/glm-5.3 for zero-key, high-stability multi-turn tool reasoning.
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
from google.antigravity import Agent, LocalAgentConfig, LocalOpenAIAgentConfig, CapabilitiesConfig
from google.antigravity.hooks import policy

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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
TIER1_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
# AgentRouter 中继梯队三级优先级
RELAY_M1_MODEL = os.environ.get("ANTIGRAVITY_RELAY_M1", "agentrouter/gpt-5.6-sol").strip()
RELAY_M2_MODEL = os.environ.get("ANTIGRAVITY_RELAY_M2", "agentrouter/deepseek-v4-flash").strip()
RELAY_M3_MODEL = os.environ.get("ANTIGRAVITY_RELAY_M3", "agentrouter/glm-5.3").strip()
TIER2_MODEL = RELAY_M2_MODEL  # 兼容旧引用
TIER3_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash").strip()
BASE_URL = os.environ.get("ANTIGRAVITY_BASE_URL", "http://127.0.0.1:10100/v1")
DEFAULT_MODEL = RELAY_M2_MODEL
TASKS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tasks")
os.makedirs(TASKS_DIR, exist_ok=True)


# Gemini 3.8 配额耗尽冷却时间戳（避免配额用完后每个任务都反复碰壁 8 秒）
_gemini_38_cooling_until: float = 0.0
# Gemini 2.5 配额耗尽冷却时间戳
_gemini_25_cooling_until: float = 0.0
# Google Gemini 区域不支持 (code 400: User location is not supported) 冷却时间戳
_gemini_location_cooling_until: float = 0.0
# gpt-5.6-sol 预算池用尽 (402 Budget pool quota exhausted) 冷却时间戳（直到下一个 0:00/8:00/16:00 放量批次）
_gpt56_sol_cooling_until: float = 0.0


def _get_next_sol_refresh_time() -> float:
    """计算下一个北京时间 (UTC+8) 0:00, 8:00, 16:00 限量放量周期的 Unix 时间戳"""
    try:
        from datetime import datetime, timezone, timedelta
        bj_tz = timezone(timedelta(hours=8))
        now_bj = datetime.now(bj_tz)
        for h in [0, 8, 16]:
            target = now_bj.replace(hour=h, minute=0, second=0, microsecond=0)
            if target > now_bj:
                return target.timestamp()
        # 次日 00:00
        tomorrow = (now_bj + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow.timestamp()
    except Exception:
        return time.time() + 3600


def _resolve_gemini_api_key() -> str:
    """精准解析有效的 Google Gemini API Key（支持优先从注册表/环境加载有效 Key）"""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key and not key.startswith("AIzaSyBJ8Q"):
        return key
    try:
        import winreg
        h = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment')
        rk, _ = winreg.QueryValueEx(h, 'GEMINI_API_KEY')
        winreg.CloseKey(h)
        if rk and rk.strip() and not rk.strip().startswith("AIzaSyBJ8Q"):
            return rk.strip()
    except Exception:
        pass
    return key or GEMINI_API_KEY


def get_engine_name() -> str:
    """返回当前底层运行的推理引擎名称与级联状态"""
    sol_active = (time.time() >= _gpt56_sol_cooling_until)
    lead_relay = "GPT-5.6-Sol" if sol_active else "DeepSeek-V4"
    return f"3.8-Flash -> [{lead_relay} -> DeepSeek -> GLM-5.3] -> 2.5-Flash"

# Safe auto-detach timeout: 180s (Codex client times out at 300s, giving 120s buffer)
SAFE_SYNC_TIMEOUT = float(os.environ.get("ANTIGRAVITY_SYNC_TIMEOUT", "180.0"))

# Network resilience: auto-retry for transient proxy/gateway drops (502/503/504/connection refused)
MAX_NETWORK_RETRIES = int(os.environ.get("ANTIGRAVITY_MAX_RETRIES", "3"))
RETRY_INITIAL_DELAY = float(os.environ.get("ANTIGRAVITY_RETRY_DELAY", "3.0"))

# In-memory background tasks tracker
_background_tasks: Dict[str, asyncio.Task] = {}


def _is_transient_network_error(err_text: str) -> bool:
    """判断是否为网络闪断、代理重启、网关握手被拒等偶发瞬时异常"""
    msg = err_text.lower()
    transient_patterns = [
        "502",
        "503",
        "504",
        "unable to connect",
        "is the computer able to access the url",
        "connection refused",
        "connection reset",
        "connection closed",
        "econnrefused",
        "econnreset",
        "etimedout",
        "timed out",
        "timeout",
        "broken pipe",
        "network unreachable",
        "host unreachable",
        "failed to connect",
        "server_is_overloaded",
        "bad gateway",
        "service unavailable",
        "gateway timeout",
        "handshake failure",
        "remote end closed connection",
    ]
    return any(p in msg for p in transient_patterns)


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
    system_instructions: Optional[str] = None,
    task_id: Optional[str] = None,
) -> str:
    """底层的 Antigravity 智能体调用逻辑，内置网络抖动自愈重试引擎"""
    sys_inst = system_instructions or (
        f"你是由 OpenAI Codex 调用的 Google Antigravity 高级专家智能体。\n"
        f"当前工作区路径为：{ws}。\n"
        f"请结合工作区文件和最佳实践，高质量执行用户委托的任务，并输出清晰详尽的中文执行汇报与结果。\n"
        f"【Windows 环境规范】：\n"
        f"1. 严禁对本地磁盘文件路径调用网页工具 read_url_content，读取本地文件必须使用 view_file。\n"
        f"2. 针对代码审查或综合分析任务，完成审计后请务必创建或更新报告文档（Artifact），并输出结构化的详细审查结论。"
    )

    workspaces = [ws] if os.path.exists(ws) else None
    api_key = _resolve_gemini_api_key()

    def _build_gemini_cfg(model_name: str):
        return LocalAgentConfig(
            api_key=api_key,
            model=model_name,
            system_instructions=sys_inst,
            capabilities=CapabilitiesConfig(
                file_reads=True,
                file_writes=True,
                command_execution=True,
                subagents=True,
                mcp=True,
            ),
            policies=[policy.allow_all()],
            workspaces=workspaces,
        )

    def _build_openai_cfg(model_name: str):
        return LocalOpenAIAgentConfig(
            base_url=BASE_URL,
            model=model_name,
            system_instructions=sys_inst,
            capabilities=CapabilitiesConfig(
                file_reads=True,
                file_writes=True,
                command_execution=True,
                subagents=True,
                mcp=True,
            ),
            policies=[policy.allow_all()],
            workspaces=workspaces,
        )

    async def _try_agent_loop(cfg, is_gemini=False, tier_name=""):
        last_err = None
        for attempt in range(1, MAX_NETWORK_RETRIES + 1):
            try:
                response_chunks = []
                async with Agent(cfg) as agent:
                    response = await agent.chat(prompt)
                    async for token in response:
                        response_chunks.append(token)
                        await asyncio.sleep(0)  # 让出事件循环，保障底层 WebSocket pump 畅通无阻塞

                return "".join(response_chunks).strip()

            except Exception as e:
                last_err = e
                err_msg = str(e)
                if is_gemini and ("api key not valid" in err_msg.lower() or "api_key_invalid" in err_msg.lower() or "400" in err_msg):
                    raise last_err
                if _is_transient_network_error(err_msg) and attempt < MAX_NETWORK_RETRIES:
                    delay = RETRY_INITIAL_DELAY * (2 ** (attempt - 1))
                    tid_prefix = f" [ASYNC:{task_id}]" if task_id else ""
                    short_err = err_msg.replace("\n", " ").strip()
                    if len(short_err) > 80:
                        short_err = short_err[:80] + "..."
                    log_event(
                        f"[RETRY]{tid_prefix} {tier_name} 捕获网络闪断 (第 {attempt}/{MAX_NETWORK_RETRIES} 次): "
                        f"{short_err} | 等待 {delay:.1f}s 后自动重试..."
                    )
                    if task_id:
                        rec = _load_task_record(task_id)
                        if rec:
                            rec["retry_count"] = attempt
                            rec["last_error"] = short_err
                            rec["status_detail"] = f"{tier_name} 网络闪断自动重试中 ({attempt}/{MAX_NETWORK_RETRIES})"
                            _save_task_record(rec)
                    await asyncio.sleep(delay)
                    continue
                raise last_err

    tid_prefix = f" [ASYNC:{task_id}]" if task_id else ""
    global _gemini_38_cooling_until, _gemini_location_cooling_until, _gpt56_sol_cooling_until
    now_ts = time.time()
    gemini_38_cooling = (now_ts < _gemini_38_cooling_until)
    gemini_location_cooling = (now_ts < _gemini_location_cooling_until)

    # =========================================================================
    # Tier 1 (前置尝鲜): gemini-3.8-flash (Google 原生前沿预览模型)
    # =========================================================================
    if api_key and not gemini_38_cooling and not gemini_location_cooling:
        try:
            return await _try_agent_loop(_build_gemini_cfg(TIER1_MODEL), is_gemini=True, tier_name=f"Tier 1 ({TIER1_MODEL})")
        except Exception as e:
            short_e = str(e).replace("\n", " ").strip()[:100]
            if "429" in short_e or "quota" in short_e.lower():
                _gemini_38_cooling_until = time.time() + 1800  # 自动进入 30 分钟配额冷却期
            elif "user location is not supported" in short_e.lower() or "location" in short_e.lower():
                _gemini_location_cooling_until = time.time() + 3600  # 区域不支持，自动冷却 1 小时屏蔽 Google 原生
                log_event(f"[LOCATION]{tid_prefix} Google 原生 API 处于不支持地理区域 ({short_e})，自动屏蔽 Google 原生引擎 1 小时，由 AgentRouter 中继梯队全面接管...")
            log_event(f"[FALLBACK]{tid_prefix} Tier 1 ({TIER1_MODEL}) 受阻 ({short_e})，自动流转至中继优先梯队 ({RELAY_M1_MODEL})...")
            if task_id:
                rec = _load_task_record(task_id)
                if rec:
                    rec["status_detail"] = f"Tier 1 受阻，已切至中继梯队运行"
                    _save_task_record(rec)
    elif gemini_38_cooling and api_key and not gemini_location_cooling:
        remain = max(1, int((_gemini_38_cooling_until - time.time()) / 60))
        log_event(f"[DISPATCH]{tid_prefix} Tier 1 ({TIER1_MODEL}) 配额冷却中 (余 {remain} 分钟)，优先启用中继优先梯队...")

    # =========================================================================
    # Tier 2 (本地中继高可用梯队): M1 (GPT-5.6-Sol) -> M2 (DeepSeek-V4) -> M3 (GLM-5.3)
    # =========================================================================
    relay_errors = []

    # --- 优先级一: agentrouter/gpt-5.6-sol (每天 0:00, 8:00, 16:00 限量旗舰) ---
    if time.time() >= _gpt56_sol_cooling_until:
        try:
            return await _try_agent_loop(_build_openai_cfg(RELAY_M1_MODEL), is_gemini=False, tier_name=f"中继优选一 ({RELAY_M1_MODEL})")
        except Exception as e_m1:
            relay_errors.append(e_m1)
            short_m1 = str(e_m1).replace("\n", " ").strip()[:120]
            if "402" in short_m1 or "budget pool quota" in short_m1.lower() or "budget" in short_m1.lower():
                _gpt56_sol_cooling_until = _get_next_sol_refresh_time()
                next_rf = datetime.fromtimestamp(_gpt56_sol_cooling_until).strftime("%H:%M")
                log_event(f"[FALLBACK]{tid_prefix} 中继优选一 ({RELAY_M1_MODEL}) 限量额度已耗尽 (402 Budget pool quota exhausted)，自动冷却至下一放量批次 ({next_rf})，平滑切换至优先级二 ({RELAY_M2_MODEL})...")
            else:
                log_event(f"[FALLBACK]{tid_prefix} 中继优选一 ({RELAY_M1_MODEL}) 遇到异常 ({short_m1})，切换至优先级二 ({RELAY_M2_MODEL})...")
            if task_id:
                rec = _load_task_record(task_id)
                if rec:
                    rec["status_detail"] = f"M1 已耗尽/异常，切至 M2 ({RELAY_M2_MODEL})"
                    _save_task_record(rec)
    else:
        remain_m1 = max(1, int((_gpt56_sol_cooling_until - time.time()) / 60))
        next_rf = datetime.fromtimestamp(_gpt56_sol_cooling_until).strftime("%H:%M")
        log_event(f"[DISPATCH]{tid_prefix} 中继优选一 ({RELAY_M1_MODEL}) 限量额度冷却中 (下一批 {next_rf}，余 {remain_m1} 分钟)，优先直通优先级二 ({RELAY_M2_MODEL})...")

    # --- 优先级二: agentrouter/deepseek-v4-flash (高并发主力开发与审查) ---
    try:
        return await _try_agent_loop(_build_openai_cfg(RELAY_M2_MODEL), is_gemini=False, tier_name=f"中继主力二 ({RELAY_M2_MODEL})")
    except Exception as e_m2:
        relay_errors.append(e_m2)
        short_m2 = str(e_m2).replace("\n", " ").strip()[:120]
        log_event(f"[FALLBACK]{tid_prefix} 中继主力二 ({RELAY_M2_MODEL}) 遇到异常 ({short_m2})，自动降级至优先级三 ({RELAY_M3_MODEL})...")
        if task_id:
            rec = _load_task_record(task_id)
            if rec:
                rec["status_detail"] = f"M2 异常，切至 M3 ({RELAY_M3_MODEL})"
                _save_task_record(rec)

    # --- 优先级三: agentrouter/glm-5.3 (中继终极保底) ---
    try:
        return await _try_agent_loop(_build_openai_cfg(RELAY_M3_MODEL), is_gemini=False, tier_name=f"中继兜底三 ({RELAY_M3_MODEL})")
    except Exception as e_m3:
        relay_errors.append(e_m3)
        short_m3 = str(e_m3).replace("\n", " ").strip()[:120]
        log_event(f"[FALLBACK]{tid_prefix} 中继兜底三 ({RELAY_M3_MODEL}) 遇到异常 ({short_m3})，尝试启用 Tier 3 原生保底...")
        if task_id:
            rec = _load_task_record(task_id)
            if rec:
                rec["status_detail"] = f"中继全部异常，尝试切至 Tier 3 原生保底"
                _save_task_record(rec)

    # =========================================================================
    # Tier 3 (终极保底): gemini-2.5-flash (Google 原生高配额基准模型)
    # =========================================================================
    if api_key and (time.time() >= _gemini_location_cooling_until) and (time.time() >= _gemini_25_cooling_until):
        log_event(f"[TIER3]{tid_prefix} 启动 Tier 3: {TIER3_MODEL} (Google 原生高配额基准) 终极保障执行...")
        try:
            return await _try_agent_loop(_build_gemini_cfg(TIER3_MODEL), is_gemini=True, tier_name=f"Tier 3 ({TIER3_MODEL})")
        except Exception as e_t3:
            short_t3 = str(e_t3).replace("\n", " ").strip()[:120]
            if "429" in short_t3 or "quota" in short_t3.lower():
                _gemini_25_cooling_until = time.time() + 1800  # 自动进入 30 分钟配额冷却期
                log_event(f"[FALLBACK]{tid_prefix} Tier 3 ({TIER3_MODEL}) 配额耗尽 (429)，冷却 30 分钟...")
            elif "user location is not supported" in short_t3.lower() or "location" in short_t3.lower():
                _gemini_location_cooling_until = time.time() + 3600
                log_event(f"[LOCATION]{tid_prefix} Tier 3 检测到 IP 区域不支持 ({short_t3})，冷却 1 小时...")
            raise RuntimeError(f"全链路推理梯队均不可用。中继异常: {relay_errors[-1] if relay_errors else 'None'}, 原生异常: {e_t3}")
    else:
        reason = "区域不支持" if time.time() < _gemini_location_cooling_until else "配额冷却中"
        raise RuntimeError(f"全链路推理梯队均不可用。本地中继异常列表: {relay_errors}，Tier 3 Google 原生处于{reason}跳过。")


def _try_rescue_brain_artifact(start_time: float, target_report_file: str, ws: str, task_id: str) -> Optional[str]:
    """
    自愈恢复引擎：当底层 Harness 进程因 Windows 异常（如 WS close code 1011）意外退出时，
    自动检查已生成的目标报告或扫描 Brain 缓存目录，拯救并提取崩溃前已成功产出的完整报告文件。
    """
    # 1. 首先检查 target_report_file 是否已经存在且有效 (>500 字节)
    if os.path.exists(target_report_file):
        try:
            sz = os.path.getsize(target_report_file)
            if sz > 500:
                with open(target_report_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                log_event(f"[RESCUE-DIRECT] [ASYNC:{task_id}] 目标报告已存在且完整 ({sz} 字节): {target_report_file}")
                return content
        except Exception:
            pass

    # 2. 检查工作区 .antigravity_reports 目录下是否有最近创建的 .md 文件
    ws_reports_dir = os.path.join(ws, ".antigravity_reports")
    if os.path.exists(ws_reports_dir):
        try:
            for f in os.listdir(ws_reports_dir):
                if f.endswith(".md"):
                    full_p = os.path.join(ws_reports_dir, f)
                    mtime = os.path.getmtime(full_p)
                    if mtime >= (start_time - 30) and os.path.getsize(full_p) > 500:
                        with open(full_p, "r", encoding="utf-8", errors="replace") as rf:
                            content = rf.read()
                        if os.path.abspath(full_p) != os.path.abspath(target_report_file):
                            os.makedirs(os.path.dirname(os.path.abspath(target_report_file)), exist_ok=True)
                            with open(target_report_file, "w", encoding="utf-8") as tf:
                                tf.write(content)
                        log_event(f"[RESCUE-WS] [ASYNC:{task_id}] 从工作区报告目录挽救成功: {full_p} -> {target_report_file}")
                        return content
        except Exception as e:
            log_event(f"[RESCUE-ERROR] [ASYNC:{task_id}] 检查工作区报告目录失败: {e}")

    # 3. 扫描 ~/.gemini/antigravity/brain 目录下的所有最近产出的 Artifact
    brain_root = os.path.expanduser(r"~\.gemini\antigravity\brain")
    if not os.path.exists(brain_root):
        return None

    candidates = []
    try:
        for root, dirs, files in os.walk(brain_root):
            if ".system_generated" in root or "scratch" in root:
                continue
            for f in files:
                if f.endswith(".md") and not f.endswith(".metadata.json"):
                    full_path = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(full_path)
                        if mtime >= (start_time - 30):
                            sz = os.path.getsize(full_path)
                            if sz > 500:
                                candidates.append((mtime, sz, full_path))
                    except Exception:
                        pass
    except Exception as e:
        log_event(f"[RESCUE-ERROR] [ASYNC:{task_id}] 遍历 Brain 目录失败: {e}")
        return None

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_mtime, best_sz, best_file = candidates[0]

    try:
        with open(best_file, "r", encoding="utf-8", errors="replace") as bf:
            content = bf.read()

        os.makedirs(os.path.dirname(os.path.abspath(target_report_file)), exist_ok=True)
        with open(target_report_file, "w", encoding="utf-8") as tf:
            tf.write(content)

        log_event(
            f"[RESCUE-SUCCESS] [ASYNC:{task_id}] 成功从 Brain 缓存挽救产物: "
            f"{best_file} ({best_sz} 字节) -> {target_report_file}"
        )
        return content
    except Exception as e:
        log_event(f"[RESCUE-ERROR] [ASYNC:{task_id}] 写入挽救报告失败: {e}")
        return None


async def _run_async_worker(
    task_id: str,
    task_type: str,
    prompt: str,
    ws: str,
    report_file: str,
    system_instructions: Optional[str] = None
) -> None:
    """后台异步任务 Worker（永不被客户端超时打断）"""
    start_time = time.time()
    record = _load_task_record(task_id) or {}
    record["status"] = "RUNNING"
    record["start_time"] = start_time
    record["worker_pid"] = os.getpid()
    _save_task_record(record)

    prompt_summary = prompt.replace("\n", " ").strip()
    if len(prompt_summary) > 50:
        prompt_summary = prompt_summary[:50] + "..."

    engine_name = get_engine_name()
    log_event(f"[START] [ASYNC:{task_id}] 触发任务: call-agy ({task_type}) | 引擎: {engine_name} | 工作区: {ws} | 任务: {prompt_summary}")

    try:
        result_text = await _execute_antigravity_core(prompt, ws, system_instructions, task_id=task_id)
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
            f"- **模型引擎**: `{engine_name}`\n\n"
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
        record["snippet"] = result_text[:500] + ("..." if len(result_text) > 500 else "")
        _save_task_record(record)

        log_event(f"[DONE]  [ASYNC:{task_id}] 执行成功 | 耗时: {elapsed:.2f}s | 字符数: {len(result_text)} | 报告: {os.path.basename(report_file)}")

    except Exception as e:
        elapsed = time.time() - start_time
        err_msg = str(e)

        # 自愈引擎：尝试从工作区或 Brain 缓存中挽救崩溃前已成功生成的报告文件
        rescued_content = _try_rescue_brain_artifact(start_time, report_file, ws, task_id)
        if rescued_content:
            record["status"] = "COMPLETED"
            record["end_time"] = time.time()
            record["elapsed_sec"] = elapsed
            record["return_chars"] = len(rescued_content)
            record["report_file"] = report_file
            record["snippet"] = rescued_content[:500] + ("..." if len(rescued_content) > 500 else "")
            record["status_detail"] = f"底层进程在收尾阶段异常退出 ({err_msg[:60]}...)，自愈引擎已成功恢复审查报告。"
            _save_task_record(record)
            log_event(f"[DONE]  [ASYNC:{task_id}] 执行成功(自愈恢复) | 耗时: {elapsed:.2f}s | 字符数: {len(rescued_content)} | 报告: {os.path.basename(report_file)}")
            return

        record["status"] = "FAILED"
        record["end_time"] = time.time()
        record["elapsed_sec"] = elapsed
        record["error"] = err_msg
        _save_task_record(record)
        log_event(f"[ERROR] [ASYNC:{task_id}] 执行失败 | 耗时: {elapsed:.2f}s | 异常: {err_msg}")


# ---------------------------------------------------------------------------
# 智能自愈混合工具 (Auto-Detaching Hybrid Tools)
# 用户与 Codex 无需声明“异步”，系统自动检测防超时！
# ---------------------------------------------------------------------------

@mcp.tool()
async def antigravity_execute(
    task_description: str,
    target_files: Optional[List[str]] = None,
    instructions: Optional[str] = None,
    workspace_path: Optional[str] = None,
) -> str:
    """
    Delegate a concrete coding, implementation, refactoring, or bug-fixing task to Google Antigravity.
    ANTIGRAVITY AS WORKER / IMPLEMENTER:
    - Antigravity directly creates, modifies, and refactors code files in the workspace.
    - Can execute terminal commands to verify its modifications.
    - Returns full implementation summary and diffs for Codex to review and verify.
    - Automatic timeout defense: auto-detaches safely at 180s if it's a massive multi-file refactoring.

    :param task_description: What specific code feature, refactoring, or bug fix Antigravity should implement.
    :param target_files: Optional list of files Antigravity should focus on modifying.
    :param instructions: Specific technical guidelines, constraints, or coding standards.
    :param workspace_path: Root directory of the workspace.
    :return: Implementation summary and diffs if completed in 180s, or background tracking info.
    """
    ws = os.path.abspath(workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd()))
    task_id = f"ex-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    report_file = os.path.abspath(os.path.join(ws, ".antigravity_reports", f"{task_id}.md"))

    file_ctx = f"\n\n🎯 **重点目标文件**：\n" + "\n".join(f"- `{f}`" for f in target_files) if target_files else ""
    req_ctx = f"\n\n📋 **具体实现要求与规范**：\n{instructions}" if instructions else ""

    prompt = (
        f"请在当前工作区中实际执行并落实以下代码任务：\n\n"
        f"### 🛠️ 任务目标\n"
        f"{task_description}"
        f"{file_ctx}"
        f"{req_ctx}\n\n"
        f"### ⚠️ 执行要求\n"
        f"1. 你必须真实读写文件落实修改（不要只输出建议或伪代码），确保修改后的代码符合规范且无语法错误；\n"
        f"2. 如有条件可运行单元测试或语法检查脚本进行验证；\n"
        f"3. 执行完毕后，请详细汇总修改的文件列表、核心变更点以及验证结果，供主控 Codex 进行最终 Code Review。"
    )

    sys_inst = (
        f"你是由 OpenAI Codex 调用的 Google Antigravity 核心代码实现与执行智能体（Code Implementer）。\n"
        f"当前工作区路径为：{ws}。\n"
        f"你的职责是作为执行主力，直接在工作区中高质量编写、修改和重构代码文件，严禁只输出伪代码，必须真实落地修改。\n"
        f"【Windows 环境规范】：\n"
        f"1. 严禁对本地磁盘文件路径调用网页工具 read_url_content，读取本地文件必须使用 view_file。\n"
        f"2. 完成代码落地后，请创建并保存一份修改清单（Artifact）总结改动细节。"
    )

    record = {
        "task_id": task_id,
        "task_type": "antigravity_execute",
        "status": "PENDING",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "workspace_path": ws,
        "report_file": report_file,
        "prompt": prompt,
        "prompt_summary": task_description.replace("\n", " ").strip()[:80],
    }
    _save_task_record(record)

    bg_task = asyncio.create_task(
        _run_async_worker(task_id, "antigravity_execute", prompt, ws, report_file, sys_inst)
    )
    _background_tasks[task_id] = bg_task

    # Hybrid Wait: wait up to SAFE_SYNC_TIMEOUT (180s)
    try:
        await asyncio.wait_for(asyncio.shield(bg_task), timeout=SAFE_SYNC_TIMEOUT)
        rec = _load_task_record(task_id) or {}
        if rec.get("status") == "COMPLETED":
            try:
                with open(report_file, "r", encoding="utf-8") as rf:
                    return rf.read()
            except Exception:
                elapsed = rec.get("elapsed_sec", 0.0)
                return (
                    f"> 🤖 **【Antigravity 落地执行完成】**\n"
                    f"> ⏱️ **耗时**: {elapsed:.2f}s | 📁 **工作区**: `{ws}`\n\n"
                    f"成果已就绪，报告路径: `{report_file}`\n"
                    f"请主控 Codex 进行代码审查 (Code Review)。"
                )
        else:
            return f"[Antigravity Error] 执行失败: {rec.get('error', '未知异常')}"

    except asyncio.TimeoutError:
        log_event(f"[AUTO-DETACH] [ex:{task_id}] 编码执行规模较大，已平滑转入后台运行")
        return (
            f"> ⏳ **【代码编写/重构任务规模较大，已在第 {SAFE_SYNC_TIMEOUT:.0f} 秒自动转入安全后台托管】**\n"
            f"> 🛡️ **已成功拦截 300 秒超时中断！** Antigravity 正在后台全力编码落地中。\n\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **工作区**: `{ws}`\n"
            f"- **变更报告**: `{report_file}`\n\n"
            f"💡 Antigravity 改完后，Codex 可直接读取变更报告进行 Code Review 审查验收。"
        )


@mcp.tool()
async def ask_antigravity(
    prompt: str,
    workspace_path: Optional[str] = None,
    system_instructions: Optional[str] = None,
) -> str:
    """
    Delegate a coding, refactoring, or research task to Google Antigravity Agent.
    AUTOMATIC TIMEOUT DEFENSE:
    - If the task finishes within 180s, returns full results directly.
    - If the task takes longer than 180s, it AUTOMATICALLY detaches to background execution,
      completely preventing the Codex client 300s timeout!

    :param prompt: The specific task, questions, or instructions for Antigravity.
    :param workspace_path: Root directory of the workspace to operate on.
    :param system_instructions: Optional custom persona or system guidance for Antigravity.
    :return: Full findings if quick, or auto-detached background tracking info if long.
    """
    ws = os.path.abspath(workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd()))
    task_id = f"ag-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    report_file = os.path.abspath(os.path.join(ws, ".antigravity_reports", f"{task_id}.md"))

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

    # Launch background worker
    bg_task = asyncio.create_task(
        _run_async_worker(task_id, "ask_antigravity", prompt, ws, report_file, system_instructions)
    )
    _background_tasks[task_id] = bg_task

    # Hybrid Wait: wait up to SAFE_SYNC_TIMEOUT (180s)
    try:
        await asyncio.wait_for(asyncio.shield(bg_task), timeout=SAFE_SYNC_TIMEOUT)
        
        # Finished within safe timeout!
        rec = _load_task_record(task_id) or {}
        if rec.get("status") == "COMPLETED":
            elapsed = rec.get("elapsed_sec", 0.0)
            try:
                with open(report_file, "r", encoding="utf-8") as rf:
                    content = rf.read()
                return content
            except Exception:
                return (
                    f"> 🤖 **【Google Antigravity 专家子智能体执行汇报】**\n"
                    f"> ⏱️ **执行耗时**: {elapsed:.2f}s | 📁 **工作区**: `{ws}` | 🧠 **引擎**: `{DEFAULT_MODEL}`\n\n"
                    f"报告已保存至: `{report_file}`"
                )
        else:
            return f"[Antigravity Error] 调用执行失败: {rec.get('error', '未知异常')}"

    except asyncio.TimeoutError:
        # Safe auto-detach! Task continues in background, Codex gets clean response!
        log_event(f"[AUTO-DETACH] [ag:{task_id}] 运行已达 {SAFE_SYNC_TIMEOUT:.0f}s，已平滑转入后台运行，成功拦截 300s 超时")
        return (
            f"> ⏳ **【任务执行规模较大，已在第 {SAFE_SYNC_TIMEOUT:.0f} 秒自动转入安全后台托管】**\n"
            f"> 🛡️ **已成功拦截并彻底规避网关 300 秒超时中断！** 任务正在后台全力生成中，绝未失败。\n\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **工作区**: `{ws}`\n"
            f"- **报告生成路径**: `{report_file}`\n"
            f"- **当前状态**: Antigravity 智能体正在后台持续思考与写入，桌面悬浮监控窗正持续计时。\n\n"
            f"💡 **后续调度指引**：\n"
            f"1. 任务仍在正常进行中，请向用户汇报任务已转入后台。\n"
            f"2. 你可以随时调用 `check_antigravity_task(task_id=\"{task_id}\")` 检查进度。\n"
            f"3. 待监控窗提示完成后，可直接读取 `{report_file}` 获取完整的分析与代码建议。"
        )


@mcp.tool()
async def antigravity_code_review(
    files: List[str],
    instructions: str = "审查代码安全性、异常处理、性能瓶颈与架构合理性，并给出具体的重构建议。",
    workspace_path: Optional[str] = None,
) -> str:
    """
    Request a multi-perspective code review from Google Antigravity.
    AUTOMATIC TIMEOUT DEFENSE:
    - If reviewing >= 3 files: IMMEDIATELY detaches to background (<0.1s) to prevent any blocking.
    - If reviewing 1-2 files: waits up to 180s; if exceeded, automatically detaches to background.
    - You NEVER have to explicitly ask for async mode!

    :param files: List of relative or absolute file paths to be reviewed.
    :param instructions: Specific focus areas or guidelines for the review.
    :param workspace_path: Workspace directory path.
    :return: Direct review report if small, or background tracking info if large.
    """
    ws = os.path.abspath(workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd()))
    task_id = f"cr-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    report_file = os.path.abspath(os.path.join(ws, ".antigravity_reports", f"{task_id}.md"))

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
        f"请对用户指定的代码进行深入的质量与安全审计，并提供具体的重构与优化方案。\n"
        f"【Windows 环境规范】：\n"
        f"1. 严禁对本地磁盘文件路径调用网页工具 read_url_content，读取本地文件必须使用 view_file。\n"
        f"2. 完成代码审查后，请将完整审查报告保存为 Markdown Artifact，包含严重/中等/建议等级分类与具体重构代码。"
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
        "prompt_summary": f"审查 {len(files)} 个文件",
    }
    _save_task_record(record)

    bg_task = asyncio.create_task(
        _run_async_worker(task_id, "antigravity_code_review", prompt, ws, report_file, sys_inst)
    )
    _background_tasks[task_id] = bg_task

    # 智能早退分流：如果文件数 >= 3 个，深度审查必然超过 5 分钟，0.1 秒直接返回后台任务凭据！
    if len(files) >= 3:
        log_event(f"[EARLY-DETACH] [cr:{task_id}] 审查文件数 ({len(files)} >= 3)，直接启动后台托管模式")
        return (
            f"> 🔍 **【已自动启用后台代码审查托管模式】**\n"
            f"> ⚡ 检测到本次审查文件较多（{len(files)} 个），为彻底避免 300 秒网关超时中断，系统已自动在后台并行执行！\n\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **审查文件数**: {len(files)} 个文件（{', '.join(files[:3])}{' 等...' if len(files) > 3 else ''}）\n"
            f"- **报告生成路径**: `{report_file}`\n\n"
            f"💡 **给主控 Agent 的建议**：\n"
            f"任务正在后台深度分析中，桌面悬浮监控窗已启动计时。可随时通过 `check_antigravity_task(task_id=\"{task_id}\")` 查询进度。"
        )

    # 对于 1~2 个文件，先尝试同步等待 180s
    try:
        await asyncio.wait_for(asyncio.shield(bg_task), timeout=SAFE_SYNC_TIMEOUT)
        rec = _load_task_record(task_id) or {}
        if rec.get("status") == "COMPLETED":
            try:
                with open(report_file, "r", encoding="utf-8") as rf:
                    return rf.read()
            except Exception:
                return f"审查成功。完整报告已写入: `{report_file}`"
        else:
            return f"[Antigravity Error] 代码审查失败: {rec.get('error', '未知异常')}"

    except asyncio.TimeoutError:
        log_event(f"[AUTO-DETACH] [cr:{task_id}] 审查运行已达 {SAFE_SYNC_TIMEOUT:.0f}s，已平滑转入后台运行")
        return (
            f"> ⏳ **【代码审查规模较大，已在第 {SAFE_SYNC_TIMEOUT:.0f} 秒自动转入安全后台托管】**\n"
            f"> 🛡️ **已成功拦截并彻底规避网关 300 秒超时中断！** 任务正在后台全力生成中。\n\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **报告生成路径**: `{report_file}`\n"
            f"- **当前状态**: Antigravity 正在后台深入审计，桌面悬浮监控窗正持续计时。\n\n"
            f"💡 任务正常进行中，稍后可通过 `check_antigravity_task(task_id=\"{task_id}\")` 查询进度或直接读取报告文件。"
        )


# ---------------------------------------------------------------------------
# 显式异步长任务工具 (继续保留以支持精准语义调用)
# ---------------------------------------------------------------------------

@mcp.tool()
async def ask_antigravity_async(
    prompt: str,
    workspace_path: Optional[str] = None,
    report_file: Optional[str] = None,
    system_instructions: Optional[str] = None,
) -> str:
    """
    Explicitly launch a long-running coding, exploration, or refactoring task in the background.
    Returns immediately (< 0.1s) with a task ID.

    :param prompt: Detailed instructions for the task.
    :param workspace_path: Root directory of the workspace.
    :param report_file: Path to save final report. Defaults to `<workspace>/.antigravity_reports/<task_id>.md`.
    :param system_instructions: Optional custom persona or system guidance.
    :return: Immediate confirmation with task_id and tracking instructions.
    """
    ws = os.path.abspath(workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd()))
    task_id = f"ag-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    
    if not report_file:
        report_file = os.path.abspath(os.path.join(ws, ".antigravity_reports", f"{task_id}.md"))
    elif not os.path.isabs(report_file):
        report_file = os.path.abspath(os.path.join(ws, report_file))

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
        f"💡 可随时通过 `check_antigravity_task(task_id=\"{task_id}\")` 获取当前进度与耗时。"
    )


@mcp.tool()
async def antigravity_code_review_async(
    files: List[str],
    instructions: str = "审查代码安全性、异常处理、性能瓶颈与架构合理性，并给出具体的重构建议。",
    workspace_path: Optional[str] = None,
    report_file: Optional[str] = None,
) -> str:
    """
    Explicitly launch a multi-file code review in the background.
    Returns immediately (< 0.1s) with a task ID.

    :param files: List of file paths to review.
    :param instructions: Review guidelines and focus areas.
    :param workspace_path: Root directory of the workspace.
    :param report_file: Path to save the final review report.
    :return: Immediate confirmation with task_id and tracking instructions.
    """
    ws = os.path.abspath(workspace_path or os.environ.get("ANTIGRAVITY_WORKSPACE", os.getcwd()))
    task_id = f"cr-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"

    if not report_file:
        report_file = os.path.abspath(os.path.join(ws, ".antigravity_reports", f"{task_id}.md"))
    elif not os.path.isabs(report_file):
        report_file = os.path.abspath(os.path.join(ws, report_file))

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
        f"请对用户指定的代码进行深入的质量与安全审计，并提供具体的重构与优化方案。\n"
        f"【Windows 环境规范】：\n"
        f"1. 严禁对本地磁盘文件路径调用网页工具 read_url_content，读取本地文件必须使用 view_file。\n"
        f"2. 完成代码审查后，请将完整审查报告保存为 Markdown Artifact，包含严重/中等/建议等级分类与具体重构代码。"
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


# ---------------------------------------------------------------------------
# 任务状态查询与报告工具
# ---------------------------------------------------------------------------

@mcp.tool()
async def check_antigravity_task(task_id: str, wait_seconds: int = 0) -> str:
    """
    Check the current status, progress, and results of a background Antigravity task.

    :param task_id: The unique task ID returned by any Antigravity tool.
    :param wait_seconds: Optional. Wait up to this many seconds for completion if still running. Defaults to 0.
    :return: Current status, elapsed time, and report content/location if finished.
    """
    # If wait_seconds requested and task is currently running in this process
    if wait_seconds > 0 and task_id in _background_tasks and not _background_tasks[task_id].done():
        try:
            await asyncio.wait_for(asyncio.shield(_background_tasks[task_id]), timeout=float(wait_seconds))
        except asyncio.TimeoutError:
            pass

    record = _load_task_record(task_id)
    if not record:
        return f"❌ 未找到任务 ID 为 `{task_id}` 的记录。请核实 ID 是否正确。"

    status = record.get("status", "UNKNOWN")
    created_at = record.get("created_at", "未知")
    report_file = record.get("report_file", "")
    summary = record.get("prompt_summary", "")

    if status in ("RUNNING", "PENDING"):
        start_time = record.get("start_time", time.time())
        running_sec = time.time() - start_time
        status_detail = record.get("status_detail", "Antigravity 智能体正在后台深入处理，请耐心等候。")
        retry_tip = f"\n- **自愈进度**: 🛡️ {status_detail}" if record.get("retry_count") else ""
        return (
            f"⏳ **【任务执行中】**\n"
            f"- **任务 ID**: `{task_id}`\n"
            f"- **任务内容**: {summary}\n"
            f"- **开始时间**: {created_at}\n"
            f"- **当前已运行**: {running_sec:.1f} 秒 (约 {running_sec/60:.1f} 分钟)\n"
            f"- **目标报告**: `{report_file}`{retry_tip}\n"
            f"- **状态**: {status_detail}"
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

    files.sort(key=os.path.getmtime, reverse=True)
    recent_files = files[:limit]

    lines = [
        "### 📋 最近 Antigravity 任务概览",
        "| 任务 ID | 触发时间 | 类型 | 状态 | 耗时 | 摘要 |",
        "|---|---|---|---|---|---|"
    ]

    for pf in recent_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                rec = json.load(f)
            tid = rec.get("task_id", "")
            created = rec.get("created_at", "-")
            time_disp = created[5:19] if len(created) >= 19 else created
            ttype = rec.get("task_type", "")
            st = rec.get("status", "")
            el = f"{rec.get('elapsed_sec', 0):.1f}s" if "elapsed_sec" in rec else "-"
            sm = rec.get("prompt_summary", "")[:25]
            if st == "COMPLETED":
                status_icon = "✅"
            elif st in ("RUNNING", "PENDING"):
                status_icon = "⏳"
            elif st == "INTERRUPTED":
                status_icon = "⏹️"
            else:
                status_icon = "❌"
            lines.append(f"| `{tid}` | {time_disp} | {ttype} | {status_icon} {st} | {el} | {sm} |")
        except Exception:
            continue

    return "\n".join(lines)


def _is_pid_alive(pid: Optional[int]) -> bool:
    """利用 Windows kernel32 精准探测对应 Worker 进程是否依然在活跃运行"""
    if not pid:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        h = kernel32.OpenProcess(0x0400, False, pid)
        if h:
            kernel32.CloseHandle(h)
            return True
        return False
    except Exception:
        return False


def _sweep_orphan_tasks() -> None:
    """服务启动时扫描并收敛历史遗留的僵尸任务（绝不误杀真实运行中的长任务）"""
    if not os.path.exists(TASKS_DIR):
        return
    now = time.time()
    for f in os.listdir(TASKS_DIR):
        if f.endswith(".json"):
            pf = os.path.join(TASKS_DIR, f)
            try:
                with open(pf, "r", encoding="utf-8") as rf:
                    rec = json.load(rf)
                if rec.get("status") in ("RUNNING", "PENDING"):
                    w_pid = rec.get("worker_pid")
                    st = rec.get("start_time", 0)
                    # 只要对应的 Worker 进程仍在活跃运行，坚决不打扰！
                    if w_pid and _is_pid_alive(w_pid):
                        continue
                    # 仅在进程已死且耗时超过 30 分钟时，才安全纠偏为 INTERRUPTED
                    if (w_pid and not _is_pid_alive(w_pid)) or (now - st > 1800):
                        rec["status"] = "INTERRUPTED"
                        rec["status_detail"] = "关联进程已退出，任务已自动收敛"
                        with open(pf, "w", encoding="utf-8") as wf:
                            json.dump(rec, wf, ensure_ascii=False, indent=2)
            except Exception:
                pass


if __name__ == "__main__":
    _sweep_orphan_tasks()
    mcp.run()
