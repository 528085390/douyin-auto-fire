# 一键出发：全账号串行批量执行（号间强制错峰）— 实施计划（plan）

- 日期：2026-09-08
- Task-ID：BAT-001
- 状态：待用户签字（2026-09-08 Reviewer 第三轮 APPROVED，`reviews/BAT-001-plan-review.md`；签字后方可 IMPLEMENT）
- 依赖的 approved spec：`docs/superpowers/specs/2026-09-08-one-click-batch-all-accounts-design.md`
  （2026-09-08 Reviewer 两轮评审 APPROVED，`reviews/BAT-001-spec-review.md`；spec 免签生效）

---

## 一、目标与验收

按 spec 三章目标逐条实现：面板首页「一键出发」→ 全部已添加账号顺次跑各自私聊任务
（各号已保存文案/目标），号间结束→启动强制错峰 15 分钟；独立子进程执行器
`batch_runner.py`；进度横幅全程可见；防双发 / 可取消；verify.py RED→GREEN。

验收标准（全绿条件）：

1. verify.py：RED 阶段 FAIL = 既有 2 + 新增 16 = **18**；GREEN 阶段仅剩既有 2 FAIL
   （账号任务注册的环境态，见遗留）。
2. 单元级冒烟（打桩，不动真实浏览器）通过，留 `test-results/` 证据。
3. 功能级冒烟待用户授权（见十一-1），用 `--stagger-minutes 1`。
4. 文档同步（spec 4.6）完成；隐私扫描 0 命中；提交粒度按任务分。

---

## 二、任务拆分与提交

| Task | 内容 | 提交（中文 conventional） |
|---|---|---|
| 1 | verify.py 新增 16 条防回归断言（先 RED） | `test(verify): BAT-001 RED 16 条防回归断言（期望 18 FAIL=既有 2+新增 16）` |
| 2 | 新建 batch_runner.py 批量执行器 | `feat(batch): BAT-001 一键出发批量执行器（串行+错峰15分钟+防双发+取消+陈旧守卫自愈）` |
| 3 | panel.py：/api/trigger-all、/api/batch-state、/api/batch-cancel + 批量期单号动作拒绝 | `feat(panel): BAT-001 一键出发 API 三端点 + 批量期单号动作拒绝` |
| 4 | panel.html：一键出发按钮 + 批量进度横幅 + busy 置灰扩展 | `feat(panel): BAT-001 一键出发按钮与批量进度横幅` |
| 5 | verify 转 GREEN + 单元级冒烟（打桩） | `test(verify): BAT-001 GREEN 全绿（仅剩既有 2 FAIL）+ 单元冒烟证据` |
| 6 | 文档同步（spec 4.6 两文件）+ status 推进 | `docs: BAT-001 文档同步（一键出发指南 + 架构 batch_runner）` |

代码与文档分开提交。全程直接提交 main（仓库惯例）。

---

## 三、Task 1 — RED 断言（verify.py，先 RED 后 GREEN）

在 verify.py「★SIV-002」断言块（现位于 douyin.py 面板块尾部、verify.py:357-366，
以实际 grep 定位为准）之后、汇总节之前新增。**关键（评审 P1-F1）**：verify.py 的
`read()`（:43-44，`(BASE / name).read_bytes()`）对缺文件**无容错**、全文件无兜底
try/except——RED 态下 batch_runner.py 尚不存在，必须加存在性守卫：
`b = read("batch_runner.py") if (BASE / "batch_runner.py").exists() else ""`。
**关键（评审 P1-F2）**：verify.py 里 `h` 从不是 panel.html（:143/149/155 是
`panel.api_tasks("main")["health"]` 健康字典），HTML 断言一律内联 `read("panel.html")`。
16 条，逐条锁定语义与源码 token：

