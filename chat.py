import ttkbootstrap as tb
from ttkbootstrap.constants import *
import requests
import keyboard
import threading
import pyperclip
import time
import json
import os
from datetime import datetime
from urllib.parse import quote

CONFIG_PATH = 'config.json'
API_URL = 'http://127.0.0.1:5030/api/v1/chatlog'

def today_str():
    return datetime.now().strftime('%Y-%m-%d')

def default_config():
    return {
        "chats": [
            {"name": "群聊A"},
            {"name": "群聊B"}
        ],
        "custom_templates": [
            {
                "name": "模板A",
                "content": "这是A正文",
                "enabled_chats": [True, False]
            },
            {
                "name": "模板B",
                "content": "这是B正文",
                "enabled_chats": [True, True]
            }
        ],
        "current_template": 0,
        "global_date_from": today_str(),
        "global_date_to": today_str()
    }

def load_config():
    if not os.path.exists(CONFIG_PATH):
        return default_config()
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    n = len(cfg.get("chats", []))
    for tpl in cfg.get("custom_templates", []):
        en = tpl.get("enabled_chats", [])
        if len(en) < n:
            en += [False] * (n - len(en))
        elif len(en) > n:
            en = en[:n]
        tpl["enabled_chats"] = en
    return cfg

def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def build_url(chat):
    return f"{API_URL}?time={global_date_from_var.get()}~{global_date_to_var.get()}&talker={quote(chat['name'])}"

def fetch_url(url):
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        return f"[ERROR] {url}\n{e}"

chat_rows = []
template_list = []

def sync_enabled_chats_len():
    n = len(chat_rows)
    for t in template_list:
        e = t["enabled_vars"]
        if len(e) < n:
            for i in range(n - len(e)):
                v = tb.BooleanVar(value=False)
                e.append(v)
        elif len(e) > n:
            del e[n:]
        update_template_chat_checks(t)

def get_gui_config():
    chats = []
    for row in chat_rows:
        chats.append({
            "name": row["name_var"].get()
        })
    templates = []
    for t in template_list:
        enabled = [v.get() for v in t["enabled_vars"]]
        templates.append({
            "name": t["name_var"].get(),
            "content": t["content_box"].get("1.0", tb.END).strip(),
            "enabled_chats": enabled
        })
    idx = template_select.current() if template_select['values'] else 0
    return {
        "chats": chats,
        "custom_templates": templates,
        "current_template": idx,
        "global_date_from": global_date_from_var.get(),
        "global_date_to": global_date_to_var.get()
    }

def set_gui_config(cfg):
    global_date_from_var.set(cfg.get("global_date_from", today_str()))
    global_date_to_var.set(cfg.get("global_date_to", today_str()))
    for row in chat_rows:
        for widget in row["widgets"]:
            widget.destroy()
    chat_rows.clear()
    for chat in cfg.get("chats", []):
        add_chat_row(chat)
    for t in template_list:
        t["frame"].destroy()
    template_list.clear()
    tpl_list = cfg.get("custom_templates", [])
    n_chat = len(chat_rows)
    for tpl in tpl_list:
        add_template_row(tpl, n_chat)
    update_template_select()
    idx = cfg.get("current_template", 0)
    if idx >= len(template_list):
        idx = 0
    template_select.current(idx)
    switch_template(idx)

