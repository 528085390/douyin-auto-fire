# 多账号目录隔离（账号自定义别名 + 每账号独立环境/数据 + 面板账号切换）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 日期：2026-09-05
- 状态：待用户签字（plan 评审 APPROVED 后由用户签字生效，签字前禁止进入 IMPLEMENT）
- 关联 spec：`docs/superpowers/specs/2026-09-04-multi-account-isolation-design.md`（版本 2，已批准）
- 前置：Spec Review APPROVED（`docs/superpowers/reviews/MAI-001-spec-review.md` 版本 2）；`.hermes.md` 71481d5（spec 免签、plan 保留用户签字）

**Goal:** 把「单账号全局私有数据」改造为「每账号独立目录 + 显式账号参数」：`userdata/accounts/<别名>/` 内含各自 user_data.yaml / browser_data / conversations_cache.json / runs；面板顶部账号切换联动三块数据；CLI/定时任务按账号（`--account`、每账号一条 `DouyinAutoFire-<别名>` 任务）；跨进程 `.running` 守卫保证「同一时刻绝不并发」；verify.py 防串号断言先 RED 后 GREEN。

**Architecture:** 改造集中在配置/入口层——main.py 提供账号层解析与守卫原语（`account_root/list_accounts/create_account/load_config(alias=None)/update_*(alias)/legacy_pending/migrate_legacy_to_account/acquire_run_guard`）；runner.py 与 main.py CLI 解析 `--account` 后经 `panel.trigger_run(..., account=…)` 合流；panel.py 所有路径函数按账号解析、动作路径强制显式 account、新增账号/迁移/任务收尾端点与 `_resolve_account` 单一入口；panel.html 加账号栏与迁移引导。douyin.py 发送核心零改动（唯一注入点 browser.user_data_dir 由 load_config(alias) 覆盖）。

**Tech Stack:** Python 3.11 / Playwright (sync API, channel=chrome, headless=False) / 无测试框架，自检靠 `verify.py`（`.venv/Scripts/python.exe verify.py`）。面板纯标准库 BaseHTTPRequestHandler；HTML 原生 JS。

**Spec:** `docs/superpowers/specs/2026-09-04-multi-account-isolation-design.md`（版本 2，commit 0b20f8b + 0d9824d）

## Global Constraints

- **防串号红线（spec 三.1.3/R1）**：账户数据读写/运行路径一律**显式 alias/account，无隐式默认**；漏传就报错，绝不静默回落「唯一账号」兜底（唯一账号自动沿用只允许出现在 CLI/runner 的**入口解析层**，不允许出现在数据读写函数内部）。
- **跨进程守卫（spec 4.3/P1-1）**：`USERDATA_DIR/.running` 独占创建（`os.O_CREAT|os.O_EXCL|os.O_WRONLY`），内容 JSON `{account, pid, start_ts}`；`finally` 删除；创建遇已存在先查 pid 存活（`tasklist /FI "PID eq <pid>"`），pid 不存在视为陈旧残留删除重试一次。runner/面板/手动（含 login/sync 窗口，评审 A2）全走守卫。
- **`real_chrome_profile` 互斥（spec 4.1/P1-2）**：多账号期间视为不支持、必须保持 false；config.yaml 注释三处警告；R1 措辞收窄。**不得**为账号映射真实 profile。
- **`ensure_userdata()` 收窄（spec 4.1/P1-3）**：只保证 `userdata/` 目录存在；**不再**自动创建顶层 `user_data.yaml / browser_data / runs / conversations_cache.json`。私有骨架只在 `create_account` 内于账号目录创建。
- **`load_config(alias=None)` 双入口（spec 4.1/P1-4）**：`alias=None` 只合并 config.yaml 公开键（面板启动读 port 等零账号路径用）；传 alias 才合并该账号私有键并覆盖 `browser.user_data_dir = str(account_root(alias)/"browser_data")`。账户数据读写函数（load_user_data/update_*）只收 alias，不收 None。
- **别名校验（spec 4.1/P2-5）**：1~24 字符 `^[A-Za-z0-9_]+$`；拒绝中文/空格/`-`/Windows 文件名字符 `\ / : * ? " < > |`/首尾点；**拒绝 Windows 保留设备名**（`CON NUL PRN AUX`、`COM1-9`、`LPT1-9`，大小写不敏感）。校验函数唯一入口在 main.py，panel/CLI 共用。
- **截图/明细按 run_id 的 meta.account 反查（spec 4.4/P2-4）**：只读不依赖 last_account/当前账号；路径穿越防护（resolve + startswith 前缀）不放宽。
- **切号缓存重载（spec 4.4/P2-3）**：切号后必须先按新账号重载 conversations_cache 进内存，之后才允许勾选/保存；保存前重读账号缓存文件合并，不直接信内存全局列表。
- **verify stub 适配（spec 4.6-7/P2-1）**：verify 内 `panel.load_config = lambda…` 零参 stub 随签名改 `lambda *a, **k:`（stub 适配属 RED 本分，不是改断言）。
- **单账号零打扰（spec 4.3/P2-2）**：CLI/runner 未给 `--account` 且恰 1 账号 → 自动沿用该账号（不报错不留痕）；多账号（>1）且未给 `--account` → exit 2 报错并列别名（spec 评审拍板 ④）。`--test` 免账号。
- **隐私红线**：进 git 的文件（含本 plan、verify.py、文档、示例）不得出现真实会话名/真实内容/真实账号别名；示例一律用 `main`/`backup` 等占位。真实数据只存在于 gitignored `userdata/`。
- 验证命令一律：`cd D:/ai_project/douyin-auto-fire && ./.venv/Scripts/python.exe verify.py`
- 提交粒度：每个 Task 结束提交一次；commit message 中文 conventional commits（先例：`test(verify): …`、`feat(main): …`、`fix(panel): …`、`docs: …`）。
- 不改动（spec 三.6/E7/E9）：douyin.py 发送/校验/审计核心零改动；`_detect_risk_control` 等风控逻辑；面板既有非目标清单（XSS/CSRF/截图前缀等）。`browser_data` 目录锁冲突提示分支保留（作为守卫之外的二次保险）。

## File Structure

| 文件 | 责任 | 本次动作 |
|---|---|---|
| `main.py` | 账号层原语 / CLI 入口 | 新增 ACCOUNTS_ROOT/account_root/list_accounts/create_account/validate_alias/load_user_data/save_user_data/legacy_pending/migrate_legacy_to_account/task_name/守卫原语；`load_config(alias=None)` 双入口；`ensure_userdata()` 收窄；update_* 收 alias；CLI 增 `--account/--migrate/--list-accounts` 与交互选号 |
| `runner.py` | 定时任务入口 | 解析 `--account`；调 `panel.trigger_run(texts, headless=None, account=…)`；轮询 `panel._load_meta(run_id, account)` |
| `panel.py` | 面板数据层 / API / 路由 | 路径函数账号化；worker/trigger_run/login/sync 携带 account 并走守卫；run meta 增 account；`_resolve_account` 单一入口；新增 /api/accounts /api/migrate /api/tasks/adopt-legacy /api/select；runs 明细/截图按 meta.account 反查；切号缓存重载 |
| `panel.html` | 面板 UI | 账号栏（标题下、页签上）、迁移引导条、空态、fetch 封装自动附 account、三块数据随账号联动 |
| `verify.py` | 永久自检 | 新增/改造 MAI 断言（RED 先行）；第 3 节按账号探测改造；stub 适配 |
| `config.yaml` | 公开配置 | user_data_dir 注释改账号语义；real_chrome_profile 注释加多账号警告（值不动） |
| `user_data.yaml.example` | 模板 | 头部说明多账号布局 |
| `README.md` / `docs/*.md` | 文档 | 目录结构、账号一节、CLI/任务名、架构账号层（spec 4.7 清单） |
| `userdata/` | 私有运行数据（gitignore） | 不提交；人工核对时使用 |

**关键接口契约（跨 Task 共享，plan 定字节级形态，Task 1 断言锁定，后续 Task 必须照此实现）：**

main.py 新增/改名：

```python
ACCOUNTS_ROOT = USERDATA_DIR / "accounts"
RUN_GUARD_PATH = USERDATA_DIR / ".running"
VALID_ALIAS_RE = re.compile(r"^[A-Za-z0-9_]{1,24}$")
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} \
    | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}

def validate_alias(alias: str) -> str | None:
    """合法返回 None；非法返回给用户看的完整中文错误文案。"""
def account_root(alias: str) -> Path: ...
def list_accounts() -> list[str]: ...
def create_account(alias: str) -> Path: ...
def load_user_data(alias: str) -> dict: ...          # 只收 alias
def save_user_data(alias: str, data: dict) -> None: ...  # 只收 alias，写账号目录
def update_schedule_time(alias: str, time_str: str) -> None: ...
def update_message_texts(alias: str, texts: list[str]) -> None: ...
def update_targets(alias: str, targets: list[dict]) -> None: ...
def task_name(alias: str) -> str: return "DouyinAutoFire-" + alias
def legacy_pending() -> bool: ...
def migrate_legacy_to_account(alias: str) -> dict: ...  # {"ok": bool, "moved": [...], "failed": [...], "error": str|None}
def acquire_run_guard(account: str) -> str | None:  # None=成功；失败返回占用人描述
def release_run_guard() -> None: ...
def _pid_alive(pid: int) -> bool: ...   # tasklist /FI
def load_config(alias: str | None = None) -> dict: ...  # None=仅公开键；alias=合并私有+覆盖 user_data_dir
def ensure_userdata() -> None: ...      # 收窄：仅 mkdir USERDATA_DIR / ACCOUNTS_ROOT
def resolve_account(flag_alias: str | None) -> str:  # CLI 入口解析：显式>唯一>报错 exit 2
def list_accounts() ...
```

