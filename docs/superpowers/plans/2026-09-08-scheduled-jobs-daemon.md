# 定时任务条目库 + 常驻调度器（自动切号 / 目标文案独立 / 串行错峰）— 实施计划（plan）

- 日期：2026-09-08
- Task-ID：SCH-001
- 状态：待用户签字
- 依赖的 approved spec：`docs/superpowers/specs/2026-09-08-scheduled-jobs-daemon-design.md`
  （2026-09-08 Reviewer APPROVED，`reviews/SCH-001-spec-review.md`；spec 免签生效；评审
  F1–F4 已并入 spec 正文、F5–F7 本 plan 实施注意落实）

---

## 一、目标与验收

按 spec 三章目标实现：定时任务 = jobs 条目（账号/每日时刻/目标/文案，与手动完全独立）；
常驻守护 `scheduler_daemon.py` 到点自动切号、串行执行、错峰固定 15 分钟（end→start）；
撞车排队不跳过；错过当日补跑一次；取消/停止优雅收尾；心跳 + 注册表 Run 自启；
面板任务库管理 + 迁移 + 旧 schtasks 一次性清理。**全程零新增 schtasks 定时注册。**

验收标准（全绿条件）：

1. verify.py RED 阶段：FAIL = 既有 2 + 新增失败 21 = **23**、PASS = 123（含 2 条「runner/batch
   未接新参数」锁定断言自 RED 即绿）；基线 2026-09-08 实测 通过 121 / 失败 2。
2. verify.py GREEN 阶段（Task 7 改写第 3 节后）：**FAIL = 0、exit 0**；通过数 =
   121 + 21（SCH 新断言转绿）+ 2（锁定断言）+ 4（第 3 节守护机制自检）= **148**。
3. 单元级打桩冒烟（不触真实浏览器/真实账号数据）通过，留 `test-results/SCH-001-IMPL.md` 证据。
4. 功能级冒烟（面板 API curl + 守护真跑演示 + 注册表自启开关往返）通过；**真实发送需用户逐次授权**
   （见八），未授权前只交付代码与演示级证据。
5. 文档同步：spec 已 APPROVED；本 plan 签字后进入实现；隐私扫描全程 0 命中。

---

## 二、任务拆分与提交

| Task | 内容 | 提交（中文 conventional） |
|---|---|---|
| 1 | verify.py 新增 23 条 SCH-001 断言（先 RED：21 新增失败 + 2 锁定即绿） | `test(verify): SCH-001 RED 23 条防回归断言（期望 23 FAIL=既有 2+新增 21）` |
| 2 | panel.py 注入缝：trigger_run/_worker 支持 targets/persist_texts | `feat(panel): SCH-001 触发注入缝（targets/persist_texts，手动路径零感知）` |
| 3 | 新建 jobs.py 任务条目存取模块 | `feat(jobs): SCH-001 定时任务条目存取（scheduler_jobs.json 原子写+校验+迁移标志）` |
| 4 | 新建 scheduler_daemon.py 常驻守护 | `feat(sched): SCH-001 常驻调度守护（到点切号/串行错峰15/补跑/心跳/自启/崩溃复核）` |
| 5 | panel.py：/api/jobs 与 /api/scheduler 端点 | `feat(panel): SCH-001 任务库与守护 API 八端点` |
| 6 | panel.html：定时任务页改造（任务表+状态卡+迁移/清理入口） | `feat(panel): SCH-001 定时任务页改造（任务库/守护状态卡/迁移与清理）` |
| 7 | verify 第 3 节改写 + 全绿 + 单元打桩冒烟 | `test(verify): SCH-001 第3节守护自检改写 + 全绿（期望 148/0）+ 冒烟证据` |
| 8 | 文档同步 + status 推进 | `docs: SCH-001 文档同步（定时任务指南/守护机制）+ status 推进` |

代码与文档分开提交；全程直接提交 main（仓库惯例）；每个 Task 提交前跑一次 verify 记录 FAIL 数。

每 Task verify 演进（RED 口径：第 22/23 条为「未接新参数」锁定断言，RED 态即绿、计入 PASS，
不计新增失败；以实际输出核对为准）：