def add_chat_row(chat=None):
    if chat is None:
        chat = {"name": ""}
    idx = len(chat_rows)
    name_var = tb.StringVar(value=chat.get("name", ""))

    row_frame = tb.Frame(chat_inner_frame)
    row_frame.grid(row=idx+1, column=0, columnspan=4, sticky="ew", padx=0, pady=1)
    row_frame.grid_columnconfigure(0, weight=1)
    row_frame.grid_columnconfigure(1, weight=0)
    row_frame.grid_columnconfigure(2, weight=0)
    row_frame.grid_columnconfigure(3, weight=0)

    name_entry = tb.Entry(row_frame, width=22, textvariable=name_var)
    name_entry.grid(row=0, column=0, padx=(2, 6), pady=2, sticky="ew")
    from_label = tb.Label(row_frame, textvariable=global_date_from_var, width=12)
    from_label.grid(row=0, column=1, padx=2, pady=2)
    to_label = tb.Label(row_frame, textvariable=global_date_to_var, width=12)
    to_label.grid(row=0, column=2, padx=2, pady=2)
    btn_del = tb.Button(row_frame, text="✖", command=lambda: del_chat_row(idx), width=3)
    btn_del.grid(row=0, column=3, padx=(6, 2), pady=2)

    def on_name_change(*args):
        for t in template_list:
            update_template_chat_checks(t)
    name_var.trace_add('write', on_name_change)

    chat_rows.append({
        "name_var": name_var,
        "widgets": [row_frame, name_entry, from_label, to_label, btn_del]
    })
    sync_enabled_chats_len()
    update_chat_canvas_scrollregion()

def del_chat_row(idx):
    if idx >= len(chat_rows):
        return
    for widget in chat_rows[idx]["widgets"]:
        widget.destroy()
    chat_rows.pop(idx)
    for i, row in enumerate(chat_rows):
        for j, widget in enumerate(row["widgets"]):
            widget.grid(row=i+1, column=j, padx=3, pady=2, sticky="ew")
    sync_enabled_chats_len()
    update_chat_canvas_scrollregion()

def add_template_row(tpl=None, n_chat=0):
    if tpl is None:
        tpl = {"name": "新模板", "content": "", "enabled_chats": [False]*n_chat}
    idx = len(template_list)
    frame = tb.LabelFrame(template_inner_frame, text="模板编辑", padding=(16, 12))
    frame.pack(fill='x', pady=(8, 16), padx=12, ipadx=2)

    name_var = tb.StringVar(value=tpl["name"])
    def on_template_name_change(*args):
        update_template_select()
    name_var.trace_add('write', on_template_name_change)

    tb.Label(frame, text="模板标题：").pack(anchor='w')
    name_entry = tb.Entry(frame, width=50, textvariable=name_var)
    name_entry.pack(anchor='w', pady=(0,6), fill="x")

    tb.Label(frame, text="正文内容/提示词：").pack(anchor='w')
    content_box = tb.Text(frame, width=85, height=7)
    content_box.insert(tb.END, tpl.get("content", ""))
    content_box.pack(anchor='w', pady=(0,8), fill="x", expand=True)

    enabled_vars = []
    checks_frame = tb.Frame(frame)
    checks_frame.pack(anchor='w', pady=(2,6))
    for i in range(n_chat):
        v = tb.BooleanVar(value=tpl["enabled_chats"][i] if i < len(tpl["enabled_chats"]) else False)
        enabled_vars.append(v)
        cb = tb.Checkbutton(checks_frame, text=chat_rows[i]["name_var"].get() if i < len(chat_rows) else f"群聊{i+1}", variable=v)
        cb.grid(row=i, column=0, sticky='w')
    btn_del = tb.Button(frame, text="🗑 删除该模板", command=lambda: del_template_row(idx))
    btn_del.pack(anchor='e', pady=(8, 0))

    template_list.append({
        "frame": frame, "name_var": name_var, "content_box": content_box,
        "name_entry": name_entry, "enabled_vars": enabled_vars, "checks_frame": checks_frame
    })

def update_template_chat_checks(t):
    for w in t["checks_frame"].winfo_children():
        w.destroy()
    for i, row in enumerate(chat_rows):
        v = t["enabled_vars"][i]
        cb = tb.Checkbutton(
            t["checks_frame"],
            text=row["name_var"].get() or f"群聊{i+1}",
            variable=v
        )
        cb.grid(row=i, column=0, sticky='w')

def del_template_row(idx):
    if idx >= len(template_list):
        return
    template_list[idx]["frame"].destroy()
    template_list.pop(idx)
    update_template_select()
    if template_list:
        template_select.current(0)
        switch_template(0)
    else:
        add_template_row(n_chat=len(chat_rows))
        update_template_select()
        template_select.current(0)
        switch_template(0)