panel.py 关键签名（改动后）：

```python
from main import (account_root, list_accounts, create_account, load_user_data,
                  update_schedule_time, update_message_texts, update_targets,
                  load_config as _main_load_config, ensure_userdata,
                  task_name, legacy_pending, migrate_legacy_to_account,
                  acquire_run_guard, release_run_guard, USERDATA_DIR, TASK_NAME)  # TASK_NAME 语义见下

def load_config(account: str | None = None) -> dict:   # 包装 _main_load_config(account)，零账号时 None
def _meta_path(run_id: str, account: str) -> Path:     # account_root(account)/"runs"/<id>.json
def _log_path(run_id: str, account: str) -> Path
def _run_dir(run_id: str, account: str) -> Path
def _load_meta(run_id: str, account: str) -> dict | None
def _delete_run(rid: str, account: str) -> bool
def list_runs(account: str, keep: int | None = 3) -> list[dict]
def prune_runs(account: str, keep: int = 3, max_delete: int = 1)
def _find_run_account(run_id: str) -> str | None       # P2-4：遍历 list_accounts 找含该 meta 的账号
def _load_conversations_cache(account: str) -> list[dict]
def _save_conversations_cache(account: str) -> None
def _resolve_account(query_or_body: dict, *, action: bool = False) -> str | None
def _worker(run_id: str, texts: list[str], headless: bool | None, account: str)
def trigger_run(texts: list[str], headless: bool | None = None, account: str | None = None) -> str | None
def trigger_login(account: str) -> bool
def _login_worker(account: str)
def trigger_sync(account: str) -> bool
def _sync_worker(account: str)
def create_task(time_str: str, texts: list[str], account: str) -> dict
def change_task(action: str, account: str) -> dict
def query_system_task(name: str | None = None) -> dict | None  # None 时抛/由调用方给 task_name(account)
def api_state(account: str) -> dict
def api_tasks(account: str) -> dict
def api_run_detail(run_id: str) -> dict                # 内部 _find_run_account
def api_run_screenshots(run_id: str) -> list[dict]
def api_conversations(account: str) -> dict
```

panel.py 模块级状态与常量（改动后）：

```python
TASK_NAME_PREFIX = "DouyinAutoFire"          # 旧任务名/任务前缀，仅迁移收尾用（不再叫 TASK_NAME 作默认任务名）
PANEL_STATE_PATH = USERDATA_DIR / "panel_state.json"   # {"last_account": alias}
_current_run_account: str | None = None      # 本次运行属哪个号（api_state 返回）
```

> 注意：`query_system_task(name=None)` 语义改为——显式传 `task_name(alias)` 时查该账号任务；不传时保持旧行为只查 `DouyinAutoFire`（兼容 verify 第 4 节打桩与既有调用，直到 Task 3/4 全量改完；最终形态由调用方总是显式传 name）。

---

### Task 1: verify.py 先 RED（MAI 断言 + 第 3 节按账号探测改造 + stub 适配）

**Files:**
- Modify: `verify.py`（新增「MAI 多账号隔离」断言节；改造第 3 节；第 4 节 stub 适配）

**Interfaces:**
- Consumes: 无（本 Task 只加断言/探测）
- Produces: 一批会在 Task 2–4 后转 GREEN 的断言。Task 2/3/4 实现者以此为准绳，字面形态必须逐字一致。

> 为什么先 RED：项目没有测试框架，verify.py 就是事实测试命令。先红证明后续绿不是假绿。基线确认：本机当前 verify 全绿（exit 0，2026-09-05 实测）。

- [ ] **Step 1: 改造第 3 节为「按账号探测 + 账号层未实现时退回旧单任务探测」**

将 `verify.py:79-105`（`# --- 3. 已注册的定时任务 ---` 到 `else: check(...)` 段整体）替换为：

```python
# --- 3. 已注册的定时任务（MAI-001：账号层未实现时退回旧单任务名探测） ---
import panel  # noqa: E402

_account_layer = None
try:
    from main import list_accounts, task_name  # noqa: E402
    _account_layer = True
except Exception:  # noqa: BLE001  (RED 过渡期/异常导入：退回旧探测)
    _account_layer = False

if _account_layer:
    aliases = list_accounts()
else:
    aliases = []


def _probe_task(tn: str):
    task = panel.query_system_task(tn)
    if task and task.get("exists"):
        cmd = task.get("command", "")
        check(f"任务 {tn} 不再套 cmd /c（不弹黑框）", not cmd.lower().startswith("cmd /c"))
        check(f"任务 {tn} 入口是 runner.py", "runner.py" in cmd)
        exes = re.findall(r'"([^"]+\.exe)"|(\S+\.exe)', cmd, re.I)
        exes = [a or b for a, b in exes]
        check(f"任务 {tn} 命令可解析出解释器", bool(exes), cmd[:70])
        for e in exes:
            check(f"★任务 {tn} 引用的 exe 真实存在（原 bug 复现点）", Path(e).exists(), e)
    else:
        check(f"账号任务 {tn} 已注册", False, f"未找到 {tn}（请在面板为对应账号注册）")


if aliases:
    for a in aliases:
        _probe_task(task_name(a))
else:
    # 零账号（新装未建号）或账号层尚未实现：按现状报「未注册」，保留旧断言形态
    task = panel.query_system_task()
    if task and task.get("exists"):
        cmd = task.get("command", "")
        check("任务不再套 cmd /c（不弹黑框）", not cmd.lower().startswith("cmd /c"))
        check("任务入口是 runner.py", "runner.py" in cmd)
        exes = re.findall(r'"([^"]+\.exe)"|(\S+\.exe)', cmd, re.I)
        exes = [a or b for a, b in exes]
        check("任务命令可解析出解释器", bool(exes), cmd[:70])
        for e in exes:
            check(f"★任务引用的 exe 真实存在（原 bug 复现点）", Path(e).exists(), e)
        rsrc = (BASE / "runner.py").read_text(encoding="utf-8")
        check("runner.py 复用 panel.trigger_run（合流手动触发逻辑）",
              "import panel" in rsrc and "panel.trigger_run" in rsrc)
        check("runner 用真实有头浏览器（不强制 headless=False 可见）",
              "headless=None" in rsrc and "headless=False" not in rsrc.split("trigger_run")[-1])
        check("runner.py 不再直接调 main.job 旁路",
              not re.search(r'^\s*main\.job\s*\(', rsrc, re.M)
              and not re.search(r'DouyinStreak\(cfg\)\.run\(\)\s*$', rsrc, re.M))
    else:
        check("定时任务已注册", False, "未找到 DouyinAutoFire（请在面板注册）")
```

> RED 预期：本机已有旧任务 `DouyinAutoFire` 且账号层未实现 → `aliases=[]` 走旧分支，旧断言仍过；新断言失败来自 Step 2 的 MAI 节，不会 AttributeError 崩溃。

- [ ] **Step 2: 在文件末尾「汇总」之前（`verify.py:246` 前）插入 MAI 断言节**

```python
# ================= MAI-001 多账号目录隔离（2026-09-05 spec 版本 2） =================
m = read("main.py")
m_no = strip_comments(read("main.py"), "py")
mtree = ast.parse(m)
mfuncs = {n.name for n in ast.walk(mtree) if isinstance(n, ast.FunctionDef)}

check("main.py 定义账号根目录", "ACCOUNTS_ROOT" in m)
check("main.py 定义 account_root(", "account_root(" in m)
check("main.py 定义 create_account", "create_account" in mfuncs)
check("main.py 定义 list_accounts", "list_accounts" in mfuncs)
check("main.py 定义 migrate_legacy_to_account", "migrate_legacy_to_account" in mfuncs)
check("main.py 定义 legacy_pending", "legacy_pending" in mfuncs)
check("main.py 引用 userdata/accounts", '"userdata/accounts"' in m)

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
check("main.py 守卫删除在 finally", "finally" in m)

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
```

> 注意：Step 1 已把 `import ast` 提前使用——verify.py 顶部只有 `import re/sys/tempfile/pathlib`，`ast` 在第 5b 节才 import（`verify.py:137`）。本 MAI 节放在文件尾部，`ast` 与 `yaml` 在 5b/6 节已 import 过，**直接可用**（文件是顺序执行的，不是函数作用域）。若 Step 1 的替换把 `import panel` 位置改变不影响——`panel` 与 `re` 均已 import。

- [ ] **Step 3: 第 4 节 stub 适配（P2-1）**

`verify.py:117` 的 `panel.load_config = lambda: {"browser": {"headless": True}}` 改为：

```python
    panel.load_config = lambda *a, **k: {"browser": {"headless": True}}
```

> 同节 `panel.query_system_task = lambda *a, **k: {...}` 已带 `*a, **k`，不动。若 Task 4 后 `panel.api_tasks(account)` 收必选 account，此节调用处也要传参——GREEN 阶段由 Task 4 收尾时一并核对（见 Task 4 Step 6）。

- [ ] **Step 4: 跑 verify.py 确认 RED**