| Task | 动作 | FAIL | PASS |
|---|---|---|---|
| 1 | RED 23 条（21 新增失败 + 2 锁定即绿） | 23 | 123 |
| 2 | 注入缝 3 条转绿（1–3） | 20 | 126 |
| 3 | jobs 模块 4 条转绿（4–7） | 16 | 130 |
| 4 | 守护 9 条转绿（8–16） | 7 | 139 |
| 5 | API 2 条转绿（17–18） | 5 | 141 |
| 6 | 页面 3 条转绿（19–21） | 2 | 144 |
| 7 | 第 3 节改写（-2 FAIL、+4 PASS） | 0 | 148 |

---

## 三、Task 1 — RED 断言（verify.py，先 RED 后 GREEN）

**插入点**：verify.py「★ BAT-001」块尾（现 :390，以实际 grep 定位为准）之后、`# --- 汇总 ---`（:392）之前。
**关键**：新文件 jobs.py / scheduler_daemon.py RED 态不存在，`read()`（verify.py:43-44）无缺文件容错，
必须存在性守卫：`j = read("jobs.py") if (BASE / "jobs.py").exists() else ""`（BAT-001 评审 P1-F1 同款教训）。
变量：`j`/`s` 为新文件源码；`h = read("panel.html")`（放在块内，其后无 `h`=健康字典的消费点；
若担心冲突用 `h1`，实现期以 grep 确认 `h` 最后消费位置再定）。`rsrc` 已由 :61 赋值（runner.py），
`b` 现为 batch_runner.py 文本（:372 赋值，其后无消费），均可直接用。

23 条，逐条锁定语义与 token（**断言为准绳：GREEN 失败对照断言修实现措辞，不许改断言迁就实现**）：

```python
# ★ SCH-001 定时任务条目库 + 常驻调度器（2026-09-08 spec；零 schtasks 定时，取代 MAI-001 每号单任务形态）
# 任务=jobs 条目(账号/时刻/目标/文案 自带独立)；守护进程到点自动切号、串行、错峰固定 15 分钟；
# 撞车排队不跳过；错过当日补跑一次；取消/停止优雅收尾；心跳+注册表 Run 自启；手动路径零感知。
j = read("jobs.py") if (BASE / "jobs.py").exists() else ""
s = read("scheduler_daemon.py") if (BASE / "scheduler_daemon.py").exists() else ""
h = read("panel.html")
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
check("★SCH-001 页面任务库入口", "新建定时任务" in h and "loadJobs" in h)
check("★SCH-001 页面守护状态卡", "开机自启" in h and "下次触发" in h)
check("★SCH-001 迁移/清理引导按钮", "一键迁移" in h and "清理旧系统任务" in h)
check("★SCH-001 runner 未接新参数(默认语义保留)", "persist_texts" not in rsrc and "targets=" not in rsrc)
check("★SCH-001 batch_runner 未接新参数(默认语义保留)", "persist_texts" not in b and "targets=" not in b)
```

**计数 = 23 条**（第 22/23 条为「未接新参数」锁定断言，RED 态即绿；真正新增失败 = 21）。

断言语义自查（提交 RED 前必做）：
- RED 态下 23 条中面向新文件/新字面的 token 在 panel.py/panel.html/磁盘应 0 命中；`persist_texts`/
  `cfg["targets"] = targets`/`if persist_texts and texts:`/`tgt_list = targets if targets is not None`/
  `CurrentVersion\Run`/`DouyinAutoFireScheduler`/`/api/scheduler/*`/`/api/jobs/update` 等在现有源码
  grep 应为 0 命中（`/api/jobs` 与 `/api/tasks` 不同串不冲突）——实现前逐条实测；
- 中文页面 token「新建定时任务」「开机自启」「下次触发」「一键迁移」「清理旧系统任务」在现有
  panel.html 应 0 命中（现有「一键触发/一键同步」不同串）。
- runner.py / batch_runner.py **不改**（断言锁定默认形态）。

RED 期望：**23 FAIL = 既有 2 + 新增失败 21**（PASS 123；既有 2 = 第 3 节按号任务未注册的
环境态，Task 7 处置）。

---

## 四、Task 2 — panel.py 注入缝（targets / persist_texts）

改两处 + 一处 meta 目标源，默认行为完全不变（既有调用方 runner/batch//api/trigger 不传新参数）。

### 4.1 `trigger_run`（现 :539-596）

签名改为：

