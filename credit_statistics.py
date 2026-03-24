"""
哈尔滨工程大学本科生学分统计系统
带图形界面的自动登录、成绩查询、学分统计和毕业要求检查工具。
跨平台兼容（Windows / macOS / Linux）。
"""

import re
import sys
import time
import base64
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import ddddocr
from collections import defaultdict

# 高DPI适配（必须在创建Tk之前调用）
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ============ 网络配置 ============
CAS_BASE = "https://cas-443.wvpn.hrbeu.edu.cn"
JWGL_BASE = "https://jwgl-443.wvpn.hrbeu.edu.cn"
MAX_CAPTCHA_RETRIES = 30


# ============ 毕业要求配置 ============
# 修改此列表即可调整通过标准
# key 说明：
#   "zx"    → 专选总学分
#   "A0"    → 公选A0类学分
#   "A+B+C" → 公选A+B+C类学分之和（用+连接多个类别）
#   "B"     → 公选B类学分
#   "F"     → 公选F类学分
GRADUATION_REQUIREMENTS = [
    {"desc": "专选 ≥ 15学分",                      "key": "zx",              "min": 15},
    {"desc": "A0(中华传统文化类) ≥ 1学分",          "key": "A0",             "min": 1},
    {"desc": "A + B + C + D + E + F ≥ 12学分",    "key": "A+B+C+D+E+F",   "min": 12},
    {"desc": "B(艺术鉴赏与审美体验) ≥ 1学分",      "key": "B",              "min": 1},
    {"desc": "F(创新思维与创业实践) ≥ 6学分",       "key": "F",              "min": 6},
]


# ============ 公选课类别 ============
GX_CATEGORY_NAMES = {
    "A0": "中华传统文化类",
    "A": "人文素质与文化传承",
    "B": "艺术鉴赏与审美体验",
    "C": "社会发展与公民责任",
    "D": "自然科学与工程技术",
    "E": "海洋科学与技术认知",
    "F": "创新思维与创业实践",
}


# ============ 工具函数 ============
def extract_gx_category(display_text):
    """从公选课显示文本中提取类别代号"""
    if not display_text:
        return "未分类"
    m = re.search(r'[（(]([A-Z]\d?)[）)]', display_text)
    return m.group(1) if m else "未分类"


def semester_sort_key(s):
    return tuple(int(p) for p in s.split("-"))


# ============ 网络逻辑 ============
def create_session():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    session.verify = False
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def cas_login(session, username, password, on_status=None):
    """CAS SSO登录，on_status(msg) 回调状态更新"""
    def status(msg):
        if on_status:
            on_status(msg)

    portal_url = f"{JWGL_BASE}/jwapp/sys/emaphome/portal/index.do"
    ocr = ddddocr.DdddOcr(show_ad=False, beta=True)

    status("正在连接教务系统...")
    resp = session.get(portal_url, allow_redirects=True, timeout=15)
    cas_login_url = resp.url

    if "cas/login" not in cas_login_url:
        status("已通过会话登录")
        return True

    lt = ""
    execution = "e1s1"
    m = re.search(r'name="lt"\s+value="([^"]+)"', resp.text)
    if m:
        lt = m.group(1)
    m_exec = re.search(r'name="execution"\s+value="([^"]+)"', resp.text)
    if m_exec:
        execution = m_exec.group(1)

    for attempt in range(1, MAX_CAPTCHA_RETRIES + 1):
        status(f"识别验证码... (第{attempt}次)")

        captcha_resp = session.get(
            f"{CAS_BASE}/sso/apis/v2/open/captcha?imageWidth=100&captchaSize=4",
            timeout=15,
        )
        captcha_data = captcha_resp.json()
        captcha_token = captcha_data["token"]
        captcha_b64 = captcha_data["img"].replace("\n", "")
        captcha_bytes = base64.b64decode(captcha_b64)
        captcha_text = re.sub(r'[^a-z0-9]', '',
                              ocr.classification(captcha_bytes).lower().strip())

        if len(captcha_text) != 4:
            continue

        resp = session.post(cas_login_url, data={
            "username": username, "password": password,
            "captcha": captcha_text, "token": captcha_token,
            "lt": lt, "execution": execution,
            "_eventId": "submit", "source": "cas",
        }, allow_redirects=True, timeout=15)

        if "cas/login" not in resp.url:
            status("登录成功，正在加载数据...")
            session.get(portal_url, allow_redirects=True, timeout=15)
            return True

        m = re.search(r'name="lt"\s+value="([^"]+)"', resp.text)
        if m:
            lt = m.group(1)
        m_exec = re.search(r'name="execution"\s+value="([^"]+)"', resp.text)
        if m_exec:
            execution = m_exec.group(1)

        if "未能够识别出目标" in resp.text or "TicketNotFound" in resp.text:
            resp2 = session.get(cas_login_url, timeout=15)
            m2 = re.search(r'name="lt"\s+value="([^"]+)"', resp2.text)
            if m2:
                lt = m2.group(1)
            m2_exec = re.search(r'name="execution"\s+value="([^"]+)"', resp2.text)
            if m2_exec:
                execution = m2_exec.group(1)
            continue

        ec = re.search(r'id="errorcode"[^>]*value="([^"]*)"', resp.text)
        if ec and ec.group(1) == "INVALID_CREDENTIAL":
            raise ValueError("用户名或密码错误")

        time.sleep(0.5)

    raise TimeoutError("验证码识别多次失败，请稍后重试")