Run: `./.venv/Scripts/python.exe verify.py`
Expected: 大量失败、exit 1。失败集中在 MAI 节（`main.py 定义 ACCOUNTS_ROOT` 到 `panel.py 触发路径经 load_config(account)`、`config.yaml real_chrome_profile 注释含多账号互斥警告` 等全红）；旧节（1/2/4/5/5b/6/7/8）保持绿。**禁止出现 traceback/AttributeError**（若有，说明第 3 节或 MAI 节存在对未定义名字的直接引用——先修 verify 再继续）。

- [ ] **Step 5: 提交（红测试独立提交，仓库先例 8c2d69d）**

```bash
git add verify.py && git commit -m "test(verify): MAI-001 账号层/防串号/守卫断言先 RED（第 3 节按账号探测改造）"
```

---

### Task 2: main.py 账号层（账号原语 + ensure_userdata 收窄 + load_config 双入口 + 守卫）

**Files:**
- Modify: `main.py`（常量区、ensure_userdata/load_config/_load_user_data/_save_user_data/update_*、新增账号层函数区、守卫原语）

**Interfaces:**
- Consumes: 既有 `CONFIG_PATH/USERDATA_DIR/USER_DATA_PATH/CONV_CACHE_PATH/RUNS_DIR/BROWSER_DATA_DIR/TIME_RE/TASK_NAME/_PRIVATE_KEYS`
- Produces: Task 1 断言锁定的全部名字与形态（见 Global Constraints「关键接口契约」）+ `TASK_NAME` 语义改为「旧任务名前缀」（保留常量供迁移收尾/兼容，值仍 `DouyinAutoFire`）。

- [ ] **Step 1: 常量区追加（main.py:31-42 之后）**

```python
# 多账号（MAI-001）：每账号一个目录；私有骨架只在 create_account 时于账号目录内创建
ACCOUNTS_ROOT = USERDATA_DIR / "accounts"
RUN_GUARD_PATH = USERDATA_DIR / ".running"          # 跨进程运行守卫（独占文件）
PANEL_STATE_PATH = USERDATA_DIR / "panel_state.json"  # {last_account: alias}（由 panel.py 读写）
VALID_ALIAS_RE = re.compile(r"^[A-Za-z0-9_]{1,24}$")
# Windows 保留设备名（大小写不敏感），作为目录名会失败，校验函数直接挡下
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} \
    | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
```

> `PANEL_STATE_PATH` 也可放 panel.py——但状态文件与账号布局强相关，main 提供常量、panel 使用，verify 只锁 `.running` 与账号函数，不锁该常量名。二选一即可，plan 定为 main 常量。

- [ ] **Step 2: `ensure_userdata()` 收窄（main.py:45-60 整函数替换）**

```python
def ensure_userdata() -> None:
    """缺失 userdata/ 时建目录（多账号语义，spec 4.1/P1-3）。

    只保证 userdata/ 与 accounts/ 存在；不再自动创建顶层 user_data.yaml /
    browser_data / runs / conversations_cache.json —— 那些私有骨架改由
    create_account 在 accounts/<别名>/ 内创建，避免「空骨架被误判为旧数据」。
    """
    USERDATA_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_ROOT.mkdir(exist_ok=True)
```

- [ ] **Step 3: `load_config(alias=None)` 双入口（main.py:63-76 整函数替换）**

```python
def load_config(alias: str | None = None) -> dict:
    """加载配置。alias=None：只合并 config.yaml 公开键（基础设施读，零账号安全，
    不碰任何账号私有文件）；alias 给定：再合并该账号 user_data.yaml 私有键并覆盖
    browser.user_data_dir 指向账号 browser_data（防串号关键覆盖）。"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"找不到配置文件: {CONFIG_PATH}")
    ensure_userdata()
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        merged = yaml.safe_load(f) or {}
    if alias is not None:
        user = load_user_data(alias)
        for key in _PRIVATE_KEYS:
            if key in user:
                merged[key] = user[key]
        merged.setdefault("browser", {})["user_data_dir"] = \
            str(account_root(alias) / "browser_data")
    return merged
```

> 行为差异说明：旧版 load_config() 无条件 `ensure_userdata()` 建顶层骨架 + 合并顶层 user_data.yaml。新版无 alias 时不合并私有键；顶层私有文件**不再被读取**（迁移后也不应再有）。panel.py `main()` 启动读 port 用 `load_config()`（None）安全。

- [ ] **Step 4: 私有数据读写账号化（把 `_load_user_data/_save_user_data` 改造为 account-root 版，新增 `load_user_data/save_user_data`；update_* 收 alias）**

将 `main.py:109-148` 的 `_load_user_data/_save_user_data/update_schedule_time/update_message_texts/update_targets` 整体替换为：

```python
def account_root(alias: str) -> Path:
    """账号目录（调用方保证别名已校验）。"""
    return ACCOUNTS_ROOT / alias


def list_accounts() -> list[str]:
    """扫描 accounts/ 下含 user_data.yaml 或 browser_data 的子目录名，排序返回。"""
    if not ACCOUNTS_ROOT.is_dir():
        return []
    out = []
    for d in sorted(ACCOUNTS_ROOT.iterdir()):
        if d.is_dir() and ((d / "user_data.yaml").exists() or (d / "browser_data").is_dir()):
            out.append(d.name)
    return out


def validate_alias(alias: str) -> str | None:
    """别名合法性检查：合法返回 None；非法返回给用户看的中文错误文案（完整规则）。

    panel/CLI 共用同一入口（spec 4.1）。规则：1~24 个字符，仅英文/数字/下划线，
    拒绝中文、空格、-、Windows 文件名字符 \\ / : * ? " < > |、首尾点、
    Windows 保留设备名（CON/NUL/PRN/AUX/COM1-9/LPT1-9，大小写不敏感）。
    """
    if not isinstance(alias, str) or not alias:
        return "别名不能为空（1~24 个字符，仅限英文/数字/下划线）。"
    if not VALID_ALIAS_RE.match(alias):
        return ("别名不合法：仅限 1~24 个英文/数字/下划线字符，"
                "不能含中文、空格、连字符及 \\ / : * ? \" < > | 等符号，首尾不能是点。")
    if alias.upper() in WINDOWS_RESERVED_NAMES:
        return f"别名 {alias!r} 是 Windows 保留设备名，无法作为目录名，请换一个。"
    return None


def create_account(alias: str) -> Path:
    """校验别名 → mkdir → 写账号骨架（user_data.yaml + browser_data/ + runs/ +
    conversations_cache.json []），返回账号目录。别名非法抛 ValueError（含文案）。"""
    err = validate_alias(alias)
    if err:
        raise ValueError(err)
    root = account_root(alias)
    if root.exists():
        raise ValueError(f"账号 {alias!r} 已存在。")
    root.mkdir(parents=True, exist_ok=True)
    (root / "browser_data").mkdir(exist_ok=True)
    (root / "runs").mkdir(exist_ok=True)
    ud = root / "user_data.yaml"
    if not ud.exists():
        ud.write_text(
            "# 私有用户数据（账号: " + alias + "）—— 会话名/发送内容/发送时间，请勿提交\n"
            "# 多账号下每个账号一份，位于 userdata/accounts/<别名>/user_data.yaml\n\n"
            "targets: []\n"
            "message:\n  texts: [\"在吗\"]\n  random: false\n"
            "schedule:\n  time: \"21:30\"\n",
            encoding="utf-8",
        )
    cc = root / "conversations_cache.json"
    if not cc.exists():
        cc.write_text("[]", encoding="utf-8")
    return root


def load_user_data(alias: str) -> dict:
    """读取账号私有数据；文件不存在返回空 dict。只收 alias（防串号）。"""
    if validate_alias(alias) is not None:
        return {}  # 非法别名不抛——调用方先用 validate_alias 给完整文案
    p = account_root(alias) / "user_data.yaml"
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_user_data(alias: str, data: dict) -> None:
    """整体写回账号私有数据（保留可读结构）。"""
    root = account_root(alias)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "user_data.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def update_schedule_time(alias: str, time_str: str) -> None:
    """把 schedule.time 写回账号 user_data.yaml。"""
    data = load_user_data(alias)
    data.setdefault("schedule", {})["time"] = time_str
    save_user_data(alias, data)


def update_message_texts(alias: str, texts: list[str]) -> None:
    """把 message.texts 写回账号 user_data.yaml（自动维护 random）。"""
    data = load_user_data(alias)
    data.setdefault("message", {})["texts"] = list(texts)
    data["message"]["random"] = len(texts) > 1
    save_user_data(alias, data)


def update_targets(alias: str, targets: list[dict]) -> None:
    """把 targets 写回账号 user_data.yaml。"""
    data = load_user_data(alias)
    data["targets"] = [{"name": str(t.get("name", "")).strip(),
                        "type": str(t.get("type", "private")).strip() or "private"}
                       for t in targets]
    save_user_data(alias, data)
```

> 兼容说明：旧顶层 `USER_DATA_PATH/_load_user_data/_save_user_data` 名不再存在；若 verify/panel 还引用旧名会在 Task 3/4 一并改。Task 2 后 main.py 里不得残留调用顶层 `USER_DATA_PATH` 的读写路径（`ensure_userdata` 已不再写它）。

- [ ] **Step 5: 旧数据迁移（新增 `legacy_pending` 与 `migrate_legacy_to_account`，置于账号层函数区之后）**