def update_template_select():
    names = [t["name_var"].get() for t in template_list]
    template_select['values'] = names
    if names:
        if template_select.current() < 0 or template_select.current() >= len(names):
            template_select.current(0)

def switch_template(idx):
    for i, t in enumerate(template_list):
        t["frame"].pack_forget()
    if 0 <= idx < len(template_list):
        template_list[idx]["frame"].pack(fill='x', padx=4, pady=(2, 6))
        t = template_list[idx]
        t["content_box"].focus_set()
        t["content_box"].see("end")
    template_select.current(idx)

def on_select_template(evt=None):
    idx = template_select.current()
    switch_template(idx)

def add_new_template():
    add_template_row(n_chat=len(chat_rows))
    update_template_select()
    idx = len(template_list) - 1
    template_select.current(idx)
    switch_template(idx)

def combine_and_paste():
    cfg = get_gui_config()
    save_config(cfg)
    idx = cfg.get("current_template", 0)
    templates = cfg.get("custom_templates", [])
    chats = cfg.get("chats", [])
    if 0 <= idx < len(templates):
        tpl = templates[idx]
        template_text = f"{tpl.get('name', '')}\n\n{tpl.get('content', '')}".strip()
        enabled = tpl.get('enabled_chats', [False]*len(chats))
    else:
        template_text = ""
        enabled = []
    result = template_text
    for i, chat in enumerate(chats):
        if i < len(enabled) and enabled[i]:
            url = build_url(chat)
            content = fetch_url(url)
            result += f"\n\n{'='*8}\n【群聊：{chat['name']}】\n{'='*8}\n{content}"
    pyperclip.copy(result)
    time.sleep(0.2)
    keyboard.press_and_release('ctrl+v')
    time.sleep(0.1)
    keyboard.press_and_release('enter')

def save_current_config():
    cfg = get_gui_config()
    save_config(cfg)
    tb.Messagebox.show_info("配置已保存到config.json！", "保存成功")

def update_chat_canvas_scrollregion():
    chat_canvas.update_idletasks()
    chat_canvas.config(scrollregion=chat_canvas.bbox("all"))

# ----------- 主界面 --------------
root = tb.Window(themename="cosmo")
root.title("信息汇总 内部专用")
root.geometry("1450x900")
root.resizable(False, False)
root.configure(bg="#f4f8fc")

global_date_from_var = tb.StringVar(value=today_str())
global_date_to_var = tb.StringVar(value=today_str())

date_frame = tb.Frame(root)
date_frame.pack(fill="x", padx=18, pady=(10, 0))
tb.Label(date_frame, text="全局起始日期：").pack(side="left")
tb.Entry(date_frame, textvariable=global_date_from_var, width=14).pack(side="left", padx=(0, 16))
tb.Label(date_frame, text="全局结束日期：").pack(side="left")
tb.Entry(date_frame, textvariable=global_date_to_var, width=14).pack(side="left", padx=(0, 16))

main_frame = tb.Frame(root)
main_frame.pack(fill="both", expand=True, padx=18, pady=14)
main_frame.grid_rowconfigure(0, weight=1)
main_frame.grid_columnconfigure(0, weight=2, minsize=700)
main_frame.grid_columnconfigure(1, weight=3, minsize=900)

# 左侧：群聊列表
left_frame = tb.Labelframe(main_frame, text="群聊设置（全局共享）", bootstyle=PRIMARY, padding=(16, 12))
left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 24), pady=0)
left_frame.grid_rowconfigure(0, weight=1)  # 保证canvas区域自动填满
left_frame.grid_rowconfigure(1, weight=0)
left_frame.grid_columnconfigure(0, weight=1)

# 群聊滚动区域
chat_canvas = tb.Canvas(left_frame, width=600, height=470, highlightthickness=0)
chat_scrollbar = tb.Scrollbar(left_frame, orient="vertical", command=chat_canvas.yview)
chat_canvas.grid(row=0, column=0, sticky="nsew")
chat_scrollbar.grid(row=0, column=1, sticky="ns")