```python
# ★ BAT-001 一键出发：全账号串行批量（2026-09-08 spec，独立执行器 batch_runner.py）
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
check("★BAT-001 状态文件原子写", 'os.replace(' in b and "batch_state.json" in b)
check("★BAT-001 等待/错峰状态机 token", "waiting_stagger" in b and "waiting_guard" in b)
check("★BAT-001 陈旧守卫 pid 感知自愈(P1-F1)", "def _stale_guard_cleanup" in b)
check("★BAT-001 防双发读最近 run(keep=1)", "list_runs(acc, keep=1)" in b)
check("★BAT-001 各号已存文案 api_state(acc)", "api_state(acc)" in b)
check("★BAT-001 触发与轮询复用 panel 链路", "panel.trigger_run(" in b and "panel._load_meta(" in b)
check("★BAT-001 前端一键出发按钮与横幅",
      "一键出发" in read("panel.html") and "loadBatchState" in read("panel.html"))
```

（16 条 = spec 4.5 的 12 条意图按「一意图可拆多 token」细化展开；计数以本 plan 为准，
spec 的「约 12 条」为意图级估计。）

断言语义自查（提交 RED 前必做，仓库仲裁：断言为准绳，不许改断言迁就实现）：
- RED 态下 16 个 token 在 panel.py / panel.html / 磁盘均应 0 命中、batch_runner.py 不存在
  ——本轮已实测（评审第二轮「已核实安全」#15 同源）；Task 2-4 实现时逐字按本 plan
  写实现，GREEN 失败即对照断言修实现措辞。
- 注意「一键出发」与既有「一键触发」「一键同步」（panel.html:304/336/338）不同串，
  互不干扰。

RED 期望：**18 FAIL = 既有 2 + 新增 16**（基线 2026-09-08 实测 105 通过 / 2 失败）。

---

## 四、Task 2 — batch_runner.py（新文件，根目录，与 runner.py 并列）

### 4.1 模块骨架

```python
"""一键出发批量执行器（BAT-001 spec 4.2，独立进程，与面板生命周期解耦）。

用法（由面板 /api/trigger-all 经 pythonw 拉起，也可手动 CLI 调试）：
    python batch_runner.py --batch-all [--stagger-minutes N]
    --stagger-minutes 默认 15（spec 拍板错峰下限）；显式传更小值仅供测试/演示，
    面板启动路径固定不传该参数。执行进度写 userdata/batch_state.json（原子写），
    面板轮询渲染；本进程退出不影响已排队列继续执行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

# 守卫/账号工具与 runner.py 同源（runner.py 先例：独立进程 import 模块复用）
from main import (ensure_userdata, USERDATA_DIR, RUN_GUARD_PATH,
                  _pid_alive, list_accounts, account_root)  # noqa: E402
import panel  # noqa: E402  （trigger_run / api_state / list_runs / _load_meta / load_config）

ensure_userdata()
CRASH_LOG = USERDATA_DIR / "run.log"
BATCH_STATE_PATH = USERDATA_DIR / "batch_state.json"

def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```

### 4.2 原子状态写（两写方约定：先读最新 → 只改自己字段 → tmp + os.replace）

```python
def _read_state() -> dict | None:
    try:
        return json.loads(BATCH_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None

def _write_state(st: dict) -> None:
    """原子写：tmp + os.replace，杜绝面板读到半截 JSON（spec 4.2 两写方约定）。"""
    # 唯一 tmp（评审 P2-F7）：两写方（执行器/面板取消）共用同名 tmp 会互相
    # os.replace 掉对方文件 → lost-update 另一入口。tmp 带 pid 后缀。
    tmp = Path(str(BATCH_STATE_PATH) + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, BATCH_STATE_PATH)
```

### 4.3 陈旧守卫 pid 感知自愈（spec 4.2-② / 评审 P1-F1）