```python
def legacy_pending() -> bool:
    """顶层是否存在「真实旧数据」（评审 A1 锚点，与旧骨架默认值彻底解耦）：
    user_data.yaml 的 targets 非空，或 browser_data/ 非空目录，或 runs/ 非空目录。
    旧版 ensure_userdata 生成的默认骨架（message.texts/schedule.time 非空但 targets 空）
    不算——避免「只设过时间没配过目标」的空壳被误判为 legacy 走无谓迁移。
    （spec 4.1 宽口径在本 plan 收窄为 A1 锚点，保证「迁移后不复发、新装机不误判」不变。）
    """
    ud = USERDATA_DIR / "user_data.yaml"
    if ud.exists():
        try:
            with ud.open("r", encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            if user.get("targets"):
                return True
        except Exception:  # noqa: BLE001
            return True  # 读不了按未迁移保守处理，交给用户
    bd = USERDATA_DIR / "browser_data"
    if bd.is_dir() and any(bd.iterdir()):
        return True
    rd = USERDATA_DIR / "runs"
    if rd.is_dir() and any(rd.iterdir()):
        return True
    return False


def migrate_legacy_to_account(alias: str) -> dict:
    """把旧顶层单账号数据迁入 accounts/<别名>/。幂等可重跑。

    返回 {"ok": bool, "moved": [已迁移项], "failed": [失败项], "error": str|None}。
    已存在同名账号 → error 拒绝；逐项 shutil.move（源存在才移）；失败不中断整体。
    """
    err = validate_alias(alias)
    if err:
        return {"ok": False, "moved": [], "failed": [], "error": err}
    root = account_root(alias)
    if root.exists():
        return {"ok": False, "moved": [], "failed": [],
                "error": f"账号 {alias!r} 已存在，请换名或先手动处理。"}
    root.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    failed: list[str] = []
    pairs = [
        (USERDATA_DIR / "user_data.yaml", root / "user_data.yaml"),
        (USERDATA_DIR / "conversations_cache.json", root / "conversations_cache.json"),
        (USERDATA_DIR / "browser_data", root / "browser_data"),
        (USERDATA_DIR / "runs", root / "runs"),
    ]
    for src, dst in pairs:
        if not src.exists():
            continue
        try:
            shutil.move(str(src), str(dst))
            moved.append(src.name)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{src.name}（{e}）")
    ok = not failed
    return {"ok": ok, "moved": moved, "failed": failed,
            "error": None if ok else ("部分迁移失败，可重跑续迁："
                                      + "; ".join(failed))}
```

- [ ] **Step 6: 跨进程守卫原语（新增；放账号层函数区之后）**

```python
def _pid_alive(pid: int) -> bool:
    """Windows 上探测 pid 是否存活（tasklist /FI）。"""
    try:
        res = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        return str(pid) in res.stdout
    except Exception:  # noqa: BLE001
        return True  # 探测失败保守视为存活，宁可拦下让用户手动处理


def acquire_run_guard(account: str) -> str | None:
    """独占创建 userdata/.running（O_EXCL）。成功返回 None；已被占用返回占用描述
    （含账号+pid），调用方据此报「账号 X（pid Y）正在运行中」并跳过本次。

    陈旧残留自愈：文件已存在且记录的 pid 不存在 → 删除后重试一次（正常路径跑不到
    重试）。调用方保证 finally 中 release_run_guard()。
    """
    data = {"account": account, "pid": os.getpid(), "start_ts": time.time()}
    for attempt in (1, 2):
        try:
            fd = os.open(RUN_GUARD_PATH,
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return None
        except FileExistsError:
            try:
                cur = json.loads(RUN_GUARD_PATH.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                cur = {}
            pid = int(cur.get("pid") or 0)
            if pid and _pid_alive(pid):
                return f"账号 {cur.get('account', '?')}（pid {pid}）正在运行中"
            # 陈旧残留（pid 已不存在）：删除重试
            try:
                RUN_GUARD_PATH.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                return "运行守卫文件无法清理，请手动删除 userdata/.running 后重试"
            continue
        except OSError as e:
            return f"创建运行守卫失败：{e}"
    return "运行守卫被占用且未能清理，请手动检查 userdata/.running"


def release_run_guard() -> None:
    """释放跨进程守卫（finally 中调用）。"""
    try:
        RUN_GUARD_PATH.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
```

> `main.py` 已 import `json/os/subprocess/time`（os 在 `_detect_real_chrome_profile` 内才 import，但 main.py:18-28 已 import json/subprocess/time；os 需在守卫区 `import os` 或顶部补——检查 main.py:18-28 无 os，故在守卫函数文件顶部加 `import os`（模块级））。若顶部已无 os，把 `import os` 加到文件 import 区。

- [ ] **Step 7: 跑一次快速语法/导入自检**

Run: `./.venv/Scripts/python.exe -c "import main; print('ok', main.list_accounts())"`
Expected: 打印 `ok []`（或含现有账号的列表），无异常。再跑 `./.venv/Scripts/python.exe verify.py` → Expected: 旧断言仍绿、MAI 节红（比 Task 1 少一部分失败：ACCOUNTS_ROOT/account_root/validate_alias/load_user_data/守卫等已实现）；仍红的包括 CLI（--account 等）、runner（account=）、panel（_resolve_account/端点/load_config(account)/_find_run_account）、config 注释、panel meta account。**本 Task 不要求全绿**——继续 Task 3。

- [ ] **Step 8: 提交**

```bash
git add main.py && git commit -m "feat(main): 账号层原语+ensure_userdata 收窄+load_config 双入口+跨进程守卫（.running）"
```

---

### Task 3: main.py CLI + runner.py 账号化（--account/--migrate/--list-accounts、任务名、交互选号、runner 透传）

**Files:**
- Modify: `main.py`（CLI argparse、main()、setup_auto/run_once 相关、try_register_task 收 alias、交互模式选号）
- Modify: `runner.py`（解析 --account；trigger_run/轮询带 account）

**Interfaces:**
- Consumes: Task 2 账号层 + `task_name(alias)`（本 Task 内定义）
- Produces: `task_name(alias)`、`resolve_account(flag_alias)` 入口解析、`try_register_task(time_str, alias)`、runner `--account` 透传——Task 4 面板 `create_task` 同款逻辑复用 main 的 `try_register_task` 或自行等价（见 Task 4）。

- [ ] **Step 1: 新增 `task_name` 与入口账号解析（main.py 账号层区追加）**

```python
def task_name(alias: str) -> str:
    """账号的任务名 = 前缀 + 别名（纯 ASCII）。"""
    return "DouyinAutoFire-" + alias


def resolve_account(flag_alias: str | None) -> str:
    """CLI/runner 非交互入口账号解析（spec 4.3/评审拍板④）：

    1) --account 显式 → 用之（不存在则报错列别名 exit 2）；
    2) 未给且恰 1 账号 → 自动沿用（单账号零打扰）；
    3) 未给且多账号 → 报错列别名 exit 2（不默认跑第一个，防串号）；
    4) 未给且 legacy_pending() → 提示先 --migrate，exit 2；
    5) 零账号且无 legacy → 报「请先在面板添加账号或迁移旧数据」，exit 2。
    """
    aliases = list_accounts()
    if flag_alias is not None:
        err = validate_alias(flag_alias)
        if err or flag_alias not in aliases:
            sys.exit(f"账号 {flag_alias!r} 不存在或别名不合法。可用账号：{aliases or '(无)'}")
        return flag_alias
    if len(aliases) == 1:
        return aliases[0]
    if len(aliases) > 1:
        sys.exit(f"存在多个账号（{'、'.join(aliases)}），请用 --account 显式指定要运行的账号。")
    if legacy_pending():
        sys.exit("检测到旧版单账号数据，请先执行：python main.py --migrate <别名> "
                 "或打开面板按迁移引导操作。")
    sys.exit("尚未创建任何账号。请在面板添加账号，或执行 python main.py --migrate <别名> 迁移旧数据。")
```

- [ ] **Step 2: `try_register_task(time_str, alias)`（main.py:198-231 签名改造）**

把函数签名 `def try_register_task(time_str: str) -> bool:` 改为 `def try_register_task(time_str: str, alias: str | None = None) -> bool:`，内部任务名与触发命令：

```python
    tn = task_name(alias) if alias is not None else TASK_NAME
    trigger = f'"{python_exe}" "{runner}" --run-once' \
        + (f' --account "{alias}"' if alias is not None else "")
    cmd = ["schtasks", "/Create", "/TN", tn,
           "/TR", trigger, "/SC", "DAILY", "/ST", time_str, "/F"]
```

> 兼容：alias=None 保留旧单任务名行为（迁移收尾/旧调用）。Task 4 面板 create_task 最终会显式传 alias。

- [ ] **Step 3: `setup_auto/setup_auto_with_messages/run_once_with_messages/interactive` 账号化（main.py:151-281 区）**

要点：
- `setup_auto_with_messages(time_str, texts, alias)`：`update_schedule_time(alias, time_str)`、`update_message_texts(alias, texts)`、`try_register_task(time_str, alias)`。
- `setup_auto(time_str, alias)`：`update_schedule_time(alias, time_str)`、`try_register_task(time_str, alias)`。
- `run_once_with_messages(texts, alias)`：`cfg = load_config(alias)`；同旧逻辑发消息；账号不存在/非法 → 先走 resolve_account。
- 交互模式开头（`interactive(alias=None)`）：若 alias 未给，打印可用账号列表让用户选（`[1] main  [2] backup`），输入序号或直接回车（恰一个时默认）；**零账号出口**——`legacy_pending()` → 提示先 `--migrate <别名>` 或开面板迁移条并 return；无 legacy → 提示先开面板「添加账号」并 return（不复用 resolve_account 的 exit 2，交互模式给提示而非退出）。之后 1/2 菜单不变，把 alias 传进上述函数。
- 手动触发路径也走守卫：`run_once_with_messages` 开头 `holder = acquire_run_guard(alias)`，None 才继续，`finally: release_run_guard()`。

