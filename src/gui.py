#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adif2xlsx 的图形界面。

面向中国业余无线电爱好者：全中文，简约可爱的 INS 风格——奶油底色、樱花粉
主色、圆角卡片、大量留白。

界面只做三件事：
  1. 选择 ADIF 日志（文件或文件夹）
  2. 选择要输出的列（必选列 + 附加列）
  3. 选择保存位置，然后转换

转换在工作线程里进行，窗口不会卡住。

运行：python src/gui.py
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import adif2xlsx as core  # noqa: E402
import postage  # noqa: E402

# ---------------------------------------------------------------------------
# 配色：低饱和度的马卡龙色，一个角色一个颜色，不堆砌。
# ---------------------------------------------------------------------------
CREAM = "#FFFBF7"        # 窗口底色
CARD = "#FFFFFF"         # 卡片
BLUSH = "#FFE4EC"        # 浅粉
BLUSH_DEEP = "#FFC9DA"
PINK = "#FF7EA8"         # 主色
PINK_DARK = "#F06694"
LAVENDER = "#EFE6FF"     # 淡紫
MINT = "#DFF6EE"         # 薄荷
MINT_TEXT = "#2F8F6F"
INK = "#46404B"          # 主文字
INK_SOFT = "#8C8494"     # 次要文字
GOLD = "#FFC46B"

FONT_UI = "Microsoft YaHei UI"
FONT_EMOJI = "Segoe UI Emoji"
FONT_ROMAN = "Segoe UI"

# 窗口要能装下整个布局：按钮掉到屏幕外就等于没有按钮。
# 最小高度很关键——屏幕小的时候窗口会被压到这个值，也正是底部控件被挤掉的时候。
WINDOW_W, WINDOW_H = 660, 830
MIN_W, MIN_H = 640, 660

# 常用列的快捷组合
PRESETS = {
    "常用": ("CALL", "QSO_DATE", "TIME_ON_UTC", "BAND", "MODE",
             "RST_SENT", "RST_RCVD", "STATION_CALLSIGN",
             "DXCC_ENTITY", "QSL_POSTAGE_AIR"),
    "全部": None,
    "仅必选": (),
}