def init_app(session, app_name):
    resp = session.get(
        f"{JWGL_BASE}/jwapp/sys/{app_name}/*default/index.do", timeout=15)
    if "cas/login" in resp.url:
        raise RuntimeError("会话已过期，请重新登录")


def fetch_all_data(session, on_status=None):
    """登录后一次性获取所有需要的数据"""
    def status(msg):
        if on_status:
            on_status(msg)

    status("获取学期信息...")
    init_app(session, "cjcx")
    session.post(
        f"{JWGL_BASE}/jwapp/sys/jwpubapp/pub/setJwCommonAppRole.do", timeout=15)

    resp = session.post(
        f"{JWGL_BASE}/jwapp/sys/cjcx/modules/cjcx/cxdqxnxqhsygxnxq.do",
        timeout=15)
    semesters = [r["XNXQDM"]
                 for r in resp.json()["datas"]["cxdqxnxqhsygxnxq"]["rows"]]
    current_semester = (max(semesters, key=semester_sort_key)
                        if semesters else "2025-2026-2")

    status("获取成绩数据...")
    resp = session.post(
        f"{JWGL_BASE}/jwapp/sys/cjcx/modules/cjcx/xscjcx.do",
        data={"querySetting": "[]", "*order": "-XNXQDM",
              "pageSize": "500", "pageNumber": "1"},
        timeout=15)
    grades = resp.json()["datas"]["xscjcx"]["rows"]

    status("获取课表数据...")
    init_app(session, "wdkb")
    resp = session.post(
        f"{JWGL_BASE}/jwapp/sys/wdkb/modules/xskcb/cxxszhxqkb.do",
        data={"XNXQDM": current_semester}, timeout=15)
    rows = resp.json()["datas"]["cxxszhxqkb"]["rows"]
    seen, schedule = set(), []
    for r in rows:
        if r["KCH"] not in seen:
            seen.add(r["KCH"])
            schedule.append(r)

    return grades, schedule, current_semester


# ============ 数据处理 ============
def compute_stats(grades):
    """从成绩数据计算学分统计"""
    passed = [g for g in grades if g.get("SFJG") == "1"]
    total_bx, total_zx, total_gx = 0.0, 0.0, 0.0
    gx_by_cat = defaultdict(float)
    gx_count_by_cat = defaultdict(int)
    bx_count, zx_count = 0, 0
    by_semester = defaultdict(list)

    for g in passed:
        xf = float(g["XF"])
        ctype = g["KCXZDM_DISPLAY"]
        by_semester[g["XNXQDM"]].append(g)
        if ctype == "必修":
            total_bx += xf
            bx_count += 1
        elif ctype == "专选":
            total_zx += xf
            zx_count += 1
        elif ctype == "公选":
            total_gx += xf
            cat = extract_gx_category(g.get("XGXKLBDMKC_DISPLAY", ""))
            gx_by_cat[cat] += xf
            gx_count_by_cat[cat] += 1

    return {
        "passed": passed,
        "total_bx": total_bx, "bx_count": bx_count,
        "total_zx": total_zx, "zx_count": zx_count,
        "total_gx": total_gx,
        "gx_by_cat": dict(gx_by_cat),
        "gx_count_by_cat": dict(gx_count_by_cat),
        "by_semester": dict(by_semester),
    }


