"""
Antigravity Desktop Floating Monitor Widget v3.1 (Visual & Ergonomic Overhaul)
Provides a modern, lightweight, always-on-top status widget for monitoring
Codex -> Antigravity MCP calls in real time.

V3.1 Visual & Ergonomic Enhancements:
- Smart Dynamic Hover Transparency: Translucent at idle (0.85/0.70), wakes up to 0.98 on hover.
- Opacity Quick Switcher (🌓): Cycle through 100% / 85% / 70% with persistent config.
- Custom 6px Slim Dark Scrollbar: Completely replaces thick Win32 3D gray arrow scrollbars.
- Global Smooth Wheel Scrolling: Seamless mousewheel scrolling across the entire reader.
- Maximize / Restore (🗖/🗗) & Corner Resize Grip (⋰): For comfortable wide-screen reading.
- Crisp 1px Micro-Glow Border: High-contrast definition on dark editor backgrounds.
- Main Card Instant Actions: [👁️ 预览] [📄 打开] [📂 目录].
- Structured Task Cards & Clean Filtered Logs (Dual Tab).
- Long-Task Windows Balloon Notification + Sound (>60s).
"""

import os
import sys
import time
import re
import json
import base64
import subprocess
from datetime import datetime
import tkinter as tk
from tkinter import ttk

# Enable DPI awareness on Windows for crisp high-resolution rendering
try:
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

# Paths
CONFIG_FILE = os.path.expanduser("~/.codex/mcp_servers/widget_config.json")
TASKS_DIR = os.path.expanduser("~/.codex/mcp_servers/.tasks")

def resolve_log_file() -> str:
    if "ANTIGRAVITY_LOG_FILE" in os.environ:
        return os.environ["ANTIGRAVITY_LOG_FILE"]
    home_log = os.path.expanduser("~/.codex/mcp_servers/antigravity.log")
    if os.path.exists(home_log):
        return home_log
    repo_log = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_servers", "antigravity.log")
    if os.path.exists(repo_log):
        return repo_log
    return home_log

LOG_FILE = resolve_log_file()

# Modern Catppuccin Mocha / Dark Theme
BG_MAIN = "#1e1e2e"         # Main background
BG_HEADER = "#181825"       # Header bar
BG_CARD = "#252538"         # Status card background
BG_CARD_HOVER = "#2f2f45"   # Card hover
BG_BTN = "#313244"          # Action button background
BG_BTN_HOVER = "#45475a"    # Action button hover
BG_TAG = "#363a4f"          # Badge background
BORDER_COLOR = "#313244"    # Subtle 1px window border

TEXT_PRIMARY = "#cdd6f4"    # Main text
TEXT_MUTED = "#a6adc8"      # Subdued text
TEXT_HIGHLIGHT = "#f5e0dc"  # High contrast text

COLOR_IDLE = "#a6e3a1"      # Green
COLOR_BUSY = "#f9e2af"      # Amber/Yellow
COLOR_BUSY_ALT = "#fab387"  # Pulse Amber
COLOR_ERR = "#f38ba8"       # Red
COLOR_ACCENT = "#89b4fa"    # Blue
COLOR_PURPLE = "#cba6f7"    # Purple for reviews
COLOR_TEAL = "#94e2d5"      # Teal for architecture

SCALE_STEPS = [0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0]
DEFAULT_SCALE_INDEX = 2  # 1.15x by default
OPACITY_PRESETS = [0.65, 0.50, 0.75, 0.85, 1.0]  # 默认更高透明度档位 (65%/50%/75%/85%/100%)


# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def is_pid_running(pid: int) -> bool:
    """利用 Windows kernel32 精准判断指定 PID 是否依然在活跃运行"""
    if not pid:
        return False
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # SYNCHRONIZE (0x00100000) | PROCESS_QUERY_LIMITED_INFORMATION (0x1000)
        h = kernel32.OpenProcess(0x00101000, False, int(pid))
        if not h:
            return False
        try:
            res = kernel32.WaitForSingleObject(h, 0)
            if res == 258:  # WAIT_TIMEOUT -> 进程依然活跃运行中
                return True
            code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(h, ctypes.byref(code)):
                return code.value == 259  # STILL_ACTIVE
            return False
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return False


def open_report_file(file_path: str) -> bool:
    """在系统默认编辑器中打开报告（如 VS Code / Typora / Notepad 等）"""
    if not file_path:
        return False
    norm_path = os.path.abspath(file_path)
    if os.path.exists(norm_path):
        try:
            os.startfile(norm_path)
            return True
        except Exception as e:
            sys.stderr.write(f"[Open Error] {e}\n")
    return False


def reveal_in_explorer(file_path: str) -> bool:
    """在 Windows 资源管理器中打开并选中报告文件"""
    if not file_path:
        return False
    norm_path = os.path.abspath(file_path)
    try:
        if os.path.exists(norm_path):
            subprocess.Popen(['explorer.exe', f'/select,{os.path.normpath(norm_path)}'])
            return True
        elif os.path.exists(os.path.dirname(norm_path)):
            os.startfile(os.path.dirname(norm_path))
            return True
    except Exception as e:
        sys.stderr.write(f"[Explorer Error] {e}\n")
    return False


def send_win_notification(title: str, msg: str) -> None:
    """触发 Windows 原生气泡通知与温和提示音（长任务完成时异步触发）"""
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass

    try:
        clean_title = title.replace("'", " ").replace('"', " ")
        clean_msg = msg.replace("'", " ").replace('"', " ")
        ps_code = f"""
[void] [System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms')
$ni = New-Object System.Windows.Forms.NotifyIcon
$ni.Icon = [System.Drawing.SystemIcons]::Information
$ni.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Info
$ni.BalloonTipTitle = '{clean_title}'
$ni.BalloonTipText = '{clean_msg}'
$ni.Visible = $True
$ni.ShowBalloonTip(4000)
Start-Sleep -Seconds 1
$ni.Dispose()
"""
        encoded = base64.b64encode(ps_code.encode('utf-16le')).decode('utf-8')
        subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-WindowStyle', 'Hidden', '-EncodedCommand', encoded],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Custom 6px Slim Dark Scrollbar (极简平直暗黑滑块)
# ---------------------------------------------------------------------------

class SlimScrollbar(tk.Canvas):
    """
    极简平直 6px 暗黑滚动条，彻底替代 Windows 原生 Win32 粗灰底箭头滚动条
    """
    def __init__(self, parent, target_widget, width=6, bg=BG_CARD, thumb_color="#45475a", hover_color=COLOR_ACCENT):
        super().__init__(parent, width=width, bg=bg, bd=0, highlightthickness=0)
        self.target = target_widget
        self.width = width
        self.thumb_color = thumb_color
        self.hover_color = hover_color
        self.current_thumb_color = thumb_color
        self.first = 0.0
        self.last = 1.0
        self._drag_data = {"y": 0, "first": 0.0}

        self.bind("<Configure>", self.draw)
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

    def set(self, first, last):
        self.first = float(first)
        self.last = float(last)
        self.draw()

    def draw(self, event=None):
        self.delete("all")
        h = self.winfo_height()
        if h <= 1:
            return

        # Content fits entirely, no need to show scrollbar thumb
        if self.first <= 0.001 and self.last >= 0.999:
            return

        y1 = int(self.first * h)
        y2 = int(self.last * h)

        # Ensure minimum visible height for usability
        min_thumb_h = 24
        if y2 - y1 < min_thumb_h:
            y2 = min(h, y1 + min_thumb_h)
            if y2 == h:
                y1 = max(0, h - min_thumb_h)

        # Draw sleek flat rectangle thumb
        self.create_rectangle(
            1, y1, self.width - 1, y2,
            fill=self.current_thumb_color, outline="", tags="thumb"
        )

    def on_press(self, event):
        h = self.winfo_height()
        if h <= 0:
            return
        thumb_y1 = int(self.first * h)
        thumb_y2 = int(self.last * h)
        if not (thumb_y1 <= event.y <= thumb_y2):
            new_first = max(0.0, min(1.0, (event.y - 12) / float(h)))
            self.target.yview_moveto(new_first)
        self._drag_data["y"] = event.y
        self._drag_data["first"] = self.first

    def on_drag(self, event):
        h = self.winfo_height()
        if h <= 0:
            return
        dy = event.y - self._drag_data["y"]
        df = dy / float(h)
        new_first = max(0.0, min(1.0 - (self.last - self.first), self._drag_data["first"] + df))
        self.target.yview_moveto(new_first)

    def on_enter(self, event):
        self.current_thumb_color = self.hover_color
        self.draw()

    def on_leave(self, event):
        self.current_thumb_color = self.thumb_color
        self.draw()


# ---------------------------------------------------------------------------
# Lightweight Markdown Preview Window (With Maximize & Resize Grip)
# ---------------------------------------------------------------------------