- [ ] **Step 4: `main()` argparse 与分支（main.py:284-324 改造）**

```python
    parser.add_argument("--account", help="指定账号别名（不传且多账号时报错；单账号自动沿用）")
    parser.add_argument("--migrate", metavar="ALIAS", help="迁移旧版单账号数据到新账号目录")
    parser.add_argument("--list-accounts", action="store_true", help="列出所有账号别名")
    args = parser.parse_args()

    if args.list_accounts:
        for a in list_accounts():
            print(a)
        return

    if args.migrate:
        if not legacy_pending():
            print("未检测到旧版单账号数据，无需迁移。")
            return
        res = migrate_legacy_to_account(args.migrate)
        if res["ok"]:
            print(f"迁移完成，已移入账号 {args.migrate!r}：{res['moved']}")
            print("提示：旧定时任务 DouyinAutoFire 可能仍在，请在面板执行"
                  "「同步注册新任务并删除旧任务」，或手动 schtasks /Delete /TN DouyinAutoFire /F")
        else:
            sys.exit(f"迁移未完成：{res['error']}")
        return

    if args.test:
        config = load_config()  # alias=None：只读公开键即可跑测试
        run_test(config)
        return

    # 非 test/非迁移：确定账号（交互会在 interactive 内再让用户选，这里先解析显式/唯一）
    flag_alias = args.account
    if args.time or args.run_once or args.setup_login:
        alias = resolve_account(flag_alias)
        config = load_config(alias)
        setup_logging(config)
        if args.run_once:
            import panel
            texts = (config.get("message") or {}).get("texts", [])
            rid = panel.trigger_run([str(t) for t in texts], headless=None, account=alias)
            ...轮询 _load_meta(rid, alias)...
        if args.setup_login:
            DouyinStreak(config).setup_login()
            return
        if args.time:
            setup_auto(args.time, alias)
            return
    # 无参数或纯交互：账号可空进 interactive（内部选号）
    config = load_config()  # 公开键即可，交互内选号后重载
    setup_logging(config)
    interactive(args.account)
```

> 具体保持与现文件结构一致的最小改动即可；核心是：**所有数据/运行路径先 resolve_account 拿 alias**；`--migrate`/`--list-accounts` 不走账号解析。

- [ ] **Step 5: runner.py 账号化（runner.py:47-99 main() 改造）**

把 `runner.py` 的 main() 中 argv 解析部分替换：

```python
    account = None
    argv = sys.argv[1:]
    run_once = "--run-once" in argv
    if "--account" in argv:
        i = argv.index("--account")
        if i + 1 < len(argv):
            account = argv[i + 1]
    if account is None:
        # 与 main 同规则：单账号自动沿用；多账号/legacy/零账号报错（resolve_account exit 2）
        from main import resolve_account
        try:
            account = resolve_account(None)
        except SystemExit as e:
            _crash(f"账号解析失败: {e}")
            return 2
    ...
    if run_once:
        ric = panel.api_state(account).get("message_texts") or []
        texts = [str(t) for t in ric]
    run_id = panel.trigger_run(texts, headless=None, account=account)
    ...
    meta = panel._load_meta(run_id, account)
```

> 注意：`panel.api_state(account)` 是 Task 4 签名——本 Task 与 Task 4 有耦合。**实现顺序建议**：先做 Task 4 的 panel 数据层/API（worker/trigger_run/路径函数/api_state 收 account），再回头收 runner 的调用处？plan 要求可独立提交——折中：本 Task 只改 runner 的 `--account` 解析与把 account 传给 `trigger_run`，`api_state(account)` 的调用改到 Task 4 落地后本 Task Step 5b 一并提交。故本 Task 拆为两个提交：5a runner 解析 + trigger_run 传参（面板尚未收 account 时传参无害，位置参数小心——Task 4 会定义 `trigger_run(texts, headless=None, account=None)`，加关键字参数 account= 安全）；5b 在 Task 4 完成后回填 api_state(account)/_load_meta(rid, account) 的调用与验证。

- [ ] **Step 6: 跑 verify 确认 RED 收窄**

Run: `./.venv/Scripts/python.exe verify.py`
Expected: MAI 节中 CLI 三条（--account/--migrate/--list-accounts）转绿；runner `--account`/`account=` 转绿；仍红：panel 相关（_resolve_account/端点/load_config(account)/_find_run_account/meta account）、config 注释。

- [ ] **Step 7: 提交**

```bash
git add main.py runner.py && git commit -m "feat(main/runner): CLI 与 runner 账号化（--account/--migrate/--list-accounts，任务名按账号）"
```

---

### Task 4: panel.py 数据层与 API 账号化（路径函数/worker/守卫/新端点/meta.account 反查/缓存重载）

**Files:**
- Modify: `panel.py`（模块级常量与 import；路径/缓存函数；worker/trigger/login/sync；任务函数；api_*；Handler 路由；main()）

**Interfaces:**
- Consumes: Task 2/3 的 main 账号原语；Task 1 断言。
- Produces: Task 1 断言锁定的全部 panel 形态；Task 5 panel.html 依赖的端点契约。

- [ ] **Step 1: 顶部 import 与模块常量（panel.py:41-52、101-114 区）**

把 `from main import (...)` 扩为：

```python
from main import (
    update_schedule_time,
    update_message_texts,
    update_targets,
    load_config as _main_load_config,
    ensure_userdata,
    account_root,
    list_accounts,
    create_account,
    task_name,
    legacy_pending,
    migrate_legacy_to_account,
    acquire_run_guard,
    release_run_guard,
    USERDATA_DIR,
    PANEL_STATE_PATH,
)
```

删掉 panel 自己的 `RUNS_DIR.mkdir(exist_ok=True)`（:102）与模块期 `ensure_userdata()` 保留（收窄后只建 userdata/ 与 accounts/，安全）。`TASK_NAME` 若仍被引用（:104）改名为 `TASK_NAME_PREFIX = "DouyinAutoFire"`；`:539` 的默认参数同步改。

新增模块级：

```python
_current_run_account: str | None = None
```

并把 `panel.py:163` 的模块期缓存初始化从 `_conversations = _load_conversations_cache()` 改为
`_conversations: list[dict] = []`（内存态默认空；多账号下无「当前账号」概念可加载，账号缓存改由
Task 4 Step 7 的 main() 在确定 last_account/唯一账号后按账号加载，切换时由 /api/select 前端流程重载）。

- [ ] **Step 2: 路径/缓存函数账号化（panel.py:139-158、233-325 区）**

把 `_CONV_CACHE_PATH` 用法改为函数参数：`_load_conversations_cache(account)`/`_save_conversations_cache(account)` 内部用 `account_root(account)/"conversations_cache.json"`；`_meta_path/_log_path/_run_dir(run_id, account)` 用 `account_root(account)/"runs"`。`_load_meta(run_id, account)`、`_save_meta(meta)`（meta 含 account，路径从 meta["account"] 推）签名统一为显式 account。`list_runs(account, keep)`/`prune_runs(account, keep, max_delete)` 遍历该账号 runs。`_delete_run(rid, account)`。

新增反查（P2-4）：

```python
def _find_run_account(run_id: str) -> str | None:
    """run_id 全局唯一：遍历账号目录找含该 meta 的账号（只读，不依赖当前账号）。"""
    for a in list_accounts():
        if (account_root(a) / "runs" / f"{run_id}.json").exists():
            return a
    return None
```

- [ ] **Step 3: `load_config(account=None)` 包装与 `_resolve_account`（panel.py:213-219 区 + 新函数）**

```python
def load_config(account: str | None = None) -> dict:
    # 复用 main.load_config(alias)：None=只读公开键（零账号/基础设施安全）
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"找不到配置文件: {CONFIG_PATH}")
    return _main_load_config(account)


def _read_last_account() -> str | None:
    try:
        st = json.loads(PANEL_STATE_PATH.read_text(encoding="utf-8"))
        return st.get("last_account") or None
    except Exception:  # noqa: BLE001
        return None


def _write_last_account(alias: str) -> None:
    try:
        PANEL_STATE_PATH.write_text(
            json.dumps({"last_account": alias}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _resolve_account(params: dict, *, action: bool = False) -> str | None:
    """账号解析统一入口。GET 传 urlparse+parse_qs 结果；POST 传 body。

    显式 account → 用之（不在账号列表则 None）；动作路径(action=True)无 account →
    返回 None 由端点报「请先添加账号/缺少 account」；只读路径允许缺省：
    last_account → 唯一账号 → None（前端空态/首启）。
    """
    acc = (params.get("account") or "").strip()
    if acc:
        return acc if acc in list_accounts() else None
    if action:
        return None
    la = _read_last_account()
    if la in list_accounts():
        return la
    aliases = list_accounts()
    return aliases[0] if len(aliases) == 1 else None
```

- [ ] **Step 4: worker/trigger/login/sync 账号化 + 守卫（panel.py:330-526 区）**

- `_worker(run_id, texts, headless, account)`：
  - 开头守卫已在 trigger_run 获取（见下），worker 内 `cfg = load_config(account)`；截图目录 `str(_run_dir(run_id, account))`；finally 里释放守卫 `release_run_guard()`（与 `_current_run=None` 同一 finally）；写回 `update_message_texts(account, ...)`；`prune_runs(account, 3)`；`_save_meta` 写回含 account。
  - run meta 初始化加 `"account": account`。
