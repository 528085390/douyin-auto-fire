"""自检脚本：`python verify.py`

项目没有单元测试，这个脚本承担「改完代码后能不能放心用」的验证职责。
不发送任何消息、不改动已注册的定时任务，可随时安全运行。

覆盖历史上真实踩过的坑：
  1. 定时任务指向了一个已不存在的 python.exe（venv 被删/迁移）
     -> 到点弹一下黑框就 exit 1，浏览器不启动，日志一个字都不写
  2. headless: true 被抖音风控 100% 拦截（拼图滑块），一条也发不出去
  3. bat/vbs 里硬编码的解释器路径同样失效
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

FAILS: list[str] = []
PASSES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASSES if cond else FAILS).append(f"{name}{' :: ' + detail if detail else ''}")


def strip_comments(text: str, kind: str) -> str:
    """剥掉注释，避免把「说明已经不用它了」的注释误判成还在用。"""
    if kind == "vbs":
        return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("'"))
    if kind == "bat":
        return "\n".join(
            l for l in text.splitlines()
            if not l.lstrip().lower().startswith(("rem ", "::"))
        )
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    return "\n".join(l.split("#", 1)[0] for l in text.splitlines())


def read(name: str) -> str:
    return (BASE / name).read_bytes().decode("utf-8", "replace")


# --- 1. 解释器探测 ------------------------------------------------------------
import pyenv  # noqa: E402

py = pyenv.resolve_python(windowless=True)
check("解释器可解析", py is not None)
if py:
    check("解释器文件存在", py.exists(), str(py))
    check("解释器指向项目 .venv", ".venv" in str(py), str(py))
    check("解释器装有 playwright", pyenv._has_playwright(py.with_name("python.exe")))
    check("未解析到已失效的 .workbuddy 路径", ".workbuddy" not in str(py))

# --- 2. runner.py 兜底行为 ----------------------------------------------------
import runner  # noqa: E402

rsrc = read("runner.py")
check("runner 会 chdir 到项目根", "os.chdir(BASE)" in rsrc)
check("runner 默认 --run-once", "--run-once" in rsrc)

tmp = Path(tempfile.mkdtemp(prefix="hermes-verify-"))
orig = runner.CRASH_LOG
try:
    runner.CRASH_LOG = tmp / "run.log"
    runner._crash("verify-probe")
    check("runner 早期异常会写入日志",
          runner.CRASH_LOG.exists()
          and "verify-probe" in runner.CRASH_LOG.read_text(encoding="utf-8"))
finally:
    runner.CRASH_LOG = orig
    for f in tmp.glob("*"):
        f.unlink(missing_ok=True)
    tmp.rmdir()

# --- 3. 定时机制（SCH-001：schtasks 定时由常驻守护取代；第 3 节改为守护机制自检） ---
import panel  # noqa: E402  （整节重写后第 4 节起仍用 panel，必须保留）
import jobs  # noqa: E402
import scheduler_daemon  # noqa: E402  （模块 import 不启动主循环）

check("定时机制：jobs 模块可导入且有条目函数",
      hasattr(jobs, "load_jobs") and hasattr(jobs, "save_jobs"))
check("定时机制：守护模块可导入且有主循环/自启",
      hasattr(scheduler_daemon, "run_daemon") and hasattr(scheduler_daemon, "set_autostart"))
rsrc3 = read("runner.py")
check("定时机制：runner 复用 panel.trigger_run（合流触发链路）",
      "import panel" in rsrc3 and "panel.trigger_run" in rsrc3)
check("定时机制：runner 不再直接调 main.job 旁路",
      not re.search(r"^\s*main\.job\s*\(", rsrc3, re.M)
      and not re.search(r"DouyinStreak\(cfg\)\.run\(\)\s*$", rsrc3, re.M))

# --- 4. 面板健康自检能识别故障 ------------------------------------------------
# MAI-001（P1-2）：api_tasks 收必选 account；本节用占位账号 "main" 调用——
# stub 已 mock query_system_task 与 load_config，占位账号不会触真实账号数据。
_q, _l = panel.query_system_task, panel.load_config
try:
    panel.query_system_task = lambda *a, **k: {
        "exists": True, "command": r'"C:\gone\python.exe" runner.py'}
    h = panel.api_tasks("main")["health"]
    check("能识别失效的解释器路径",
          not h["ok"] and any("不存在" in p for p in h["problems"]))

    panel.query_system_task = _q
    panel.load_config = lambda *a, **k: {"browser": {"headless": True}}
    h = panel.api_tasks("main")["health"]
    check("能识别 headless 会被风控拦截",
          not h["ok"] and any("headless" in p for p in h["problems"]))
finally:
    panel.query_system_task, panel.load_config = _q, _l

h = panel.api_tasks("main")["health"]
check("当前工程状态健康", h["ok"], str(h["problems"]))

# --- 5. 真实有头浏览器语义（不启动浏览器） -----------------------------------
d = read("douyin.py")
check("不把窗口挪到屏幕外", "--window-position=-32000,-32000" not in d
      and "--start-minimized" not in d)
check("不再读取 offscreen 配置", "offscreen" not in d)
check("extra_args 为拷贝而非别名", 'list(self.browser_cfg.get("extra_args"' in d)

# --- 5b. /chat 独立页链路（2026-08-10 迁移） ----------------------------------
# 抖音改版后首页「消息」浮层入口消失，IM 独立成 /chat 单页。
# 这些断言锁住迁移后的形态，防止回退到浮层时代的补偿逻辑。
import ast  # noqa: E402

dtree = ast.parse(d)
dfuncs = {n.name for n in ast.walk(dtree) if isinstance(n, ast.FunctionDef)}

check("douyin.py 定义 DOUYIN_CHAT 常量", "DOUYIN_CHAT" in d)
check("douyin.py 不再保留 DOUYIN_IM（/im/ 旧页）", "DOUYIN_IM" not in d)
check("导航直达 /chat", "douyin.com/chat" in d)

# 浮层时代的补偿代码必须整体消失（AST 级，避免注释里提到就算数）
for dead in ("_navigate_to_im", "_try_switch_to_chat_tab", "_wait_im_frame",
             "_locator_by_name_prefix", "_chat_panel_probe", "_extract_conversation_names"):
    check(f"已删除浮层时代函数 {dead}", dead not in dfuncs)
check("已删除几何推断 _PROBE_JS", "_PROBE_JS" not in d)

# 新链路必须使用确定性语义锚点
check("使用 data-e2e 会话项埋点", 'data-e2e="conversation-item"' in d)
check("使用 slate 编辑器锚点", "data-slate-editor" in d)
check("使用发送按钮 e2e 锚点", "e2e-send-msg-btn" in d)
check("使用选中态 class 校验会话", "curConversation" in d)
check("使用右侧标题锚点校验会话", "RightPanelHeadertitle" in d)

# ★ C12b 地雷：编辑器空态 textContent 是零宽字符，不是 ""
check("★编辑器判空处理零宽字符 \\u200b（原地雷点）", "\\u200b" in d)

# ★ 1B 强校验：必须有正向证据，不能「没报错即成功」
check("★发送后校验最后一条气泡来自本人（isFromMe）", "isFromMe" in d)

# 决策 2：手动兜底整体移除
check("已删除 30 秒手动兜底", "manual_select_sec" not in d)
check("config.yaml 不再含 manual_select_sec",
      "manual_select_sec" not in read("config.yaml"))

# 审计 tag 齐备：spec 五、错误处理登记的 tag 必须都在代码里发得出来
# 注：verify_fail 硬失败 tag 已在 /chat 迁移中移除；气泡文本失配只降级放行
# （sent_soft 命名截图，不截审计件）。type_fail 为「文字没进输入框」tag
# （2026-09-04 spec 4.1：发送前落地正向证据，重试一次仍失败才发）。
for tag in ("no_match", "switch_fail", "wrong_conversation",
            "no_editor", "send_fail", "type_fail"):
    check(f"审计 tag {tag} 已实现", f'"{tag}"' in d)

# ★ 发送判定空真漏洞（2026-09-04 spec 4.1，评审 P1-1/P1-2 修订）：
# 文字必须真实进入编辑器，否则「发送后输入框清空」铁证在空编辑器上恒真；
# 空/纯空白内容必须在入口被拦截（否则 ""=="" 恒真，漏洞残留）。
check("★文字没进输入框会重试一次再阻断", '"自动重试一次"' in d)
check("★落地比较抽成 _editor_text_equals（收窄只改方法体，不破断言契约）",
      "_editor_text_equals" in dfuncs and "self._editor_text_equals(text)" in d)
check("★空/纯空白内容在 _send_text 入口拦截", "text = text.strip()" in d and "纯空白" in d)
check("★误导性旧警告（可能内容没进编辑器）已删除", "可能内容没进编辑器" not in d)
check("★软校验降级路径保留（sent_soft 命名）", '"sent_soft"' in d)

# ★ SIV-001 会话项可见性（2026-09-07 spec）：虚拟列表在可视区外渲染缓冲条目——
# DOM 在、bounding_box 有坐标，但裸鼠标事件不自动滚动，点在视口外=静默落空
# （2026-09-07 真实运行：列表底部 2 目标全部 switch_fail）。三道保证：
# 点击前滚入视口并重定位句柄；_human_click 视口外拒点；未切换自动重试点击一次。
check("★_ensure_item_in_view 存在且被调用（点击前滚入视口）",
      "_ensure_item_in_view" in dfuncs and "self._ensure_item_in_view(" in d)
check("★滚动使用 scroll_into_view_if_needed", "scroll_into_view_if_needed" in d)
check("★视口判定使用 viewport_size", "viewport_size" in d)
check("★会话未切换会自动重试点击一次", '"重试点击一次"' in d)
check("★_human_click 拒绝视口外点击", '"元素在视口外' in d)

# ★ _audit_dump 不能再引用已删的几何探针（否则失败时二次崩溃，吞掉真实原因）
check("★_audit_dump 不再依赖 _chat_panel_probe", "_chat_panel_probe" not in d)

# 强校验退化开关：spec 七、风险第 4 条要求「用户可决策」，必须是可切的代码路径
check("★strict_verify 退化开关存在", "strict_verify" in d)
check("config.yaml 提供 strict_verify", "strict_verify" in read("config.yaml"))

# 风控检测必须保留（/chat 确实存在 nocaptcha 隐藏帧，删了就瞎了）
check("★保留风控检测遍历 frames", "_detect_risk_control" in dfuncs
      and "self.page.frames" in d)

# 扫描结果升级为 [{"name","type"}]，群聊能自动识别
check("扫描区分群聊/私聊", "commonConversationIconnoDrag" in d)

# --- 6. 配置未处于会被风控拦截的状态 ------------------------------------------
import yaml  # noqa: E402

b = yaml.safe_load(read("config.yaml"))["browser"]
check("配置不会触发抖音风控", not b.get("headless"),
      f"headless={b.get('headless')}")

# --- 7. 无残留死路径 ----------------------------------------------------------
for f, kind in {"启动面板.bat": "bat", "抖音续火花.bat": "bat",
                "启动面板.vbs": "vbs", "panel.py": "py", "main.py": "py"}.items():
    if (BASE / f).exists():
        check(f"{f} 无 .workbuddy 死路径", ".workbuddy" not in strip_comments(read(f), kind))

m = strip_comments(read("main.py"), "py")
check("main.py 用 schtasks 注册", '"schtasks", "/Create"' in m)
check("main.py 动态探测解释器", "resolve_python(" in m)
# 2026-09-04 真实运行暴露：--run-once 调用 panel.setup_logging（不存在）→ AttributeError
check("main.py --run-once 不调用不存在的 panel.setup_logging",
      "panel.setup_logging" not in m)

# ★ 模块 API 契约（2026-09-04 真实运行教训的结构化版本）：凡 main.py/runner.py
#   引用的 panel.<attr> 必须真实存在——跨模块引用错误只会在真实执行路径上炸，
#   结构断言在提交时就能拦住，不必等下一次运行。
_api_missing = []
for _f in ("main.py", "runner.py"):
    for _n in ast.walk(ast.parse(read(_f))):
        if isinstance(_n, ast.Attribute) and isinstance(_n.value, ast.Name) \
                and _n.value.id == "panel":
            _attr = _n.attr
            if not hasattr(panel, _attr) and _attr not in _api_missing:
                _api_missing.append(f"{_f}: panel.{_attr}")
check("main.py/runner.py 引用的 panel.* 属性均存在", not _api_missing,
      f"缺失: {_api_missing}" if _api_missing else "")
check("已移除 setup_windows_task.ps1", not (BASE / "setup_windows_task.ps1").exists())

# --- 8. .vbs 必须是纯 ASCII ---------------------------------------------------
# cscript/wscript 按 ANSI(中文系统=GBK) 解析 .vbs；若文件存成 UTF-8 且含中文，
# 字符串字面量会被撕裂，双击直接报「未终止的字符串常量」而根本起不来。
for f in BASE.glob("*.vbs"):
    bad = [i + 1 for i, line in enumerate(f.read_bytes().split(b"\n"))
           if any(b > 127 for b in line)]
    check(f"{f.name} 为纯 ASCII（否则 cscript 解析失败）", not bad,
          f"非 ASCII 行: {bad[:5]}" if bad else "")

# ================= MAI-001 多账号目录隔离（2026-09-05 spec 版本 2） =================
m = read("main.py")
m_no = strip_comments(read("main.py"), "py")
mtree = ast.parse(m)
mfuncs = {n.name for n in ast.walk(mtree) if isinstance(n, ast.FunctionDef)}

check("main.py 定义账号根目录", "ACCOUNTS_ROOT" in m and '"accounts"' in m)
check("main.py 定义 account_root(", "account_root(" in m)
check("main.py 定义 create_account", "create_account" in mfuncs)
check("main.py 定义 list_accounts", "list_accounts" in mfuncs)
check("main.py 定义 migrate_legacy_to_account", "migrate_legacy_to_account" in mfuncs)
check("main.py 定义 legacy_pending", "legacy_pending" in mfuncs)

# ★ 别名校验统一入口 + 拒绝 Windows 保留设备名（P2-5）
check("main.py 定义 validate_alias", "validate_alias" in mfuncs)
check("main.py 别名校验拒绝保留设备名", "COM" in m and "LPT" in m and "NUL" in m)
check("main.py 别名校验为 ASCII 正则", "VALID_ALIAS_RE" in m)

# ★ 防串号（P1-4/4.6-5）：账户数据函数一律收 alias；load_config 双入口 alias=None 合法
for fn in ("load_user_data", "save_user_data", "update_schedule_time",
           "update_message_texts", "update_targets"):
    node = next((x for x in ast.walk(mtree)
                 if isinstance(x, ast.FunctionDef) and x.name == fn), None)
    names = [a.arg for a in node.args.args] if node else []
    check(f"★{fn} 定义收 alias 参数（防串号：无隐式默认）", "alias" in names)
lc = next((x for x in ast.walk(mtree)
           if isinstance(x, ast.FunctionDef) and x.name == "load_config"), None)
lc_args = [a.arg for a in lc.args.args] if lc else []
check("★load_config 收可选 alias（双入口：None=公开键）", "alias" in lc_args)

# ★ 跨进程守卫（P1-1）
check("main.py 定义 .running 守卫路径", "RUN_GUARD_PATH" in m and ".running" in m)
check("main.py 守卫用 O_EXCL 独占创建", "O_EXCL" in m)
check("main.py 守卫含 pid 存活探测", "tasklist" in m)
check("main.py 定义 acquire_run_guard", "acquire_run_guard" in mfuncs)
check("main.py 定义 release_run_guard", "release_run_guard" in mfuncs)
check("main.py 守卫释放调用与 finally 成对（Task 3 手动路径落地后转绿）",
      "release_run_guard()" in m and "finally:" in m)

# ★ runner 与 CLI 账号化
r = read("runner.py")
check("runner.py 解析 --account", '"--account"' in r)
check("runner.py trigger_run 携带 account", "account=" in r)
r2 = m_no
check("main.py CLI 提供 --account", '"--account"' in r2)
check("main.py CLI 提供 --migrate", '"--migrate"' in r2)
check("main.py CLI 提供 --list-accounts", '"--list-accounts"' in r2)

# ★ panel 账号化
p = read("panel.py")
check("panel.py 含账号解析统一入口 _resolve_account", "_resolve_account" in p)
check("panel.py 提供 /api/accounts", '"/api/accounts"' in p)
check("panel.py 提供 /api/migrate", '"/api/migrate"' in p)
check("panel.py 提供任务收尾 /api/tasks/adopt-legacy", '"/api/tasks/adopt-legacy"' in p)
check("panel.py run meta 携带 account 字段", '"account"' in p)
check("panel.py 触发路径经 load_config(account)", "load_config(account)" in p)
check("panel.py worker 使用 acquire_run_guard", "acquire_run_guard" in p)
check("panel.py 截图按 meta.account 反查（不依赖当前账号）", "_find_run_account" in p)

# ★ real_chrome_profile 互斥（P1-2）：config.yaml 注释含多账号警告
b = yaml.safe_load(read("config.yaml"))["browser"]
check("config.yaml real_chrome_profile 仍为 false（多账号硬约束）",
      b.get("real_chrome_profile") is False)
check("config.yaml real_chrome_profile 注释含多账号互斥警告",
      "多账号" in read("config.yaml") and "real_chrome_profile" in read("config.yaml"))

# ★ 既有单账号保证不被破坏（抽样，全量已在上文保留）
check("main.py 用 schtasks 注册（既有）", '"schtasks", "/Create"' in m)

# ★ SIV-002 会话查找全量扫描 + 失败目标审计（2026-09-07 spec）：
# 单向向下滚动 + 跨目标滚动位置残留 → 目标在上方时漏扫误判 no_match；
# 每次查找先重置列表到顶部。失败目标名单写入 run meta，面板标红展示。
check("★查找会话前重置列表滚动位置（scrollTop=0）", "scrollTop = 0" in d)
check("★重置后等待虚拟列表重渲染", "scrollTop = 0" in d and "time.sleep(random.uniform" in d)
check("★记录失败目标名单 failed_targets", "self.failed_targets" in d
      and "failed_targets.append(name)" in d)
check("★run 每次重置 failed_targets", "self.failed_targets = []" in d)
check("★panel 写入 meta.failed_targets", 'meta["failed_targets"]' in p)
check("★面板列表页标红失败目标", "failed_targets" in read("panel.html"))

# ★ BAT-001 一键出发：全账号串行批量（2026-09-08 spec，独立执行器 batch_runner.py）
# 首页「一键出发」→ 全部已添加账号顺次跑各自私聊任务，号间强制错峰 15 分钟；
# 执行器为独立子进程（面板可关不丢队列），进度经 userdata/batch_state.json 暴露。
# RED 态 batch_runner.py 尚不存在：read() 无缺文件容错，必须存在性守卫（评审 P1-F1）。
b = read("batch_runner.py") if (BASE / "batch_runner.py").exists() else ""
check("★BAT-001 面板提供 /api/trigger-all", "/api/trigger-all" in p)
check("★BAT-001 面板提供 /api/batch-state", "/api/batch-state" in p)
check("★BAT-001 面板提供 /api/batch-cancel", "/api/batch-cancel" in p)
check("★BAT-001 批量激活期拒绝单号动作", "批量一键出发进行中" in p)
check("★BAT-001 面板读 batch_state.json 判 active", "batch_state.json" in p)
check("★BAT-001 面板 spawn batch_runner.py", "batch_runner.py" in p)
check("★BAT-001 执行器存在且支持 --batch-all", "--batch-all" in b)
check("★BAT-001 错峰下限默认 15 分钟", "default=15" in b)
check("★BAT-001 取消标志落盘与消费", "cancel_requested" in b)
check("★BAT-001 状态文件原子写", "os.replace(" in b and "batch_state.json" in b)
check("★BAT-001 等待/错峰状态机 token", "waiting_stagger" in b and "waiting_guard" in b)
check("★BAT-001 陈旧守卫 pid 感知自愈(P1-F1)", "def _stale_guard_cleanup" in b)
check("★BAT-001 防双发读最近 run(keep=1)", "list_runs(acc, keep=1)" in b)
check("★BAT-001 各号已存文案 api_state(acc)", "api_state(acc)" in b)
check("★BAT-001 触发与轮询复用 panel 链路",
      "panel.trigger_run(" in b and "panel._load_meta(" in b)
check("★BAT-001 前端一键出发按钮与横幅",
      "一键出发" in read("panel.html") and "loadBatchState" in read("panel.html"))

# ★ SCH-001 定时任务条目库 + 常驻调度器（2026-09-08 spec；零 schtasks 定时，取代 MAI-001 每号单任务形态）
# 任务=jobs 条目(账号/时刻/目标/文案 自带独立)；守护进程到点自动切号、串行、错峰固定 15 分钟；
# 撞车排队不跳过；错过当日补跑一次；取消/停止优雅收尾；心跳+注册表 Run 自启；手动路径零感知。
j = read("jobs.py") if (BASE / "jobs.py").exists() else ""
s = read("scheduler_daemon.py") if (BASE / "scheduler_daemon.py").exists() else ""
html_txt = read("panel.html")
check("★SCH-001 注入缝 worker 支持任务 targets", "persist_texts" in p and 'cfg["targets"] = targets' in p)
check("★SCH-001 定时文案不写回账号(仅 persist_texts=True)", "if persist_texts and texts:" in p)
check("★SCH-001 run meta targets 支持任务注入", "tgt_list = targets if targets is not None" in p)
check("★SCH-001 jobs 存取模块函数存在", "def load_jobs" in j and "def save_jobs" in j and "def delete_job" in j)
check("★SCH-001 jobs 文件名与原子写", "scheduler_jobs.json" in j and "os.replace(" in j)
check("★SCH-001 任务条目字段校验", "def _validate_job" in j and "def create_job" in j)
check("★SCH-001 迁移幂等标志(plan F5)", "migrated_from_legacy" in j)
check("★SCH-001 守护错峰常数固定 15", "DAEMON_STAGGER_MINUTES = 15" in s)
check("★SCH-001 守护状态/心跳文件名", "scheduler_state.json" in s and "scheduler_heartbeat.json" in s)
check("★SCH-001 两段式落盘 dispatching(plan F1)", "dispatching" in s and 'status": "running"' in s)
check("★SCH-001 崩溃复核不重发(plan F1)", "def _recover_interrupted" in s)
check("★SCH-001 出队重读防删改(plan F4)", "def _reload_job" in s)
check("★SCH-001 跨天重置不静默丢(plan F3)", "跨天未及触发" in s)
check("★SCH-001 停止标志优雅退出(plan F2)", "stop_requested" in s)
check("★SCH-001 取消消费(磁盘为准)", "cancel_requested" in s)
check("★SCH-001 注册表 Run 自启", "CurrentVersion\\Run" in s and "DouyinAutoFireScheduler" in s)
check("★SCH-001 面板提供 /api/jobs 系列", "/api/jobs/update" in p and "/api/jobs/toggle" in p and "/api/jobs/delete" in p)
check("★SCH-001 面板提供 /api/scheduler 系列", "/api/scheduler/start" in p and "/api/scheduler/stop" in p
      and "/api/scheduler/cancel" in p and "/api/scheduler/autostart" in p)
check("★SCH-001 页面任务库入口", "新建定时任务" in html_txt and "loadJobs" in html_txt)
check("★SCH-001 页面守护状态卡", "开机自启" in html_txt and "下次触发" in html_txt)
check("★SCH-001 迁移/清理引导按钮", "一键迁移" in html_txt and "清理旧系统任务" in html_txt)
check("★SCH-001 runner 未接新参数(默认语义保留)",
      "persist_texts" not in rsrc and ", targets=" not in rsrc)
check("★SCH-001 batch_runner 未接新参数(默认语义保留)",
      "persist_texts" not in b and ", targets=" not in b)

# --- 汇总 ---------------------------------------------------------------------
print(f"\n通过 {len(PASSES)} / 失败 {len(FAILS)}\n")
for p in PASSES:
    print("  [ok]  ", p)
for f in FAILS:
    print("  [FAIL]", f)
print()
sys.exit(1 if FAILS else 0)