def build_task_preview_markdown(t: dict) -> tuple[str, str]:
    """生成运行中、失败或已中止任务的富文本 Markdown 实时跟踪与排查报告"""
    tid = t.get("task_id", "")
    tid_short = tid[-8:] if tid else "未知"
    status = t.get("status", "UNKNOWN")
    created = t.get("created_at", "未知")
    label = t.get("task_type_label", "智能体任务")
    ws = t.get("workspace_path", "默认工作区")
    elapsed = t.get("elapsed_sec")
    if elapsed:
        elapsed_str = f"{elapsed:.1f} 秒"
    elif status == "INTERRUPTED":
        elapsed_str = "已中止"
    elif status == "FAILED":
        elapsed_str = "已异常中断"
    elif status == "COMPLETED":
        elapsed_str = "已完成"
    else:
        elapsed_str = "持续执行中..."
    detail = t.get("status_detail", "")
    last_err = t.get("last_error", "")
    prompt = t.get("prompt", "")

    # Status badge & title
    if status in ("RUNNING", "PENDING"):
        st_badge = "⏳ 正在分析执行中..."
        win_title = f"任务跟踪: [{tid_short}] 运行中"
    elif status == "FAILED":
        st_badge = "❌ 执行异常 / 失败"
        win_title = f"排查报告: [{tid_short}] 失败"
    elif status == "INTERRUPTED":
        st_badge = "⏹️ 任务已中止 (会话已结束或服务重启)"
        win_title = f"任务详情: [{tid_short}] 已中止"
    elif status == "COMPLETED":
        st_badge = "✅ 执行成功"
        win_title = f"成果预览: [{tid_short}] 成功"
    else:
        st_badge = f"ℹ️ {status}"
        win_title = f"任务详情: [{tid_short}]"

    # Extract matching logs from antigravity.log
    logs = []
    if os.path.exists(LOG_FILE) and tid:
        try:
            with open(LOG_FILE, "r", encoding="gb18030", errors="ignore") as f:
                for line in f:
                    if tid in line or (tid_short and tid_short in line):
                        logs.append(line.strip())
        except Exception:
            pass

    log_section = "\n".join(logs[-20:]) if logs else "暂无关联日志记录"

    md = f"""# 🤖 Antigravity 任务状态报告 [{tid_short}]

- **任务 ID**: `{tid}`
- **当前状态**: {st_badge}
- **任务类型**: {label}
- **触发时间**: {created}
- **执行耗时**: {elapsed_str}
- **工作区路径**: `{ws}`
- **目标报告**: `{rep or "无单独报告产物"}`

---

## 📌 当前进展与状态详情
> {detail or "任务正在后台有序处理中，或已处于收敛终止状态。"}

"""
    if last_err:
        md += f"""## ⚠️ 异常排查信息 (Error Trace)
```
{last_err}
```

---
"""

    if prompt:
        md += f"""## 📋 原始任务委托 (Prompt)
```text
{prompt}
```

---
"""
    elif summary:
        md += f"""## 📋 任务描述摘要
> {summary}

---
"""

    md += f"""## 📜 关联运行日志流 (Task Logs)
```log
{log_section}
```
"""
    return win_title, md