```python
def trigger_run(texts: list[str], headless: bool | None = None,
                account: str | None = None, *,
                targets: list | None = None,
                persist_texts: bool = True) -> str | None:
```

锁内建 meta 段（现 :567-571）改为（token 行逐字）：

```python
        with _run_lock:
            run_id = _new_run_id()
            cfg = load_config(account)
            tgt_list = targets if targets is not None else cfg.get("targets", [])
            meta_targets = [
                (t.get("name") or t.get("profile_url") or "?")
                for t in tgt_list
            ]
            meta = {
                "id": run_id,
                "account": account,
                "start": _now_iso(),
                "end": None,
                "status": "running",
                "texts": texts or cfg.get("message", {}).get("texts", []),
                "targets": meta_targets,
                "error": None,
            }
            _save_meta(meta)
            _run_dir(run_id, account).mkdir(parents=True, exist_ok=True)
            _current_run = run_id
            _current_run_account = account
        t = threading.Thread(
            target=_worker,
            args=(run_id, texts, headless, account, targets, persist_texts),
            daemon=True)
        t.start()
```

### 4.2 `_worker`（现 :458-536）

签名与 cfg 注入：

```python
def _worker(run_id: str, texts: list[str], headless: bool | None, account: str,
            targets: list | None = None, persist_texts: bool = True):
    ...
        cfg = load_config(account)
        if targets is not None:
            cfg["targets"] = targets          # SCH-001：任务级目标注入（douyin 读取同 cfg）
        cfg["browser"] = {**(cfg.get("browser") or {}), "headless": False}
```

收尾写回（现 :517-521）改条件：

```python
            # 定时任务（SCH-001）自带文案不得写回账号配置，防污染手动文案
            if persist_texts and texts:
                try:
                    update_message_texts(account, [str(t) for t in texts])
                except Exception as e:  # noqa: BLE001
                    logger.warning("保存发送内容到账号配置失败: %s", e)
```

### 4.3 自检

`./.venv/Scripts/python.exe verify.py`：FAIL 从 23 → **20**（注入缝 3 条转绿，第 3 节既有 2 仍在）。

---

## 五、Task 3 — jobs.py（新文件，根目录，与 runner.py 并列）

任务条目唯一写方 = 面板/迁移（守护只读；last_run 展示走 sched_state，见 Task 4）。逐字 token 行：

```python
"""定时任务条目存取（SCH-001 spec 4.2；userdata/scheduler_jobs.json，原子写）。

写方唯一 = 面板 CRUD 与一键迁移；守护进程只读本文件（运行结果在 scheduler_state.json，
展示时面板合并）。条目 = {id, account, time, targets, texts, enabled, created_at}，
目标/文案为任务创建时的独立副本，与账号手动数据（user_data.yaml targets/message）解耦。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from main import USERDATA_DIR, list_accounts

JOBS_PATH = USERDATA_DIR / "scheduler_jobs.json"

_TIME_RE = ...
```

函数契约（实现期按此展开，token/文案逐字保留）：

- `load_jobs() -> list[dict]`：文件缺失/解析失败（ValueError 等）→ `[]`（读侧兜底，BAT 纪律）；
  只返回 `enabled` 与全部条目（守护自己过滤）。
- `_atomic_write(jobs: list[dict])`：唯一 tmp（`f"{JOBS_PATH}.{os.getpid()}.tmp"`）→ `os.replace`；
  Errno 13 小重试 3×0.05s。
- `_validate_job(account, time_str, targets, texts) -> str | None`：account 在 `list_accounts()`；
  `time_str` 匹配 `HH:MM`（`^\d{2}:\d{2}$` 且时分合法）；`targets` 非空且每项含 name；
  `texts` 非空；错误返回中文提示。
- `create_job(account, time_str, targets, texts, enabled=True) -> dict`：id=`uuid4().hex`，
  created_at=now iso；落盘返回条目。同号同时刻**不拦截**（拍板②，由守护错峰顺延）。
- `update_job(job_id, *, time=None, targets=None, texts=None, enabled=None) -> dict | None`：
  全字段可改；不存在返回 None；改完原子落盘（守护每轮重读，改完即生效）。