```python
def _stale_guard_cleanup() -> bool:
    """守卫文件在但持有 pid 已死 → 删残留。返回是否清理（供外层立即重试）。

    既有自愈（main.acquire_run_guard）只在创建尝试时触发；执行器被动等待期
    无人 acquire，不主动清就会永久 waiting_guard（评审 P1-F1）。
    """
    try:
        raw = RUN_GUARD_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    try:
        pid = int(json.loads(raw).get("pid") or 0)
    except Exception:
        return False  # 解析失败不擅动，交给 acquire 自愈
    if pid and not _pid_alive(pid):
        # 复读确认仍为同一死 pid 才删（评审 P2-F6）：避免毫秒窗口内另一路触发
        # 已对同一陈旧文件做 acquire 自愈重建（活守卫）后被本方误删。
        try:
            cur2 = json.loads(RUN_GUARD_PATH.read_text(encoding="utf-8"))
        except Exception:
            return False
        if int(cur2.get("pid") or 0) != pid:
            return False
        try:
            RUN_GUARD_PATH.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        return True   # 外层守卫等待循环回到循环头重探测；若文件再现且 pid 活 → 正常等待
    return False
```

### 4.4 单号执行（核心状态机，每号一次）

```python
def _execute_account(st, acc: str, stagger_minutes: int) -> None:
    """按 spec 4.2 逐号流程：预检 → 守卫等待 → 错峰等待 → 防双发 → 触发 → 轮询收尾。
    任何单号异常只落该号 error，不中断整批。"""
    item = st["items"].setdefault(acc, {"status": "pending", "reason": None})
    # ① 预检（跳过项不占错峰等待，无浏览器动作）
    if acc not in list_accounts():
        item.update(status="skipped", reason="账号不存在"); return
    try:
        cfg = panel.load_config(acc)
    except Exception as e:
        item.update(status="error", reason=f"读取账号配置失败: {e}"); return
    texts = [str(t) for t in (cfg.get("message") or {}).get("texts", [])]
    targets = (cfg.get("targets") or [])
    if not texts:
        item.update(status="skipped", reason="未保存内容，请先为该号保存文案"); return
    if not targets:
        item.update(status="skipped", reason="未配置目标会话"); return
    bdir = account_root(acc) / "browser_data"
    if not bdir.is_dir():
        item.update(status="skipped", reason="尚未登录，请先为该号扫码登录"); return
    # ② 守卫等待（pid 感知；取消以磁盘为准——评审 P2-F3）
    while True:
        st = _read_state() or st          # 每次 wake 重读，cancel 不信任内存副本
        item = st["items"][acc]
        if st.get("cancel_requested"):
            item.update(status="skipped", reason="用户取消"); _write_state(st); return
        if not RUN_GUARD_PATH.exists():
            break
        if _stale_guard_cleanup():
            continue                       # 删残留后回循环头重探测（F6 外层复查）
        item.update(status="waiting_guard", reason=None)
        _write_state(st); time.sleep(5)
    ...
```

（第 ③ 步错峰、④ 防双发、⑤ 触发、⑥ 轮询接续如下，关键行与 token 齐全；GREEN
失败以断言为准绳微调措辞。）

### 4.5 错峰与防双发（③④，token 对齐断言 8/13）

```python
    # ③ 错峰等待：上一号实际运行 end + stagger 分钟起算（stagger 默认 15；
    #    功能冒烟用 --stagger-minutes 1 覆盖，故基准必须用参数而非写死 15）；首号
    #    取下限 max(now, 本号最近 run end + stagger)（评审 P2-F3）。
    prev_end = st.get("_prev_run_end")          # 上一号实际运行的 meta.end
    base = prev_end or None
    if base is None:
        latest = panel.list_runs(acc, keep=1)    # 防双发同源读取
        if latest and latest[0].get("end"):
            base = latest[0]["end"]
    if base:
        base_dt = datetime.strptime(str(base), "%Y-%m-%d %H:%M:%S")
        nxt = base_dt + timedelta(minutes=stagger_minutes)
        while datetime.now() < nxt:
            st = _read_state() or st             # 取消以磁盘为准（评审 P2-F3）
            item = st["items"][acc]
            if st.get("cancel_requested"):
                item.update(status="skipped", reason="用户取消"); _write_state(st); return
            item.update(status="waiting_stagger",
                        next_start_at=nxt.strftime("%Y-%m-%d %H:%M:%S"))
            _write_state(st); time.sleep(5)
    # ④ 防双发复查：本批量 started_at 后该号已被执行过（定时/手动抢先）→ 跳过
    latest = panel.list_runs(acc, keep=1)
    if latest and latest[0].get("end") and st.get("started_at") and \
            str(latest[0]["end"]) >= str(st["started_at"]):
        item.update(status="skipped", reason="本批量开始后已执行过，防同号双发")
        _write_state(st); return
```

