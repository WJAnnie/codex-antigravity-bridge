"""
Antigravity Desktop Floating Mini-Widget
Provides a modern, lightweight, always-on-top status widget for monitoring
Codex -> Antigravity MCP calls in real time with live stopwatches and history.
Supports both synchronous calls and asynchronous background long tasks.
"""

import os
import sys
import time
import re
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

# Resolve log file path dynamically
def resolve_log_file() -> str:
    if "ANTIGRAVITY_LOG_FILE" in os.environ:
        return os.environ["ANTIGRAVITY_LOG_FILE"]
    home_log = os.path.expanduser("~/.codex/mcp_servers/antigravity.log")
    if os.path.exists(home_log):
        return home_log
    # Check repo local
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


class AntigravityWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("Antigravity 监控窗")
        
        # Dimensions and positioning
        self.width = 350
        self.height_compact = 145
        self.height_expanded = 310
        self.is_expanded = False
        self.is_topmost = True
        
        # Screen position (top right corner)
        screen_w = self.root.winfo_screenwidth()
        x = max(50, screen_w - self.width - 30)
        y = 50
        self.root.geometry(f"{self.width}x{self.height_compact}+{x}+{y}")
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
        self.poll_log()
        self.update_timer()

    def setup_ui(self):
        # 1. Custom Drag Header
        self.header = tk.Frame(self.root, bg=BG_HEADER, height=30)
        self.header.pack(fill="x", side="top")
        self.header.pack_propagate(False)

        self.header.bind("<ButtonPress-1>", self.start_drag)
        self.header.bind("<B1-Motion>", self.do_drag)

        title_lbl = tk.Label(
            self.header,
            text=" 🤖 Antigravity 调度监控",
            font=("Microsoft YaHei", 9, "bold"),
            bg=BG_HEADER,
            fg=TEXT_PRIMARY,
            cursor="fleur"
        )
        title_lbl.pack(side="left", padx=5, pady=4)
        title_lbl.bind("<ButtonPress-1>", self.start_drag)
        title_lbl.bind("<B1-Motion>", self.do_drag)

        # Header action buttons
        btn_close = tk.Label(
            self.header, text="✕", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=TEXT_MUTED, cursor="hand2", padx=6
        )
        btn_close.pack(side="right")
        btn_close.bind("<Button-1>", lambda e: self.root.destroy())
        btn_close.bind("<Enter>", lambda e: btn_close.configure(fg=COLOR_ERR, bg=BG_HOVER))
        btn_close.bind("<Leave>", lambda e: btn_close.configure(fg=TEXT_MUTED, bg=BG_HEADER))

        self.btn_pin = tk.Label(
            self.header, text="📌", font=("Microsoft YaHei", 9),
            bg=BG_HEADER, fg=COLOR_ACCENT, cursor="hand2", padx=4
        )
        self.btn_pin.pack(side="right")
        self.btn_pin.bind("<Button-1>", self.toggle_topmost)

        # 2. Main Card Body
        self.body = tk.Frame(self.root, bg=BG_MAIN, padx=12, pady=8)
        self.body.pack(fill="x", expand=False)

        # Status row (Dot + Status text + Live timer)
        status_row = tk.Frame(self.body, bg=BG_MAIN)
        status_row.pack(fill="x")

        self.status_dot = tk.Label(
            status_row, text="●", font=("Segoe UI", 12),
            bg=BG_MAIN, fg=COLOR_IDLE
        )
        self.status_dot.pack(side="left")

        self.status_text = tk.Label(
            status_row, text="空闲待命", font=("Microsoft YaHei", 10, "bold"),
            bg=BG_MAIN, fg=COLOR_IDLE
        )
        self.status_text.pack(side="left", padx=(4, 8))

        self.timer_label = tk.Label(
            status_row, text="", font=("Consolas", 10, "bold"),
            bg=BG_MAIN, fg=COLOR_BUSY
        )
        self.timer_label.pack(side="right")

        # Task summary line
        self.task_lbl = tk.Label(
            self.body, text="最近任务: 暂无调用",
            font=("Microsoft YaHei", 8), bg=BG_MAIN, fg=TEXT_PRIMARY,
            anchor="w", justify="left"
        )
        self.task_lbl.pack(fill="x", pady=(4, 2))

        # Meta line (Workspace / Model engine)
        self.meta_lbl = tk.Label(
            self.body, text="引擎: agentrouter/glm-5.3 | 状态: 监听就绪",
            font=("Microsoft YaHei", 8), bg=BG_MAIN, fg=TEXT_MUTED,
            anchor="w"
        )
        self.meta_lbl.pack(fill="x")

        # Bottom Bar: Expand Details Button
        bottom_bar = tk.Frame(self.body, bg=BG_MAIN)
        bottom_bar.pack(fill="x", pady=(6, 0))

        self.expand_btn = tk.Label(
            bottom_bar, text="▼ 查看最近调用历史", font=("Microsoft YaHei", 8),
            bg=BG_CARD, fg=COLOR_ACCENT, cursor="hand2", padx=6, pady=2
        )
        self.expand_btn.pack(side="left")
        self.expand_btn.bind("<Button-1>", self.toggle_expand)

        # 3. History Panel (Collapsible)
        self.history_frame = tk.Frame(self.root, bg=BG_HEADER, padx=10, pady=6)
        
        hist_title = tk.Label(
            self.history_frame, text="最近 6 次调度明细:",
            font=("Microsoft YaHei", 8, "bold"), bg=BG_HEADER, fg=TEXT_MUTED, anchor="w"
        )
        hist_title.pack(fill="x")

        self.history_box = tk.Text(
            self.history_frame, height=8, bg=BG_HEADER, fg=TEXT_PRIMARY,
            font=("Consolas", 8), relief="flat", wrap="word",
            padx=4, pady=4, highlightthickness=0
        )
        self.history_box.pack(fill="both", expand=True)
        self.history_box.configure(state="disabled")

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
        w = self.width
        cur_x = self.root.winfo_x()
        cur_y = self.root.winfo_y()

        if self.is_expanded:
            self.history_frame.pack(fill="both", expand=True, side="bottom")
            self.root.geometry(f"{w}x{self.height_expanded}+{cur_x}+{cur_y}")
            self.expand_btn.configure(text="▲ 收起调用历史")
            self.render_history()
        else:
            self.history_frame.pack_forget()
            self.root.geometry(f"{w}x{self.height_compact}+{cur_x}+{cur_y}")
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

            # Keep last history items
            self.history_records = lines[-10:]
            if self.is_expanded:
                self.render_history()

            last_line = lines[-1]

            if "[START]" in last_line:
                self.current_state = "BUSY"
                self.status_dot.configure(fg=COLOR_BUSY)
                
                is_async = "[ASYNC" in last_line
                self.status_text.configure(
                    text="后台长任务思考中..." if is_async else "正在思考执行...", 
                    fg=COLOR_BUSY
                )
                
                # Extract task
                task_part = "任务处理中"
                if "任务:" in last_line:
                    task_part = last_line.split("任务:")[-1].strip()
                elif "列表:" in last_line:
                    task_part = "审查文件: " + last_line.split("列表:")[-1].strip()
                
                prefix = "[异步] " if is_async else ""
                if len(task_part) > 26:
                    task_part = task_part[:26] + "..."
                self.task_lbl.configure(text=f"{prefix}任务: {task_part}")

                # Extract model
                engine_part = "GLM-5.3"
                if "引擎:" in last_line:
                    engine_part = last_line.split("引擎:")[1].split("|")[0].strip()
                self.meta_lbl.configure(text=f"引擎: {engine_part} | 协同运行中...")

                # Timer start
                if self.start_timestamp == 0.0:
                    self.start_timestamp = time.time()

            elif "[DONE]" in last_line:
                self.current_state = "IDLE"
                self.start_timestamp = 0.0
                self.status_dot.configure(fg=COLOR_IDLE)
                self.status_text.configure(text="空闲待命 (最近成功)", fg=COLOR_IDLE)
                
                # Extract duration
                dur_match = re.search(r"耗时:\s*([0-9.]+s)", last_line)
                dur = dur_match.group(1) if dur_match else ""
                self.timer_label.configure(text=f"耗时: {dur}" if dur else "")

                # Extract report or characters
                if "报告:" in last_line:
                    rep_name = last_line.split("报告:")[-1].strip()
                    self.meta_lbl.configure(text=f"报告已生成: {rep_name}")
                else:
                    char_match = re.search(r"返回字符数:\s*(\d+)", last_line)
                    chars = char_match.group(1) if char_match else ""
                    self.meta_lbl.configure(text=f"上次执行成功 (返回 {chars} 字) | 就绪待命")

            elif "[ERROR]" in last_line:
                self.current_state = "ERROR"
                self.start_timestamp = 0.0
                self.status_dot.configure(fg=COLOR_ERR)
                self.status_text.configure(text="执行异常", fg=COLOR_ERR)
                err_match = re.search(r"异常:\s*(.*)", last_line)
                err_txt = err_match.group(1)[:30] if err_match else "发生错误"
                self.task_lbl.configure(text=f"报错: {err_txt}")
                self.meta_lbl.configure(text="请查看历史日志了解异常详情")

        except Exception:
            pass

    def update_timer(self):
        """实时秒表走字"""
        if self.current_state == "BUSY" and self.start_timestamp > 0.0:
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