class MarkdownPreviewWindow:
    """内置极简轻量级 Markdown 查阅弹窗（现代化暗黑风格）"""
    _current_instance = None

    @classmethod
    def show_content(cls, parent, title: str, markdown_content: str, file_path: str = ""):
        if cls._current_instance and cls._current_instance.window.winfo_exists():
            cls._current_instance.load_markdown(title, markdown_content, file_path)
            cls._current_instance.window.lift()
            return
        cls._current_instance = MarkdownPreviewWindow(parent, file_path, title=title, content=markdown_content)

    @classmethod
    def show(cls, parent, file_path: str):
        if cls._current_instance and cls._current_instance.window.winfo_exists():
            cls._current_instance.load_file(file_path)
            cls._current_instance.window.lift()
            return
        cls._current_instance = MarkdownPreviewWindow(parent, file_path)

    def __init__(self, parent, file_path: str = "", title: str = "", content: str = ""):
        self.parent = parent
        self.file_path = file_path or ""
        self.custom_title = title
        self.custom_content = content
        self.window = tk.Toplevel(parent)
        self.window.title("Antigravity 报告与状态查阅")
        self.window.configure(
            bg=BG_MAIN,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=BORDER_COLOR
        )
        self.window.attributes("-topmost", True)
        self.window.attributes("-alpha", 0.97)

        # Normal size & position
        self.base_w = 600
        self.base_h = 500
        self.is_maximized = False
        self.normal_geom = None

        px = parent.winfo_x() - self.base_w - 15
        py = parent.winfo_y()
        if px < 20:
            px = parent.winfo_x() + parent.winfo_width() + 15
        screen_w = parent.winfo_screenwidth()
        if px + self.base_w > screen_w:
            px = max(20, screen_w - self.base_w - 20)

        self.window.geometry(f"{self.base_w}x{self.base_h}+{px}+{py}")

        # Drag state
        self._offset_x = 0
        self._offset_y = 0

        # Resize grip drag state
        self._grip_start_x = 0
        self._grip_start_y = 0
        self._grip_start_w = 0
        self._grip_start_h = 0

        self.setup_ui()
        if self.custom_content:
            self.load_markdown(self.custom_title or "任务状态详情", self.custom_content, self.file_path)
        elif self.file_path:
            self.load_file(self.file_path)

        # Global smooth mousewheel binding across the whole preview window
        self.window.bind("<MouseWheel>", self.on_global_mousewheel)

    def setup_ui(self):
        # 1. Title Header
        self.header = tk.Frame(self.window, bg=BG_HEADER, height=34)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        self.header.bind("<ButtonPress-1>", self.start_drag)
        self.header.bind("<B1-Motion>", self.do_drag)

        self.title_lbl = tk.Label(
            self.header, text=" 👁️ 报告查阅",
            font=("Microsoft YaHei", 9, "bold"), bg=BG_HEADER, fg=COLOR_ACCENT
        )
        self.title_lbl.pack(side="left", padx=8)
        self.title_lbl.bind("<ButtonPress-1>", self.start_drag)
        self.title_lbl.bind("<B1-Motion>", self.do_drag)

        # Header right action buttons: Close, Maximize/Restore, External Open
        self.btn_close = tk.Label(
            self.header, text="✕", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=8
        )
        self.btn_close.pack(side="right")
        self.btn_close.bind("<Button-1>", lambda e: self.window.destroy())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.configure(fg=COLOR_ERR))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.configure(fg=TEXT_MUTED))

        self.btn_max = tk.Label(
            self.header, text="🗖", font=("Microsoft YaHei", 8),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=6
        )
        self.btn_max.pack(side="right")
        self.btn_max.bind("<Button-1>", self.toggle_maximize)
        self.btn_max.bind("<Enter>", lambda e: self.btn_max.configure(fg=COLOR_ACCENT))
        self.btn_max.bind("<Leave>", lambda e: self.btn_max.configure(fg=TEXT_MUTED))

        self.btn_min = tk.Label(
            self.header, text="—", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=6
        )
        self.btn_min.pack(side="right")
        self.btn_min.bind("<Button-1>", lambda e: self.window.iconify())
        self.btn_min.bind("<Enter>", lambda e: self.btn_min.configure(fg=COLOR_ACCENT))
        self.btn_min.bind("<Leave>", lambda e: self.btn_min.configure(fg=TEXT_MUTED))

        self.btn_open_ext = tk.Label(
            self.header, text="在外部编辑器打开 ↗", font=("Microsoft YaHei", 8),
            bg=BG_BTN, fg=TEXT_PRIMARY, cursor="hand2", padx=6, pady=2
        )
        self.btn_open_ext.pack(side="right", padx=6, pady=4)
        self.btn_open_ext.bind("<Button-1>", lambda e: open_report_file(self.file_path))
        self.btn_open_ext.bind("<Enter>", lambda e: self.btn_open_ext.configure(bg=BG_BTN_HOVER, fg=COLOR_ACCENT))
        self.btn_open_ext.bind("<Leave>", lambda e: self.btn_open_ext.configure(bg=BG_BTN, fg=TEXT_PRIMARY))

        # 2. Body with Text + Custom 6px Slim Dark Scrollbar
        self.content_frame = tk.Frame(self.window, bg=BG_MAIN, padx=8, pady=6)
        self.content_frame.pack(fill="both", expand=True)

        # Text Area
        self.text_area = tk.Text(
            self.content_frame,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            insertbackground=COLOR_ACCENT,
            font=("Consolas", 9),
            wrap="word",
            padx=10,
            pady=10,
            relief="flat",
            highlightthickness=0
        )
        self.text_area.pack(side="left", fill="both", expand=True)

        # Custom Slim Scrollbar (6px width, no bulky arrows)
        self.scrollbar = SlimScrollbar(
            self.content_frame,
            target_widget=self.text_area,
            width=6,
            bg=BG_CARD,
            thumb_color="#45475a",
            hover_color=COLOR_ACCENT
        )
        self.scrollbar.pack(side="right", fill="y", padx=(2, 0))
        self.text_area.configure(yscrollcommand=self.scrollbar.set)

        # Configure markdown styling tags
        self.text_area.tag_configure("h1", font=("Microsoft YaHei", 12, "bold"), foreground=COLOR_ACCENT, spacing3=6)
        self.text_area.tag_configure("h2", font=("Microsoft YaHei", 10, "bold"), foreground=COLOR_PURPLE, spacing3=4)
        self.text_area.tag_configure("h3", font=("Microsoft YaHei", 9, "bold"), foreground=COLOR_TEAL, spacing3=3)
        self.text_area.tag_configure("bold", font=("Consolas", 9, "bold"), foreground=TEXT_HIGHLIGHT)
        self.text_area.tag_configure("code", font=("Consolas", 9), foreground=COLOR_IDLE, background="#1b1d2b")
        self.text_area.tag_configure("bullet", foreground=COLOR_ACCENT)

        # 3. Footer Bar with Status & Resize Grip
        self.footer = tk.Frame(self.window, bg=BG_HEADER, height=20)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)

        self.footer_lbl = tk.Label(
            self.footer, text="支持鼠标滚轮平滑滚动 | 拖拽右下角手柄缩放",
            font=("Microsoft YaHei", 7), bg=BG_HEADER, fg=TEXT_MUTED
        )
        self.footer_lbl.pack(side="left", padx=8)

        # Bottom-right Resize Grip (⋰)
        self.resize_grip = tk.Label(
            self.footer, text="⋰", font=("Consolas", 9, "bold"),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="size_nw_se", padx=4
        )
        self.resize_grip.pack(side="right")
        self.resize_grip.bind("<ButtonPress-1>", self.start_resize)
        self.resize_grip.bind("<B1-Motion>", self.do_resize)
        self.resize_grip.bind("<Enter>", lambda e: self.resize_grip.configure(fg=COLOR_ACCENT))
        self.resize_grip.bind("<Leave>", lambda e: self.resize_grip.configure(fg=TEXT_MUTED))

    def _render_markdown_lines(self, lines):
        in_code_block = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                self.text_area.insert("end", line, "code")
            elif in_code_block:
                self.text_area.insert("end", line, "code")
            elif line.startswith("# "):
                self.text_area.insert("end", line, "h1")
            elif line.startswith("## "):
                self.text_area.insert("end", line, "h2")
            elif line.startswith("### "):
                self.text_area.insert("end", line, "h3")
            elif stripped.startswith("> "):
                self.text_area.insert("end", line, "bullet")
            elif stripped.startswith("- ") or stripped.startswith("* "):
                self.text_area.insert("end", line, "bullet")
            else:
                self.text_area.insert("end", line)

    def load_file(self, file_path: str):
        self.file_path = file_path or ""
        fname = os.path.basename(file_path) if file_path else "未命名报告"
        self.title_lbl.configure(text=f" 👁️ 报告预览: {fname}")
        if file_path and os.path.exists(file_path):
            self.btn_open_ext.pack(side="right", padx=6, pady=4)
        else:
            self.btn_open_ext.pack_forget()

        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")

        if not file_path or not os.path.exists(file_path):
            self.text_area.insert("end", f"⚠️ 报告文件尚未在本地找到：\n{file_path}\n\n可能任务正在后台生成或已移动。")
            self.text_area.configure(state="disabled")
            return

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            self._render_markdown_lines(lines)
        except Exception as e:
            self.text_area.insert("end", f"读取文件异常: {e}")

        self.text_area.configure(state="disabled")

    def load_markdown(self, title: str, content: str, file_path: str = ""):
        self.file_path = file_path or ""
        self.title_lbl.configure(text=f" 👁️ {title}")
        if self.file_path and os.path.exists(self.file_path):
            self.btn_open_ext.pack(side="right", padx=6, pady=4)
        else:
            self.btn_open_ext.pack_forget()

        self.text_area.configure(state="normal")
        self.text_area.delete("1.0", "end")
        self._render_markdown_lines(content.splitlines(keepends=True))
        self.text_area.configure(state="disabled")

    def on_global_mousewheel(self, event):
        """全局平滑鼠标滚轮监听"""
        if event.delta:
            units = -1 * int(event.delta / 120) * 3
            self.text_area.yview_scroll(units, "units")
            return "break"

    def toggle_maximize(self, event=None):
        """最大化 / 还原切换"""
        if not self.is_maximized:
            self.normal_geom = self.window.geometry()
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            w = min(1050, sw - 80)
            h = min(820, sh - 90)
            x = max(20, (sw - w) // 2)
            y = max(30, (sh - h) // 2)
            self.window.geometry(f"{w}x{h}+{x}+{y}")
            self.btn_max.configure(text="🗗")
            self.is_maximized = True
        else:
            if self.normal_geom:
                self.window.geometry(self.normal_geom)
            self.btn_max.configure(text="🗖")
            self.is_maximized = False

    def start_drag(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def do_drag(self, event):
        x = self.window.winfo_x() + (event.x - self._offset_x)
        y = self.window.winfo_y() + (event.y - self._offset_y)
        self.window.geometry(f"+{x}+{y}")

    def start_resize(self, event):
        self._grip_start_x = event.x_root
        self._grip_start_y = event.y_root
        self._grip_start_w = self.window.winfo_width()
        self._grip_start_h = self.window.winfo_height()

    def do_resize(self, event):
        dx = event.x_root - self._grip_start_x
        dy = event.y_root - self._grip_start_y
        new_w = max(420, self._grip_start_w + dx)
        new_h = max(320, self._grip_start_h + dy)
        cur_x = self.window.winfo_x()
        cur_y = self.window.winfo_y()
        self.window.geometry(f"{new_w}x{new_h}+{cur_x}+{cur_y}")


# ---------------------------------------------------------------------------
# Main Antigravity Widget
# ---------------------------------------------------------------------------

class AntigravityWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("Antigravity 监控")

        # Configuration & Scale
        self.config = self.load_config()
        self.scale_idx = self.config.get("scale_index", DEFAULT_SCALE_INDEX)
        if self.scale_idx < 0 or self.scale_idx >= len(SCALE_STEPS):
            self.scale_idx = DEFAULT_SCALE_INDEX
        self.font_scale = SCALE_STEPS[self.scale_idx]

        # Smart Hover Transparency settings (默认更高透明度 0.65)
        self.base_alpha = float(self.config.get("base_alpha", 0.65))
        if self.base_alpha not in OPACITY_PRESETS:
            self.base_alpha = 0.65

        # Base dimensions
        self.base_width = 380
        self.base_height_compact = 172
        self.base_height_expanded = 580
        self.custom_expanded_h = None
        self.is_expanded = False
        self.is_topmost = True
        self.is_minimized = False
        self.is_mini_mode = False
        self.saved_geometry = None
        self.active_tab = "cards"  # 'cards' | 'logs'

        # Window setup with 1px micro-border
        w = int(self.base_width * self.font_scale)
        h = int(self.base_height_compact * self.font_scale)
        screen_w = self.root.winfo_screenwidth()
        x = max(20, screen_w - w - 25)
        y = 45
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.configure(
            bg=BG_MAIN,
            highlightthickness=1,
            highlightbackground=BORDER_COLOR,
            highlightcolor=BORDER_COLOR
        )
        self.root.overrideredirect(True)  # Frameless floating
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self.base_alpha)
        self.root.lift()

        # Drag state
        self._offset_x = 0
        self._offset_y = 0

        # Resize grip drag state for main window
        self._grip_start_x = 0
        self._grip_start_y = 0
        self._grip_start_w = 0
        self._grip_start_h = 0

        # State tracking
        self.current_state = "IDLE"  # IDLE | BUSY | RETRY | ERROR
        self.start_timestamp = 0.0
        self.last_log_mtime = 0.0
        self.last_tasks_sig = (0, 0.0)
        self._last_busy_check = 0.0
        self.last_notified_task_id = None
        self.pulse_phase = 0
        self.pulse_timer_active = False
        self.latest_report_file = None
        self.latest_task = None

        self.setup_ui()
        self.apply_font_scale()
        self.poll_state()
        self.update_breathing_and_timer()

        # Keyboard / Mouse bindings
        self.root.bind("<Control-MouseWheel>", self.on_ctrl_wheel)

        # Smart Dynamic Hover Transparency (移入 0.98 清晰，移出恢复 base_alpha)
        self.root.bind("<Enter>", self.on_hover_enter)
        self.root.bind("<Leave>", self.on_hover_leave)

        # Windows Taskbar Restore Mapping
        self.root.bind("<Map>", self.on_window_map)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"scale_index": DEFAULT_SCALE_INDEX, "base_alpha": 0.65}

    def save_config(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "scale_index": self.scale_idx,
                    "base_alpha": self.base_alpha
                }, f)
        except Exception:
            pass

    # -----------------------------------------------------------------------
    # Hover Transparency & Opacity Cycling
    # -----------------------------------------------------------------------

    def on_hover_enter(self, event):
        """鼠标悬停唤醒：适度提高清晰度，并激活全域鼠标滚轮监听"""
        hover_alpha = min(0.92, max(0.82, self.base_alpha + 0.20))
        self.root.attributes("-alpha", hover_alpha)
        self.root.bind_all("<MouseWheel>", self.on_panel_mousewheel)

    def on_hover_leave(self, event):
        """鼠标离开恢复：退回轻透防遮挡基准状态，释放全域滚轮"""
        try:
            x, y = self.root.winfo_pointerx(), self.root.winfo_pointery()
            wx, wy = self.root.winfo_x(), self.root.winfo_y()
            ww, wh = self.root.winfo_width(), self.root.winfo_height()
            if not (wx <= x <= wx + ww and wy <= y <= wy + wh):
                self.root.attributes("-alpha", self.base_alpha)
                self.root.unbind_all("<MouseWheel>")
        except Exception:
            self.root.attributes("-alpha", self.base_alpha)
            self.root.unbind_all("<MouseWheel>")

    def on_panel_mousewheel(self, event):
        """全域丝滑鼠标滚轮分发"""
        if event.state & 0x0004:
            self.on_ctrl_wheel(event)
            return "break"
        if not self.is_expanded:
            return
        if self.active_tab == "cards":
            if event.delta and hasattr(self, "cards_canvas"):
                delta = event.delta
                units = -1 * int(delta / 40) if abs(delta) >= 40 else (-2 if delta > 0 else 2)
                self.cards_canvas.yview_scroll(units, "units")
                return "break"
        elif self.active_tab == "logs":
            if event.delta and hasattr(self, "history_box"):
                delta = event.delta
                units = -1 * int(delta / 40) if abs(delta) >= 40 else (-2 if delta > 0 else 2)
                self.history_box.yview_scroll(units, "units")
                return "break"


    def cycle_opacity(self, event=None):
        """循环切换基准透明度档位：85% -> 70% -> 100% -> 85%"""
        idx = OPACITY_PRESETS.index(self.base_alpha) if self.base_alpha in OPACITY_PRESETS else 0
        new_idx = (idx + 1) % len(OPACITY_PRESETS)
        self.base_alpha = OPACITY_PRESETS[new_idx]
        self.root.attributes("-alpha", self.base_alpha)
        self.save_config()

        pct = int(self.base_alpha * 100)
        self.btn_opacity.configure(text=f"🌓{pct}%")

    # -----------------------------------------------------------------------
    # UI Setup
    # -----------------------------------------------------------------------

    def setup_ui(self):
        # 1. Custom Header (Draggable)
        self.header = tk.Frame(self.root, bg=BG_HEADER, height=32)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        self.header.bind("<ButtonPress-1>", self.start_drag)
        self.header.bind("<B1-Motion>", self.do_drag)
        self.header.bind("<Double-Button-1>", self.toggle_mini_mode)

        self.title_lbl = tk.Label(
            self.header,
            text=" 🤖 Antigravity 监控",
            font=("Microsoft YaHei", 9, "bold"),
            bg=BG_HEADER,
            fg=TEXT_PRIMARY,
            cursor="fleur"
        )
        self.title_lbl.pack(side="left", padx=6, pady=3)
        self.title_lbl.bind("<ButtonPress-1>", self.start_drag)
        self.title_lbl.bind("<B1-Motion>", self.do_drag)
        self.title_lbl.bind("<Double-Button-1>", self.toggle_mini_mode)

        # Header buttons (Right to Left)
        self.btn_close = tk.Label(
            self.header, text="✕", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=6
        )
        self.btn_close.pack(side="right")
        self.btn_close.bind("<Button-1>", lambda e: self.root.destroy())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.configure(fg=COLOR_ERR, bg=BG_BTN_HOVER))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.configure(fg=TEXT_MUTED, bg=BG_HEADER))

        # 最小化按钮 (—): 左键最小化到任务栏，右键折叠为微型悬浮胶囊
        self.btn_min = tk.Label(
            self.header, text="—", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=6
        )
        self.btn_min.pack(side="right")
        self.btn_min.bind("<Button-1>", self.minimize_window)
        self.btn_min.bind("<Button-3>", self.toggle_mini_mode)
        self.btn_min.bind("<Enter>", lambda e: self.btn_min.configure(fg=COLOR_ACCENT, bg=BG_BTN_HOVER))
        self.btn_min.bind("<Leave>", lambda e: self.btn_min.configure(fg=TEXT_MUTED, bg=BG_HEADER))

        self.btn_pin = tk.Label(
            self.header, text="📌", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=COLOR_ACCENT, cursor="hand2", padx=4
        )
        self.btn_pin.pack(side="right")
        self.btn_pin.bind("<Button-1>", self.toggle_topmost)

        # Opacity Switcher Button (🌓)
        pct = int(self.base_alpha * 100)
        self.btn_opacity = tk.Label(
            self.header, text=f"🌓{pct}%", font=("Microsoft YaHei", 7),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=4
        )
        self.btn_opacity.pack(side="right")
        self.btn_opacity.bind("<Button-1>", self.cycle_opacity)
        self.btn_opacity.bind("<Enter>", lambda e: self.btn_opacity.configure(fg=COLOR_ACCENT))
        self.btn_opacity.bind("<Leave>", lambda e: self.btn_opacity.configure(fg=TEXT_MUTED))

        self.btn_reset = tk.Label(
            self.header, text="🔄", font=("Microsoft YaHei", 8),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=4
        )
        self.btn_reset.pack(side="right")
        self.btn_reset.bind("<Button-1>", self.reset_state_manually)
        self.btn_reset.bind("<Enter>", lambda e: self.btn_reset.configure(fg=TEXT_PRIMARY))
        self.btn_reset.bind("<Leave>", lambda e: self.btn_reset.configure(fg=TEXT_MUTED))

        self.btn_zoom_in = tk.Label(
            self.header, text="A+", font=("Microsoft YaHei", 8, "bold"),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=4
        )
        self.btn_zoom_in.pack(side="right")
        self.btn_zoom_in.bind("<Button-1>", lambda e: self.change_zoom(1))
        self.btn_zoom_in.bind("<Enter>", lambda e: self.btn_zoom_in.configure(fg=COLOR_ACCENT))
        self.btn_zoom_in.bind("<Leave>", lambda e: self.btn_zoom_in.configure(fg=TEXT_MUTED))

        self.btn_zoom_out = tk.Label(
            self.header, text="A-", font=("Microsoft YaHei", 8, "bold"),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=4
        )
        self.btn_zoom_out.pack(side="right")
        self.btn_zoom_out.bind("<Button-1>", lambda e: self.change_zoom(-1))
        self.btn_zoom_out.bind("<Enter>", lambda e: self.btn_zoom_out.configure(fg=COLOR_ACCENT))
        self.btn_zoom_out.bind("<Leave>", lambda e: self.btn_zoom_out.configure(fg=TEXT_MUTED))

        # 2. Main Card Body
        self.body = tk.Frame(self.root, bg=BG_MAIN, padx=12, pady=6)
        self.body.pack(fill="x", expand=False)

        # Status Row: Dot + Status Text + Live Timer
        self.status_row = tk.Frame(self.body, bg=BG_MAIN)
        self.status_row.pack(fill="x")

        self.status_dot = tk.Label(
            self.status_row, text="●", font=("Segoe UI", 12),
            bg=BG_MAIN, fg=COLOR_IDLE
        )
        self.status_dot.pack(side="left")

        self.status_text = tk.Label(
            self.status_row, text="空闲待命", font=("Microsoft YaHei", 10, "bold"),
            bg=BG_MAIN, fg=COLOR_IDLE
        )
        self.status_text.pack(side="left", padx=(4, 8))

        self.timer_label = tk.Label(
            self.status_row, text="", font=("Consolas", 10, "bold"),
            bg=BG_MAIN, fg=COLOR_BUSY
        )
        self.timer_label.pack(side="right")

        # Task Summary Line
        self.task_lbl = tk.Label(
            self.body, text="最近任务: 待命中",
            font=("Microsoft YaHei", 8), bg=BG_MAIN, fg=TEXT_PRIMARY,
            anchor="w", justify="left"
        )
        self.task_lbl.pack(fill="x", pady=(3, 2))

        # Main Card Quick Actions Bar (常驻成果操作区)
        self.quick_action_bar = tk.Frame(self.body, bg=BG_CARD, padx=6, pady=4)
        self.quick_action_bar.pack(fill="x", pady=(3, 3))

        self.quick_rep_lbl = tk.Label(
            self.quick_action_bar, text="报告就绪: 暂无",
            font=("Microsoft YaHei", 8), bg=BG_CARD, fg=TEXT_MUTED, anchor="w"
        )
        self.quick_rep_lbl.pack(side="left", fill="x", expand=True)

        self.btn_main_preview = tk.Label(
            self.quick_action_bar, text="👁️ 预览", font=("Microsoft YaHei", 8, "bold"),
            bg=BG_BTN, fg=COLOR_ACCENT, cursor="hand2", padx=5, pady=2
        )
        self.btn_main_preview.pack(side="right", padx=(2, 0))
        self.btn_main_preview.bind("<Button-1>", lambda e: self.on_preview_task(self.latest_task))
        self.btn_main_preview.bind("<Enter>", lambda e: self.btn_main_preview.configure(bg=BG_BTN_HOVER))
        self.btn_main_preview.bind("<Leave>", lambda e: self.btn_main_preview.configure(bg=BG_BTN))

        self.btn_main_open = tk.Label(
            self.quick_action_bar, text="📄 打开", font=("Microsoft YaHei", 8, "bold"),
            bg=BG_BTN, fg=COLOR_IDLE, cursor="hand2", padx=5, pady=2
        )
        self.btn_main_open.pack(side="right", padx=(2, 2))
        self.btn_main_open.bind("<Button-1>", lambda e: open_report_file(self.latest_report_file))
        self.btn_main_open.bind("<Enter>", lambda e: self.btn_main_open.configure(bg=BG_BTN_HOVER))
        self.btn_main_open.bind("<Leave>", lambda e: self.btn_main_open.configure(bg=BG_BTN))

        self.btn_main_reveal = tk.Label(
            self.quick_action_bar, text="📂 目录", font=("Microsoft YaHei", 8),
            bg=BG_BTN, fg=TEXT_PRIMARY, cursor="hand2", padx=5, pady=2
        )
        self.btn_main_reveal.pack(side="right", padx=(2, 2))
        self.btn_main_reveal.bind("<Button-1>", lambda e: reveal_in_explorer(self.latest_report_file))
        self.btn_main_reveal.bind("<Enter>", lambda e: self.btn_main_reveal.configure(bg=BG_BTN_HOVER))
        self.btn_main_reveal.bind("<Leave>", lambda e: self.btn_main_reveal.configure(bg=BG_BTN))

        # Bottom Bar: Expand Toggle Button
        self.bottom_bar = tk.Frame(self.body, bg=BG_MAIN)
        self.bottom_bar.pack(fill="x", pady=(3, 0))

        self.expand_btn = tk.Label(
            self.bottom_bar, text="▼ 查看最近调用历史", font=("Microsoft YaHei", 8),
            bg=BG_CARD, fg=COLOR_ACCENT, cursor="hand2", padx=6, pady=2
        )
        self.expand_btn.pack(side="left")
        self.expand_btn.bind("<Button-1>", self.toggle_expand)

        self.engine_mini_lbl = tk.Label(
            self.bottom_bar, text="3.8 -> [Sol/DS/GLM] -> 2.5", font=("Microsoft YaHei", 8),
            bg=BG_MAIN, fg=COLOR_TEAL
        )
        self.engine_mini_lbl.pack(side="right")

        # 3. Expanded Panel (Collapsible)
        self.history_frame = tk.Frame(self.root, bg=BG_HEADER, padx=8, pady=6)

        # Tab bar in expanded panel
        self.tab_bar = tk.Frame(self.history_frame, bg=BG_HEADER)
        self.tab_bar.pack(fill="x", pady=(0, 4))

        self.tab_cards = tk.Label(
            self.tab_bar, text="📋 任务列表", font=("Microsoft YaHei", 8, "bold"),
            bg=BG_CARD, fg=COLOR_ACCENT, cursor="hand2", padx=8, pady=2
        )
        self.tab_cards.pack(side="left", padx=(0, 4))
        self.tab_cards.bind("<Button-1>", lambda e: self.switch_tab("cards"))

        self.tab_logs = tk.Label(
            self.tab_bar, text="📜 纯净日志", font=("Microsoft YaHei", 8),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=8, pady=2
        )
        self.tab_logs.pack(side="left")
        self.tab_logs.bind("<Button-1>", lambda e: self.switch_tab("logs"))

        # Container for Tab 1: Structured Task Cards with Canvas & 6px SlimScrollbar
        self.cards_tab_frame = tk.Frame(self.history_frame, bg=BG_HEADER)
        self.cards_tab_frame.pack(fill="both", expand=True)

        self.cards_canvas = tk.Canvas(
            self.cards_tab_frame, bg=BG_HEADER, bd=0, highlightthickness=0
        )
        self.cards_canvas.pack(side="left", fill="both", expand=True)

        self.cards_scrollbar = SlimScrollbar(
            self.cards_tab_frame, target_widget=self.cards_canvas, width=6,
            bg=BG_HEADER, thumb_color="#45475a", hover_color=COLOR_ACCENT
        )
        self.cards_scrollbar.pack(side="right", fill="y", padx=(2, 0))
        self.cards_canvas.configure(yscrollcommand=self.cards_scrollbar.set)

        self.cards_container = tk.Frame(self.cards_canvas, bg=BG_HEADER)
        self.cards_window_id = self.cards_canvas.create_window((0, 0), window=self.cards_container, anchor="nw")

        self.cards_container.bind("<Configure>", self._on_cards_configure)
        self.cards_canvas.bind("<Configure>", self._on_canvas_configure)

        # Container for Tab 2: Clean Log Box
        self.logs_container = tk.Frame(self.history_frame, bg=BG_HEADER)

        self.history_box = tk.Text(
            self.logs_container, bg=BG_CARD, fg=TEXT_PRIMARY,
            font=("Consolas", 8), relief="flat", wrap="word",
            padx=6, pady=6, highlightthickness=0
        )
        self.history_box.pack(side="left", fill="both", expand=True)

        # Slim scrollbar for log box too!
        self.log_scrollbar = SlimScrollbar(
            self.logs_container, target_widget=self.history_box, width=6,
            bg=BG_CARD, thumb_color="#45475a", hover_color=COLOR_ACCENT
        )
        self.log_scrollbar.pack(side="right", fill="y", padx=(2, 0))
        self.history_box.configure(yscrollcommand=self.log_scrollbar.set)
        self.history_box.configure(state="disabled")

        # Setup log tags
        self.history_box.tag_configure("tag_done", foreground=COLOR_IDLE, font=("Consolas", 8, "bold"))
        self.history_box.tag_configure("tag_start", foreground=COLOR_ACCENT, font=("Consolas", 8, "bold"))
        self.history_box.tag_configure("tag_retry", foreground="#F59E0B", font=("Consolas", 8, "bold"))
        self.history_box.tag_configure("tag_err", foreground=COLOR_ERR, font=("Consolas", 8, "bold"))
        self.history_box.tag_configure("tag_time", foreground=TEXT_MUTED)

        # 4. Expanded Panel Footer with Resize Grip (⋰)
        self.history_footer = tk.Frame(self.history_frame, bg=BG_HEADER, height=18)
        self.history_footer.pack(fill="x", side="bottom", pady=(3, 0))
        self.history_footer.pack_propagate(False)

        self.footer_tip = tk.Label(
            self.history_footer, text="支持滚轮平滑滚动 | 拖拽右下角 ⋰ 缩放",
            font=("Microsoft YaHei", 7), bg=BG_HEADER, fg=TEXT_MUTED
        )
        self.footer_tip.pack(side="left", padx=4)

        self.resize_grip = tk.Label(
            self.history_footer, text="⋰", font=("Consolas", 8, "bold"),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="size_nw_se", padx=4
        )
        self.resize_grip.pack(side="right")
        self.resize_grip.bind("<ButtonPress-1>", self.start_resize)
        self.resize_grip.bind("<B1-Motion>", self.do_resize)
        self.resize_grip.bind("<Enter>", lambda e: self.resize_grip.configure(fg=COLOR_ACCENT))
        self.resize_grip.bind("<Leave>", lambda e: self.resize_grip.configure(fg=TEXT_MUTED))

    # -----------------------------------------------------------------------
    # Dynamic Scaling & Window Resizing
    # -----------------------------------------------------------------------

    def change_zoom(self, delta):
        new_idx = self.scale_idx + delta
        if 0 <= new_idx < len(SCALE_STEPS):
            self.scale_idx = new_idx
            self.font_scale = SCALE_STEPS[self.scale_idx]
            self.save_config()
            self.apply_font_scale()

    def on_ctrl_wheel(self, event):
        if event.delta > 0:
            self.change_zoom(1)
        elif event.delta < 0:
            self.change_zoom(-1)

    def apply_font_scale(self):
        s = self.font_scale
        # Update fonts
        self.title_lbl.configure(font=("Microsoft YaHei", max(8, int(9 * s)), "bold"))
        self.btn_close.configure(font=("Microsoft YaHei", max(8, int(9 * s))))
        self.btn_min.configure(font=("Microsoft YaHei", max(8, int(9 * s))))
        self.btn_pin.configure(font=("Microsoft YaHei", max(8, int(9 * s))))
        self.btn_opacity.configure(font=("Microsoft YaHei", max(7, int(7.5 * s))))
        self.btn_reset.configure(font=("Microsoft YaHei", max(7, int(8 * s))))
        self.btn_zoom_in.configure(font=("Microsoft YaHei", max(7, int(8 * s)), "bold"))
        self.btn_zoom_out.configure(font=("Microsoft YaHei", max(7, int(8 * s)), "bold"))

        self.status_dot.configure(font=("Segoe UI", max(10, int(12 * s))))
        self.status_text.configure(font=("Microsoft YaHei", max(9, int(10 * s)), "bold"))
        self.timer_label.configure(font=("Consolas", max(9, int(10 * s)), "bold"))
        self.task_lbl.configure(font=("Microsoft YaHei", max(8, int(8 * s))))
        self.quick_rep_lbl.configure(font=("Microsoft YaHei", max(7, int(8 * s))))
        self.btn_main_preview.configure(font=("Microsoft YaHei", max(7, int(8 * s)), "bold"))
        self.btn_main_open.configure(font=("Microsoft YaHei", max(7, int(8 * s)), "bold"))
        self.btn_main_reveal.configure(font=("Microsoft YaHei", max(7, int(8 * s))))

        self.expand_btn.configure(font=("Microsoft YaHei", max(7, int(8 * s))))
        self.engine_mini_lbl.configure(font=("Microsoft YaHei", max(7, int(8 * s))))

        # Resize window
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()
        w = int(self.base_width * s)
        if self.is_mini_mode:
            target_h = max(28, int(32 * s))
        else:
            target_h = (self.custom_expanded_h or int(self.base_height_expanded * s)) if self.is_expanded else int(self.base_height_compact * s)
        self.header.configure(height=max(28, int(32 * s)))
        self.root.geometry(f"{w}x{target_h}+{cur_x}+{cur_y}")

    def reset_state_manually(self, event=None):
        self.current_state = "IDLE"
        self.start_timestamp = 0.0
        self.status_dot.configure(fg=COLOR_IDLE)
        self.status_text.configure(text="空闲待命 (手动重置)", fg=COLOR_IDLE)
        self.timer_label.configure(text="")
        self.task_lbl.configure(text="最近状态: 已手动重置就绪")

    def start_drag(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def do_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._offset_x)
        y = self.root.winfo_y() + (event.y - self._offset_y)
        self.root.geometry(f"+{x}+{y}")

    def toggle_topmost(self, event=None):
        self.is_topmost = not self.is_topmost
        self.root.attributes("-topmost", self.is_topmost)
        self.btn_pin.configure(fg=COLOR_ACCENT if self.is_topmost else TEXT_MUTED)

    def minimize_window(self, event=None):
        """
        最小化监控窗口到 Windows 任务栏。
        保存无边框状态下的坐标与尺寸，解除 overrideredirect 限制后调用 iconify() 压入任务栏。
        用户点击任务栏还原时，由 on_window_map 自动恢复无边框、微光边框与置顶样式。
        """
        try:
            self.saved_geometry = (
                self.root.winfo_x(),
                self.root.winfo_y(),
                self.root.winfo_width(),
                self.root.winfo_height()
            )
            self.is_minimized = True
            self.root.overrideredirect(False)
            self.root.iconify()
        except Exception as e:
            sys.stderr.write(f"[Minimize Error] {e}\n")

    def on_window_map(self, event):
        """处理任务栏点击恢复事件"""
        if event.widget == self.root and self.is_minimized:
            self.root.after_idle(self._restore_from_minimized)

    def _restore_from_minimized(self):
        try:
            self.is_minimized = False
            self.root.overrideredirect(True)
            if self.saved_geometry:
                x, y, w, h = self.saved_geometry
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.attributes("-topmost", self.is_topmost)
            self.root.attributes("-alpha", self.base_alpha)
            self.root.lift()
        except Exception as e:
            sys.stderr.write(f"[Restore Error] {e}\n")

    def toggle_mini_mode(self, event=None):
        """在完整监控面板与极简微型悬浮条之间快速切换（双击标题栏或右击最小化按钮）"""
        s = self.font_scale
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()
        w = int(self.base_width * s)

        if self.is_mini_mode:
            # 恢复常规面板
            self.is_mini_mode = False
            self.body.pack(fill="x", expand=False)
            if self.is_expanded:
                self.history_frame.pack(fill="both", expand=True, side="bottom")
                target_h = self.custom_expanded_h or int(self.base_height_expanded * s)
            else:
                target_h = int(self.base_height_compact * s)
            self.root.geometry(f"{w}x{target_h}+{cur_x}+{cur_y}")
            self.title_lbl.configure(text=" 🤖 Antigravity 监控")
        else:
            # 折叠为微型悬浮胶囊状态条 (32px)
            self.is_mini_mode = True
            if self.is_expanded:
                self.history_frame.pack_forget()
            self.body.pack_forget()
            h = max(28, int(32 * s))
            self.root.geometry(f"{w}x{h}+{cur_x}+{cur_y}")
            st_text = self.status_text.cget("text")
            tm_text = self.timer_label.cget("text")
            pill_status = f" 🤖 [{st_text}] {tm_text}".strip()
            self.title_lbl.configure(text=pill_status)

    def toggle_expand(self, event=None):
        if self.is_mini_mode:
            self.toggle_mini_mode()
        self.is_expanded = not self.is_expanded
        s = self.font_scale
        w = int(self.base_width * s)
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()

        if self.is_expanded:
            self.history_frame.pack(fill="both", expand=True, side="bottom")
            target_h = self.custom_expanded_h or int(self.base_height_expanded * s)
            # Screen boundary guard: don't let window go off bottom of screen
            sh = self.root.winfo_screenheight()
            if cur_y + target_h > sh - 45:
                cur_y = max(20, sh - target_h - 45)
            self.root.geometry(f"{w}x{target_h}+{cur_x}+{cur_y}")
            self.expand_btn.configure(text="▲ 收起历史记录")
            self.render_active_tab()
        else:
            self.history_frame.pack_forget()
            h = int(self.base_height_compact * s)
            self.root.geometry(f"{w}x{h}+{cur_x}+{cur_y}")
            self.expand_btn.configure(text="▼ 查看最近调用历史")

    def switch_tab(self, tab_name: str):
        self.active_tab = tab_name
        if tab_name == "cards":
            self.tab_cards.configure(bg=BG_CARD, fg=COLOR_ACCENT, font=("Microsoft YaHei", 8, "bold"))
            self.tab_logs.configure(bg=BG_HEADER, fg=TEXT_MUTED, font=("Microsoft YaHei", 8))
            self.logs_container.pack_forget()
            self.cards_tab_frame.pack(fill="both", expand=True)
        else:
            self.tab_logs.configure(bg=BG_CARD, fg=COLOR_ACCENT, font=("Microsoft YaHei", 8, "bold"))
            self.tab_cards.configure(bg=BG_HEADER, fg=TEXT_MUTED, font=("Microsoft YaHei", 8))
            self.cards_tab_frame.pack_forget()
            self.logs_container.pack(fill="both", expand=True)
        self.render_active_tab()

    def render_active_tab(self):
        if not self.is_expanded:
            return
        if self.active_tab == "cards":
            self.render_task_cards()
        else:
            self.render_clean_logs()

    def on_preview_task(self, task_dict: dict):
        """统一任务预览：若有落盘成果文件则展示成果；若处于运行中/失败/中止或无独立文件，则动态生成排查与跟踪报告"""
        if not task_dict:
            return
        rep = task_dict.get("report_file", "")
        if rep and os.path.exists(rep):
            MarkdownPreviewWindow.show(self.root, rep)
        else:
            win_title, md_content = build_task_preview_markdown(task_dict)
            MarkdownPreviewWindow.show_content(self.root, title=win_title, markdown_content=md_content, file_path=rep)

    def on_preview_clicked(self, file_path: str):
        if file_path and os.path.exists(file_path):
            MarkdownPreviewWindow.show(self.root, file_path)

    def _on_cards_configure(self, event=None):
        if hasattr(self, "cards_canvas"):
            self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        if hasattr(self, "cards_canvas") and hasattr(self, "cards_window_id"):
            inner_width = max(100, event.width - 2)
            self.cards_canvas.itemconfig(self.cards_window_id, width=inner_width)

    def start_resize(self, event):
        self._grip_start_x = event.x_root
        self._grip_start_y = event.y_root
        self._grip_start_w = self.root.winfo_width()
        self._grip_start_h = self.root.winfo_height()

    def do_resize(self, event):
        dx = event.x_root - self._grip_start_x
        dy = event.y_root - self._grip_start_y
        min_w = int(self.base_width * 0.9)
        min_h = int(self.base_height_compact * self.font_scale) + 160
        new_w = max(min_w, self._grip_start_w + dx)
        new_h = max(min_h, self._grip_start_h + dy)
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()
        self.root.geometry(f"{new_w}x{new_h}+{cur_x}+{cur_y}")
        self.custom_expanded_h = new_h
        if hasattr(self, "cards_canvas"):
            self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox("all"))

    # -----------------------------------------------------------------------
    # State Polling & Task Rendering
    # -----------------------------------------------------------------------

    def poll_state(self):
        """定期扫描 .tasks 与 antigravity.log，无缝同步状态"""
        try:
            tasks_updated = False
            if os.path.exists(TASKS_DIR):
                latest_mtime = 0.0
                file_count = 0
                try:
                    with os.scandir(TASKS_DIR) as it:
                        for entry in it:
                            if entry.name.endswith(".json") and entry.is_file():
                                file_count += 1
                                st = entry.stat()
                                if st.st_mtime > latest_mtime:
                                    latest_mtime = st.st_mtime
                    sig = (file_count, latest_mtime)
                    if sig != self.last_tasks_sig:
                        self.last_tasks_sig = sig
                        tasks_updated = True
                except Exception:
                    pass

            log_updated = False
            if os.path.exists(LOG_FILE):
                mtime = os.path.getmtime(LOG_FILE)
                if mtime != self.last_log_mtime:
                    self.last_log_mtime = mtime
                    log_updated = True

            # 运行中状态守卫：若当前处于 BUSY，至少每 2 秒主动复核一次 worker 状态，防止进程退出后界面悬挂
            now = time.time()
            force_busy_check = (self.current_state in ("BUSY", "RETRY") and now - self._last_busy_check >= 2.0)
            if force_busy_check:
                self._last_busy_check = now

            if tasks_updated or log_updated or force_busy_check:
                self.sync_with_data()
                if self.is_expanded:
                    self.render_active_tab()

        except Exception:
            pass

        self.root.after(600, self.poll_state)

    def load_recent_tasks_data(self, limit=4):
        """从 .tasks/*.json 读取结构化任务记录"""
        if not os.path.exists(TASKS_DIR):
            return []

        task_files = [os.path.join(TASKS_DIR, f) for f in os.listdir(TASKS_DIR) if f.endswith(".json")]
        if not task_files:
            return []

        task_files.sort(key=os.path.getmtime, reverse=True)
        recent_tasks = []

        for pf in task_files[:limit]:
            try:
                with open(pf, "r", encoding="utf-8") as f:
                    rec = json.load(f)

                tid = rec.get("task_id", "")
                ttype = rec.get("task_type", "ask_antigravity")
                status = rec.get("status", "UNKNOWN")
                start_time = rec.get("start_time", 0.0)
                elapsed = rec.get("elapsed_sec")
                ws = rec.get("workspace_path", "")
                rep = rec.get("report_file", "")
                summary = rec.get("prompt_summary", "")
                created = rec.get("created_at", "")

                # 孤儿任务/超时状态自愈清理（利用 Win32 kernel32 精准探测 Worker 进程存活状态，绝不误杀真实长任务）：
                if status in ("RUNNING", "PENDING"):
                    w_pid = rec.get("worker_pid")
                    is_alive = is_pid_running(w_pid) if w_pid else False
                    
                    if not is_alive:
                        # 仅在明确检测到进程已退出，或者未声明 pid 且耗时超过 30 分钟（1800秒）时，才安全纠偏为 INTERRUPTED
                        if (w_pid and not is_alive) or (start_time and (time.time() - start_time > 1800)):
                            status = "INTERRUPTED"
                            rec["status"] = "INTERRUPTED"
                            rec["status_detail"] = "关联进程已退出，任务已自动收敛"
                            if not rec.get("elapsed_sec") and start_time:
                                rec["elapsed_sec"] = time.time() - start_time
                            try:
                                with open(pf, "w", encoding="utf-8") as wf:
                                    json.dump(rec, wf, ensure_ascii=False, indent=2)
                                os.utime(TASKS_DIR, None)
                            except Exception:
                                pass

                if rep and not os.path.isabs(rep) and ws:
                    rep = os.path.abspath(os.path.join(ws, rep))

                if "ex-" in tid or "execute" in ttype or "coding" in ttype:
                    type_icon = "🔨 代码落地"
                elif "cr-" in tid or "review" in ttype:
                    type_icon = "🔍 辅助审查"
                elif "ask" in ttype or "ag-" in tid:
                    type_icon = "⚡ 综合执行"
                else:
                    type_icon = "🤖 智能体任务"

                task_item = dict(rec)
                task_item["task_id"] = tid
                task_item["task_type_label"] = type_icon
                task_item["status"] = status
                task_item["elapsed_sec"] = elapsed
                task_item["report_file"] = rep
                task_item["prompt_summary"] = summary
                task_item["created_at"] = created
                task_item["exists"] = os.path.exists(rep) if rep else False
                recent_tasks.append(task_item)
            except Exception:
                continue

        return recent_tasks

    def sync_with_data(self):
        """同步最新任务状态到主卡片"""
        tasks = self.load_recent_tasks_data(limit=1)
        if not tasks:
            return

        latest = tasks[0]
        self.latest_task = latest
        tid = latest.get("task_id", "")
        status = latest.get("status", "UNKNOWN")
        elapsed = latest.get("elapsed_sec")
        rep_file = latest.get("report_file", "")
        summary = latest.get("prompt_summary") or "Antigravity 任务"

        self.latest_report_file = rep_file

        # 1. 状态行更新
        if status in ("RUNNING", "PENDING"):
            self.current_state = "BUSY"
            self.status_dot.configure(fg=COLOR_BUSY)
            self.status_text.configure(text="正在分析执行中...", fg=COLOR_BUSY)
            if self.start_timestamp == 0.0:
                self.start_timestamp = time.time()
        elif status == "COMPLETED":
            self.current_state = "IDLE"
            self.start_timestamp = 0.0
            self.status_dot.configure(fg=COLOR_IDLE)
            self.status_text.configure(text="空闲待命 (最近成功)", fg=COLOR_IDLE)
            if elapsed:
                self.timer_label.configure(text=f"耗时: {elapsed:.1f}s")

            # 触发长任务 Windows 完成气泡通知 (>60秒)
            if elapsed and elapsed >= 60.0 and self.last_notified_task_id != tid:
                self.last_notified_task_id = tid
                send_win_notification(
                    "🤖 Antigravity 任务已完成",
                    f"任务 [{tid[-8:]}] 执行完毕！耗时: {elapsed:.1f} 秒\n报告已就绪，点击悬浮窗可快速查阅。"
                )
        elif status == "INTERRUPTED":
            self.current_state = "IDLE"
            self.start_timestamp = 0.0
            self.status_dot.configure(fg=TEXT_MUTED)
            self.status_text.configure(text="空闲待命 (会话已收敛)", fg=TEXT_MUTED)
            if elapsed:
                self.timer_label.configure(text=f"已中止 ({elapsed:.0f}s)")
            else:
                self.timer_label.configure(text="")
        elif status == "FAILED":
            self.current_state = "ERROR"
            self.start_timestamp = 0.0
            self.status_dot.configure(fg=COLOR_ERR)
            self.status_text.configure(text="执行异常", fg=COLOR_ERR)

        # 2. 任务描述更新
        created_raw = latest.get("created_at", "")
        time_tag = f"[{created_raw[11:16]}] " if len(created_raw) >= 16 else ""
        prefix = f"{time_tag}[{tid[-8:]}] " if tid else time_tag
        disp_summary = summary[:28] + "..." if len(summary) > 28 else summary
        self.task_lbl.configure(text=f"{prefix}{disp_summary}")

        # 3. 常驻成果按钮栏状态更新
        if rep_file and os.path.exists(rep_file):
            rep_name = os.path.basename(rep_file)
            disp_rep = rep_name[:22] + "..." if len(rep_name) > 22 else rep_name
            self.quick_rep_lbl.configure(text=f"📄 {disp_rep}", fg=COLOR_IDLE)
            self.btn_main_preview.configure(text="👁️ 预览", fg=COLOR_ACCENT)
            self.btn_main_preview.pack(side="right", padx=(2, 0))
            self.btn_main_open.pack(side="right", padx=(2, 2))
            self.btn_main_reveal.pack(side="right", padx=(2, 2))
        elif status in ("RUNNING", "PENDING"):
            self.quick_rep_lbl.configure(text="⏳ 任务执行中 (可实时跟踪)", fg=COLOR_BUSY)
            self.btn_main_preview.configure(text="👁️ 实时跟踪", fg=COLOR_ACCENT)
            self.btn_main_preview.pack(side="right", padx=(2, 0))
            self.btn_main_open.pack_forget()
            self.btn_main_reveal.pack_forget()
        elif status == "FAILED":
            self.quick_rep_lbl.configure(text="❌ 执行失败 (点击异常排查)", fg=COLOR_ERR)
            self.btn_main_preview.configure(text="👁️ 异常排查", fg=COLOR_ERR)
            self.btn_main_preview.pack(side="right", padx=(2, 0))
            self.btn_main_open.pack_forget()
            self.btn_main_reveal.pack_forget()
        elif status == "INTERRUPTED":
            self.quick_rep_lbl.configure(text="⏹️ 任务已中止 (点击查看详情)", fg=TEXT_MUTED)
            self.btn_main_preview.configure(text="👁️ 详情预览", fg=COLOR_ACCENT)
            self.btn_main_preview.pack(side="right", padx=(2, 0))
            self.btn_main_open.pack_forget()
            self.btn_main_reveal.pack_forget()
        else:
            self.quick_rep_lbl.configure(text="梯队: 3.8-Flash -> DeepSeek -> 2.5-Flash", fg=TEXT_MUTED)
            self.btn_main_preview.pack_forget()
            self.btn_main_open.pack_forget()
            self.btn_main_reveal.pack_forget()

    def render_task_cards(self):
        """渲染 Tab 1: 结构化任务卡片流"""
        for widget in self.cards_container.winfo_children():
            widget.destroy()

        tasks = self.load_recent_tasks_data(limit=12)
        if not tasks:
            empty_lbl = tk.Label(
                self.cards_container, text="暂无最近任务记录",
                font=("Microsoft YaHei", 8), bg=BG_HEADER, fg=TEXT_MUTED, pady=20
            )
            empty_lbl.pack()
            if hasattr(self, "cards_canvas"):
                self.cards_canvas.configure(scrollregion=(0, 0, 100, 100))
            return

        for t in tasks:
            card = tk.Frame(self.cards_container, bg=BG_CARD, padx=8, pady=6, relief="flat")
            card.pack(fill="x", pady=3)

            # Top Row: [Type Badge] [ID] [Time/Duration] [Status]
            top_row = tk.Frame(card, bg=BG_CARD)
            top_row.pack(fill="x")

            if "代码" in t["task_type_label"] or "落地" in t["task_type_label"]:
                type_color = COLOR_IDLE
            elif "审查" in t["task_type_label"]:
                type_color = COLOR_PURPLE
            else:
                type_color = COLOR_TEAL
            lbl_type = tk.Label(
                top_row, text=t["task_type_label"],
                font=("Microsoft YaHei", 8, "bold"), bg=BG_TAG, fg=type_color, padx=4, pady=1
            )
            lbl_type.pack(side="left", padx=(0, 6))

            tid_short = t["task_id"][-8:] if t["task_id"] else ""
            lbl_id = tk.Label(
                top_row, text=f"[{tid_short}]",
                font=("Consolas", 8), bg=BG_CARD, fg=TEXT_MUTED
            )
            lbl_id.pack(side="left")

            # 任务时间标签 (Task Time)
            created_str = t.get("created_at", "")
            if created_str:
                today_str = datetime.now().strftime("%Y-%m-%d")
                if created_str.startswith(today_str) and len(created_str) >= 19:
                    time_label_text = created_str[11:19]
                elif len(created_str) >= 16:
                    time_label_text = created_str[5:16]
                else:
                    time_label_text = created_str
                lbl_time = tk.Label(
                    top_row, text=f"🕒 {time_label_text}",
                    font=("Consolas", 8), bg=BG_CARD, fg=COLOR_ACCENT
                )
                lbl_time.pack(side="left", padx=(6, 0))

            st = t["status"]
            if st == "COMPLETED":
                st_text, st_color = "✅ 成功", COLOR_IDLE
            elif st in ("RUNNING", "PENDING"):
                st_text, st_color = "⏳ 运行中", COLOR_BUSY
            elif st == "INTERRUPTED":
                st_text, st_color = "⏹️ 已中止", TEXT_MUTED
            else:
                st_text, st_color = "❌ 失败", COLOR_ERR

            lbl_st = tk.Label(
                top_row, text=st_text,
                font=("Microsoft YaHei", 8, "bold"), bg=BG_CARD, fg=st_color
            )
            lbl_st.pack(side="right")

            if t["elapsed_sec"]:
                lbl_dur = tk.Label(
                    top_row, text=f"⏱ {t['elapsed_sec']:.1f}s",
                    font=("Consolas", 8), bg=BG_CARD, fg=TEXT_MUTED
                )
                lbl_dur.pack(side="right", padx=(0, 6))

            # Middle Row: Prompt summary
            sm_text = t["prompt_summary"] or "未命名任务"
            if len(sm_text) > 36:
                sm_text = sm_text[:36] + "..."
            lbl_summary = tk.Label(
                card, text=sm_text, font=("Microsoft YaHei", 8),
                bg=BG_CARD, fg=TEXT_PRIMARY, anchor="w"
            )
            lbl_summary.pack(fill="x", pady=(2, 3))

            # Bottom Row: Actions (无论是否有落盘文件，均展示操作栏与查阅入口)
            btn_row = tk.Frame(card, bg=BG_CARD)
            btn_row.pack(fill="x", pady=(2, 0))

            rep = t.get("report_file", "")
            if rep and t.get("exists"):
                rep_name = os.path.basename(rep)
                if len(rep_name) > 22:
                    rep_name = rep_name[:22] + "..."
                lbl_fn = tk.Label(
                    btn_row, text=f"📄 {rep_name}", font=("Consolas", 7),
                    bg=BG_CARD, fg=TEXT_MUTED, anchor="w"
                )
                lbl_fn.pack(side="left", fill="x", expand=True)

                btn_p = tk.Label(
                    btn_row, text="👁️ 预览", font=("Microsoft YaHei", 7),
                    bg=BG_BTN, fg=COLOR_ACCENT, cursor="hand2", padx=4, pady=1
                )
                btn_p.pack(side="right", padx=2)
                btn_p.bind("<Button-1>", lambda e, task_item=t: self.on_preview_task(task_item))
                btn_p.bind("<Enter>", lambda e, b=btn_p: b.configure(bg=BG_BTN_HOVER))
                btn_p.bind("<Leave>", lambda e, b=btn_p: b.configure(bg=BG_BTN))

                btn_o = tk.Label(
                    btn_row, text="📄 打开", font=("Microsoft YaHei", 7),
                    bg=BG_BTN, fg=COLOR_IDLE, cursor="hand2", padx=4, pady=1
                )
                btn_o.pack(side="right", padx=2)
                btn_o.bind("<Button-1>", lambda e, p=rep: open_report_file(p))
                btn_o.bind("<Enter>", lambda e, b=btn_o: b.configure(bg=BG_BTN_HOVER))
                btn_o.bind("<Leave>", lambda e, b=btn_o: b.configure(bg=BG_BTN))

                btn_r = tk.Label(
                    btn_row, text="📂 目录", font=("Microsoft YaHei", 7),
                    bg=BG_BTN, fg=TEXT_PRIMARY, cursor="hand2", padx=4, pady=1
                )
                btn_r.pack(side="right", padx=2)
                btn_r.bind("<Button-1>", lambda e, p=rep: reveal_in_explorer(p))
                btn_r.bind("<Enter>", lambda e, b=btn_r: b.configure(bg=BG_BTN_HOVER))
                btn_r.bind("<Leave>", lambda e, b=btn_r: b.configure(bg=BG_BTN))
            else:
                if st in ("RUNNING", "PENDING"):
                    hint_txt, hint_fg = "⏳ 任务后台执行中...", COLOR_BUSY
                    btn_txt, btn_fg = "👁️ 实时跟踪", COLOR_ACCENT
                elif st == "FAILED":
                    hint_txt, hint_fg = "⚠️ 任务异常终止", COLOR_ERR
                    btn_txt, btn_fg = "👁️ 异常排查", COLOR_ERR
                elif st == "INTERRUPTED":
                    hint_txt, hint_fg = "⏹️ 会话已结束/已中止", TEXT_MUTED
                    btn_txt, btn_fg = "👁️ 详情预览", COLOR_ACCENT
                else:
                    hint_txt, hint_fg = "✨ 无单独报告文件", TEXT_MUTED
                    btn_txt, btn_fg = "👁️ 详情预览", COLOR_ACCENT

                lbl_fn = tk.Label(
                    btn_row, text=hint_txt, font=("Microsoft YaHei", 7),
                    bg=BG_CARD, fg=hint_fg, anchor="w"
                )
                lbl_fn.pack(side="left", fill="x", expand=True)

                btn_p = tk.Label(
                    btn_row, text=btn_txt, font=("Microsoft YaHei", 7),
                    bg=BG_BTN, fg=btn_fg, cursor="hand2", padx=4, pady=1
                )
                btn_p.pack(side="right", padx=2)
                btn_p.bind("<Button-1>", lambda e, task_item=t: self.on_preview_task(task_item))
                btn_p.bind("<Enter>", lambda e, b=btn_p: b.configure(bg=BG_BTN_HOVER))
                btn_p.bind("<Leave>", lambda e, b=btn_p: b.configure(bg=BG_BTN))

        # Bottom spacer for breathing room so bottom-most card is never clipped
        spacer = tk.Frame(self.cards_container, bg=BG_HEADER, height=14)
        spacer.pack(fill="x")

        # Update scrollregion once idle tasks complete
        self.cards_container.update_idletasks()
        if hasattr(self, "cards_canvas"):
            self.cards_canvas.configure(scrollregion=self.cards_canvas.bbox("all"))

    def render_clean_logs(self):
        """渲染 Tab 2: 过滤净化后的关键日志"""
        self.history_box.configure(state="normal")
        self.history_box.delete("1.0", "end")

        if not os.path.exists(LOG_FILE):
            self.history_box.insert("end", "暂无运行日志\n")
            self.history_box.configure(state="disabled")
            return

        try:
            with open(LOG_FILE, "r", encoding="gb18030", errors="ignore") as f:
                lines = f.readlines()

            clean_lines = []
            noisy_keywords = [
                "starting directory is not a subdirectory",
                "localharness.exe",
                "strconv.Atoi",
                "Traceback (most recent call last)",
                "[Log Error]",
                "File \"",
            ]

            valid_tags = ["[START]", "[DONE]", "[RETRY]", "[FALLBACK]", "[AUTO-DETACH]", "[EARLY-DETACH]", "[ERROR]", "[RESCUED]"]

            for l in reversed(lines):
                s = l.strip()
                if not s:
                    continue
                if any(k in s for k in noisy_keywords):
                    continue
                if any(tag in s for tag in valid_tags):
                    clean_lines.append(s)
                if len(clean_lines) >= 12:
                    break

            clean_lines.reverse()

            if not clean_lines:
                self.history_box.insert("end", "暂无关键生命周期日志\n")
            else:
                for line in clean_lines:
                    time_part = ""
                    content_part = line
                    m = re.match(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(.*)", line)
                    if m:
                        time_part = m.group(1)[11:] + " "
                        content_part = m.group(2)

                    if time_part:
                        self.history_box.insert("end", time_part, "tag_time")

                    if "[DONE]" in content_part:
                        self.history_box.insert("end", content_part + "\n", "tag_done")
                    elif "[START]" in content_part:
                        self.history_box.insert("end", content_part + "\n", "tag_start")
                    elif "[RETRY]" in content_part or "[FALLBACK]" in content_part:
                        self.history_box.insert("end", content_part + "\n", "tag_retry")
                    elif "[ERROR]" in content_part:
                        self.history_box.insert("end", content_part + "\n", "tag_err")
                    else:
                        self.history_box.insert("end", content_part + "\n")

            self.history_box.see("end")

        except Exception as e:
            self.history_box.insert("end", f"日志解析异常: {e}\n")

        self.history_box.configure(state="disabled")

    # -----------------------------------------------------------------------
    # Breathing Animation & Timer Loop
    # -----------------------------------------------------------------------

    def update_breathing_and_timer(self):
        """毫秒级秒表走字与运行呼吸灯动效"""
        if self.current_state in ("BUSY", "RETRY") and self.start_timestamp > 0.0:
            elapsed = int(time.time() - self.start_timestamp)
            mins = elapsed // 60
            secs = elapsed % 60
            self.timer_label.configure(text=f"⏱ {mins:02d}:{secs:02d}")
        elif self.current_state == "IDLE" and not self.timer_label.cget("text").startswith("耗时") and not self.timer_label.cget("text").startswith("已中止"):
            self.timer_label.configure(text="")

        if self.current_state in ("BUSY", "RETRY"):
            self.pulse_phase = (self.pulse_phase + 1) % 4
            pulse_colors = [COLOR_BUSY, COLOR_BUSY_ALT, COLOR_ACCENT, COLOR_BUSY_ALT]
            self.status_dot.configure(fg=pulse_colors[self.pulse_phase])
        elif self.current_state == "IDLE":
            self.status_dot.configure(fg=COLOR_IDLE)

        # 在微型胶囊模式下同步标题栏状态与计时
        if self.is_mini_mode:
            st_text = self.status_text.cget("text")
            tm_text = self.timer_label.cget("text")
            pill_status = f" 🤖 [{st_text}] {tm_text}".strip()
            self.title_lbl.configure(text=pill_status)

        self.root.after(250, self.update_breathing_and_timer)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

def main():
    try:
        root = tk.Tk()
        app = AntigravityWidget(root)
        root.mainloop()
    except Exception as e:
        err_log = os.path.expanduser("~/.codex/mcp_servers/antigravity_widget_err.log")
        try:
            with open(err_log, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now()}] Widget Error: {e}\n")
                import traceback
                traceback.print_exc(file=f)
        except Exception:
            pass

if __name__ == "__main__":
    main()