### 4.6 触发与轮询（⑤⑥，token 对齐断言 14/15）

```python
    # ⑤ 触发：各号已保存文案，headless=None 走该号 config（同 runner.py 语义）。
    #    trigger_run 返回 None = 守卫被占/内部繁忙 → 回守卫等待语义重试（上限 3 次），
    #    而非原地空等 15s 后误报 error（评审 P2-F5）。
    item.update(status="running", run_id=None, reason=None)
    _write_state(st)
    run_id = None
    for attempt in (1, 2, 3):
        st = _read_state() or st
        item = st["items"][acc]
        if st.get("cancel_requested"):
            item.update(status="skipped", reason="用户取消"); _write_state(st); return
        if RUN_GUARD_PATH.exists() and not _stale_guard_cleanup():
            item.update(status="waiting_guard", reason=None)
            _write_state(st); time.sleep(5)
            continue
        run_id = panel.trigger_run(
            panel.api_state(acc).get("message_texts") or texts,
            headless=None, account=acc)
        if run_id:
            break
        time.sleep(5)
    if not run_id:
        item.update(status="error",
                    reason="触发被拒（守卫被占/内部繁忙，重试 3 次后放弃）")
        _write_state(st); return
    item.update(run_id=run_id)
    # ⑥ 轮询 run meta 至非 running（每 ~3s；运行中号自然收尾，不中途杀浏览器）。
    #    15 分钟 deadline 兜底（镜像 runner.py:101-111）：meta 异常卡 running 时
    #    不拖死整批（评审 P2-F8）。取消由 run_batch 逐号读磁盘 cancel 实现：
    #    本号收尾后自然停整批，无需 _cancel_after_run 死赋值。
    deadline = time.time() + 15 * 60
    while True:
        meta = panel._load_meta(run_id, acc)
        if meta and meta.get("status") != "running":
            break
        if time.time() > deadline:
            _crash(f"[BATCH] 账号 {acc} run {run_id} 超过 15 分钟仍未结束，记 error 继续下一号。")
            break
        time.sleep(3)
    meta = panel._load_meta(run_id, acc) or {}
    status = meta.get("status", "error")
    if status == "running":                        # 超时兜底
        status = "error"
        meta = {**meta, "end": _now_iso(), "error": "运行超时（>15 分钟未结束）"}
    # ⑦ 单号收尾显式原子落盘（评审 P2-F4）：不落盘则末号永久 running、
    #    后序号从磁盘读不到 _prev_run_end → 号间错峰基准丢失。
    item = (_read_state() or {}).get("items", {}).get(acc, item)
    item.update(status=status, end=meta.get("end"),
                failed_targets=list(meta.get("failed_targets") or []),
                error=meta.get("error"))
    st = _read_state() or st
    st["items"][acc] = item
    st["_prev_run_end"] = meta.get("end") or _now_iso()   # 下一号错峰基准
    _write_state(st)
```

### 4.7 run_batch 主循环 + main