- `trigger_run(texts, headless=None, account=None)`：
  - 签名改收 account；`account` 为 None 时（历史 CLI 兼容）先 `_resolve_account({}, action=True)`，仍 None → return None（log 提示）。
  - **守卫**：进入函数先 `guard_err = acquire_run_guard(account)`；非 None → log + return None（调用方拿到 None 报「账号 X 正在运行中」）。守卫在 worker finally 释放（trigger_run 返回后运行在线程里）。
  - 内部进程锁逻辑保留（`_current_run or _login_running` → return None）；`cfg = load_config(account)`；targets 从 cfg。
- `trigger_login(account)`/`_login_worker(account)`、`trigger_sync(account)`/`_sync_worker(account)`：签名收 account；同样 `acquire_run_guard(account)` 进、`release_run_guard()` finally 出（A2：login/sync 窗口也走守卫，避免跨账号两浏览器并存）；cfg=load_config(account)；sync 写 `_save_conversations_cache(account)`；`_conversations` 保持内存态但语义为「当前账号的列表」。
- `trigger_login_reset/trigger_run_reset`：在进程内锁重置基础上**不自动删守卫**（守卫跨进程，pid 探测自愈；若本进程持有则由 finally 释放）。文档注明。

- [ ] **Step 5: 任务函数账号化（panel.py:539-646 区）**

- `query_system_task(name: str | None = None)`：name 为 None 时沿用 `TASK_NAME_PREFIX`（兼容 verify 打桩与旧调用）；否则查 `schtasks /TN <name>`（name 已含前缀，如 `DouyinAutoFire-main`）。
- `create_task(time_str, texts, account)`：
  - 写 `update_schedule_time(account, time_str)`/`update_message_texts(account, texts)`；
  - `tn = task_name(account)`；trigger = `pythonw runner.py --run-once --account <account>`；`/TN tn`；成功 `task: query_system_task(tn)`。
- `change_task(action, account)`：`tn = task_name(account)`；全部 schtasks 调用改用 tn。
- `api_state(account)`：从 `load_config(account)` 读私有键；新增返回 `running_account: _current_run_account`。
- `api_tasks(account)`：`cfg = load_config(account)`；`task = query_system_task(task_name(account))`。
- `api_conversations(account)`：`cfg = load_config(account)`；saved = cfg targets；`list` = 内存（当前账号）`_conversations`。

- [ ] **Step 6: 新端点 + 既有端点按账号（Handler.do_GET/do_POST，panel.py:811-941）**

do_GET：`qs = parse_qs(urlparse(self.path).query)`；`params = {k: v[0] for k, v in qs.items()}`。

```python
            if path == "/api/accounts":
                return self._send_json({
                    "accounts": [{"alias": a,
                                  "has_task": bool((query_system_task(task_name(a)) or {}).get("exists"))}
                                 for a in list_accounts()],
                    "legacy": legacy_pending(),
                    "last_account": _read_last_account(),
                })
            if path == "/api/state":
                acc = _resolve_account(params) or ""
                return self._send_json(api_state(acc) if acc else {
                    "running": _current_run is not None,
                    "current_run": _current_run,
                    "running_account": _current_run_account,
                    "login_running": _login_running,
                    "progress": _current_progress.get("message", "就绪"),
                    "no_account": True,
                })
            if path == "/api/runs":
                acc = _resolve_account(params) or ""
                if not acc:
                    return self._send_json({"runs": [], "no_account": True})
                try:
                    prune_runs(acc, 3)
                except Exception:  # noqa: BLE001
                    pass
                return self._send_json({"runs": list_runs(acc)})
            if path == "/api/conversations":
                acc = _resolve_account(params) or ""
                if not acc:
                    return self._send_json({"syncing": False, "list": [], "saved": [], "no_account": True})
                return self._send_json(api_conversations(acc))
```

runs 明细/截图/截图文件服务：`api_run_detail(run_id)`/`api_run_screenshots(run_id)`/`_send_screenshot(run_id, filename)` 内部先 `acc = _find_run_account(run_id)`，None → 404；路径用 `_run_dir(run_id, acc)`（原路径穿越防护逻辑原样保留，base 换成该账号 run_dir）。

do_POST：先 `body = self._read_body()`；`params = dict(body)`（POST 取 body/query 的 account，plan 定 POST 也接受 query 的 account，简单起见 `_resolve_account({**params}, action=True)`，body 为主）。

```python
            if path == "/api/accounts":
                alias = (body.get("alias") or "").strip()
                err = validate_alias(alias)
                if err:
                    return self._send_json({"error": err}, 400)
                if alias in list_accounts():
                    return self._send_json({"error": f"账号 {alias!r} 已存在。"}, 409)
                create_account(alias)
                _write_last_account(alias)
                return self._send_json({"ok": True, "alias": alias,
                                        "message": f"已创建账号 {alias!r}，请扫码登录。"})
            if path == "/api/migrate":
                alias = (body.get("alias") or "").strip()
                # 守卫占住：迁移期间不允许任何运行/登录/同步（R2）
                if _current_run or _login_running or _sync_running:
                    return self._send_json({"error": "已有运行/登录/同步进行中，请稍后再试。"}, 409)
                res = migrate_legacy_to_account(alias)
                if not res["ok"]:
                    return self._send_json({"error": res["error"] or "迁移失败"}, 400)
                _write_last_account(alias)
                legacy_task = bool((query_system_task() or {}).get("exists"))
                return self._send_json({"ok": True, "moved": res["moved"],
                                        "legacy_task": legacy_task,
                                        "message": "迁移完成。"})
            if path == "/api/tasks/adopt-legacy":
                alias = (body.get("alias") or "").strip()
                if alias not in list_accounts():
                    return self._send_json({"error": f"账号 {alias!r} 不存在。"}, 400)
                ud = load_user_data(alias)  # main 导入
                tm = (ud.get("schedule") or {}).get("time")
                texts = (ud.get("message") or {}).get("texts") or []
                if tm:
                    r = create_task(tm, [str(t) for t in texts], alias)
                    if not r.get("ok"):
                        return self._send_json(r, 400)
                old = query_system_task()  # 旧 DouyinAutoFire
                if old and old.get("exists"):
                    # 删除旧任务（不走 change_task 的账号任务名语义，直接按旧名删，幂等）
                    try:
                        _run_hidden(["schtasks", "/Delete", "/TN", "DouyinAutoFire", "/F"],
                                    encoding="utf-8", timeout=30)
                    except Exception:  # noqa: BLE001
                        pass
                return self._send_json({"ok": True,
                                        "message": "已注册新任务并删除旧任务。"})
```

> `query_system_task()` 无参查旧任务名（兼容 Task 4 Step 5 的 None 语义）；删除旧任务直接 schtasks /Delete，幂等（不存在时 /F 失败忽略）。

既有动作端点补 account：
- `/api/setup-login`：`acc = _resolve_account(body, action=True)`；None → 400「请先添加账号/指定 account」；`trigger_login(acc)`。
- `/api/sync-conversations`、`/api/trigger`、`/api/save-targets`、`/api/save-message`、`/api/tasks`（POST）、`/api/tasks/disable|enable|delete` 同：先解析 action account，再调对应函数并传 account。save-targets 保存前**重读该账号缓存合并**（P2-3）：
  - `_conversations` 内存语义 = 当前账号；保存时把 clean 并入 `_load_conversations_cache(acc)` 结果后 `_save_conversations_cache(acc)` 与内存同步。
- `/api/select`：`POST {alias}` → `_write_last_account(alias)` → ok。前端切号先调它，再刷新；后端无需额外重载（读取路径按 account 现读）。
- `/api/login-reset`、`/api/run-reset`、`/api/shutdown`：不改（全局动作）。

Handler import 区补：`from urllib.parse import urlparse, quote, unquote, parse_qs`（panel.py:32 加 parse_qs）；`from main import validate_alias, load_user_data`（或经 update 命名空间访问——直接 import）。

- [ ] **Step 7: panel main() 启动适配（panel.py:944-970）**

- 读 port：`cfg = load_config()`（None，安全）——已如此，不改。
- `prune_runs(3)` → 逐账号：`for a in list_accounts(): prune_runs(a, 3)`。
- targets 种子（:956-970）改为：若有 `last_account` 或唯一账号，`cfg = load_config(acc)` 种入 `_conversations` 并 `_save_conversations_cache(acc)`；零账号跳过。
- 其余启动不变。

- [ ] **Step 8: 全绿核对（回填 runner 调用）+ 跑 verify**

Run: `./.venv/Scripts/python.exe -c "import panel; print('panel ok')"`（防 import 期崩溃）。
Run: `./.venv/Scripts/python.exe verify.py`
Expected: MAI 节接近全绿（panel 端点/load_config(account)/_find_run_account/meta account 转绿）。仍可能红：config.yaml 注释（Task 5 顺带或本 Task 尾）、panel.html 相关未断言（Task 1 未锁 HTML，若锁了在 Task 5 转绿）。确认 Task 3 Step 5b：把 runner 的 `api_state()` → `api_state(account)`、`_load_meta(rid)` → `_load_meta(rid, account)` 回填（若 Step 5a 已写）。同步改 verify.py:82 若 `aliases=[]` 分支用了 `panel.query_system_task()` 无参——`query_system_task(None)` 兼容旧任务名，OK。