- `toggle_job(job_id, enabled) -> dict | None`。
- `delete_job(job_id) -> bool`。
- `has_legacy_schedule(aliases=None) -> bool`：任一账号 user_data.yaml 含非空 `schedule.time`。
- `migrate_from_legacy() -> list[dict]`（幂等，plan F5）：仅当 JOBS 无 `migrated_from_legacy` 标志
  且任务库为空时执行——逐号生成 `{account, time=历史 schedule.time, targets=该号 targets 全量副本,
  texts=该号 message.texts 副本, enabled=true}`；完成后写 `{"version":1, "migrated_from_legacy": true,
  "jobs": [...]}`。有任务或已迁移 → 直接返回现状并置标志（横幅据此熄灭）。
- 迁移不修改 user_data.yaml（手动数据原样）。

自检：verify FAIL **20 → 16**（jobs 4 条转绿：4/5/6/7）。

---

## 六、Task 4 — scheduler_daemon.py（新文件，常驻守护）

模块骨架与 token 行（逐字保留 **token 行**；整体语义按 spec 4.3 + 评审 F1–F4 落地）：

```python
"""定时任务守护进程（SCH-001 spec 4.3，常驻；面板 /api/scheduler/start 经 pythonw 拉起，
开机经注册表 Run 自启；零 schtasks 定时——拍板⑤）。

主循环每 POLL_SECONDS 一轮：写心跳 → 跨天重置 → 找今日到点未触发任务入队 → 逐条串行执行
（出队重读 → 预检 → 守卫等待 → 错峰 ≥15min → 两段式触发 → 轮询收尾 → 回写 fired）。
与手动/一键出发共用全局守卫 userdata/.running：撞车排队不跳过。错过当日时刻恢复后补跑一次；
fired 含日期跨天重置，不跨天补。
"""
from __future__ import annotations

import json
import os
import sys
import time
import winreg
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from main import (ensure_userdata, USERDATA_DIR, RUN_GUARD_PATH,   # noqa: E402
                  _pid_alive, list_accounts, account_root)
import panel  # noqa: E402
from jobs import JOBS_PATH, load_jobs  # noqa: E402

ensure_userdata()
CRASH_LOG = USERDATA_DIR / "run.log"
STATE_PATH = USERDATA_DIR / "scheduler_state.json"
HEARTBEAT_PATH = USERDATA_DIR / "scheduler_heartbeat.json"
DAEMON_STAGGER_MINUTES = 15        # 拍板④：错峰固定 ≥15（end→start），不暴露配置
POLL_SECONDS = 20                  # 主循环周期（面板判停阈值 ≥3× ≈60s，plan F7）
AUTOSTART_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE = "DouyinAutoFireScheduler"
```

函数清单（实现按 spec 4.3 语义展开；签名与关键 token/文案逐字）：

- `_now_iso()`；`_crash(msg)`（写 run.log，runner.py 同款）；
- `_read_json(path) -> dict`（缺失/解析失败→`{}`）；`_write_json(path, data)`（唯一 tmp 带 pid +
  `os.replace` + Errno 13 重试）；
- `set_autostart(enabled: bool) -> bool`：winreg 打开 `AUTOSTART_RUN_KEY`（HKCU），enabled=True
  写 `AUTOSTART_VALUE` = `'"<pythonw.exe>" "<BASE>/scheduler_daemon.py"'`（resolve_python
  windowless），False 删值（不存在则成功）；返回操作结果；
- `_write_heartbeat(current: str, next_due: str | None)`：`{pid, ts, boot_at, current, next_due}`；
- `load_state() -> dict`：`{date, fired:{}, last_results:{}, queue:[], cancel_requested:False,
  stop_requested:False, prev_run_end:None}` 与磁盘合并（解析失败→默认，BAT 读侧纪律）；
- `_reset_if_new_day(st) -> dict`：`st.date != today` → 对 `queue` 中未触发条目记
  `last_results[job_id]={"status":"skipped","reason":"跨天未及触发"}`（评审 F3，**文案逐字**），
  再重置 date/fired/queue/cancel/stop（last_results 保留最近一次供展示）；
- `_due_jobs(jobs, st, now)`：enabled 且 `HH:MM(now)>=job.time` 且 `job.id not in st.fired`
  （按 time, created_at 升序）；
- `_reload_job(job_id)`：从磁盘 `load_jobs()` 中按 id 重读 → 不存在或 `enabled=false` 返回
  `None`（评审 F4：出队执行前调用，防「删了还跑、改了还发旧的」）；