chat_inner_frame = tb.Frame(chat_canvas)
chat_inner_frame.bind("<Configure>", lambda e: chat_canvas.configure(scrollregion=chat_canvas.bbox("all")))
chat_canvas.create_window((0,0), window=chat_inner_frame, anchor="nw")
chat_canvas.configure(yscrollcommand=chat_scrollbar.set)

# 群聊表头
for i, label in enumerate(["群聊名称", "起始日期", "结束日期", ""]):
    tb.Label(chat_inner_frame, text=label).grid(row=0, column=i, padx=3, pady=2, sticky="ew")
chat_rows = []

# 添加群聊按钮：永远在面板最下方
btn_add_chat = tb.Button(
    left_frame,
    text="＋ 添加群聊",
    command=lambda: add_chat_row(),
    bootstyle="primary-outline",
    width=22
)
btn_add_chat.grid(row=1, column=0, pady=(12, 0), sticky="we", padx=8)
# 右侧：模板管理
right_frame = tb.LabelFrame(main_frame, text="模板管理", padding=(16, 12))
right_frame.grid(row=0, column=1, sticky="nsew")
right_frame.grid_rowconfigure(1, weight=1)
right_frame.grid_columnconfigure(0, weight=1)

temp_select_row = tb.Frame(right_frame)
temp_select_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
tb.Label(temp_select_row, text="模板选择：").pack(side="left", padx=2)
template_select = tb.Combobox(temp_select_row, state="readonly", width=28)
template_select.pack(side="left", padx=6)
template_select.bind('<<ComboboxSelected>>', on_select_template)
tb.Button(temp_select_row, text="新建模板", command=add_new_template).pack(side="left", padx=14)

# ---- 关键改动区域 ----
TEMPLATE_HEIGHT = 500
TEMPLATE_WIDTH = 820
template_canvas = tb.Canvas(right_frame, highlightthickness=0, height=TEMPLATE_HEIGHT, width=TEMPLATE_WIDTH)
template_scrollbar = tb.Scrollbar(right_frame, orient="vertical", command=template_canvas.yview)
template_canvas.grid(row=1, column=0, sticky="nsew")
template_scrollbar.grid(row=1, column=1, sticky="ns")

template_inner_frame = tb.Frame(template_canvas)
template_canvas.create_window((0, 0), window=template_inner_frame, anchor="nw", width=TEMPLATE_WIDTH)

def _on_template_configure(event):
    template_canvas.configure(scrollregion=template_canvas.bbox("all"))
template_inner_frame.bind("<Configure>", _on_template_configure)
template_canvas.configure(yscrollcommand=template_scrollbar.set)

def _on_mousewheel(event):
    template_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
template_canvas.bind_all("<MouseWheel>", _on_mousewheel)

template_list = []
# ---- end ----

# 底部按钮
btn_row = tb.Frame(right_frame)
btn_row.grid(row=2, column=0, sticky="ew", pady=(16, 0), padx=4)
btn_save = tb.Button(btn_row, text="💾 保存配置", command=save_current_config, width=14)
btn_save.pack(side="left", padx=16)
btn_combine = tb.Button(
    btn_row,
    text="🚀 立即粘贴并发送 (Ctrl+M)",
    command=combine_and_paste,
    width=26
)
btn_combine.pack(side="left", padx=24)

tb.Label(root, text="请将光标放在目标输入框，点击按钮或按 Ctrl+M 可自动粘贴+发送").pack(pady=(8, 2))
tb.Label(root, text="—— 世界上最乖的宝宝 李明明专用 ——").pack(pady=(0, 10))

set_gui_config(load_config())
template_select.bind('<<ComboboxSelected>>', on_select_template)
threading.Thread(target=keyboard.add_hotkey, args=('ctrl+m', combine_and_paste), daemon=True).start()
root.mainloop()