- [ ] **Step 9: 提交**

```bash
git add panel.py runner.py && git commit -m "feat(panel): 面板数据层/API 账号化+守卫+账号迁移收尾端点（meta.account 反查）"
```

---

### Task 5: panel.html 账号栏/迁移引导/空态/fetch 封装（UI）

**Files:**
- Modify: `panel.html`（header 下新增账号栏区；容器顶迁移引导条；空态；JS fetch 封装与切号刷新）

**Interfaces:**
- Consumes: Task 4 端点（/api/accounts、/api/migrate、/api/tasks/adopt-legacy、/api/select；其余端点 account 参数）
- Produces: 前端完整交互（spec 4.5）。verify 不锁 HTML（仓库先例），GREEN 靠真实面板人工冒烟 + verify 其余绿。

- [ ] **Step 1: header 之后插入账号栏 HTML（panel.html:257 header 结束 `</header>` 之后）**

```html
<!-- 账号栏（MAI-001）：当前账号下拉 + 运行中徽标；空态/迁移引导由此驱动 -->
<div class="account-bar" style="display:none;padding:8px 24px;border-bottom:1px solid var(--line);background:rgba(15,23,42,.55);align-items:center;gap:10px;flex-wrap:wrap">
  <label style="font-size:13px;color:var(--muted)">当前账号</label>
  <select id="accountSelect" style="background:var(--surface);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:6px 10px;font-size:14px"></select>
  <span id="runBadge" class="badge run" style="display:none"></span>
  <button id="addAccountBtn" class="btn ghost sm">＋ 添加账号</button>
  <span id="accountHint" class="muted" style="font-size:12px"></span>
</div>
<!-- 迁移引导条：仅 legacy=true 显示 -->
<div id="migrateBanner" style="display:none;padding:12px 24px;border-bottom:1px solid var(--line);background:rgba(245,158,11,.12);align-items:center;gap:10px;flex-wrap:wrap">
  <span>检测到旧版单账号数据，请为它命名以启用多账号：</span>
  <input id="migrateAlias" type="text" placeholder="如 main" style="background:var(--surface);color:var(--txt);border:1px solid var(--line);border-radius:8px;padding:6px 10px" />
  <button id="migrateBtn" class="btn">开始迁移</button>
  <span id="migrateAdoptWrap" style="display:none">
    <button id="adoptLegacyBtn" class="btn">同步注册新任务并删除旧任务</button>
  </span>
</div>
```

> 单账号且无 legacy 时由 JS 隐藏整个 `.account-bar`（spec 4.5：仅一个账号且无 legacy 时隐藏下拉，但保留「＋ 添加账号」入口——取舍：只有一个账号时仍显示账号栏但隐藏下拉与标签，仅保留添加按钮与徽标；实现按 spec 文字：下拉隐藏指 select 隐藏，account-bar 保留以容纳添加按钮）。

- [ ] **Step 2: JS 顶部加状态与 fetch 封装（panel.html script 开头区）**

```javascript
let activeAccount = null;         // 当前账号（null=零账号空态）
let hasLegacy = false;
const qs = (obj) => Object.keys(obj).map(k => encodeURIComponent(k) + "=" + encodeURIComponent(obj[k])).join("&");
async function api(path, opts = {}) {
  opts = opts || {};
  const method = opts.method || "GET";
  let url = path;
  const payload = Object.assign({}, opts.body || {});
  if (activeAccount) {
    if (method === "GET") url += (url.includes("?") ? "&" : "?") + qs({account: activeAccount});
    else payload.account = activeAccount;
  }
  const init = {method, headers: {"Content-Type": "application/json"}};
  if (method !== "GET") init.body = JSON.stringify(payload);
  const r = await fetch(url, init);
  const j = await r.json().catch(() => ({}));
  return {ok: r.ok, j};
}
```

- [ ] **Step 3: 账号加载/渲染/切号/添加/迁移/收尾函数（JS，插在 tab 切换之后）**

```javascript
async function loadAccounts() {
  // /api/accounts 是全局首启/轮询端点，不带 account 参数（封装在 activeAccount 为空时也不带）
  const {j} = await api("/api/accounts", {method: "GET"});
  hasLegacy = !!j.legacy;
  const accs = j.accounts || [];
  const sel = $("#accountSelect");
  sel.innerHTML = "";
  accs.forEach(a => {
    const o = document.createElement("option");
    o.value = a.alias; o.textContent = a.alias + (a.has_task ? "" : "（未设任务）");
    sel.appendChild(o);
  });
  const target = j.last_account && accs.some(a => a.alias === j.last_account)
    ? j.last_account : (accs[0] ? accs[0].alias : null);
  setActiveAccount(target, accs);
  renderAccountBarState(accs);
  renderMigrateBanner();
  renderEmptyState(accs);
}
function setActiveAccount(alias, accs, keepCurrentTab = true) {
  const changed = alias !== activeAccount;
  activeAccount = alias;
  if (alias) fetch("/api/select", {method: "POST", headers: {"Content-Type": "application/json"},
                                   body: JSON.stringify({alias})}).catch(() => {});
  if (changed) {
    // P2-3：切号即换数据源；后端按 account 现读账号缓存，前端重置内存态并全量刷新当前页签
    convCache = []; convSavedMap = {};
    loadConversations();
    loadRunsSilent();
    if ($("#tab-tasks").classList.contains("active")) loadTasks();
    refreshStatus();
  }
}
function renderAccountBarState(accs) {
  const bar = document.querySelector(".account-bar");
  const sel = $("#accountSelect");
  if (!bar) return;
  if (activeAccount) sel.value = activeAccount;
  // ≥1 账号或 legacy 时显示账号栏（容纳添加入口）；纯零账号空态由 renderEmptyState 接管
  bar.style.display = (accs.length || hasLegacy) ? "flex" : "none";
  // 仅一个账号且无 legacy：隐藏下拉（spec 4.5），保留添加按钮
  sel.style.display = (accs.length > 1 || (accs.length === 1 && hasLegacy)) ? "" : "none";
}
function renderEmptyState(accs) {
  const es = $("#emptyState");
  if (es) es.style.display = (!accs.length && !hasLegacy) ? "flex" : "none";
}
function renderMigrateBanner() {
  const b = $("#migrateBanner");
  if (b) b.style.display = hasLegacy ? "flex" : "none";
}
```

> 触发按钮运行中置灰需跨账号（spec 4.4）：refreshStatus 里若 `s.running_account && s.running_account !== activeAccount` → 触发/同步/保存/登录按钮置灰并显示「账号 <X> 正在运行中」到 accountHint/statusPill。在 refreshStatus() 内补充该分支。

- [ ] **Step 4: 事件绑定（加在既有 `$("#triggerBtn").onclick = doTrigger;` 区附近）**

```javascript
$("#accountSelect").onchange = (e) => {
  if (e.target.value) setActiveAccount(e.target.value, null);
};
$("#addAccountBtn").onclick = async () => {
  const alias = prompt("新账号别名（1~24 个英文/数字/下划线）：", "").trim();
  if (!alias) return;
  const {ok, j} = await api("/api/accounts", {method: "POST", body: {alias}});
  if (!ok) { toast(j.error || "添加失败", "err"); return; }
  toast(j.message || "已添加账号", "ok");
  await loadAccounts();
  if (activeAccount) { $("#accountSelect").value = activeAccount; }
  // 引导扫码：点开「打开浏览器」等价动作
  $("#loginBtn").click();
};
$("#migrateBtn").onclick = async () => {
  const alias = $("#migrateAlias").value.trim();
  if (!alias) { toast("请输入别名", "err"); return; }
  const {ok, j} = await api("/api/migrate", {method: "POST", body: {alias}});
  if (!ok) { toast(j.error || "迁移失败", "err"); return; }
  toast("迁移完成 ✅", "ok");
  if (j.legacy_task) $("#migrateAdoptWrap").style.display = "";
  else { hasLegacy = false; renderMigrateBanner(); }
  await loadAccounts();
};
$("#adoptLegacyBtn").onclick = async () => {
  if (!confirm("将用当前迁移账号的时间/内容注册新任务，并删除旧任务 DouyinAutoFire。继续？")) return;
  const {ok, j} = await api("/api/tasks/adopt-legacy", {method: "POST", body: {alias: activeAccount}});
  if (!ok) { toast(j.error || "收尾失败", "err"); return; }
  toast("已注册新任务并删除旧任务 ✅", "ok");
  hasLegacy = false; renderMigrateBanner();
  if ($("#tab-tasks").classList.contains("active")) loadTasks();
};
```

- [ ] **Step 5: 既有 fetch 全部改走 api() 封装（或逐处带 account）**

改造点（panel.html 内既有 fetch 列表，逐一替换为 `api(...)` 并适配返回 `{ok,j}` 或 GET 的 `j`）：
- `refreshStatus` 的 `/api/state` → `api("/api/state")`；取 `j`；处理 `j.no_account` → 显示空态/提示添加。
- `doTrigger`、save-message、setup-login、login-reset、run-reset、sync-conversations、save-targets、tasks GET/POST、tasks disable/enable/delete、runs 列表/详情/截图、conversations：全部带 activeAccount（封装自动带）；`loadRuns/showDetail/loadScreenshots` 的 `/api/runs/<id>` 由后端 meta.account 反查，无需 account（封装仍带无害——端点忽略多余 query 的 account 或接受）。
- **触发按钮 disabled 条件**在 refreshStatus 里同步（若运行中账号 ≠ 当前账号仍置灰，文案「账号 X 正在运行中」）。
- 初始化改为先 `loadAccounts()` 再进入既有 refreshStatus/loadConversations 序列；`setInterval(refreshStatus, 5000)` 保留。