- `_recover_interrupted(st)`：守护启动时遍历 `fired`——`status=="running"` 且带 run_id →
  `_poll_meta(run_id, account)` 收尾后回写终态（**不重新触发**）；`status=="dispatching"` 且无
  run_id → 视为未触发（条目 at 已陈旧）→ 从 fired 移除，允许当天重新入队补跑一次（评审 F1）；
- `_execute_job(job, st) -> None`：镜像 batch_runner._execute_account ①~⑦（batch_runner.py:121-270）：
  ① 预检：`_reload_job` 先跑；account 在 list_accounts、browser_data 目录在、texts/targets 非空，
  缺项 → fired/ last_results skipped+reason，继续下一条；
  ② 守卫等待：`RUN_GUARD_PATH.exists()` → pid 感知（`_pid_alive`）等待，每轮从磁盘重读
  state（cancel/stop 为准）；
  ③ 错峰等待：`start ≥ max(now, prev_run_end + DAEMON_STAGGER_MINUTES)`；`prev_run_end` 启动初值 =
  max(各账号 `panel.list_runs(acc, keep=1)[0].end`)；执行状态在 state 展示字段
  `current`/`queue`（面板可见「等待守卫/等待错峰/运行中」与预计时刻，参考 batch
  waiting_guard/waiting_stagger 语义）；
  ④ 两段式触发（评审 F1）：先 `st.fired[job.id]={"status":"dispatching","at":now}` 原子落盘 →
  `run_id = panel.trigger_run(job["texts"], headless=None, account=job["account"],
  targets=job["targets"], persist_texts=False)`；None → 回等待语义重试上限 3 次，仍失败 →
  fired error「触发被拒（守卫被占/内部繁忙，重试 3 次后放弃）」继续队列（诚实报错不假成功）；
  成功 → 同一条目补 `run_id`、`"status": "running"` 落盘；
  ⑤ 轮询收尾：`panel._load_meta(run_id, acc)` 至非 running（15min deadline 兜底，runner 同款）；
  `fired/ last_results[job.id] = {status, run_id, at, end, error, failed_targets}`（status 映射
  success/partial/error/needs_verify 原样）；`prev_run_end = meta.end`；
  ⑥ 取消/停止：每轮从磁盘重读——`cancel_requested` → 当前任务自然收尾后剩余队列
  skipped「用户取消」；`stop_requested` → 同上且守护进程退出（评审 F2，绝不中途杀浏览器）；
- `run_daemon() -> int`：启动即 `_recover_interrupted`；主循环 while not stop：
  `_write_heartbeat(...)` → `_reset_if_new_day` → 队列空则 `_due_jobs` 补队 →
  队首 `_execute_job` → `time.sleep(POLL_SECONDS)`；整轮 try/except 记 last_err 不自杀；
- `main()`：防双开（读心跳 pid 存活则记日志退出）；`if __name__ == "__main__": sys.exit(main())`
  ——**import 无副作用**（verify/冒烟可直接 import）。

触发语义与 runner 一致：headless=None 走该号 config（真实有头窗口）。

自检：verify FAIL **16 → 7**（守护 9 条转绿：8–16）。

---

## 七、Task 5 — panel.py API 八端点

在路由区（现 :1274-1345 一带）新增（token 行逐字；账号/状态校验风格对齐现有）：

- `GET /api/jobs`：`{jobs: load_jobs(), state: 摘要(守护心跳/queue/fired/last_results 合并),
  legacy: has_legacy_schedule(), migrated: 标志}`；
- `POST /api/jobs`（创建：body account/time/targets/texts → create_job；校验失败 400 中文提示；
  同时回写 400/409 语义对齐现有；F6 提示：`time` 已过当日 HH:MM 且 enabled → 响应带
  `catchup_today: true`，前端明示「保存后当日会立即补跑一次」）；
- `POST /api/jobs/update`（id + 字段）；`POST /api/jobs/toggle`（id + enabled）；
  `POST /api/jobs/delete`（id）；
- `POST /api/jobs/migrate`：migrate_from_legacy()（幂等）；
- `POST /api/scheduler/start`：防双开（读心跳 pid）→ Popen pythonw scheduler_daemon.py
  （CREATE_NO_WINDOW + _HIDDEN_STARTUP，batch_runner spawn 先例 panel.py:1336-1342）；