```python
def run_batch(stagger_minutes: int) -> int:
    st = _read_state() or {}
    accounts = [a for a in (st.get("items") or {}).keys()]  # 启动快照顺序
    for acc in list(accounts):
        if _read_state().get("cancel_requested"):
            break
        _execute_account(_read_state() or st, acc, stagger_minutes)
    st = _read_state() or st
    if st.get("cancel_requested"):
        st["phase"] = "cancelled"
        for it in st.get("items", {}).values():
            if it.get("status") in ("pending", "waiting_guard", "waiting_stagger"):
                it.update(status="skipped", reason="用户取消")
    else:
        st["phase"] = "finished"
    st["finished_at"] = _now_iso()
    _write_state(st)
    return 0

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="一键出发批量执行器（BAT-001）")
    parser.add_argument("--batch-all", action="store_true", help="跑全部已添加账号")
    parser.add_argument("--stagger-minutes", type=int, default=15,
                        help="号间错峰分钟数（默认 15；仅测试/演示可传更小值）")
    args = parser.parse_args(argv)
    # 独占建档（O_EXCL，同守卫模式）；已激活且 pid 存活 → 拒绝
    ...
    accounts = list_accounts()
    st = {"pid": os.getpid(), "started_at": _now_iso(),
          "stagger_minutes": args.stagger_minutes, "accounts": accounts,
          "cancel_requested": False, "phase": "running",
          "finished_at": None, "crashed": False,
          "items": {a: {"status": "pending", "reason": None} for a in accounts}}
    写入 state（O_EXCL 独占，已存在且 pid 存活 → 报错退出；陈旧残留删除重试）
    每号前重读磁盘 state（不信任内存副本）……
    return run_batch(args.stagger_minutes)
```

顶部最外层 try/except 兜底：`[BATCH]` 前缀写 CRASH_LOG（run.log），附
「重按一键出发或单号补跑」指引（评审 P2-F5），state 置 crashed=True 后退出非 0。

---

## 五、Task 3 — panel.py 三端点 + 批量期单号动作拒绝

### 5.1 模块级（import 区附近，`logger` 定义之后）

```python
# BAT-001：一键出发批量状态文件（userdata/ 下，gitignored）
BATCH_STATE_PATH = USERDATA_DIR / "batch_state.json"

def _batch_active() -> bool:
    """批量执行器是否仍在运行（pid 存活判定；陈旧 state 由执行器/前端兜底）。"""
    try:
        cur = json.loads(BATCH_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    pid = int(cur.get("pid") or 0)
    if not pid:
        return False
    from main import _pid_alive
    return _pid_alive(pid) and cur.get("phase") not in ("finished", "cancelled")

def read_batch_state() -> dict:
    """/api/batch-state 数据源：active/crashed + 执行器 state 全字段透传。"""
    try:
        cur = json.loads(BATCH_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"active": False, "crashed": False}
    alive = _batch_active()
    terminal = cur.get("phase") in ("finished", "cancelled")
    return {**cur, "active": alive, "crashed": not alive and not terminal}
```

### 5.2 批量激活期拒绝单号动作

`/api/trigger`、`/api/setup-login`、`/api/sync-conversations` 三端点处理器**开头**
（`_resolve_account` 之前）各插入：

```python
if _batch_active():
    return self._send_json({"error": "批量一键出发进行中，请先取消或等待结束。"}, 409)
```

### 5.3 do_POST 新增