def eval_requirement(key, stats):
    """根据key计算已获得的学分值。A0算在A类里。"""
    if key == "zx":
        return stats["total_zx"]
    total = 0
    for p in key.split("+"):
        total += stats["gx_by_cat"].get(p, 0)
        if p == "A":  # A0 归入 A 类
            total += stats["gx_by_cat"].get("A0", 0)
    return total


def check_requirements(stats, requirements=None):
    """检查毕业要求，返回结果列表"""
    if requirements is None:
        requirements = GRADUATION_REQUIREMENTS
    results = []
    for req in requirements:
        actual = eval_requirement(req["key"], stats)
        results.append({
            "desc": req["desc"],
            "actual": actual,
            "required": req["min"],
            "passed": actual >= req["min"],
        })
    return results


def compute_predicted_stats(stats, schedule):
    """模拟本学期课程全部通过后的学分统计"""
    predicted = {
        "total_bx": stats["total_bx"],
        "total_zx": stats["total_zx"],
        "total_gx": stats["total_gx"],
        "gx_by_cat": dict(stats["gx_by_cat"]),
    }
    for c in schedule:
        xf = float(c["XF"])
        ctype = c["KCXZDM_DISPLAY"]
        if ctype == "必修":
            predicted["total_bx"] += xf
        elif ctype == "专选":
            predicted["total_zx"] += xf
        elif ctype == "公选":
            predicted["total_gx"] += xf
            cat = extract_gx_category(c.get("XGXKLBDM_DISPLAY", ""))
            predicted["gx_by_cat"][cat] = predicted["gx_by_cat"].get(cat, 0) + xf
    return predicted


# ============ 字体与缩放 ============
def _get_dpi_scale(root):
    """获取当前DPI缩放比例"""
    try:
        if sys.platform == "win32":
            import ctypes
            hdc = ctypes.windll.user32.GetDC(0)
            dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX
            ctypes.windll.user32.ReleaseDC(0, hdc)
            return dpi / 96.0
    except Exception:
        pass
    return root.tk.call('tk', 'scaling') / 1.333333  # tk scaling baseline


def _pick_font():
    """选择可用的中文字体"""
    if sys.platform == "win32":
        return "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        return "PingFang SC"
    return "Noto Sans CJK SC"


