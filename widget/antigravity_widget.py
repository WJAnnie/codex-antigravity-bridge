"""
Antigravity Desktop Floating Mini-Widget v2.1
Provides a modern, lightweight, always-on-top status widget for monitoring
Codex -> Antigravity MCP calls in real time with live stopwatches, history,
and dynamic font scaling (A+ / A- / Ctrl+Wheel).
"""

import os
import sys
import time
import re
import json
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

# Theme colors (Modern Dark Theme - Catppuccin inspired)
BG_MAIN = "#1e1e2e"       # Main background
BG_HEADER = "#181825"     # Header bar
BG_CARD = "#252538"       # Status card background
BG_HOVER = "#313244"      # Button hover
TEXT_PRIMARY = "#cdd6f4"  # Main text
TEXT_MUTED = "#a6adc8"    # Subdued text
COLOR_IDLE = "#a6e3a1"    # Green
COLOR_BUSY = "#f9e2af"    # Yellow/Amber
COLOR_ERR = "#f38ba8"     # Red
COLOR_ACCENT = "#89b4fa"  # Blue

SCALE_STEPS = [0.9, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0]
DEFAULT_SCALE_INDEX = 2  # 1.15x by default


class AntigravityWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("Antigravity 监控窗")
        
        # Load config
        self.config = self.load_config()
        self.scale_idx = self.config.get("scale_index", DEFAULT_SCALE_INDEX)
        if self.scale_idx < 0 or self.scale_idx >= len(SCALE_STEPS):
            self.scale_idx = DEFAULT_SCALE_INDEX
        self.font_scale = SCALE_STEPS[self.scale_idx]

        # Base dimensions
        self.base_width = 350
        self.base_height_compact = 145
        self.base_height_expanded = 315
        self.is_expanded = False
        self.is_topmost = True
        
        # Screen position (top right corner)
        w = int(self.base_width * self.font_scale)
        h = int(self.base_height_compact * self.font_scale)
        screen_w = self.root.winfo_screenwidth()
        x = max(30, screen_w - w - 30)
        y = 50
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.configure(bg=BG_MAIN)
        self.root.overrideredirect(True)  # Frameless
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.lift()

        # Window drag handlers
        self._offset_x = 0
        self._offset_y = 0

        # State tracking
        self.current_state = "IDLE"  # IDLE | BUSY | ERROR
        self.start_timestamp = 0.0
        self.last_log_size = -1
        self.history_records = []

        self.setup_ui()
        self.apply_font_scale()
        self.poll_log()
        self.update_timer()

        # Bind Ctrl + Mousewheel on root for instant zoom
        self.root.bind("<Control-MouseWheel>", self.on_ctrl_wheel)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"scale_index": DEFAULT_SCALE_INDEX}

    def save_config(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({"scale_index": self.scale_idx}, f)
        except Exception:
            pass

    def setup_ui(self):
        # 1. Custom Drag Header
        self.header = tk.Frame(self.root, bg=BG_HEADER, height=32)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        self.header.bind("<ButtonPress-1>", self.start_drag)
        self.header.bind("<B1-Motion>", self.do_drag)

        self.title_lbl = tk.Label(
            self.header,
            text=" 🤖 Antigravity 监控",
            font=("Microsoft YaHei", 9, "bold"),
            bg=BG_HEADER,
            fg=TEXT_PRIMARY,
            cursor="fleur"
        )
        self.title_lbl.pack(side="left", padx=5, pady=3)
        self.title_lbl.bind("<ButtonPress-1>", self.start_drag)
        self.title_lbl.bind("<B1-Motion>", self.do_drag)

        # Header action buttons (Right to Left: Close, Pin, Reset, A+, A-)
        self.btn_close = tk.Label(
            self.header, text="✕", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=6
        )
        self.btn_close.pack(side="right")
        self.btn_close.bind("<Button-1>", lambda e: self.root.destroy())
        self.btn_close.bind("<Enter>", lambda e: self.btn_close.configure(fg=COLOR_ERR, bg=BG_HOVER))
        self.btn_close.bind("<Leave>", lambda e: self.btn_close.configure(fg=TEXT_MUTED, bg=BG_HEADER))

        self.btn_pin = tk.Label(
            self.header, text="📌", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=COLOR_ACCENT, cursor="hand2", padx=4
        )
        self.btn_pin.pack(side="right")
        self.btn_pin.bind("<Button-1>", self.toggle_topmost)

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
        self.body = tk.Frame(self.root, bg=BG_MAIN, padx=12, pady=8)
        self.body.pack(fill="x", expand=False)

        # Status row (Dot + Status text + Live timer)
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

        # Task summary line
        self.task_lbl = tk.Label(
            self.body, text="最近任务: 暂无调用",
            font=("Microsoft YaHei", 9), bg=BG_MAIN, fg=TEXT_PRIMARY,
            anchor="w", justify="left"
        )
        self.task_lbl.pack(fill="x", pady=(4, 2))

        # Meta line (Workspace / Model engine)
        self.meta_lbl = tk.Label(
            self.body, text="引擎: gemini-3.8-flash (Google 原生) | 状态: 监听就绪",
            font=("Microsoft YaHei", 8), bg=BG_MAIN, fg=TEXT_MUTED,
            anchor="w"
        )
        self.meta_lbl.pack(fill="x")

        # Bottom Bar: Expand Details Button
        self.bottom_bar = tk.Frame(self.body, bg=BG_MAIN)
        self.bottom_bar.pack(fill="x", pady=(6, 0))

        self.expand_btn = tk.Label(
            self.bottom_bar, text="▼ 查看最近调用历史", font=("Microsoft YaHei", 8),
            bg=BG_CARD, fg=COLOR_ACCENT, cursor="hand2", padx=6, pady=2
        )
        self.expand_btn.pack(side="left")
        self.expand_btn.bind("<Button-1>", self.toggle_expand)

        # 3. History Panel (Collapsible)
        self.history_frame = tk.Frame(self.root, bg=BG_HEADER, padx=10, pady=6)
        
        self.hist_title = tk.Label(
            self.history_frame, text="最近 6 次调度明细:",
            font=("Microsoft YaHei", 8, "bold"), bg=BG_HEADER, fg=TEXT_MUTED, anchor="w"
        )
        self.hist_title.pack(fill="x")

        self.history_box = tk.Text(
            self.history_frame, height=8, bg=BG_HEADER, fg=TEXT_PRIMARY,
            font=("Consolas", 8), relief="flat", wrap="word",
            padx=4, pady=4, highlightthickness=0
        )
        self.history_box.pack(fill="both", expand=True)
        self.history_box.configure(state="disabled")

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
        self.btn_pin.configure(font=("Microsoft YaHei", max(8, int(9 * s))))
        self.btn_reset.configure(font=("Microsoft YaHei", max(7, int(8 * s))))
        self.btn_zoom_in.configure(font=("Microsoft YaHei", max(7, int(8 * s)), "bold"))
        self.btn_zoom_out.configure(font=("Microsoft YaHei", max(7, int(8 * s)), "bold"))

        self.status_dot.configure(font=("Segoe UI", max(10, int(12 * s))))
        self.status_text.configure(font=("Microsoft YaHei", max(9, int(10 * s)), "bold"))
        self.timer_label.configure(font=("Consolas", max(9, int(10 * s)), "bold"))

        self.task_lbl.configure(font=("Microsoft YaHei", max(8, int(9 * s))))
        self.meta_lbl.configure(font=("Microsoft YaHei", max(7, int(8.5 * s))))
        self.expand_btn.configure(font=("Microsoft YaHei", max(7, int(8.5 * s))))

        self.hist_title.configure(font=("Microsoft YaHei", max(7, int(8.5 * s)), "bold"))
        self.history_box.configure(font=("Consolas", max(7, int(8.5 * s))))

        # Resize window
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()
        w = int(self.base_width * s)
        h = int((self.base_height_expanded if self.is_expanded else self.base_height_compact) * s)
        self.header.configure(height=max(28, int(32 * s)))
        self.root.geometry(f"{w}x{h}+{cur_x}+{cur_y}")

    def reset_state_manually(self, event=None):
        """手动重置状态卡片为空闲待命"""
        self.current_state = "IDLE"
        self.start_timestamp = 0.0
        self.status_dot.configure(fg=COLOR_IDLE)
        self.status_text.configure(text="空闲待命 (手动重置)", fg=COLOR_IDLE)
        self.timer_label.configure(text="")
        self.task_lbl.configure(text="最近状态: 已手动重置就绪")
        self.meta_lbl.configure(text="引擎: Google Gemini (Antigravity 原生) | 监听就绪")

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

    def toggle_expand(self, event=None):
        self.is_expanded = not self.is_expanded
        s = self.font_scale
        w = int(self.base_width * s)
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()

        if self.is_expanded:
            self.history_frame.pack(fill="both", expand=True, side="bottom")
            h = int(self.base_height_expanded * s)
            self.root.geometry(f"{w}x{h}+{cur_x}+{cur_y}")
            self.expand_btn.configure(text="▲ 收起调用历史")
            self.render_history()
        else:
            self.history_frame.pack_forget()
            h = int(self.base_height_compact * s)
            self.root.geometry(f"{w}x{h}+{cur_x}+{cur_y}")
            self.expand_btn.configure(text="▼ 查看最近调用历史")

    def render_history(self):
        self.history_box.configure(state="normal")
        self.history_box.delete("1.0", "end")
        if not self.history_records:
            self.history_box.insert("end", "暂无历史记录\n")
        else:
            for rec in self.history_records[-8:]:
                self.history_box.insert("end", f"{rec}\n")
        self.history_box.configure(state="disabled")

    def poll_log(self):
        """定期检测日志文件变化并更新状态"""
        try:
            if os.path.exists(LOG_FILE):
                size = os.path.getsize(LOG_FILE)
                if size != self.last_log_size:
                    self.last_log_size = size
                    self.parse_log_file()
        except Exception:
            pass
        self.root.after(500, self.poll_log)

    def parse_log_file(self):
        try:
            with open(LOG_FILE, "r", encoding="gb18030", errors="ignore") as f:
                lines = [l.strip() for l in f.readlines() if l.strip()]

            if not lines:
                return

            self.history_records = lines[-10:]
            if self.is_expanded:
                self.render_history()

            last_line = lines[-1]

            if "[START]" in last_line:
                self.current_state = "BUSY"
                self.status_dot.configure(fg=COLOR_BUSY)
                
                is_async = "[ASYNC" in last_line
                self.status_text.configure(
                    text="后台长任务运行中..." if is_async else "正在思考执行...", 
                    fg=COLOR_BUSY
                )
                
                task_part = "任务处理中"
                if "任务:" in last_line:
                    task_part = last_line.split("任务:")[-1].strip()
                elif "列表:" in last_line:
                    task_part = "审查文件: " + last_line.split("列表:")[-1].strip()
                
                # Extract task ID if present
                tid_match = re.search(r"\[ASYNC:([^\]]+)\]", last_line)
                tid_prefix = f"[{tid_match.group(1)[-8:]}] " if tid_match else ("[异步] " if is_async else "")
                
                if len(task_part) > 28:
                    task_part = task_part[:28] + "..."
                self.task_lbl.configure(text=f"{tid_prefix}{task_part}")

                engine_part = "GLM-5.3"
                if "引擎:" in last_line:
                    engine_part = last_line.split("引擎:")[1].split("|")[0].strip()
                self.meta_lbl.configure(text=f"引擎: {engine_part} | 后台持续运行中...")

                # Extract start time from log timestamp if available
                time_match = re.search(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", last_line)
                if time_match:
                    try:
                        log_dt = datetime.strptime(time_match.group(1), "%Y-%m-%d %H:%M:%S")
                        self.start_timestamp = log_dt.timestamp()
                    except Exception:
                        if self.start_timestamp == 0.0:
                            self.start_timestamp = time.time()
                else:
                    if self.start_timestamp == 0.0:
                        self.start_timestamp = time.time()

            elif "[DONE]" in last_line:
                self.current_state = "IDLE"
                self.start_timestamp = 0.0
                self.status_dot.configure(fg=COLOR_IDLE)
                self.status_text.configure(text="空闲待命 (最近成功)", fg=COLOR_IDLE)
                
                dur_match = re.search(r"耗时:\s*([0-9.]+s)", last_line)
                dur = dur_match.group(1) if dur_match else ""
                self.timer_label.configure(text=f"耗时: {dur}" if dur else "")

                if "报告:" in last_line:
                    rep_name = last_line.split("报告:")[-1].strip()
                    self.meta_lbl.configure(text=f"报告已生成: {rep_name}")
                else:
                    char_match = re.search(r"返回字符数:\s*(\d+)", last_line)
                    chars = char_match.group(1) if char_match else ""
                    self.meta_lbl.configure(text=f"上次执行成功 (返回 {chars} 字) | 就绪待命")

            elif "[RETRY]" in last_line:
                self.current_state = "RETRY"
                self.status_dot.configure(fg="#F59E0B")
                self.status_text.configure(text="网络闪断自愈中...", fg="#F59E0B")
                
                r_match = re.search(r"第\s*(\d+/\d+)\s*次", last_line)
                r_info = f"[{r_match.group(1)}] " if r_match else "[自愈重试] "
                
                w_match = re.search(r"等待\s*([0-9.]+s)", last_line)
                w_info = f"等待 {w_match.group(1)}" if w_match else "稍候重试"
                
                self.task_lbl.configure(text=f"{r_info}捕获代理/上游网络闪断，自动重试中")
                self.meta_lbl.configure(text=f"状态: 网络自愈中 ({w_info}) | 会话保持不中断")

            elif "[ERROR]" in last_line:
                self.current_state = "ERROR"
                self.start_timestamp = 0.0
                self.status_dot.configure(fg=COLOR_ERR)
                self.status_text.configure(text="执行异常", fg=COLOR_ERR)
                err_match = re.search(r"异常:\s*(.*)", last_line)
                err_txt = err_match.group(1)[:30] if err_match else "发生错误"
                self.task_lbl.configure(text=f"报错: {err_txt}")
                self.meta_lbl.configure(text="请点击下方展开历史查看详情")

        except Exception:
            pass

    def update_timer(self):
        """实时秒表走字"""
        if self.current_state in ("BUSY", "RETRY") and self.start_timestamp > 0.0:
            elapsed = int(time.time() - self.start_timestamp)
            mins = elapsed // 60
            secs = elapsed % 60
            self.timer_label.configure(text=f"⏱ {mins:02d}:{secs:02d}")
        elif self.current_state == "IDLE" and not self.timer_label.cget("text").startswith("耗时"):
            self.timer_label.configure(text="")
            
        self.root.after(200, self.update_timer)


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