- `POST /api/scheduler/stop`：**置 `stop_requested=true`（最小写集）**——不 taskkill（评审 F2）；
  守护看到后当前 run 收尾即退；未运行则返回提示；
- `POST /api/scheduler/cancel`：置 `cancel_requested=true`（最小写集，只改标志字段，先读最新）；
- `POST /api/scheduler/autostart`：body enabled → `scheduler_daemon.set_autostart(enabled)`
  （import scheduler_daemon；写真实注册表 Run，往返还原由功能冒烟负责）；
- `GET /api/scheduler`：合并进 /api/jobs 响应即可（前端单次拉取）。

旧 `/api/tasks`（单号 schtasks create/disable/enable/delete）保留实现、页面不再引导
（spec 4.5；是否整段移除不属本任务范围，避免 verify 既有断言大面积改动）。

自检：verify FAIL **7 → 5**（API 2 条转绿：17/18）。

---

## 八、Task 6 — panel.html 定时任务页改造

「定时任务」页整页改造（结构概念；实现期对齐现有页面风格与 fetch 封装、refreshStatus ~5s 轮询）：

1. **守护进程状态卡**：运行中（心跳 ts 新鲜 ≤60s）/ 已停止（>60s，红点提示，plan F7）；显示
   「下次触发」倒计时与当前队列进度（current/queue 来自 /api/jobs state）；按钮：启动守护 /
   停止守护 / 取消当前队列 / 「开机自启」开关（autostart 状态随 /api/jobs 返回）。
2. **任务表（跨号）**：每行 = 账号 | 时刻 | 目标（数量+悬停明细）| 文案摘要 | 启用开关(toggle) |
   上次运行（last_results：日期+状态；失败红字含失败目标）| 删除；行点击/编辑按钮进编辑态。
3. **新建/编辑表单**：选账号（下拉 list_accounts）→ 时间 HH:MM → 目标多选（默认该号全量 targets，
   可改；数据源 conversations cache）→ 文案（默认该号已存文案，可改）→ 保存；
   F6：保存响应 catchup_today=true 时弹提示「该时刻今日已过，保存后将立即补跑一次」。
4. **旧数据迁移/清理区**：`has_legacy && !migrated && 任务库为空` → 「一键迁移」按钮（调
   /api/jobs/migrate，完成后刷新；迁移产物 = 每号一条，目标/文案为账号副本，之后可逐条改）；
   「清理旧系统任务」按钮：对 `DouyinAutoFire` 及每号 `DouyinAutoFire-<别名>` 调既有
   query_system_task 探测存在 → schtasks 删除（一次性收尾，此后零系统定时任务）。
5. 页面 token 行：`新建定时任务`（表单标题/按钮）、`loadJobs`（拉取函数）、`开机自启`、
   `下次触发`、`一键迁移`、`清理旧系统任务`（**逐字**，供 RED 断言 19/20/21）。

自检：verify FAIL **5 → 2**（页面 3 条转绿：19/20/21；剩余 2 = 第 3 节既有注册探测，Task 7 改写消除）。

---

## 九、Task 7 — verify 第 3 节改写 + 全绿 + 单元打桩冒烟

### 9.1 第 3 节改写（现 :79-134）

机制替换（spec 4.7）：按号 schtasks 注册探测由「守护机制自检」取代。删除 :89-134 的按号/单号
任务注册与命令探测分支，替换为（守护/jobs 文件已存在；import 无副作用）：

```python
# --- 3. 定时机制（SCH-001：schtasks 定时由常驻守护取代；第 3 节改为守护机制自检） ---
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
```

（原 :95-107 的 cmd/exe 存在性运行时探测随按号任务移除——旧任务清理后无对象；runner 语义两条
保留为第 3 节基线。）第 3 节改写使既有 2 FAIL 消失、新增 4 PASS。

### 9.2 全绿口径

实现全部落地后：`./.venv/Scripts/python.exe verify.py` → **通过 148 / 失败 0、exit 0**
（121 基线 + 23 SCH + 4 守护自检 − 0；注册探测 2 FAIL 随第 3 节改写消失）。

### 9.3 单元级打桩冒烟（验证守护状态机，动笔前读 `references/red-green-smoke.md` 配方）