# ============ GUI ============
class CreditStatsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("哈尔滨工程大学 · 学分统计系统")

        # DPI 缩放
        self.scale = _get_dpi_scale(root)
        self.font_family = _pick_font()

        # 设置tk缩放（让ttk控件尺寸正确）
        root.tk.call('tk', 'scaling', self.scale * 1.333333)

        # 登录窗口尺寸（按缩放调整）
        w, h = int(520 * self.scale), int(400 * self.scale)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        root.resizable(False, False)

        style = ttk.Style()
        try:
            if sys.platform == "win32":
                style.theme_use("vista")
            elif sys.platform == "darwin":
                style.theme_use("aqua")
            else:
                style.theme_use("clam")
        except tk.TclError:
            pass

        # 统一字体配置
        f = self.font_family
        rh = max(28, int(26 * self.scale))
        style.configure("Treeview", rowheight=rh, font=(f, 10))
        style.configure("Treeview.Heading", font=(f, 10, "bold"))
        style.configure("TLabel", font=(f, 10))
        style.configure("TButton", font=(f, 10))
        style.configure("TLabelframe.Label", font=(f, 11, "bold"))
        style.configure("TNotebook.Tab", font=(f, 10))

        self._build_login()

    # -------------------- 登录界面 --------------------
    def _build_login(self):
        f = self.font_family
        self.login_frame = ttk.Frame(self.root, padding=30)
        self.login_frame.pack(expand=True, fill="both")

        center = ttk.Frame(self.login_frame)
        center.place(relx=0.5, rely=0.42, anchor="center")

        ttk.Label(center, text="哈尔滨工程大学",
                  font=(f, 18, "bold")).pack(pady=(0, 2))
        ttk.Label(center, text="学分统计系统",
                  font=(f, 13)).pack(pady=(0, 28))

        form = ttk.Frame(center)
        form.pack()

        ttk.Label(form, text="学号：", font=(f, 11)).grid(
            row=0, column=0, padx=(0, 6), pady=8, sticky="e")
        self.user_var = tk.StringVar()
        self.user_entry = ttk.Entry(
            form, textvariable=self.user_var, width=24, font=(f, 11))
        self.user_entry.grid(row=0, column=1, pady=8)

        ttk.Label(form, text="密码：", font=(f, 11)).grid(
            row=1, column=0, padx=(0, 6), pady=8, sticky="e")
        self.pass_var = tk.StringVar()
        self.pass_entry = ttk.Entry(
            form, textvariable=self.pass_var, width=24, show="\u2022",
            font=(f, 11))
        self.pass_entry.grid(row=1, column=1, pady=8)

        self.login_btn = ttk.Button(
            center, text="登录查询", command=self._on_login, width=18)
        self.login_btn.pack(pady=22)

        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(
            center, textvariable=self.status_var, foreground="gray",
            font=(f, 9))
        self.status_label.pack()

        # 快捷键
        self.user_entry.bind("<Return>", lambda _: self.pass_entry.focus())
        self.pass_entry.bind("<Return>", lambda _: self._on_login())
        self.user_entry.focus()

    def _on_login(self):
        username = self.user_var.get().strip()
        password = self.pass_var.get().strip()
        if not username or not password:
            messagebox.showwarning("提示", "请输入学号和密码")
            return

        self.login_btn.config(state="disabled")
        self.user_entry.config(state="disabled")
        self.pass_entry.config(state="disabled")
        threading.Thread(
            target=self._worker, args=(username, password), daemon=True
        ).start()

    def _set_status(self, msg):
        self.root.after(0, lambda: self.status_var.set(msg))

    def _worker(self, username, password):
        try:
            session = create_session()
            cas_login(session, username, password, on_status=self._set_status)
            data = fetch_all_data(session, on_status=self._set_status)
            self._set_status("加载完成")
            self.root.after(0, lambda: self._show_results(*data))
        except (ValueError, TimeoutError, RuntimeError) as e:
            self._set_status(str(e))
            self.root.after(0, self._unlock_login)
        except Exception as e:
            self._set_status(f"错误: {e}")
            self.root.after(0, self._unlock_login)

    def _unlock_login(self):
        self.login_btn.config(state="normal")
        self.user_entry.config(state="normal")
        self.pass_entry.config(state="normal")

    # -------------------- 结果界面 --------------------
    def _show_results(self, grades, schedule, semester):
        self.login_frame.destroy()
        s = self.scale
        w, h = int(960 * s), int(700 * s)
        mw, mh = int(800 * s), int(500 * s)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self.root.resizable(True, True)
        self.root.minsize(mw, mh)

        # 保存数据供后续刷新使用
        self.stats = compute_stats(grades)
        self.schedule = schedule
        self.semester = semester
        self.requirements = list(GRADUATION_REQUIREMENTS)  # 可编辑副本

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(expand=True, fill="both", padx=8, pady=8)

        self._tab_overview(self.nb)
        self._tab_grades(self.nb)
        self._tab_schedule(self.nb)
        self._tab_requirements(self.nb)

    # ---- Tab 1: 学分总览 ----
    def _tab_overview(self, nb):
        self.overview_outer = ttk.Frame(nb)
        nb.add(self.overview_outer, text=" 学分总览 ")
        self._refresh_overview()

    def _refresh_overview(self):
        """重建学分总览内容（requirements变更后调用）"""
        outer = self.overview_outer
        for w in outer.winfo_children():
            w.destroy()

        stats = self.stats
        reqs = check_requirements(stats, self.requirements)
        predicted = compute_predicted_stats(stats, self.schedule)
        pred_reqs = check_requirements(predicted, self.requirements)

        canvas = tk.Canvas(outer, highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=12)
        inner.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        f = self.font_family

        # ---- 学分统计 ----
        sf = ttk.LabelFrame(inner, text="学分统计", padding=12)
        sf.pack(fill="x", pady=(0, 14))

        total = stats["total_bx"] + stats["total_zx"] + stats["total_gx"]
        lines = [
            f"已通过课程 {len(stats['passed'])} 门，总学分 {total:.1f}",
            "",
            f"  必修：{stats['total_bx']:.1f} 学分（{stats['bx_count']} 门）",
            f"  专选：{stats['total_zx']:.1f} 学分（{stats['zx_count']} 门）",
            f"  公选：{stats['total_gx']:.1f} 学分",
        ]
        for code in ["A0", "A", "B", "C", "D", "E", "F"]:
            if code in stats["gx_by_cat"]:
                nm = GX_CATEGORY_NAMES.get(code, code)
                xf = stats["gx_by_cat"][code]
                cnt = stats["gx_count_by_cat"][code]
                lines.append(f"      {code}（{nm}）：{xf:.1f} 学分（{cnt} 门）")
            elif any(r["key"] == code or code in r["key"].split("+")
                     for r in self.requirements):
                nm = GX_CATEGORY_NAMES.get(code, code)
                lines.append(f"      {code}（{nm}）：0.0 学分（0 门）")

        ttk.Label(sf, text="\n".join(lines), justify="left",
                  font=(f, 11)).pack(anchor="w")

        # ---- 毕业要求检查（当前） ----
        rf = ttk.LabelFrame(inner, text="毕业要求检查 — 当前", padding=12)
        rf.pack(fill="x", pady=(0, 14))

        all_pass = all(r["passed"] for r in reqs)
        for r in reqs:
            self._render_req_line(rf, r)

        ttk.Separator(rf, orient="horizontal").pack(fill="x", pady=(10, 6))
        if all_pass:
            ttk.Label(rf, text="  所有毕业要求均已满足！",
                      foreground="#228B22", font=(f, 13, "bold")).pack(anchor="w")
        else:
            ttk.Label(rf, text="  部分毕业要求未达标",
                      foreground="#CC0000", font=(f, 13, "bold")).pack(anchor="w")

        # ---- 毕业要求预测（本学期课程全部通过后） ----
        pf = ttk.LabelFrame(
            inner, text=f"毕业要求预测 — 若本学期（{self.semester}）课程全部通过",
            padding=12)
        pf.pack(fill="x", pady=(0, 14))

        all_pred_pass = all(r["passed"] for r in pred_reqs)
        for curr, pred in zip(reqs, pred_reqs):
            improved = (not curr["passed"]) and pred["passed"]
            self._render_req_line(pf, pred, highlight_improved=improved)

        ttk.Separator(pf, orient="horizontal").pack(fill="x", pady=(10, 6))
        if all_pred_pass:
            ttk.Label(pf, text="  本学期结束后可满足所有毕业要求！",
                      foreground="#228B22", font=(f, 13, "bold")).pack(anchor="w")
        else:
            still_fail = [r for r in pred_reqs if not r["passed"]]
            ttk.Label(pf, text=f"  本学期结束后仍有 {len(still_fail)} 项未达标",
                      foreground="#CC0000", font=(f, 13, "bold")).pack(anchor="w")

    def _render_req_line(self, parent, r, highlight_improved=False):
        ok = r["passed"]
        marker = "[达标]" if ok else "[不足]"
        diff = r["actual"] - r["required"]
        if diff < 0:
            detail = f"（已 {r['actual']:.1f}，还差 {-diff:.1f}）"
        else:
            detail = f"（已 {r['actual']:.1f}，已达标）"
        if highlight_improved:
            fg = "#0066CC"
            marker = "[达标↑]"
        else:
            fg = "#228B22" if ok else "#CC0000"
        ttk.Label(parent, text=f"  {marker}  {r['desc']}  {detail}",
                  foreground=fg, font=(self.font_family, 11)).pack(anchor="w", pady=2)

    # ---- Tab 2: 成绩明细 ----
    def _tab_grades(self, nb):
        stats = self.stats
        frame = ttk.Frame(nb)
        nb.add(frame, text=" 成绩明细 ")

        cols = ("sem", "name", "type", "cat", "credit", "score")
        tree = ttk.Treeview(frame, columns=cols, show="headings")

        headers = {"sem": "学期", "name": "课程名称", "type": "类型",
                   "cat": "公选类别", "credit": "学分", "score": "成绩"}
        widths = {"sem": 140, "name": 280, "type": 55,
                  "cat": 180, "credit": 55, "score": 65}
        for c in cols:
            tree.heading(c, text=headers[c])
            anch = "w" if c in ("name", "cat") else "center"
            tree.column(c, width=widths[c], anchor=anch)

        # 斑马纹
        tree.tag_configure("odd", background="#F5F5F5")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        idx = 0
        for sem in sorted(stats["by_semester"], key=semester_sort_key):
            for g in stats["by_semester"][sem]:
                sem_d = g.get("XNXQDM_DISPLAY", sem)
                name = g["KCM"]
                ctype = g["KCXZDM_DISPLAY"]
                xf = g["XF"]
                score = g.get("ZCJ") or g.get("DJCJMC") or \
                    g.get("XSZCJMC") or ""
                cat = ""
                if ctype == "公选":
                    cc = extract_gx_category(
                        g.get("XGXKLBDMKC_DISPLAY", ""))
                    cn = GX_CATEGORY_NAMES.get(cc, "")
                    cat = f"{cc}（{cn}）" if cn else cc
                tag = ("odd",) if idx % 2 else ()
                tree.insert("", "end",
                            values=(sem_d, name, ctype, cat, xf, score),
                            tags=tag)
                idx += 1

    # ---- Tab 3: 本学期课表 ----
    def _tab_schedule(self, nb):
        schedule = self.schedule
        semester = self.semester
        frame = ttk.Frame(nb)
        nb.add(frame, text=f" 本学期课表（{semester}）")

        cols = ("name", "type", "cat", "credit", "teacher", "time")
        tree = ttk.Treeview(frame, columns=cols, show="headings")

        headers = {"name": "课程名称", "type": "类型", "cat": "类别",
                   "credit": "学分", "teacher": "教师", "time": "时间地点"}
        widths = {"name": 260, "type": 55, "cat": 180,
                  "credit": 55, "teacher": 80, "time": 300}
        for c in cols:
            tree.heading(c, text=headers[c])
            anch = "w" if c in ("name", "cat", "time") else "center"
            tree.column(c, width=widths[c], anchor=anch)

        tree.tag_configure("odd", background="#F5F5F5")

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        for idx, c in enumerate(schedule):
            name = c["KCM"]
            ctype = c["KCXZDM_DISPLAY"]
            xf = c["XF"]
            teacher = c.get("SKJS", "")
            sched = c.get("YPSJDD", "")
            cat = ""
            if ctype == "公选":
                cc = extract_gx_category(c.get("XGXKLBDM_DISPLAY", ""))
                cn = GX_CATEGORY_NAMES.get(cc, "")
                cat = f"{cc}（{cn}）" if cn else cc
            tag = ("odd",) if idx % 2 else ()
            tree.insert("", "end",
                        values=(name, ctype, cat, xf, teacher, sched),
                        tags=tag)

        total_xf = sum(float(c["XF"]) for c in schedule)
        ttk.Label(frame,
                  text=f"共 {len(schedule)} 门课程，{total_xf:.1f} 学分",
                  font=(self.font_family, 10)).pack(pady=6)

    # ---- Tab 4: 毕业要求配置 ----
    def _tab_requirements(self, nb):
        frame = ttk.Frame(nb, padding=12)
        nb.add(frame, text=" 毕业要求配置 ")
        f = self.font_family

        ttk.Label(frame, text='编辑毕业学分要求，修改后点击「应用」可实时更新学分总览。',
                  font=(f, 10), foreground="gray").pack(anchor="w", pady=(0, 8))

        hint = ('key 填写说明："zx" = 专选总学分；单个类别如 "A0" "B" "F"；'
                '多个类别求和用 + 连接，如 "A+B+C"')
        ttk.Label(frame, text=hint, font=(f, 9), foreground="#666",
                  wraplength=800).pack(anchor="w", pady=(0, 10))

        # Treeview
        tree_frame = ttk.Frame(frame)
        tree_frame.pack(fill="both", expand=True)

        cols = ("desc", "key", "min")
        self.req_tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", height=8)
        self.req_tree.heading("desc", text="描述")
        self.req_tree.heading("key", text="Key")
        self.req_tree.heading("min", text="最低学分")
        self.req_tree.column("desc", width=350, anchor="w")
        self.req_tree.column("key", width=120, anchor="center")
        self.req_tree.column("min", width=100, anchor="center")
        self.req_tree.tag_configure("odd", background="#F5F5F5")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.req_tree.yview)
        self.req_tree.configure(yscrollcommand=vsb.set)
        self.req_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._populate_req_tree()

        # 编辑表单
        edit_frame = ttk.LabelFrame(frame, text="添加 / 编辑", padding=10)
        edit_frame.pack(fill="x", pady=(10, 0))

        row0 = ttk.Frame(edit_frame)
        row0.pack(fill="x", pady=2)
        ttk.Label(row0, text="描述：", font=(f, 10)).pack(side="left")
        self.req_desc_var = tk.StringVar()
        ttk.Entry(row0, textvariable=self.req_desc_var, width=40,
                  font=(f, 10)).pack(side="left", padx=(4, 16))
        ttk.Label(row0, text="Key：", font=(f, 10)).pack(side="left")
        self.req_key_var = tk.StringVar()
        ttk.Entry(row0, textvariable=self.req_key_var, width=14,
                  font=(f, 10)).pack(side="left", padx=(4, 16))
        ttk.Label(row0, text="最低学分：", font=(f, 10)).pack(side="left")
        self.req_min_var = tk.StringVar()
        ttk.Entry(row0, textvariable=self.req_min_var, width=8,
                  font=(f, 10)).pack(side="left", padx=(4, 0))

        btn_frame = ttk.Frame(edit_frame)
        btn_frame.pack(fill="x", pady=(8, 0))
        ttk.Button(btn_frame, text="添加",
                   command=self._req_add, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="更新选中",
                   command=self._req_update, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="删除选中",
                   command=self._req_delete, width=10).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="应用并刷新总览",
                   command=self._req_apply,
                   width=16).pack(side="right", padx=4)

        self.req_tree.bind("<<TreeviewSelect>>", self._req_on_select)

    def _populate_req_tree(self):
        for item in self.req_tree.get_children():
            self.req_tree.delete(item)
        for i, req in enumerate(self.requirements):
            tag = ("odd",) if i % 2 else ()
            self.req_tree.insert(
                "", "end", iid=str(i),
                values=(req["desc"], req["key"], req["min"]),
                tags=tag)

    def _req_on_select(self, _event):
        sel = self.req_tree.selection()
        if not sel:
            return
        vals = self.req_tree.item(sel[0], "values")
        self.req_desc_var.set(vals[0])
        self.req_key_var.set(vals[1])
        self.req_min_var.set(vals[2])

    def _validate_req_input(self):
        desc = self.req_desc_var.get().strip()
        key = self.req_key_var.get().strip()
        min_s = self.req_min_var.get().strip()
        if not desc or not key or not min_s:
            messagebox.showwarning("提示", "请填写所有字段")
            return None
        valid_keys = {"zx"} | set(GX_CATEGORY_NAMES.keys())
        parts = key.split("+")
        if key != "zx" and not all(p in valid_keys for p in parts):
            messagebox.showwarning(
                "提示",
                f"Key 无效。可用值：zx, {', '.join(sorted(GX_CATEGORY_NAMES.keys()))}\n"
                f"多个类别用 + 连接，如 A+B+C")
            return None
        try:
            min_val = float(min_s)
        except ValueError:
            messagebox.showwarning("提示", "最低学分必须是数字")
            return None
        return {"desc": desc, "key": key, "min": min_val}

    def _req_add(self):
        req = self._validate_req_input()
        if not req:
            return
        self.requirements.append(req)
        self._populate_req_tree()
        self._clear_req_form()

    def _req_update(self):
        sel = self.req_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选中要更新的行")
            return
        req = self._validate_req_input()
        if not req:
            return
        idx = int(sel[0])
        self.requirements[idx] = req
        self._populate_req_tree()

    def _req_delete(self):
        sel = self.req_tree.selection()
        if not sel:
            messagebox.showwarning("提示", "请先选中要删除的行")
            return
        idx = int(sel[0])
        del self.requirements[idx]
        self._populate_req_tree()
        self._clear_req_form()

    def _req_apply(self):
        """将当前配置应用到学分总览"""
        self._refresh_overview()
        self.nb.select(self.overview_outer)

    def _clear_req_form(self):
        self.req_desc_var.set("")
        self.req_key_var.set("")
        self.req_min_var.set("")


# ============ 入口 ============
if __name__ == "__main__":
    root = tk.Tk()
    app = CreditStatsApp(root)
    root.mainloop()