空态 HTML（零账号且无 legacy，.account-bar 隐藏时容器内显示）：

```html
<div id="emptyState" style="display:none;min-height:40vh;align-items:center;justify-content:center;text-align:center">
  <div class="card" style="max-width:520px">
    <h3>添加第一个账号</h3>
    <p class="muted">多账号模式下每个抖音号一个独立目录与登录态。点击上方「＋ 添加账号」开始，随后扫码登录。</p>
  </div>
</div>
```

JS：`loadAccounts` 后若 `!accs.length && !hasLegacy` → 显示 emptyState、隐藏三页签容器与账号栏；否则相反。执行细节以保持现状布局不破坏为准。

- [ ] **Step 6: 浏览器人工冒烟（无抖音真实操作）**

启动面板 `./.venv/Scripts/python.exe panel.py`，浏览器开 `http://127.0.0.1:8765` 人工核对：账号栏渲染、切号联动、迁移条显隐（可通过临时 `legacy_pending()` 真实值核对；真实迁移留用户）。**agent 不执行真实迁移/扫码**。无代码改动则无需提交。

- [ ] **Step 7: 跑 verify + 提交**

Run: `./.venv/Scripts/python.exe verify.py`
Expected: MAI 节全绿、失败 0、exit 0（若 Task 5 未锁 HTML，verify 应已在 Task 4 全绿——GREEN 以 Task 6 汇总为准，此处确认无回退）。
Run: `git diff --stat`（应恰好本 Task 涉及文件）。

```bash
git add panel.html && git commit -m "feat(panel): 面板账号栏/迁移引导/空态/fetch 账号化（三块数据随账号联动）"
```

---

### Task 6: 收尾 GREEN（config.yaml 注释 / 示例 / 文档同步）+ verify 全绿

**Files:**
- Modify: `config.yaml`、`user_data.yaml.example`、`README.md`、`docs/配置参考.md`、`docs/管理面板使用指南.md`、`docs/命令行与定时任务.md`、`docs/工作原理与架构.md`
- Modify（如残留）: `verify.py`（仅当 Task 1-5 后有断言措辞需对齐——禁止为过测试而放宽断言）

**Interfaces:**
- Consumes: Task 2-5 后真实语义。
- Produces: 文档与代码一致；verify 全绿 exit 0；`git status` 干净（error.log 为历史遗留 untracked，记录在案不提交）。

- [ ] **Step 1: config.yaml 注释（值不动）**

`config.yaml:10-11`：

```yaml
  # 浏览器数据目录：多账号下此键由账号层覆盖（实际 = userdata/accounts/<别名>/browser_data）。
  # 此处仅作旧版单账号兜底/示例值，多账号下无需修改。
  user_data_dir: "./userdata/browser_data"
```

`config.yaml:25-28` real_chrome_profile 注释段追加：

```yaml
  # ⚠️ 多账号目录隔离（MAI-001）：real_chrome_profile 必须保持 false。
  #    为 true 时登录态会指向真实 Chrome 目录、绕过账号隔离，两个账号会共用同一份登录态（串号）。
  real_chrome_profile: false
```

- [ ] **Step 2: user_data.yaml.example 头部说明**

文件头注释追加：

```text
# 多账号（v2）：私有配置位于 userdata/accounts/<别名>/user_data.yaml（面板「添加账号」/迁移自动生成）。
# 本模板保留为结构与字段参考；顶层 user_data.yaml 不再使用。
```

- [ ] **Step 3: README.md**

- 目录结构（README.md:33-39 附近）加 `userdata/accounts/<别名>/` 与 `.running` 说明行。
- 「核心特性」加多账号条目。
- 快速开始补「添加第二个账号/切换账号」一小节（引用 docs/管理面板使用指南.md 的账号一节）。
- 配置段落补 real_chrome_profile 多账号警告（README.md 若提及浏览器配置）。

- [ ] **Step 4: docs/配置参考.md**

- 私有数据章节改为账号目录布局表（accounts/<别名>/ 下四类数据）。
- user_data_dir 语义行更新（账号层覆盖）。
- real_chrome_profile 表行加「多账号下必须 false」警告。

- [ ] **Step 5: docs/管理面板使用指南.md**

- 新增「账号」一节：账号栏位置/切换/添加/迁移引导/每账号三块数据（会话、发送内容、执行记录、定时任务）；「同步注册新任务并删除旧任务」收尾按钮；空态引导。
- 执行记录按账号说明（runs 明细/截图按账号目录；切号即换数据源）。

- [ ] **Step 6: docs/命令行与定时任务.md**

- `--account <别名>` / `--migrate <别名>` / `--list-accounts` 说明与示例。
- 任务名 `DouyinAutoFire-<别名>`：每账号一条、错峰建议（≥15 分钟）。
- 启用/禁用/删除按账号；旧任务 `DouyinAutoFire` 迁移收尾说明。

- [ ] **Step 7: docs/工作原理与架构.md**

- 模块职责加账号层（main.py 账号原语/守卫、runner 透传、panel 账号解析）。
- 单次运行数据流补账号解析步骤。
- 目录布局图含 accounts/ 与 .running。
- 执行纪律段改写「进程内锁 + 跨进程守卫（.running）」。

- [ ] **Step 8: 全库残留扫 + verify 全绿**

Run: `./.venv/Scripts/python.exe verify.py` → Expected: 失败 0、exit 0。
Run: `git diff --stat` → 恰好上述 7 个文件（verify.py 若已无改动则不出现）。
Run: `grep -rn "顶层 user_data.yaml 仍在使用\|账号A\|真实会话名" README.md docs/ user_data.yaml.example` → 预期无真实隐私内容。

- [ ] **Step 9: 提交（文档与代码分开提交）**

```bash
git add config.yaml user_data.yaml.example README.md docs/配置参考.md docs/管理面板使用指南.md docs/命令行与定时任务.md docs/工作原理与架构.md
git commit -m "docs: 多账号目录隔离文档同步（配置注释/示例/README/五份 docs）"
```

---

### Task 7: 收尾交付（真实操作由用户执行，agent 不触碰真实 userdata）

**触发条件：** Task 6 全绿、Plan 已签字、评审/测试通过后，作为交付物给用户的人工核对清单（不写代码）。agent 交付以下核对清单文本（进聊天/交付说明，不进 git）：

1. 启动面板 → 若曾用旧版：顶部出现迁移引导条 → 输入别名（如 `main`）→「开始迁移」→ 若提示旧任务存在 → 点「同步注册新任务并删除旧任务」（注册 `DouyinAutoFire-main` 并删除 `DouyinAutoFire`）。
2. 全新装/迁移后：点「＋ 添加账号」→ 输别名（如 `backup`）→ 弹浏览器扫码登录第一个号；切到第二账号重复扫码。
3. 一键同步两个号各自的会话，分别勾选保存 targets；填各号发送内容并保存。
4. 定时任务页分别设置两个号的时间（错峰 ≥15 分钟，如 21:00 / 21:30）。
5. 前台触发一次任一号，核对执行记录/截图/会话与账号对应（防串号目测）。
6. 次日核对两号各自按设定时间完成发送、执行记录都在各自账号目录 `userdata/accounts/<别名>/runs/`。

**验收标准（本次任务 DONE 的最终闸）：** Reviewer APPROVED（reviews/MAI-001-plan-review.md 与代码评审）+ Tester PASS（test-results/ 文件含 verify 全绿命令输出）+ 用户已签 plan + status MAI-001 state=DONE + git 干净（error.log 历史遗留除外）。

---

## 验证总览

| Task | 命令 | 期望 |
|---|---|---|
| 1 | `verify.py` | RED：MAI 断言批量失败、旧断言绿、无 traceback |
| 2 | `verify.py` + `python -c "import main; print(main.list_accounts())"` | MAI 红收窄（账号原语绿）；import 无异常 |
| 3 | `verify.py` | CLI/runner 断言转绿；panel 断言仍红 |
| 4 | `verify.py` + `python -c "import panel"` | MAI 近全绿；import 无异常 |
| 5 | 面板人工冒烟 + `verify.py` | UI 交互正确；verify 不回退 |
| 6 | `verify.py` + `git diff --stat` | 失败 0、exit 0；恰好 7 文档文件 |
| 7 | 人工核对清单（用户执行） | 见 Task 7 清单 |

## 风险与已知边界（plan 补充，从 spec 继承）

- **单账号旧任务自动沿用 vs 多账号报错**：入口解析（resolve_account）是唯一允许「唯一账号兜底」的地方；数据函数无默认。verify 断言锁定数据函数收 alias，防止回归。
- **守卫与既有「面板进程内锁」的关系**：进程内锁管同面板并发（状态置灰），守卫管跨进程（runner/面板/手动）。login/sync 也走守卫（A2 采纳）——扫码期用户在场，跨账号浏览器并存的边界已消除。
- **RED 阶段第 3 节**：账号层未实现时退回旧单任务名探测，避免 AttributeError 崩溃（评审 5.2 底线）。
- **验证免责（spec 六-3 继承）**：真实迁移、双号扫码、错峰定时、次日发送无法自动化，verify 只锁代码结构；收尾以 Task 7 人工核对清单交付。别名已 ASCII 化，无中文任务名兼容性探针需求。