def _enable_hidpi() -> None:
    """开启 Per-Monitor DPI，文字才不糊。"""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (ImportError, AttributeError, OSError):
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except (ImportError, AttributeError, OSError):
            pass


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    """tkinter 没有圆角矩形，用平滑多边形画一个。"""
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedButton(tk.Canvas):
    """胶囊按钮，鼠标移上去会变深。"""

    def __init__(self, parent, text, command, *, width=200, height=46,
                 fill=PINK, hover=PINK_DARK, fg="#FFFFFF", font=None,
                 radius=None):
        super().__init__(parent, width=width, height=height,
                         highlightthickness=0, bd=0, bg=parent["bg"])
        self._command = command
        self._fill = fill
        self._hover = hover
        self._enabled = True
        self._radius = radius if radius is not None else height // 2
        self._shape = _round_rect(self, 1, 1, width - 1, height - 1,
                                  self._radius, fill=fill, outline="")
        self._label = self.create_text(width // 2, height // 2, text=text,
                                       fill=fg, font=font)
        self.bind("<Enter>", lambda _e: self._shade(self._hover))
        self.bind("<Leave>", lambda _e: self._shade(self._fill))
        self.bind("<Button-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def _shade(self, colour):
        if self._enabled:
            self.itemconfig(self._shape, fill=colour)

    def _press(self, _event):
        if self._enabled:
            self.itemconfig(self._shape, fill=PINK_DARK)
            self.move(self._label, 0, 1)

    def _release(self, event):
        if not self._enabled:
            return
        self.move(self._label, 0, -1)
        self._shade(self._hover)
        if 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height():
            self._command()

    def set_text(self, text):
        self.itemconfig(self._label, text=text)

    def set_enabled(self, enabled):
        self._enabled = enabled
        self.itemconfig(self._shape, fill=self._fill if enabled else "#E8E4EC")
        self.itemconfig(self._label, fill="#FFFFFF" if enabled else "#B3AEB8")


class FieldPicker(tk.Toplevel):
    """选择要输出哪些列。

    必选列永远输出（没有呼号和日期的日志没有意义），所以只显示、不可取消；
    附加列可以自由勾选。
    """

    def __init__(self, parent, available, selected, required, on_save):
        super().__init__(parent)
        self.title("选择列")
        self.configure(bg=CREAM)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None
        self._on_save = on_save
        self._vars = {}

        selected = set(selected) if selected is not None else set(available)

        head = tk.Frame(self, bg=CREAM)
        head.pack(fill="x", padx=18, pady=(16, 4))
        tk.Label(head, text="选择要输出的列", font=(FONT_UI, 13, "bold"),
                 bg=CREAM, fg=INK).pack(anchor="w")
        tk.Label(head,
                 text="必选列一定会输出；附加列只在你勾选时输出。\n"
                      "全为空的附加列本来就不会输出，勾选后才会保留空列。",
                 font=(FONT_UI, 9), bg=CREAM, fg=INK_SOFT,
                 justify="left").pack(anchor="w", pady=(4, 0))

        # --- 快捷按钮 ---
        quick = tk.Frame(self, bg=CREAM)
        quick.pack(fill="x", padx=18, pady=(10, 6))
        tk.Label(quick, text="快捷：", font=(FONT_UI, 9), bg=CREAM,
                 fg=INK_SOFT).pack(side="left")
        for name in ("常用", "全部", "仅必选"):
            self._soft_button(quick, name,
                              lambda n=name: self._apply_preset(n)).pack(
                side="left", padx=(0, 6))

        # --- 滚动列表框 ---
        body = tk.Frame(self, bg=CARD, highlightthickness=1,
                        highlightbackground=BLUSH_DEEP)
        body.pack(fill="both", expand=True, padx=18, pady=(4, 8))
        canvas = tk.Canvas(body, bg=CARD, highlightthickness=0, bd=0,
                           width=470, height=360)
        scroll = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=CARD)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)

        def _layout(_event=None):
            """Keep the scroll region and the scrollbar in step with content.

            One handler for both: binding <Configure> twice replaces the first
            callback, which left the scroll region unset and made the list
            unscrollable (and looked like blank space while dragging).
            """
            canvas.itemconfigure(window, width=canvas.winfo_width())
            bbox = canvas.bbox("all")
            if bbox:
                canvas.configure(scrollregion=bbox)
            needs = bool(bbox) and (bbox[3] - bbox[1]) > canvas.winfo_height()
            if needs and not scroll.winfo_ismapped():
                scroll.pack(side="right", fill="y")
            elif not needs and scroll.winfo_ismapped():
                scroll.pack_forget()

        def _scroll(event):
            """Scroll only while the pointer is over the list, and never past
            the content.  Bound to the canvas rather than globally: a global
            wheel binding scrolled this list from anywhere in the dialog, and
            scrolling past the end showed a blank area."""
            bbox = canvas.bbox("all")
            if not bbox or (bbox[3] - bbox[1]) <= canvas.winfo_height():
                return "break"          # nothing to scroll; leave it alone
            canvas.yview_scroll(-1 * (event.delta // 120), "units")
            return "break"

        inner.bind("<Configure>", _layout)
        canvas.bind("<Configure>", _layout)
        canvas.bind("<Map>", _layout)
        # Bind to the canvas only, so the wheel works over the list and nowhere
        # else, plus inside the frame itself (children do not inherit).
        for target in (canvas, inner):
            target.bind("<MouseWheel>", _scroll)
        self.after(60, _layout)

        # 必选列
        tk.Label(inner, text="必选列（共 %d 列，始终输出）" % len(required),
                 font=(FONT_UI, 10, "bold"), bg=CARD, fg=PINK_DARK
                 ).pack(anchor="w", padx=12, pady=(10, 4))
        for column in required:
            self._row(inner, column, locked=True)

        # 附加列
        optional = [c for c in available if c not in set(required)]
        tk.Label(inner, text="附加列（勾选后输出）",
                 font=(FONT_UI, 10, "bold"), bg=CARD, fg=INK
                 ).pack(anchor="w", padx=12, pady=(14, 4))
        for column in optional:
            self._row(inner, column, locked=False)
        if not optional:
            tk.Label(inner, text="（这个日志没有可选的附加字段）",
                     font=(FONT_UI, 9), bg=CARD, fg=INK_SOFT
                     ).pack(anchor="w", padx=12)

        # --- 底部按钮 ---
        footer = tk.Frame(self, bg=CREAM)
        footer.pack(fill="x", padx=18, pady=(0, 16))
        self.count_label = tk.Label(footer, text="", font=(FONT_UI, 9),
                                    bg=CREAM, fg=INK_SOFT)
        self.count_label.pack(side="left")
        RoundedButton(footer, "取消", self.destroy, width=96, height=38,
                      fill="#E8E4EC", hover="#DAD4E0", fg=INK,
                      font=(FONT_UI, 10)).pack(side="right")
        RoundedButton(footer, "确定", self._save, width=110, height=38,
                      font=(FONT_UI, 10, "bold")).pack(side="right", padx=8)
        # Only now can the selection be shown: _update_count needs count_label.
        self._apply_selection(selected)

    def _soft_button(self, parent, text, command):
        button = tk.Label(parent, text=text, font=(FONT_UI, 9),
                          bg=BLUSH, fg=INK, padx=10, pady=4, cursor="hand2")
        button.bind("<Enter>", lambda _e: button.configure(bg=BLUSH_DEEP))
        button.bind("<Leave>", lambda _e: button.configure(bg=BLUSH))
        button.bind("<Button-1>", lambda _e: command())
        return button

    def _row(self, parent, column, *, locked):
        row = tk.Frame(parent, bg=CARD)
        row.pack(fill="x", padx=12, pady=1)
        var = tk.BooleanVar(value=locked)
        self._vars[column] = (var, locked)
        if locked:
            tk.Label(row, text="✓", font=(FONT_UI, 10, "bold"), bg=CARD,
                     fg=PINK, width=2).pack(side="left")
        else:
            cb = tk.Checkbutton(row, variable=var, bg=CARD,
                                activebackground=CARD, selectcolor=CARD,
                                highlightthickness=0, bd=0, cursor="hand2",
                                command=self._update_count)
            cb.pack(side="left")
        tk.Label(row, text=core.field_label(column), font=(FONT_UI, 9),
                 bg=CARD, fg=INK if locked else INK).pack(side="left")
        tk.Label(row, text=column, font=(FONT_ROMAN, 8), bg=CARD,
                 fg=INK_SOFT).pack(side="right")

    def _apply_selection(self, selected):
        for column, (var, locked) in self._vars.items():
            if not locked:
                var.set(column in selected)
        self._update_count()

    def _apply_preset(self, name):
        wanted = PRESETS[name]
        if wanted is None:
            self._apply_selection(set(self._vars))
        else:
            self._apply_selection(set(wanted))
        self._update_count()

    def _chosen(self):
        return [c for c, (var, locked) in self._vars.items()
                if locked or var.get()]

    def _update_count(self):
        chosen = self._chosen()
        required = core.REQUIRED_COLUMNS
        locked = sum(1 for c in chosen if c in required)
        self.count_label.configure(
            text=f"已选 {len(chosen)} 列（必选 {locked} + 附加 {len(chosen) - locked}）")

    def _save(self):
        self.result = self._chosen()
        self._on_save(self.result)
        self.destroy()


class AdifApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.paths: list[str] = []
        self.busy = False
        self.events: "queue.Queue[tuple]" = queue.Queue()
        # None = 全部有数据的列；列表 = 用户指定的列
        self.selected_columns: "list[str] | None" = None
        self._available: list[str] = list(core.REQUIRED_COLUMNS)
        self._build()
        self._drain()

    # -- 构建界面 ----------------------------------------------------------
    def _build(self):
        root = self.root
        root.title("ADIF 转 Excel ✨")
        root.configure(bg=CREAM)
        root.minsize(MIN_W, MIN_H)
        self._centre(WINDOW_W, WINDOW_H)
        self._set_icon()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        header = tk.Frame(root, bg=CREAM)
        header.pack(fill="x", padx=26, pady=(18, 4))
        tk.Label(header, text="ADIF", font=(FONT_ROMAN, 25, "bold"),
                 bg=CREAM, fg=INK).pack(side="left")
        tk.Label(header, text=" → ", font=(FONT_ROMAN, 21, "bold"),
                 bg=CREAM, fg=PINK).pack(side="left")
        tk.Label(header, text="Excel", font=(FONT_ROMAN, 25, "bold"),
                 bg=CREAM, fg=INK).pack(side="left")
        tk.Label(header, text="✨", font=(FONT_EMOJI, 19),
                 bg=CREAM).pack(side="left", padx=(6, 0))

        tk.Label(root, text="把业余无线电日志整理成一张干净的表格",
                 font=(FONT_UI, 9), bg=CREAM, fg=INK_SOFT
                 ).pack(anchor="w", padx=28, pady=(0, 10))

        # 状态栏先打包（贴底），这样它一定占得到位置：放在最后打包时，
        # 屏幕一小就被挤出窗口。
        self._build_status()
        self._build_files()
        self._build_options()
        self._build_action()

    def _set_icon(self):
        icon = os.path.join(HERE, "assets", "adif2xlsx.ico")
        if not os.path.isfile(icon):
            return
        try:
            self.root.iconbitmap(default=icon)
        except tk.TclError:
            pass

    def _centre(self, w, h):
        """居中摆放，并且绝不超过可用屏幕高度。

        固定高度在 768 像素的屏幕上会钻到任务栏底下，状态栏就看不见了。
        """
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        work_h = self._work_area_height(screen_h)
        h = min(h, work_h - 40)
        w = min(w, screen_w - 40)
        x = max(0, (screen_w - w) // 2)
        y = max(0, (work_h - h) // 2)
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    @staticmethod
    def _work_area_height(fallback: int) -> int:
        """屏幕高度减去任务栏（Windows 工作区）。"""
        if os.name != "nt":
            return fallback
        try:
            import ctypes
            import ctypes.wintypes as wintypes
            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(
                    0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                return rect.bottom - rect.top
        except (ImportError, AttributeError, OSError):
            pass
        return fallback - 48

    def _build_files(self):
        wrap = tk.Frame(self.root, bg=CREAM)
        wrap.pack(fill="both", expand=True, padx=22)

        panel = tk.Frame(wrap, bg=CARD, highlightthickness=1,
                         highlightbackground=BLUSH_DEEP)
        panel.pack(fill="both", expand=True)

        head = tk.Frame(panel, bg=CARD)
        head.pack(fill="x", padx=16, pady=(12, 6))
        tk.Label(head, text="📻", font=(FONT_EMOJI, 13), bg=CARD
                 ).pack(side="left")
        tk.Label(head, text="  日志文件", font=(FONT_UI, 11, "bold"),
                 bg=CARD, fg=INK).pack(side="left")
        self.count_label = tk.Label(head, text="还没有文件", font=(FONT_UI, 9),
                                    bg=CARD, fg=INK_SOFT)
        self.count_label.pack(side="right")

        self.listbox = tk.Listbox(
            panel, selectmode="extended", activestyle="none",
            font=(FONT_UI, 10), bg="#FFF8FB", fg=INK,
            selectbackground=BLUSH, selectforeground=INK,
            highlightthickness=0, bd=0, relief="flat",
            # 请求高度小一点，整个布局才装得进最小窗口；多余的空间它照样会撑满。
            height=6,
            # 不要滚动条：列表一有内容就冒出来，很破坏干净的感觉。
            yscrollcommand=None, xscrollcommand=None)
        self.listbox.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.listbox.bind("<Enter>",
                          lambda _e: self.listbox.bind_all("<MouseWheel>", self._wheel))
        self.listbox.bind("<Leave>", lambda _e: self.listbox.unbind_all("<MouseWheel>"))

        buttons = tk.Frame(panel, bg=CARD)
        buttons.pack(fill="x", padx=16, pady=(0, 12))
        self._soft_button(buttons, "＋ 添加文件", self.add_files).pack(side="left")
        self._soft_button(buttons, "🗂 添加文件夹", self.add_folder
                          ).pack(side="left", padx=8)
        self._soft_button(buttons, "✕ 移除所选", self.remove_selected
                          ).pack(side="left")
        self._soft_button(buttons, "清空", self.clear_files).pack(side="right")

    def _wheel(self, event):
        self.listbox.yview_scroll(-1 * (event.delta // 120), "units")

    def _build_options(self):
        wrap = tk.Frame(self.root, bg=CREAM)
        wrap.pack(fill="x", padx=22, pady=(12, 0))
        panel = tk.Frame(wrap, bg=CARD, highlightthickness=1,
                         highlightbackground=LAVENDER)
        panel.pack(fill="x")

        # --- 要输出的列 ---
        row = tk.Frame(panel, bg=CARD)
        row.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(row, text="📋", font=(FONT_EMOJI, 13), bg=CARD).pack(side="left")
        tk.Label(row, text="  要输出的列", font=(FONT_UI, 11, "bold"),
                 bg=CARD, fg=INK).pack(side="left")
        self.columns_label = tk.Label(row, text="", font=(FONT_UI, 9),
                                      bg=CARD, fg=INK_SOFT)
        self.columns_label.pack(side="left", padx=10)
        self._soft_button(row, "选择列…", self.choose_columns).pack(side="right")

        # --- 保存位置 ---
        row2 = tk.Frame(panel, bg=CARD)
        row2.pack(fill="x", padx=16, pady=(10, 4))
        tk.Label(row2, text="💾", font=(FONT_EMOJI, 13), bg=CARD).pack(side="left")
        tk.Label(row2, text="  保存到", font=(FONT_UI, 11, "bold"),
                 bg=CARD, fg=INK).pack(side="left")
        tk.Label(row2, text="默认存到桌面", font=(FONT_UI, 9),
                 bg=CARD, fg=INK_SOFT).pack(side="left", padx=8)

        path_row = tk.Frame(panel, bg=CARD)
        path_row.pack(fill="x", padx=16, pady=(0, 8))
        self.output_var = tk.StringVar(value=core.default_output_path())
        entry = tk.Entry(path_row, textvariable=self.output_var,
                         font=(FONT_UI, 9), bg="#FFF8FB", fg=INK,
                         relief="flat", highlightthickness=1,
                         highlightbackground=BLUSH_DEEP,
                         highlightcolor=PINK)
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        self._soft_button(path_row, "另存为…", self.choose_output).pack(side="left")

        # --- 其他选项 ---
        opts = tk.Frame(panel, bg=CARD)
        opts.pack(fill="x", padx=16, pady=(0, 10))
        self.recursive_var = tk.BooleanVar(value=False)
        self._check(opts, "包含子文件夹", self.recursive_var).pack(side="left")
        self.open_var = tk.BooleanVar(value=True)
        self._check(opts, "完成后打开表格", self.open_var).pack(side="left", padx=18)

        # --- 说明 ---
        info = tk.Frame(panel, bg=MINT)
        info.pack(fill="x", padx=16, pady=(0, 12))
        tk.Label(info, text="ⓘ", font=(FONT_EMOJI, 11), bg=MINT, fg=MINT_TEXT
                 ).pack(side="left", padx=(10, 6), pady=6)
        tk.Label(info,
                 text=(f"自动附上 DXCC 分区与 QSL 平信邮资"
                       f"（{postage.REFERENCE_WEIGHT_G} 克，资费核对于 "
                       f"{postage.RATES_VERIFIED_ON}）；"
                       f"所有时间为 UTC，不做时区换算"),
                 font=(FONT_UI, 9), bg=MINT, fg=MINT_TEXT,
                 justify="left").pack(side="left", pady=6)
        self._refresh_columns_label()

    def _build_action(self):
        wrap = tk.Frame(self.root, bg=CREAM)
        wrap.pack(fill="x", padx=22, pady=(12, 2))
        self.button = RoundedButton(
            wrap, "开始转换  ✨", self.start, width=250, height=50,
            font=(FONT_UI, 12, "bold"))
        self.button.pack()
        self.progress = ttk.Progressbar(wrap, mode="indeterminate", length=250)
        # 先不显示：空闲时的进度条是一条空的粉色槽，看着像画错了。
        # 转换时才出现。
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TProgressbar", background=PINK, troughcolor=BLUSH,
                        bordercolor=BLUSH, lightcolor=PINK, darkcolor=PINK)

    def _build_status(self):
        self.status = tk.Label(self.root, text="准备好了～ 先添加 ADIF 日志吧",
                               font=(FONT_UI, 9), bg=CREAM, fg=INK_SOFT,
                               wraplength=580, justify="center")
        self.status.pack(side="bottom", fill="x", padx=26, pady=(6, 20))

    def _soft_button(self, parent, text, command):
        button = tk.Label(parent, text=text, font=(FONT_UI, 9),
                          bg=BLUSH, fg=INK, padx=11, pady=5, cursor="hand2")
        button.bind("<Enter>", lambda _e: button.configure(bg=BLUSH_DEEP))
        button.bind("<Leave>", lambda _e: button.configure(bg=BLUSH))
        button.bind("<Button-1>", lambda _e: command())
        return button

    def _check(self, parent, text, variable):
        return tk.Checkbutton(parent, text=text, variable=variable,
                              font=(FONT_UI, 9), bg=CARD, fg=INK,
                              activebackground=CARD, activeforeground=PINK,
                              selectcolor=CARD, cursor="hand2",
                              highlightthickness=0, bd=0)

    # -- 列选择 ------------------------------------------------------------
    def choose_columns(self):
        """打开列选择窗口。附带先把已选文件读一遍，得到真实字段列表。"""
        available = self._available
        if self.paths:
            available = self._scan_fields() or available
        FieldPicker(self.root, available, self.selected_columns,
                    list(core.REQUIRED_COLUMNS), self._on_columns_chosen)

    def _scan_fields(self):
        """读取已选文件，返回它们能产生的列名。出错就返回 None。"""
        try:
            inputs = core.discover_inputs(
                self.paths, recursive=self.recursive_var.get())
        except (OSError, core.AdifParseError):
            return None
        if not inputs:
            return None
        self._say("正在读取字段…")
        self.root.update_idletasks()
        available: list[str] = []
        for path in inputs:
            try:
                res = core.parse_adif(path)
            except (core.AdifParseError, OSError):
                continue
            result = core.build_rows([(path, res.records, res.header,
                                       res.unknown_tags)])
            for column in result.available:
                if column not in available:
                    available.append(column)
        if available:
            self._available = available
        self._say(f"读取到 {len(available)} 个可用字段")
        return available or None

    def _on_columns_chosen(self, columns):
        self.selected_columns = columns
        self._refresh_columns_label()

    def _refresh_columns_label(self):
        if self.selected_columns is None:
            text = f"全部有数据的列（必选 {len(core.REQUIRED_COLUMNS)} 列 + 附加）"
        else:
            total = len(self.selected_columns)
            text = f"已选 {total} 列"
        self.columns_label.configure(text=text)

    # -- 文件操作 ----------------------------------------------------------
    def add_files(self):
        chosen = filedialog.askopenfilenames(
            title="选择 ADIF 日志",
            filetypes=[("ADIF 日志", "*.adi *.adif"), ("所有文件", "*.*")])
        self._add(chosen)

    def add_folder(self):
        chosen = filedialog.askdirectory(title="选择包含 ADIF 的文件夹")
        if chosen:
            self._add([chosen])

    def _add(self, chosen):
        added = 0
        for item in chosen:
            path = os.path.abspath(item)
            if path not in self.paths:
                self.paths.append(path)
                added += 1
        self._refresh_list()
        if added:
            self._say(f"添加了 {added} 项，共 {len(self.paths)} 项")

    def remove_selected(self):
        for index in sorted(self.listbox.curselection(), reverse=True):
            if index < len(self.paths):
                self.paths.pop(index)
        self._refresh_list()

    def clear_files(self):
        self.paths.clear()
        self._refresh_list()

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for path in self.paths:
            name = os.path.basename(path.rstrip("\\/")) or path
            mark = "📁" if os.path.isdir(path) else "📄"
            self.listbox.insert("end", f"  {mark}  {name}")
        count = len(self.paths)
        self.count_label.configure(
            text="还没有文件" if not count else f"共 {count} 项")

    def choose_output(self):
        chosen = filedialog.asksaveasfilename(
            title="保存 Excel 到", defaultextension=".xlsx",
            initialfile=os.path.basename(self.output_var.get()),
            filetypes=[("Excel 工作簿", "*.xlsx")])
        if chosen:
            self.output_var.set(chosen)

    # -- 转换 --------------------------------------------------------------
    def start(self):
        if self.busy:
            return
        if not self.paths:
            messagebox.showinfo("还没有文件", "请先添加 ADIF 日志文件或文件夹 🙂",
                                parent=self.root)
            return
        output = self.output_var.get().strip()
        if not output:
            messagebox.showinfo("缺少保存位置", "请先选择保存位置 🙂",
                                parent=self.root)
            return
        if not output.lower().endswith(".xlsx"):
            output += ".xlsx"
            self.output_var.set(output)
        if os.path.exists(output) and not messagebox.askyesno(
                "已有同名文件",
                f"{os.path.basename(output)} 已存在，要覆盖吗？",
                parent=self.root):
            return

        self.busy = True
        self.button.set_enabled(False)
        self.button.set_text("转换中…  ⏳")
        self.progress.pack(pady=(8, 0))
        self.progress.start(12)
        self._say("正在读取日志…")
        options = (list(self.paths), output, self.recursive_var.get(),
                   self.selected_columns)
        threading.Thread(target=self._worker, args=options, daemon=True).start()

    def _worker(self, paths, output, recursive, columns):
        try:
            inputs = core.discover_inputs(paths, recursive=recursive)
            if not inputs:
                self.events.put(("error", "这些路径里没有 .adi / .adif 文件"))
                return
            parsed = []
            skipped = []
            for path in inputs:
                try:
                    res = core.parse_adif(path)
                except (core.AdifParseError, OSError) as exc:
                    skipped.append(f"{os.path.basename(path)}：{exc}")
                    continue
                parsed.append((path, res.records, res.header, res.unknown_tags))
                self.events.put(("progress",
                                 f"已读取 {os.path.basename(path)}"
                                 f"（{len(res.records)} 条）"))
            if not parsed:
                self.events.put(("error", "没有可转换的记录\n" + "\n".join(skipped[:5])))
                return
            result = core.convert_to_workbook(parsed, output, columns)
            self.events.put(("done", result, output, skipped))
        except core.AdifParseError as exc:
            self.events.put(("error", str(exc)))
        except OSError as exc:
            self.events.put(("error", f"无法写入文件：{exc}"))
        except Exception as exc:  # noqa: BLE001 - 任何意外都要让用户看到
            self.events.put(("error", f"意外错误：{type(exc).__name__}: {exc}"))

    def _drain(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    self._say(event[1])
                elif kind == "error":
                    self._finish()
                    self._say("出错了 😢 " + event[1].splitlines()[0])
                    messagebox.showerror("转换失败", event[1], parent=self.root)
                elif kind == "done":
                    self._finish()
                    self._report(event[1], event[2], event[3])
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def _finish(self):
        self.busy = False
        self.progress.stop()
        self.progress.pack_forget()
        self.button.set_enabled(True)
        self.button.set_text("开始转换  ✨")

    def _report(self, result, output, skipped):
        self._say(f"完成啦 🎉 {result.total_records} 条记录 → "
                  f"{os.path.basename(output)}")
        lines = [
            "转换成功！🎉",
            "",
            f"记录条数：{result.total_records}",
            f"输出列数：{len(result.columns)}",
            f"来源文件：{len(result.sources)}",
            "",
            f"已保存到：\n{output}",
        ]
        if skipped:
            lines += ["", f"跳过 {len(skipped)} 个文件："] + skipped[:4]
        if result.incomplete:
            lines += ["", f"提示：{len(result.incomplete)} 条记录有字段为空，"
                          f"详见 Summary 表"]
        if self.open_var.get() and os.path.exists(output):
            self._open(output)
            lines += ["", "（已为你打开表格）"]
        messagebox.showinfo("转换完成", "\n".join(lines), parent=self.root)

    @staticmethod
    def _open(path):
        try:
            if os.name == "nt":
                os.startfile(path)  # noqa: S606 - 就是要用 Excel 打开
            else:
                import subprocess
                subprocess.Popen(["xdg-open", path], check=False)
        except OSError:
            pass

    def _say(self, text):
        self.status.configure(text=text)

    def _on_close(self):
        if self.busy and not messagebox.askyesno(
                "正在转换", "转换还没结束，确定要关闭吗？", parent=self.root):
            return
        self.root.destroy()


def write_marker(text: str) -> None:
    """给测试用的记录点；绝不抛异常。"""
    target = os.environ.get("ADIF2XLSX_GUI_MARKER")
    if not target:
        return
    try:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except OSError:
        pass


def _stamp(label: str, start: float) -> float:
    """记录启动阶段，仅在 ADIF2XLSX_GUI_TIMING=1 时写日志。"""
    import time
    now = time.perf_counter()
    if os.environ.get("ADIF2XLSX_GUI_TIMING"):
        try:
            import adif2xlsx as core_module
            core_module.write_log(f"  [gui] {label}: {now - start:.2f}s")
        except Exception:  # noqa: BLE001 - 诊断不能拖垮启动
            pass
    return now


def main() -> int:
    import time
    start = time.perf_counter()
    _enable_hidpi()
    _stamp("hidpi", start)
    root = tk.Tk()
    _stamp("Tk created", start)
    app = AdifApp(root)
    _stamp("widgets built", start)

    if "--self-test" in sys.argv:
        root.update_idletasks()
        root.update()
        _stamp("first paint", start)
        app._say("self-test")
        app._refresh_list()
        root.update_idletasks()
        width, height = root.winfo_width(), root.winfo_height()
        root.destroy()
        write_marker(f"gui self-test ok: {width}x{height}")
        return 0 if width > 100 and height > 100 else 1

    # 事件循环一开始就把窗口显示出来，并记录它真正出现的时刻：
    # 一分钟才出现的窗口看起来就是坏的。
    root.deiconify()
    root.lift()
    root.after(1, lambda: _stamp("window on screen", start))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