```python
if path == "/api/trigger-all":
    if _batch_active():
        return self._send_json({"error": "批量一键出发已在运行。"}, 409)
    with _run_lock:
        if _current_run or _login_running or _sync_running:
            return self._send_json(
                {"error": "面板当前有任务/登录/同步在运行，结束后再一键出发。"}, 423)
    aliases = list_accounts()
    if not aliases:
        return self._send_json({"error": "请先添加账号。"}, 400)
    python_exe = resolve_python(windowless=True)
    if python_exe is None:
        return self._send_json(
            {"error": "找不到可用的 Python 解释器（需已安装 playwright）。"}, 500)
    try:
        subprocess.Popen(
            [python_exe, str(BASE / "batch_runner.py"), "--batch-all"],
            cwd=str(BASE),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            startupinfo=_HIDDEN_STARTUP,
        )
    except Exception as e:  # noqa: BLE001
        return self._send_json({"error": f"启动批量执行器失败: {e}"}, 500)
    return self._send_json({"ok": True, "message": "一键出发已启动：全部账号将顺次执行（号间错峰 15 分钟）。",
                            "accounts": len(aliases)})
if path == "/api/batch-cancel":
    try:
        cur = json.loads(BATCH_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return self._send_json({"error": "无进行中的批量。"}, 400)
    if cur.get("phase") in ("finished", "cancelled"):
        return self._send_json({"error": "无进行中的批量。"}, 400)
    cur["cancel_requested"] = True          # 最小写集：只改本字段（评审 P2-F2）
    # 唯一 tmp（评审 P2-F7 面板侧）：与执行器 _write_state 一样带 pid 后缀，
    # 两写方不再共用同名 tmp → 无互相 os.replace 丢失窗口。
    tmp = Path(str(BATCH_STATE_PATH) + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, BATCH_STATE_PATH)
    return self._send_json({"ok": True, "message": "已请求取消：当前账号跑完后停止。"})
```

（`Path`/`os`/`subprocess`/`resolve_python` 均已 import；`BASE`/`_HIDDEN_STARTUP`
已有。取消端点无文件 → 400「无进行中的批量」token 与错误表一致。）

### 5.4 do_GET 新增

```python
if path == "/api/batch-state":
    return self._send_json(read_batch_state())
```

---

## 六、Task 4 — panel.html 前端

1. **按钮**：账号栏 `addAccountBtn` 前插入（账号栏有账号时随栏显示）：

```html
<button id="batchBtn" class="btn">一键出发 <span class="badge brand"
  id="batchBadge" style="margin-left:4px">→ 0 账号</span></button>
```

2. **横幅容器**：`account-bar` 之后插入：

```html
<div id="batchBanner" style="display:none;padding:10px 24px;border-bottom:1px solid var(--line);
  background:rgba(15,23,42,.55)"></div>
```

3. **JS**（`refreshStatus` 附近新增 `loadBatchState()`，并入既有 5s 轮询
   `setInterval(refreshStatus, 5000)` 同步调用；横幅倒计时用本地 1s tick 仅刷数字）：
   - `$("#batchBtn").onclick = doBatchStart`：POST `/api/trigger-all` →
     toast 文案 → `loadBatchState()`；失败 409/423 红字 toast（服务器错误文案原样）。
   - `loadBatchState()`：GET `/api/batch-state` → `renderBatch(st)`。
   - `renderBatch(st)`：st.active/crashed 控制横幅显隐与样式（crashed 红色横幅文案
     「批量执行器已中断，已完成 i/N 号；重按一键出发会令已完成账号再发一轮」）；
     逐号渲染 `st.items` 行：别名 + 状态徽章（success/partial/error/needs_verify/
     skipped/waiting_stagger/waiting_guard/running/pending + cancel_requested 提示），
     waiting_stagger 显示「距启动 mm:ss」倒计时（本地算，源 `next_start_at`），
     终态行点击 → 切该号 + 跳「执行记录」页签（复用既有切号/切 tab 逻辑）。
   - `$("#cancelBatchBtn")`（横幅内渲染）→ POST `/api/batch-cancel`。
   - `refreshStatus` busy 判定追加批量激活：`batchActive` 时置灰
     `triggerBtn/saveMsgBtn/loginBtn/syncBtn`（后端另有 409 双保险）。
   - `updateAccounts`/账号栏刷新处同步更新 `batchBadge`（N=账号数）与按钮显隐。
   - 事件：`/api/select` 切号后仍保留横幅（批量与当前账号无关）。

---

## 七、Task 5 — verify 转 GREEN + 单元级冒烟

1. `./.venv/Scripts/python.exe verify.py` → 期望仅剩既有 2 FAIL（Task 2-4 后新增
   16 条全过）。