冒烟脚本（userdata/_smoke_sch001.py，gitignored 区）打桩点：
- `scheduler_daemon.JOBS_PATH / STATE_PATH / HEARTBEAT_PATH / CRASH_LOG` → tempfile；
- `sched.panel = FakePanel()`：`trigger_run` 写假 run meta（保留真 `_load_meta` 读文件轮询语义 →
  FakePanel._load_meta 读 tmp 目录 meta 文件）、`list_runs` 返回空/预设；
- `sched.list_accounts`/`sched.account_root` → 假别名 + tmp 假账号目录（含 browser_data）；
- `time.sleep` 压 ~0.02s（先存 real_sleep）；`_write_json` 走真实原子写（逼 Windows 竞态）；
- 时间源：把 `_due_jobs`/主循环的「now」参数化注入假时钟序列。

场景矩阵（断言看 `scheduler_state.json`/heartbeat 终态 JSON，不看日志）：
1. 两号同刻 21:30 → 按序执行、第二条 start ≥ 第一条 end + 15（压 15 → monkeypatch
   `DAEMON_STAGGER_MINUTES=1` 与 `POLL_SECONDS` 小值）；
2. 同号同时刻两条 → 并存顺延不拦截；
3. 到点触发 → fired 两段式：先 dispatching 后 running(run_id)（断言中间态与终态）；
4. 崩溃复核：手工造 fired=running 残留 + 假 meta 终态 → `_recover_interrupted` 收尾不重发；
   fired=dispatching 无 run_id 残留 → 移除后重新入队补跑一次；
5. cancel/stop：执行中置标志 → 当前收尾、剩余 skipped、stop 后主循环退出；
6. 跨天：造 date=昨天 + queue 残留 → `_reset_if_new_day` 记「跨天未及触发」并重置；
7. 出队重读：入队后删除任务 → 执行时 skipped「任务已删除/停用」不发送。

通过标准：7 场景终态断言全绿，产出 `test-results/SCH-001-IMPL.md`（命令 + 真实输出 + 结论；
引输出时脱敏假别名/占位）。

### 9.4 功能冒烟（无真实发送）

面板 API curl 冒烟（/api/jobs CRUD + migrate 幂等 + scheduler start→心跳出现→stop→心跳停更）；
autostart 开关往返（写后读回再删，还原现场）；守护真跑一轮演示用任务（时刻=当前+1min、
目标=必然不存在的假会话名触发 no_match 失败路径或 enabled=false 演示条目）——**涉及真实账号
浏览器动作前必须用户授权**（见十）。

---

## 十、遗留与授权（实现完成后仍需用户）

1. **真实发送冒烟**：对真实目标的一次性发送需用户逐次授权（提供目标名+无害文本），agent 不代跑。
2. **旧任务清理与迁移**：清理旧 schtasks（DouyinAutoFire 等）与「一键迁移」由用户在面板点击执行
   （涉及真实账号数据迁移动作）；agent 只交付代码与面板指引。
3. 注册表自启开关默认关闭，由用户在面板按需开启。
4. 全部 Task 提交完 = verify 全绿（148/0）+ `git status` 无新增未跟踪文件即结束；真实运行核对
   留待用户下次观察（面板状态卡/执行记录）。

---

## 十一、风险与约束（实施纪律）

- 本仓库无测试框架：verify.py 为事实标准；每个 Task 提交前跑一次并记录 FAIL 数变化。
- 改 panel.py 时逐条 patch、逐条看 lint；同一文件多处修改勿并行批量 patch（缩进雪崩教训）；
  改坏区段用 `git checkout` 还原重做。
- 状态文件写方纪律（BAT-001 固化）：唯一 tmp 带 pid 后缀 + os.replace；读侧解析失败 → None/{}
  兜底；取消/停止类重试耗尽诚实报错不假成功；等待循环每轮从磁盘重读标志。
- 隐私红线：实现/注释/冒烟证据不得出现真实账号别名、真实目标名、真实文案；假账号用 ASCII
  假别名；扫描命令不内联真实名。
- 长于面板生命周期的执行放独立进程（守护本就是独立进程）；面板仅启动器 + 只读状态源。
- 冒烟/演示先确认登录态与 browser_data 目录锁（README 既有教训）。
