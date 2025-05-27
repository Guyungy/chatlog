import tkinter as tk
from tkinter import messagebox, ttk
from datetime import datetime
import requests
import keyboard
import threading
import pyperclip
import time
import json
import os
from urllib.parse import quote

CONFIG_PATH = 'config.json'
API_URL = 'http://127.0.0.1:5030/api/v1/chatlog'

def today_str():
    return datetime.now().strftime('%Y-%m-%d')

def default_config():
    return {
        "chats": [
            {"name": "群聊A", "date_from": today_str(), "date_to": today_str()},
            {"name": "群聊B", "date_from": today_str(), "date_to": today_str()}
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
        "current_template": 0
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

def sync_enabled_chats_len():
    n = len(chat_rows)
    for t in template_list:
        e = t["enabled_vars"]
        if len(e) < n:
            for i in range(n - len(e)):
                v = tk.BooleanVar(value=False)
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
            "content": t["content_box"].get("1.0", tk.END).strip(),
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
    name_var = tk.StringVar(value=chat.get("name", ""))

    row_frame = tk.Frame(chat_inner_frame, bg="#f7faff")
    row_frame.grid(row=idx+1, column=0, columnspan=4, sticky="ew", padx=0, pady=1)
    row_frame.grid_columnconfigure(0, weight=1)
    row_frame.grid_columnconfigure(1, weight=0)
    row_frame.grid_columnconfigure(2, weight=0)
    row_frame.grid_columnconfigure(3, weight=0)

    def on_enter(e): row_frame.config(bg="#e3f0ff")
    def on_leave(e): row_frame.config(bg="#f7faff")
    row_frame.bind("<Enter>", on_enter)
    row_frame.bind("<Leave>", on_leave)

    name_entry = tk.Entry(row_frame, width=22, textvariable=name_var, font=('微软雅黑', 10), relief="groove", bd=2)
    name_entry.grid(row=0, column=0, padx=(2, 6), pady=2, sticky="ew")
    from_label = tk.Label(row_frame, textvariable=global_date_from_var, width=12, font=('微软雅黑', 10), bg="#f7faff")
    from_label.grid(row=0, column=1, padx=2, pady=2)
    to_label = tk.Label(row_frame, textvariable=global_date_to_var, width=12, font=('微软雅黑', 10), bg="#f7faff")
    to_label.grid(row=0, column=2, padx=2, pady=2)
    btn_del = tk.Button(row_frame, text="✖", command=lambda: del_chat_row(idx), font=('微软雅黑', 10), width=3, fg="#d9534f", bg="#f7faff", bd=0, relief="flat", activebackground="#ffeaea")
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
    frame = tk.LabelFrame(
        template_inner_frame, text="模板编辑",
        padx=16, pady=12,
        font=('微软雅黑', 11, 'bold'), fg='#185ee0',
        bg="#ffffff", bd=0, relief="flat"
    )
    frame.pack(fill='x', pady=(8, 16), padx=12, ipadx=2)

    name_var = tk.StringVar(value=tpl["name"])
    def on_template_name_change(*args):
        update_template_select()
    name_var.trace_add('write', on_template_name_change)

    tk.Label(frame, text="模板标题：", font=('微软雅黑', 10), bg="#f7faff").pack(anchor='w')
    name_entry = tk.Entry(frame, width=50, textvariable=name_var, font=('微软雅黑', 11, 'bold'), relief="groove", bd=2)
    name_entry.pack(anchor='w', pady=(0,6), fill="x")

    tk.Label(frame, text="正文内容/提示词：", font=('微软雅黑', 10), bg="#f7faff").pack(anchor='w')
    content_box = tk.Text(frame, width=85, height=7, font=('微软雅黑', 10), relief="groove", bd=2)
    content_box.insert(tk.END, tpl.get("content", ""))
    content_box.pack(anchor='w', pady=(0,8), fill="x", expand=True)

    enabled_vars = []
    checks_frame = tk.Frame(frame, bg="#f7faff")
    checks_frame.pack(anchor='w', pady=(2,6))
    for i in range(n_chat):
        v = tk.BooleanVar(value=tpl["enabled_chats"][i] if i < len(tpl["enabled_chats"]) else False)
        enabled_vars.append(v)
        cb = tk.Checkbutton(checks_frame, text=chat_rows[i]["name_var"].get() if i < len(chat_rows) else f"群聊{i+1}", variable=v, font=('微软雅黑', 10), bg="#f7faff", activebackground="#e3f0ff")
        cb.grid(row=i, column=0, sticky='w')
    btn_del = tk.Button(
        frame, text="🗑 删除该模板",
        command=lambda: del_template_row(idx),
        font=('微软雅黑', 10, "bold"),
        fg="#d9534f", bg="#fbeaea",
        bd=0, relief="flat", activebackground="#ffeaea"
    )
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
        cb = tk.Checkbutton(
            t["checks_frame"],
            text=row["name_var"].get() or f"群聊{i+1}",
            variable=v,
            font=('微软雅黑', 10),
            bg="#f7faff"
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
    messagebox.showinfo("保存成功", "配置已保存到config.json！")

def update_chat_canvas_scrollregion():
    chat_canvas.update_idletasks()
    chat_canvas.config(scrollregion=chat_canvas.bbox("all"))

# ----------- 主界面 --------------
root = tk.Tk()
root.title("信息汇总 内部专用")
root.geometry("1450x720")
root.resizable(False, False)
root.configure(bg="#f4f8fc")  # 更柔和的蓝白色

# 全局日期设置区
global_date_from_var = tk.StringVar(value=today_str())
global_date_to_var = tk.StringVar(value=today_str())

date_frame = tk.Frame(root, bg="#f7faff")
date_frame.pack(fill="x", padx=18, pady=(10, 0))
tk.Label(date_frame, text="全局起始日期：", font=('微软雅黑', 10), bg="#f7faff").pack(side="left")
tk.Entry(date_frame, textvariable=global_date_from_var, width=14, font=('微软雅黑', 10)).pack(side="left", padx=(0, 16))
tk.Label(date_frame, text="全局结束日期：", font=('微软雅黑', 10), bg="#f7faff").pack(side="left")
tk.Entry(date_frame, textvariable=global_date_to_var, width=14, font=('微软雅黑', 10)).pack(side="left", padx=(0, 16))

main_frame = tk.Frame(root, bg="#f7faff")
main_frame.pack(fill="both", expand=True, padx=18, pady=14)
main_frame.grid_rowconfigure(0, weight=1)
main_frame.grid_columnconfigure(0, weight=1, minsize=540)
main_frame.grid_columnconfigure(1, weight=2, minsize=850)

# 左侧：群聊列表
left_frame = tk.LabelFrame(
    main_frame, text="群聊设置（全局共享）",
    font=("微软雅黑", 13, "bold"),
    bg="#ffffff", fg="#185ee0",
    bd=0, relief="flat", padx=16, pady=12
)
left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 24), pady=0)
left_frame.grid_rowconfigure(0, weight=1)
left_frame.grid_columnconfigure(0, weight=1)

chat_canvas = tk.Canvas(left_frame, bg="#f7faff", highlightthickness=0, width=510)
chat_scrollbar = tk.Scrollbar(left_frame, orient="vertical", command=chat_canvas.yview)
chat_inner_frame = tk.Frame(chat_canvas, bg="#f7faff")
chat_inner_frame.bind("<Configure>", lambda e: chat_canvas.configure(scrollregion=chat_canvas.bbox("all")))
chat_canvas.create_window((0,0), window=chat_inner_frame, anchor="nw")
chat_canvas.configure(yscrollcommand=chat_scrollbar.set)

chat_canvas.grid(row=0, column=0, sticky="nsew")
chat_scrollbar.grid(row=0, column=1, sticky="ns")
left_frame.rowconfigure(0, weight=1)
left_frame.columnconfigure(0, weight=1)

for i, label in enumerate(["群聊名称", "起始日期", "结束日期", ""]):
    tk.Label(chat_inner_frame, text=label, font=('微软雅黑', 10, 'bold'), bg="#f7faff").grid(row=0, column=i, padx=3, pady=2, sticky="ew")
chat_rows = []
btn_add_chat = tk.Button(
    left_frame, text="＋ 添加群聊",
    command=lambda: add_chat_row(),
    font=('微软雅黑', 11, "bold"),
    bg="#e3f0ff", fg="#185ee0",
    relief="flat", activebackground="#d6eaff",
    bd=0, height=2
)
btn_add_chat.grid(row=1, column=0, pady=12, sticky="we", padx=12)

# 只在鼠标悬停在群聊canvas时才滚动群聊区
# Windows: event.delta; Linux: Button-4/Button-5; Mac: event.delta方向需反向

def _on_mousewheel_chat(event):
    if event.num == 5 or event.delta < 0:
        chat_canvas.yview_scroll(1, "units")
    elif event.num == 4 or event.delta > 0:
        chat_canvas.yview_scroll(-1, "units")
    return "break"
chat_canvas.bind("<Enter>", lambda e: chat_canvas.bind_all("<MouseWheel>", _on_mousewheel_chat))
chat_canvas.bind("<Leave>", lambda e: chat_canvas.unbind_all("<MouseWheel>"))
chat_canvas.bind("<Button-4>", _on_mousewheel_chat)  # Linux
chat_canvas.bind("<Button-5>", _on_mousewheel_chat)  # Linux

# 右侧：模板管理
right_frame = tk.LabelFrame(
    main_frame, text="模板管理",
    font=("微软雅黑", 13, "bold"),
    bg="#ffffff", fg="#185ee0",
    bd=0, relief="flat", padx=16, pady=12
)
right_frame.grid(row=0, column=1, sticky="nsew")
right_frame.grid_rowconfigure(1, weight=1)
right_frame.grid_columnconfigure(0, weight=1)

# 上：模板选择区
temp_select_row = tk.Frame(right_frame, bg="#f7faff")
temp_select_row.grid(row=0, column=0, sticky="ew", pady=(0, 10))
tk.Label(temp_select_row, text="模板选择：", font=('微软雅黑', 10), bg="#f7faff").pack(side="left", padx=2)
template_select = ttk.Combobox(temp_select_row, state="readonly", font=('微软雅黑', 10), width=28)
template_select.pack(side="left", padx=6)
template_select.bind('<<ComboboxSelected>>', on_select_template)
tk.Button(temp_select_row, text="新建模板", command=add_new_template, font=('微软雅黑', 10)).pack(side="left", padx=14)

# 模板区滚轮只影响模板区

template_canvas = tk.Canvas(right_frame, bg="#f7faff", highlightthickness=0)
template_scrollbar = tk.Scrollbar(right_frame, orient="vertical", command=template_canvas.yview)
template_inner_frame = tk.Frame(template_canvas, bg="#f7faff")
template_inner_frame.bind("<Configure>", lambda e: template_canvas.configure(scrollregion=template_canvas.bbox("all")))
template_canvas.create_window((0,0), window=template_inner_frame, anchor="nw")
template_canvas.configure(yscrollcommand=template_scrollbar.set)

template_canvas.grid(row=1, column=0, sticky="nsew")
template_scrollbar.grid(row=1, column=1, sticky="ns")
template_list = []

def _on_mousewheel_tpl(event):
    if event.num == 5 or event.delta < 0:
        template_canvas.yview_scroll(1, "units")
    elif event.num == 4 or event.delta > 0:
        template_canvas.yview_scroll(-1, "units")
    return "break"
template_canvas.bind("<Enter>", lambda e: template_canvas.bind_all("<MouseWheel>", _on_mousewheel_tpl))
template_canvas.bind("<Leave>", lambda e: template_canvas.unbind_all("<MouseWheel>"))
template_canvas.bind("<Button-4>", _on_mousewheel_tpl)
template_canvas.bind("<Button-5>", _on_mousewheel_tpl)

# 中：模板编辑大区（加滚动条）
template_canvas = tk.Canvas(right_frame, bg="#f7faff", highlightthickness=0)
template_scrollbar = tk.Scrollbar(right_frame, orient="vertical", command=template_canvas.yview)
template_inner_frame = tk.Frame(template_canvas, bg="#f7faff")
template_inner_frame.bind("<Configure>", lambda e: template_canvas.configure(scrollregion=template_canvas.bbox("all")))
template_canvas.create_window((0,0), window=template_inner_frame, anchor="nw")
template_canvas.configure(yscrollcommand=template_scrollbar.set)

template_canvas.grid(row=1, column=0, sticky="nsew")
template_scrollbar.grid(row=1, column=1, sticky="ns")
template_list = []

# 底部按钮区美化
btn_row = tk.Frame(right_frame, bg="#f7faff")
btn_row.grid(row=2, column=0, sticky="ew", pady=(16, 0), padx=4)
btn_save = tk.Button(
    btn_row, text="💾 保存配置",
    command=save_current_config,
    font=('微软雅黑', 11, "bold"),
    width=14, bg="#e3f0ff", fg="#185ee0",
    relief="flat", activebackground="#d6eaff", bd=0, height=2
)
btn_save.pack(side="left", padx=16)
btn_combine = tk.Button(
    btn_row, 
    text="🚀 立即粘贴并发送 (Ctrl+M)", 
    command=combine_and_paste,
    font=('微软雅黑', 12, "bold"),
    bg="#185ee0", fg="white",
    relief="flat", activebackground="#1360a3",
    activeforeground="white", width=26, height=2, bd=0
)
btn_combine.pack(side="left", padx=24)

# 顶部提示语美化
tk.Label(
    root,
    text="请将光标放在目标输入框，点击按钮或按 Ctrl+M 可自动粘贴+发送",
    font=('微软雅黑', 10, "italic"),
    bg="#f4f8fc", fg="#185ee0"
).pack(pady=(8, 2))
tk.Label(
    root,
    text="—— 世界上最乖的宝宝 李明明专用 ——",
    font=('微软雅黑', 9, "bold"),
    fg="#185ee0", bg="#f4f8fc"
).pack(pady=(0, 10))

set_gui_config(load_config())
template_select.bind('<<ComboboxSelected>>', on_select_template)
threading.Thread(target=keyboard.add_hotkey, args=('ctrl+m', combine_and_paste), daemon=True).start()
root.mainloop()