2. **单元级冒烟（打桩，不动真实浏览器/不真实触发）**：临时脚本驱动
   `import batch_runner` 并 monkeypatch：
   - `batch_runner.BATCH_STATE_PATH` → 临时文件（tempfile）；
   - `batch_runner.panel.list_runs` 打桩（返回空/受控 meta）；
   - `batch_runner.panel.trigger_run` 打桩（写一个假 run meta 进临时 runs 目录后
     sleep 0.3s 返回 run_id）；
   - `main.list_accounts`/`panel.load_config` 对假账号目录打桩或直接以真实账号目录
     只跑预检路径（不触发）；
   断言：① 状态机按序推进（pending→running→success）；② 首号后错峰基准生效
   （`_prev_run_end` 写入）；③ 防双发命中（假 meta end 晚于 started_at → skipped）；
   ④ 取消路径两例：运行中置 cancel_requested → 本号收尾后剩号 skipped(cancelled)；
      错峰等待中置 cancel_requested → 等待立即退出（验证磁盘重读语义，评审 P2-F3）；
   ⑤ 两写方原子写后文件可读。输出与退出码留 `docs/superpowers/test-results/BAT-001-IMPL.md`
   证据（Tester 阶段归档）。
3. 功能级冒烟（真实两号，`--stagger-minutes 1`）**待用户授权**（见十一-1）。

---

## 八、Task 6 — 文档同步（spec 4.6）

| 文件 | 改动 |
|---|---|
| `docs/管理面板使用指南.md` | 新增「一键出发（全部账号）」节：位置、串行+错峰 15 分钟、横幅状态含义、取消、批量期单号按钮禁用、执行器独立进程（面板可关）、headless 语义注①、中断重按指引注② |
| `docs/工作原理与架构.md` | 模块职责补 batch_runner.py；目录布局补 userdata/batch_state.json；执行纪律段补一键出发串行队列说明 |

---

## 九、隐私检查（提交前必做，命令本身不含真实名）

```bash
cd D:/ai_project/douyin-auto-fire && \
for d in userdata/accounts/*/; do \
  n=$(basename "$d"); \
  git grep -lE "DouyinAutoFire-${n}|accounts/${n}" -- docs/ ':!userdata' 2>/dev/null \
    && echo "PRIVACY-LEAK: $n"; \
done; echo "privacy scan done"
```

期望 0 输出（docs 全为占位符 `<号A>/<号B>/<别名>`）。真实会话名同样不得入 docs/代码。

---

## 十、验收清单（全部满足才算 DONE）

1. [ ] verify.py：RED 18 FAIL（2+16）→ GREEN 仅剩既有 2 FAIL，均有提交留痕
2. [ ] Task 2-4 实现 token 与断言逐字对齐（GREEN 无「改断言迁就实现」）
3. [ ] 单元级冒烟通过 + `test-results/BAT-001-IMPL.md` 证据
4. [ ] （待授权）功能级冒烟 PASS 或留「下次真实使用后核对」待办
5. [ ] 文档同步 + status 推进至 DONE
6. [ ] 隐私扫描 0 命中；git 状态干净或显式说明（error.log 遗留除外）

---

## 十一、待确认

1. **功能级冒烟授权**：实现全绿后是否授权对两个真实账号用 `--stagger-minutes 1`
   （约 8-10 分钟）各发一条无害文本验证全链路？（按仓库纪律必须用户明确点头）
2. **plan 签字（含错峰间隔确认）**：本文档状态为「待用户签字」——用户在会话明确回复
   批准后方可进入 IMPLEMENT。签字顺带确认 spec 八-2 遗留：「错峰间隔固定 15 分钟、
   仅提供 --stagger-minutes 测试覆盖参数、不做面板配置」（如需 30/60 分钟请直接说，
   只改 argparse `default=15` 与执行器 stagger 基准两处）。
3. 遗留确认：两个账号任务（`DouyinAutoFire-<别名>` ×2）未注册 = verify 既有 2 FAIL
   来源，需用户在面板注册后才可能全绿 0 FAIL（不阻塞本任务验收口径）。
