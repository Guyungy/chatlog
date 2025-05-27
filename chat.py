"""
Chat Log Combiner – WISMASS 内部版
=================================
• 统一汇总指定群聊（企业微信 / 微信）聊天记录并与自定义模板拼接，粘贴到光标位置。
• 支持无限群聊、无限模板，可勾选模板 -> 群聊映射。
• Ctrl+M 一键粘贴＋发送。

依赖:
    pip install ttkbootstrap keyboard pyperclip requests

作者: 2025-05-27
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List
from urllib.parse import quote

import keyboard
import pyperclip
import requests
import ttkbootstrap as tb
from ttkbootstrap.constants import *

# ---------------------------------------------------------------------------
# 常量 & 工具函数
# ---------------------------------------------------------------------------

CONFIG_PATH = "config.json"
API_URL = "http://127.0.0.1:5030/api/v1/chatlog"   # 固定后端接口

session = requests.Session()
session.headers.update({"User-Agent": "ChatLogCombiner/1.0"})


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Chat:
    name: str


@dataclass
class Template:
    name: str
    content: str
    enabled_chats: List[bool] = field(default_factory=list)


@dataclass
class AppConfig:
    chats: List[Chat]
    custom_templates: List[Template]
    current_template: int = 0
    global_date_from: str = today_str()
    global_date_to: str = today_str()

    # ----------------------- 读写 -----------------------

    @staticmethod
    def _default() -> "AppConfig":
        return AppConfig(
            chats=[Chat("群聊A"), Chat("群聊B")],
            custom_templates=[
                Template("模板A", "这是A正文", [True, False]),
                Template("模板B", "这是B正文", [True, True]),
            ],
            current_template=0,
        )

    @classmethod
    def load(cls) -> "AppConfig":
        """读取 config.json，若不存在则返回默认配置。"""
        if not os.path.exists(CONFIG_PATH):
            return cls._default()

        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)

        chats = [Chat(**c) for c in raw.get("chats", [])]
        if not chats:
            chats = [Chat("群聊1")]

        templates = []
        for tpl in raw.get("custom_templates", []):
            tpl_enabled = tpl.get("enabled_chats", [])
            # 自动补全/裁剪 enabled_chats 长度
            if len(tpl_enabled) < len(chats):
                tpl_enabled += [False] * (len(chats) - len(tpl_enabled))
            templates.append(
                Template(
                    name=tpl.get("name", "未命名模板"),
                    content=tpl.get("content", ""),
                    enabled_chats=tpl_enabled[: len(chats)],
                )
            )

        if not templates:
            templates.append(Template("默认模板", "", [False] * len(chats)))

        return AppConfig(
            chats=chats,
            custom_templates=templates,
            current_template=min(
                raw.get("current_template", 0), len(templates) - 1
            ),
            global_date_from=raw.get("global_date_from", today_str()),
            global_date_to=raw.get("global_date_to", today_str()),
        )

    def save(self) -> None:
        """保存到 config.json（确保文件简单易读）。"""
        def serialize(obj):
            if isinstance(obj, AppConfig):
                d = asdict(obj)
                # dataclass 默认会把 dataclass 对象也递归转 dict
                return d
            raise TypeError(obj)

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self, f, indent=2, ensure_ascii=False, default=serialize)


# ---------------------------------------------------------------------------
# 主应用类
# ---------------------------------------------------------------------------

class ChatCombinerApp(tb.Window):
    """Tk/ttkbootstrap GUI 封装。"""

    # -------------------- 初始化 --------------------

    def __init__(self, cfg: AppConfig):
        super().__init__(themename="cosmo")
        self.title("信息汇总 - WISMASS内部版")
        self.geometry("1450x900")
        self.resizable(False, False)
        self.configure(bg="#f4f8fc")

        self.cfg = cfg  # AppConfig 对象

        # gui 状态变量
        self.global_date_from_var = tb.StringVar(value=self.cfg.global_date_from)
        self.global_date_to_var = tb.StringVar(value=self.cfg.global_date_to)

        # 每个 chat、template 在 UI 中对应的行信息
        self._chat_rows: list[dict] = []
        self._template_frames: list[dict] = []

        self._build_ui()
        self._load_config_into_ui()
        self._register_hotkey()

    # -------------------- 布局 --------------------

    def _build_ui(self):
        # ---------- 顶部全局日期 ----------
        date_fr = tb.Frame(self)
        date_fr.pack(fill="x", padx=18, pady=(10, 0))

        tb.Label(date_fr, text="全局起始日期：").pack(side="left")
        tb.Entry(date_fr, textvariable=self.global_date_from_var, width=14).pack(
            side="left", padx=(0, 16)
        )
        tb.Label(date_fr, text="全局结束日期：").pack(side="left")
        tb.Entry(date_fr, textvariable=self.global_date_to_var, width=14).pack(
            side="left", padx=(0, 16)
        )

        # ---------- 中间双栏 ----------
        main_fr = tb.Frame(self)
        main_fr.pack(fill="both", expand=True, padx=18, pady=14)
        main_fr.grid_rowconfigure(0, weight=1)
        main_fr.grid_columnconfigure(0, weight=2, minsize=650)
        main_fr.grid_columnconfigure(1, weight=3, minsize=800)

        # -- 左：群聊列表 --
        self._build_left(main_fr)

        # -- 右：模板管理 --
        self._build_right(main_fr)

        # ---------- 底部提示 ----------
        tb.Label(
            self,
            text="将光标放在目标输入框，点击按钮或按 Ctrl+M 可自动粘贴+发送",
        ).pack(pady=(4, 2))
        tb.Label(self, text="—— WISMASS内部版 ——").pack(pady=(0, 8))

    def _build_left(self, parent):
        lf = tb.Labelframe(
            parent,
            text="群聊设置（全局共享）",
            bootstyle=PRIMARY,
            padding=(16, 12),
        )
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 24))
        lf.grid_rowconfigure(0, weight=1)
        lf.grid_columnconfigure(0, weight=1)

        # 滚动区
        self.chat_canvas = tb.Canvas(lf, width=600, height=470, highlightthickness=0)
        sb = tb.Scrollbar(lf, orient="vertical", command=self.chat_canvas.yview)
        self.chat_canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self.chat_inner = tb.Frame(self.chat_canvas)
        self.chat_inner.bind(
            "<Configure>",
            lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")),
        )
        self.chat_canvas.create_window((0, 0), window=self.chat_inner, anchor="nw")
        self.chat_canvas.configure(yscrollcommand=sb.set)

        # 表头
        for i, tx in enumerate(("群聊名称", "起始日期", "结束日期", "")):
            tb.Label(self.chat_inner, text=tx).grid(
                row=0, column=i, padx=3, pady=2, sticky="ew"
            )

        # + 添加群聊 按钮
        tb.Button(
            lf,
            text="＋ 添加群聊",
            command=self._add_chat_row,
            bootstyle="primary-outline",
            width=22,
        ).grid(row=1, column=0, pady=(12, 0), sticky="we", padx=8)

    def _build_right(self, parent):
        rf = tb.Labelframe(parent, text="模板管理", padding=(16, 12))
        rf.grid(row=0, column=1, sticky="nsew")
        rf.grid_rowconfigure(1, weight=1)
        rf.grid_columnconfigure(0, weight=1)

        # 模板选择 & 新建
        top = tb.Frame(rf)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        tb.Label(top, text="模板选择：").pack(side="left")
        self.template_select = tb.Combobox(top, state="readonly", width=28)
        self.template_select.pack(side="left", padx=6)
        self.template_select.bind("<<ComboboxSelected>>", self._on_select_template)
        tb.Button(top, text="新建模板", command=self._add_template).pack(
            side="left", padx=14
        )

        # 模板滚动区
        self.tpl_canvas = tb.Canvas(rf, height=500, highlightthickness=0)
        sb = tb.Scrollbar(rf, orient="vertical", command=self.tpl_canvas.yview)
        self.tpl_canvas.grid(row=1, column=0, sticky="nsew")
        sb.grid(row=1, column=1, sticky="ns")

        self.tpl_inner = tb.Frame(self.tpl_canvas)
        self.tpl_canvas.create_window((0, 0), window=self.tpl_inner, anchor="nw", width=820)
        self.tpl_inner.bind(
            "<Configure>",
            lambda e: self.tpl_canvas.configure(scrollregion=self.tpl_canvas.bbox("all")),
        )
        self.tpl_canvas.configure(yscrollcommand=sb.set)

        # 鼠标滚轮同步
        self.tpl_canvas.bind_all(
            "<MouseWheel>", lambda e: self.tpl_canvas.yview_scroll(int(-e.delta / 120), "units")
        )

        # 底部按钮
        btn_row = tb.Frame(rf)
        btn_row.grid(row=2, column=0, sticky="ew", pady=(16, 0), padx=4)
        tb.Button(btn_row, text="💾 保存配置", width=14, command=self._save_config).pack(
            side="left", padx=16
        )
        tb.Button(
            btn_row,
            text="🚀 立即粘贴并发送 (Ctrl+M)",
            width=26,
            command=self._combine_and_paste,
        ).pack(side="left", padx=24)

    # -------------------- Chat 行 --------------------

    def _add_chat_row(self, chat: Chat | None = None):
        """在左侧列表新增一行群聊。"""
        if chat is None:
            chat = Chat("")
            self.cfg.chats.append(chat)  # 仅新增才写入 cfg

        idx = len(self._chat_rows)
        name_var = tb.StringVar(value=chat.name)

        row_fr = tb.Frame(self.chat_inner)
        row_fr.grid(row=idx + 1, column=0, columnspan=4, sticky="ew", pady=1)
        row_fr.grid_columnconfigure(0, weight=1)

        tb.Entry(row_fr, width=22, textvariable=name_var).grid(
            row=0, column=0, padx=(2, 6), pady=2, sticky="ew"
        )
        tb.Label(row_fr, textvariable=self.global_date_from_var, width=12).grid(
            row=0, column=1, padx=2, pady=2
        )
        tb.Label(row_fr, textvariable=self.global_date_to_var, width=12).grid(
            row=0, column=2, padx=2, pady=2
        )
        tb.Button(
            row_fr,
            text="✖",
            width=3,
            command=lambda i=idx: self._del_chat_row(i),
        ).grid(row=0, column=3, padx=(6, 2), pady=2)

        # 名称变动 → 刷新所有模板复选框
        name_var.trace_add("write", lambda *_: self._refresh_template_checks())

        self._chat_rows.append(
            {"frame": row_fr, "name_var": name_var}
        )
        self._sync_template_enabled_lengths()
        self._refresh_template_checks()

    def _del_chat_row(self, idx: int):
        if idx >= len(self._chat_rows) or len(self._chat_rows) <= 1:
            return  # 至少留一行

        # 移除 UI
        self._chat_rows[idx]["frame"].destroy()
        # 移除数据
        self._chat_rows.pop(idx)
        self.cfg.chats.pop(idx)

        # 重新布局剩余行
        for i, row in enumerate(self._chat_rows):
            row["frame"].grid(row=i + 1, column=0, columnspan=4, sticky="ew", pady=1)

        self._sync_template_enabled_lengths()
        self._refresh_template_checks()

    # -------------------- Template --------------------

    def _add_template(self, tpl: Template | None = None):
        """右侧新增一个模板编辑框。"""
        if tpl is None:
            tpl = Template("新模板", "", [False] * len(self._chat_rows))
            self.cfg.custom_templates.append(tpl)

        idx = len(self._template_frames)

        fr = tb.Labelframe(self.tpl_inner, text="模板编辑", padding=(16, 12))
        fr.pack(fill="x", padx=12, pady=(8, 16))

        # 标题
        name_var = tb.StringVar(value=tpl.name)
        tb.Label(fr, text="模板标题：").pack(anchor="w")
        tb.Entry(fr, width=50, textvariable=name_var).pack(anchor="w", fill="x", pady=(0, 6))

        # 正文
        tb.Label(fr, text="正文内容 / 提示词：").pack(anchor="w")
        text_box = tb.Text(fr, width=85, height=7)
        text_box.insert(tb.END, tpl.content)
        text_box.pack(anchor="w", fill="x", expand=True, pady=(0, 8))

        # 群聊复选框
        checks_fr = tb.Frame(fr)
        checks_fr.pack(anchor="w", pady=(2, 6))
        enabled_vars: list[tb.BooleanVar] = []
        for i, chat_row in enumerate(self._chat_rows):
            v = tb.BooleanVar(value=tpl.enabled_chats[i])
            enabled_vars.append(v)
            tb.Checkbutton(
                checks_fr,
                text=chat_row["name_var"].get() or f"群聊{i + 1}",
                variable=v,
            ).grid(row=i, column=0, sticky="w")

        # 删除模板
        tb.Button(
            fr,
            text="🗑 删除该模板",
            command=lambda i=idx: self._del_template(i),
        ).pack(anchor="e", pady=(8, 0))

        # 绑定变量到 cfg
        def _on_title_change(*_):
            tpl.name = name_var.get()
            self._refresh_template_select()

        name_var.trace_add("write", _on_title_change)

        text_box.bind("<<Modified>>", lambda e, t=text_box: self._on_content_change(tpl, t))

        self._template_frames.append(
            {
                "frame": fr,
                "name_var": name_var,
                "text_box": text_box,
                "checks_fr": checks_fr,
                "enabled_vars": enabled_vars,
            }
        )
        self._refresh_template_select()

    def _del_template(self, idx: int):
        if idx >= len(self._template_frames) or len(self._template_frames) <= 1:
            return  # 至少留一个模板

        self._template_frames[idx]["frame"].destroy()
        self._template_frames.pop(idx)
        self.cfg.custom_templates.pop(idx)

        self._refresh_template_select()
        self.template_select.current(0)
        self._show_template(0)

    # ---- 模板辅助 ----

    def _on_content_change(self, tpl: Template, textbox: tb.Text):
        if textbox.edit_modified():
            tpl.content = textbox.get("1.0", tb.END).rstrip()
            textbox.edit_modified(False)

    def _refresh_template_checks(self):
        """聊天名称变化后，刷新所有模板里的复选框标签。"""
        for tpl_idx, tpl_fr in enumerate(self._template_frames):
            for i, chat_row in enumerate(self._chat_rows):
                cb: tb.Checkbutton = tpl_fr["checks_fr"].grid_slaves(row=i, column=0)[0]  # type: ignore
                cb.configure(text=chat_row["name_var"].get() or f"群聊{i + 1}")

    def _sync_template_enabled_lengths(self):
        """增删群聊时同步 enabled_chats 长度。"""
        n_chat = len(self._chat_rows)
        for tpl, fr in zip(self.cfg.custom_templates, self._template_frames):
            # 扩/裁 enabled_chats
            if len(tpl.enabled_chats) < n_chat:
                tpl.enabled_chats += [False] * (n_chat - len(tpl.enabled_chats))
            elif len(tpl.enabled_chats) > n_chat:
                tpl.enabled_chats = tpl.enabled_chats[:n_chat]

            # UI 侧变量也同步
            vars_ = fr["enabled_vars"]
            if len(vars_) < n_chat:
                for i in range(len(vars_), n_chat):
                    v = tb.BooleanVar(value=tpl.enabled_chats[i])
                    vars_.append(v)
                    tb.Checkbutton(
                        fr["checks_fr"],
                        text=self._chat_rows[i]["name_var"].get() or f"群聊{i + 1}",
                        variable=v,
                    ).grid(row=i, column=0, sticky="w")
            elif len(vars_) > n_chat:
                for v in vars_[n_chat:]:
                    # 删除多余复选框
                    cb = v._variable._widgets[0]  # type: ignore
                    cb.destroy()
                del vars_[n_chat:]

    def _refresh_template_select(self):
        """刷新顶部下拉列表。"""
        names = [tpl.name for tpl in self.cfg.custom_templates]
        self.template_select["values"] = names
        if not names:
            return
        if self.template_select.current() == -1:
            self.template_select.current(0)

    def _on_select_template(self, *_):
        self._show_template(self.template_select.current())

    def _show_template(self, idx: int):
        for i, fr in enumerate(self._template_frames):
            fr["frame"].pack_forget()
            if i == idx:
                fr["frame"].pack(fill="x", padx=12, pady=(0, 16))
                fr["text_box"].focus_set()

        self.cfg.current_template = idx

    # -------------------- Config <-> UI --------------------

    def _load_config_into_ui(self):
        """把 AppConfig 数据渲染进 UI。"""
        # 先清空任何旧行
        for row in self._chat_rows:
            row["frame"].destroy()
        self._chat_rows.clear()

        for tpl in self._template_frames:
            tpl["frame"].destroy()
        self._template_frames.clear()

        # 重新加载
        for chat in self.cfg.chats:
            self._add_chat_row(chat)

        for tpl in self.cfg.custom_templates:
            self._add_template(tpl)

        # 同步下拉
        self._refresh_template_select()
        self.template_select.current(self.cfg.current_template)
        self._show_template(self.cfg.current_template)

    def _save_config(self):
        """从 UI 读取所有变量 -> cfg -> 写盘。"""
        # 群聊
        self.cfg.chats = [
            Chat(row["name_var"].get()) for row in self._chat_rows
        ]
        # 模板
        for tpl, fr in zip(self.cfg.custom_templates, self._template_frames):
            tpl.name = fr["name_var"].get()
            tpl.content = fr["text_box"].get("1.0", tb.END).rstrip()
            tpl.enabled_chats = [v.get() for v in fr["enabled_vars"]]

        self.cfg.global_date_from = self.global_date_from_var.get()
        self.cfg.global_date_to = self.global_date_to_var.get()

        self.cfg.save()
        tb.Messagebox.show_info("配置已保存到 config.json！", "保存成功")

    # -------------------- 粘贴逻辑 --------------------

    def _build_url(self, chat_name: str) -> str:
        return (
            f"{API_URL}?time={self.global_date_from_var.get()}~"
            f"{self.global_date_to_var.get()}&talker={quote(chat_name)}"
        )

    def _fetch_chatlog(self, url: str) -> str:
        try:
            r = session.get(url, timeout=8)
            r.raise_for_status()
            return r.text.strip() or "[空]"
        except Exception as e:
            return f"[ERROR] {e}"

    def _combine_and_paste(self):
        # 确保 cfg 最新
        self._save_config()

        tpl_idx = self.cfg.current_template
        tpl = self.cfg.custom_templates[tpl_idx]

        result_parts = [tpl.name.strip(), "", tpl.content.strip()]
        for enabled, chat in zip(tpl.enabled_chats, self.cfg.chats):
            if enabled:
                url = self._build_url(chat.name)
                content = self._fetch_chatlog(url)
                result_parts.extend(
                    [
                        "",
                        "========",
                        f"【群聊：{chat.name}】",
                        "========",
                        content,
                    ]
                )

        final_text = "\n".join(part for part in result_parts if part != "" or part == "")
        pyperclip.copy(final_text)
        time.sleep(0.15)
        keyboard.press_and_release("ctrl+v")
        time.sleep(0.05)
        keyboard.press_and_release("enter")

    # -------------------- 全局热键 --------------------

    def _register_hotkey(self):
        def _worker():
            keyboard.add_hotkey("ctrl+m", lambda: self.after(0, self._combine_and_paste))
            keyboard.wait()

        threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main():
    app = ChatCombinerApp(AppConfig.load())
    app.mainloop()


if __name__ == "__main__":
    main()
