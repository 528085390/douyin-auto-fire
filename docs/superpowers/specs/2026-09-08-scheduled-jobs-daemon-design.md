# 定时任务条目库 + 常驻调度器(自动切号 / 目标文案独立 / 串行错峰)— 设计文档(spec)

- 日期：2026-09-08
- Task-ID：SCH-001
- 状态：待评审
- 决策来源：2026-09-08 用户需求（原文要点）：「定时任务到时间后触发单一账号的私聊任务；私聊目标是
  下定时任务时设定好的，与手动触发的目标区分开；可以下多个定时任务，每个定时任务的目标可以不同；
  两个账号的定时任务若设同一时间，不能同时触发、要有间隔；要自动切换到对应的账号」。追问后：
  「有别的方法吗，一定要用 Windows 计划任务？」→ 澄清为不依赖 schtasks 的常驻调度方案。
- 评审拍板记录：2026-09-08 需求澄清拍板 ×6 + 机制选择 ×1（会话 clarify 逐项，见下）：
  ① 定时任务**自带文案+目标**（创建时填写，与手动触发、账号已存文案完全独立）；
  ② 同一账号同一时刻允许多条任务**并存**，到点自动排队，后到者顺延（前一任务实际 end + 15 分钟再跑）；
  ③ 周期**仅每日固定 HH:MM**（要多时刻就下多条任务）；
  ④ 号间/任务间错峰**固定 ≥15 分钟（end→start），不可配置**（沿用 MAI-001/BAT-001 拍板，不退化）；
  ⑤ 触发机制 = **纯常驻调度守护进程，零 Windows 计划任务**；开机自启用启动文件夹/注册表 Run；
  ⑥ **补跑**：错过当天时刻（关机/睡眠/守护未开），当日恢复后自动补跑一次（晚发比不发强）；
  ⑦ 方案整体确认后进入本 spec（用户会话明确「确认，写 spec 文档走评审」）。
  MAI-001（`2026-09-04-multi-account-isolation-design.md`）拍板保留：账号目录隔离、
  全局串行守卫「同一时刻绝不并发」、错峰纪律。**本任务取代的是 MAI-001 的「每号一条 schtasks 定时
  任务」实现形态**（该形态同点触发不排队、后到者直接跳过，1.3 事故链），不重开其隔离与风控拍板；
  跨账号并行执行仍是非目标。

---

## 一、背景与问题

### 1.1 用户需求

- 到点触发**单一账号**的私聊任务；任务的目标与文案是**创建定时任务时设定**的，与手动触发目标区分开；
- 每号可下**多条**定时任务，各自目标不同（如不同时段发给不同会话子集）；
- 两个账号任务设到**同一时刻**时：不并发、有间隔，且**自动切换到各自账号**执行；
- 触发机制不再依赖 Windows 计划任务（用户明确不想要 schtasks 形态）。

### 1.2 现状约束（全部有代码锚，见二）

1. **手动触发 = 当前账号全量 targets + 面板输入文案**：`POST /api/trigger` →
   `trigger_run(texts, headless=False, account)`；`_worker` 内 `cfg = load_config(account)`，
   只覆盖 `cfg["message"]["texts"]`，**目标无法按次注入**（永远是该号 `user_data.yaml` 的 targets）。
   面板/runner/定时共用同一链路 → 「手动 vs 定时目标不同」在现状下**无法表达**。
2. **每号只有一个定时时刻**：`schedule.time`（HH:MM 单值）写在该号 `user_data.yaml`；
   系统任务按号注册 `DouyinAutoFire-<别名>`。多时刻、同号多任务无数据模型。
3. **同点触发的 schtasks 不排队**：每号独立系统任务同刻各自触发，后到者 `trigger_run` 返回 None
   即记 run.log 退出跳过（BAT-001 spec 1.3 已定性；本仓库纪律「执行不留静默缺口」）。
4. **本机实测（2026-09-08）**：任务计划程序里仅剩旧遗留任务 `DouyinAutoFire`
   （`/TR` 为 `runner.py --run-once`，**无 `--account`**）；两号已配 `schedule.time=21:30` 但
   没有对应按号任务 → 现状 21:30 实际什么都不会触发；若旧任务到点触发，`resolve_account(None)`
   在多账号下直接 exit 2（见证据 B4/B5）。
5. **独立进程执行已有仓库先例**：runner.py（schtasks 定时）与 batch_runner.py（一键全号）
   都是「独立 pythonw 进程 import panel → `trigger_run` → 轮询 run meta」，不依赖面板常驻。

### 1.3 隐藏动机与事故链

两号配置写死 21:30、系统任务只剩一条失效旧任务 → 用户已观察到「定时不可靠」，且想要更细的
「谁、几点、发给谁」编排。BAT-001「一键出发」是**手动**的全号可靠入口，本任务把同一套串行
执行思想做成**定时**且**按任务条目**编排的常驻调度器，并让结果在面板可见可管。

---

## 二、勘察结论（证据表）

| 编号 | 结论 | 证据 |
|---|---|---|
| A1 | 触发链路：`/api/trigger` → `trigger_run(texts, headless, account)` → `_worker`；文案可覆盖、目标不可注入 | panel.py:1274-1286（`/api/trigger`）；:458-536（`_worker`：:469 `load_config(account)`、:472-474 覆盖 `message.texts`、:480-481 `DouyinStreak(cfg).run()`） |
| A2 | run meta 的 `targets` 取自账号 cfg targets（触发时快照），记录页以此展示 | panel.py:567-571（`cfg = load_config(account)` → targets 列表） |
| A3 | `_worker` finally 会把本次 texts **写回账号配置** `update_message_texts(account, texts)`——定时任务若自带文案，必须避免污染账号手动文案 | panel.py:517-521 |
| A4 | 发送核心从 `cfg["targets"]` 取目标：`self.targets = config.get("targets")`（兼容旧 `target` 键），run 循环遍历 `self.targets`、失败记 `failed_targets` | douyin.py:78-85、:926-968（:943 重置、:967-968 append）→ **在 `_worker` 覆盖 `cfg["targets"]` 即可注入任务目标，douyin.py 零改动** |
| A5 | 每号一条 schtasks：任务名 `DouyinAutoFire-<别名>`，`/TR` = pythonw runner.py `--run-once --account <别名>`，`/SC DAILY /ST time` | panel.py:812-818（`create_task`）；main.py:443-480（`try_register_task`）；main.py:359-361（`task_name`） |
| A6 | runner.py 独立进程执行先例：import panel → `trigger_run` → 轮询 `_load_meta` 至非 running，15 分钟 deadline 兜底，早期异常写 run.log | runner.py:47-111（:87-90 取账号已存文案、:90 触发、:101-111 轮询兜底） |
| A7 | batch_runner.py 串行执行器状态机（本任务复用其写法）：①预检（跳过项不占错峰）②守卫等待（pid 感知自愈，每轮从磁盘重读 cancel）③错峰等待（`_prev_run_end` 基准）④防双发 ⑤触发重试 3 次 ⑥轮询 15min deadline ⑦收尾原子落盘 `_prev_run_end` | batch_runner.py:121-270；错峰默认 15 为参数 `--stagger-minutes default=15`（:335-338）；状态文件 `userdata/batch_state.json`、守卫 `userdata/.running` |
| A8 | 手动语义：面板触发发当前账号全量 targets + 输入框文案；账号 targets 经会话勾选保存 | panel.py:1274-1286；panel.py:1255-1267（`update_targets` + conversations cache） |
| A9 | verify.py 基线 2026-09-08 实测：**通过 121 / 失败 2**（exit 1）。2 失败 = 「账号任务 DouyinAutoFire-<别名> 已注册」探测（本机仅旧任务在册，环境态）→ 新机制落地后该节断言需改造，目标全绿 | `./.venv/Scripts/python.exe verify.py` 实测 |
| A10 | 本机任务计划程序实测：仅 `DouyinAutoFire`（Ready，`runner.py --run-once` 无 `--account`）；无任何 `DouyinAutoFire-<别名>` 按号任务 | 2026-09-08 `Get-ScheduledTask` 查询 |
| A11 | 多账号下无 `--account` 的入口直接 exit 2（防串号），故 A10 的旧任务即使到点也跑不动 | main.py:364-386（:381-382 多账号报错列出别名）；main.py:601-602（迁移收尾提示删旧任务） |
| A12 | 面板现有 spawn 独立执行器先例（无窗口 pythonw + batch_runner），及既有定时任务 API（单号 create/disable/enable/delete + adopt-legacy）可作启停/清理参考 | panel.py:1336-1342（Popen batch_runner）；:1102/:1161/:1306-1320（/api/tasks 系列） |

---

## 三、目标与非目标

### 目标

1. 定时任务 = **数据条目**（账号 + 每日时刻 + 目标 + 文案），同号多条、同时刻多条、跨号同刻均允许；
   每任务目标/文案与手动触发完全独立（拍板①）。
2. 由**常驻调度守护进程**到期自动触发：自动切到任务所属账号、注入任务自己的目标与文案、串行执行、
   号间/任务间错峰固定 ≥15 分钟 end→start（拍板④），与手动/一键出发共用全局守卫、撞车**排队不跳过**。
3. 守护进程**开机自启**（注册表 Run），**心跳落盘**，面板实时显示守护状态、下次触发、任务上次结果，
   可启停守护、取消当前队列、开关自启。
4. **补跑**：当日任务到点时电脑未开/睡眠/守护未运行，恢复后当天自动补跑一次（拍板⑥），不跨天。
5. 面板定时任务页改造为跨号任务库管理 + 迁移旧配置 + 一次性清理旧 schtasks 任务。
6. 不依赖 Windows 计划任务实现任何定时（唯一例外：一次性「删除旧任务」收尾动作）。

### 非目标

- **跨账号并行执行**（沿 MAI-001/BAT-001：绝不并发，串行+错峰；勿重开）。
- 复杂周期（每周几/一次性日期/每 N 天）——拍板③已排除；需要多时刻 = 多条任务。
- 指纹浏览器/代理 IP 等风控对抗升级（MAI-001 组合二，非目标继承）。
- 引入第三方调度库（如 APScheduler）：守护主循环用标准库，无新依赖。
- 修改 douyin.py 发送核心与既有审计/失败目标链。
- 面板进程承载调度（面板非必需常驻；调度在独立守护进程）。
- 跨天补跑（当天 23:59 后不再补昨天）。
- 手动触发语义不变（不引入「手动选子集」；账号 targets 仍是手动全量）。

---

## 四、方案设计

### 4.1 总体架构

```
┌── 常驻守护进程 scheduler_daemon.py（pythonw，无窗口，随登录自启）──────────┐
│ 主循环（~20s/轮，标准库）：                                                  │
│   1) 写心跳 scheduler_heartbeat.json（pid/时间/状态/下次到期）               │
│   2) 读 jobs.json（enabled 任务）→ 跨天则重置 sched_state 的 fired/queue      │
│   3) 找「今日已到点 & 今日未 fired」任务 → 入队（按 time 升序、created_at 稳定序）│
│   4) 队列非空且空闲 → 逐条执行：守卫等待 → 错峰等待 → 自动切号触发            │
│      （注入该任务 targets+texts）→ 轮询收尾 → 回写 sched_state.fired          │
└───────▲──────────────────────────▲────────────────────────────────────────┘
        │ 只读 jobs.json；状态写     │ cancel 最小写集（只改标志字段）
        │ sched_state.json/心跳      │
┌───────┴── userdata/（gitignored）──┴────────────────────────────────────────┐
│ scheduler_jobs.json   任务条目（唯一写方 = 面板 CRUD）                       │
│ scheduler_state.json  fired/队列/prev_run_end/cancel_requested（写方=守护，   │
│                         cancel_requested 另由面板最小写集）                  │
│ scheduler_heartbeat.json 心跳（写方=守护）                                   │
│ .running / batch_state.json 既有全局守卫与一键出发状态（不改）               │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **写方职责划分（防双写竞态，BAT 铁律）**：`scheduler_jobs.json` 只有面板写（守护只读）；
  任务的「最近一次运行结果」**不写回 jobs.json**，而是放 `sched_state.fired[job_id]`，面板展示时
  jobs + state 合并 → 任何文件都至多两个写方且每个字段单一写方。
- 任务结果跨天归档：`fired` 按天重置，但每个 job 的「上次结果」需要跨天可见 → 方案：
  `fired[job_id]` 写入后同步复制一份到 `sched_state.last_results[job_id]`（跨天保留最近一次），
  面板「上次运行」读 last_results。两字段均守护写，无竞态。
- 所有状态写入沿用 BAT-001 落盘纪律：**唯一 tmp（带 pid 后缀）+ `os.replace` 原子替换**、
  读侧重试（Errno 13 小重试）且 **JSONDecodeError 等解析失败 → 视为无文件/None（兜底防自锁）**、
  重试耗尽诚实报错不假成功。

### 4.2 任务数据模型（scheduler_jobs.json）

```jsonc
{
  "version": 1,
  "jobs": [
    {
      "id": "<uuid4-hex>",
      "account": "<别名>",                // 该任务所属账号（自动切号目标）
      "time": "21:30",                    // 每日 HH:MM（24h）
      "targets": [ {"name": "...", "type": "private"} ],  // 任务独有目标（创建时勾选，可含私聊/群聊）
      "texts": ["..."],                   // 任务独有文案（≥1；多条沿用 random = len>1 语义）
      "enabled": true,
      "created_at": "2026-09-08T21:30:00"
    }
  ]
}
```

- 目标来源：面板从该账号会话缓存（conversations cache）多选，**默认勾选该号当前全量 targets，
  可改**——数据与手动解耦：保存后任务的 targets/texts 是该任务的独立副本，手动路径改动不影响已建任务。
- 空校验：targets 为空 / texts 为空 / account 不存在 / time 非 HH:MM → 创建拒绝并提示。
- 同号同时刻允许多条（拍板②），不做创建拦截。

### 4.3 守护进程主循环与状态机

**触发判定（含补跑语义，拍板⑥）**：任务今日触发条件 =
`now.date() == 任务日 && HH:MM(now) >= HH:MM(job.time) && job.id ∉ sched_state.fired && job.enabled`。
守护启动/唤醒后首次扫描即会把当天已过点未 fired 的任务入队 → 自然实现「错过补跑一次」；
`fired` 键含日期（`sched_state.date`），跨天重置，**不跨天补**。

**队列与执行（逐条，串行）**：
1. 入队排序：`(time, created_at)` 升序 → 同刻多条（同号/跨号）次序稳定；
2. 出队执行，每任务状态机**镜像 batch_runner._execute_account ①~⑦**（batch_runner.py:121-270）：
   ①预检：账号存在、texts/targets 非空（任务自带，非账号配置）、`browser_data` 目录在；缺项 →
   `fired[job_id] = {status:"skipped", reason}`，继续下一条（不拖垮同批）；
   ②守卫等待：`userdata/.running` 存在则 pid 感知等待（陈旧自愈同守卫内建），每轮从磁盘重读
   cancel 与 state；
   ③错峰等待：实际开始 ≥ `max(now, prev_run_end + 15min)`；`prev_run_end` 初值 = 守护启动时
   对全部账号 `list_runs(acc, keep=1)` 取最新 end（覆盖手动/一键出发刚跑完的情形），每任务完成后
   更新为自身 end（与 batch 的 `_prev_run_end` 同语义）；
   ④触发：`panel.trigger_run(texts, headless=None, account, targets=job.targets, persist_texts=False)`
   ——headless=None 走该号 config（与 runner 语义一致，真实有头窗口）；返回 None（守卫被占/繁忙）
   → 回等待语义重试上限 3 次，仍失败 → `fired=error("触发被拒…")` 继续队列（诚实报错，不跳过不假成功）；
   ⑤**先落盘再跑**：拿到 run_id 立即写 `fired[job_id]={status:"running", run_id, at}` → 守护若在
   运行中途崩溃，重启后对 `fired.running` 条目**复核既有 run_id**（轮询 run meta 至终态/15min
   超时兜底），**不重新触发** → 防「崩溃重启重复发送」；
   ⑥轮询收尾：run meta 非 running（success/partial/error/needs_verify）→
   `fired/ last_results[job_id] = {status, run_id, at, end, error, failed_targets}`；
   `prev_run_end = meta.end`；
   ⑦取消：`sched_state.cancel_requested` 置位 → 当前任务自然收尾后，队列剩余全部
   `{status:"skipped", reason:"用户取消"}`（不杀浏览器，同 batch 语义）。

**错峰常数**：`DAEMON_STAGGER_MINUTES = 15`（固定，不暴露 CLI/UI 配置——拍板④；打桩冒烟可
monkeypatch 该常量/时间源，不需要运行时参数）。

**心跳与防双开**：每轮写 `scheduler_heartbeat.json`（pid/ts/boot_at/current/next_due/last_err）；
守护启动时若读得**存活** pid（同 pid 探测逻辑）→ 记日志退出（防双实例双写 state）；
面板按心跳时间戳新鲜度判断「运行中/已停止」。

### 4.4 触发链路注入缝（唯一触碰 panel 的改动点）

`panel.trigger_run(texts, headless=None, account=None, *, targets=None, persist_texts=True)`：
- `_worker` 增加同签名透传：`targets is not None` 时 `cfg["targets"] = targets`
  （douyin.py:78-85 自动生效，**发送核心零改动**）；
- run meta 的 `targets` 展示列表：给了 targets 参数则用参数（name 列表），否则维持 cfg targets
  现状（panel.py:567-571）；
- `persist_texts=False` 时跳过 `update_message_texts` 写回（panel.py:517-521）——**定时任务文案
  不得覆盖账号手动文案**（拍板①的数据独立，代码上必须挡住）；
- 默认值保证既有调用方零感知：runner.py / batch_runner / `/api/trigger` 均不带 targets、
  persist_texts 默认 True → 行为与现状完全一致（verify 既有契约断言不破坏）。

### 4.5 面板改造（panel.py / panel.html / 新 API）

- 页面「定时任务」整页改为**跨号任务库**：
  - 守护进程状态卡：运行中/已停止（心跳红点）+ 下次触发倒计时 + 当前队列进度 +
    按钮：启动守护 / 停止守护 / 取消当前队列 / 「开机自启」开关；
  - 任务表（跨号）：账号 | 时刻 | 目标（数量+悬停明细）| 文案摘要 | 启用开关 | 上次运行
    （日期+状态，失败红字含失败目标）| 删除；每条可编辑；
  - 新建/编辑表单：选账号 → 选时间（HH:MM）→ 从该号会话勾选目标（默认该号全量）→ 填文案 →
    保存即生效（守护每轮重读，无需重启）；
  - 旧数据迁移引导：检测到历史 `schedule.time` 且任务库为空 → 「一键迁移」按钮（4.7）；
  - 「清理旧系统任务」按钮：删除任务计划程序里遗留的 `DouyinAutoFire` 及
    `DouyinAutoFire-<别名>`（一次性收尾，此后仓库不再创建系统定时任务）。
- 新 API（全部带账号解析/鉴权同现有风格）：
  - `GET /api/jobs`（返回 jobs + 合并 last_results + 守护心跳/状态摘要）；
  - `POST /api/jobs`（创建）/ `POST /api/jobs/update` / `POST /api/jobs/toggle`
    （enabled 翻转，改完即生效）/ `POST /api/jobs/delete`；
  - `POST /api/scheduler/start`（Popen pythonw scheduler_daemon.py，无窗口，同
    batch_runner spawn 先例 panel.py:1336-1342）/ `stop`（按心跳 pid taskkill）/
    `cancel`（最小写集置 cancel_requested）/ `autostart {enabled}`（注册表 Run 写/删）；
  - 旧 `/api/tasks`（单号 schtasks）端点与页面入口不再作为主路径（保留实现供旧任务查询/
    清理收尾；是否整段移除由 plan 结合 verify 既有断言裁定，spec 方向 = 新页接管权威）。
- 前端轮询沿用既有 `refreshStatus`（~5s），面板关着不影响调度（守护独立）。

### 4.6 自启与心跳细节

- 开机自启 = 注册表 Run：`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，
  值 `DouyinAutoFireScheduler` = `"<pythonw.exe>" "<BASE>\scheduler_daemon.py"`；
  面板开关 = winreg 写/删该值（标准库，无 COM/第三方依赖）。
- 守护进程自身 `os.chdir(BASE)` + `sys.path` 注入（runner.py:48-50 同款），确保登录自启时
  工作目录与模块导入正确。
- 守护启动命令不弹窗（pythonw）；执行任务时浏览器真实有头（config headless:false，指纹纪律）。

### 4.7 迁移与旧机制收尾

- **旧配置迁移**：面板「一键迁移」（幂等，仅当任务库为空且某号存在历史 `schedule.time`）：
  逐号生成一条任务 `{account, time=历史值, targets=该号 targets 全量副本, texts=该号
  message.texts 副本, enabled=true}`；不改写 user_data.yaml（手动数据原样保留）；
  迁移产物默认「目标=全量、文案=账号已存」——与手动数据解耦后用户可再逐条改。
- **旧任务清理**：上节按钮调用 `schtasks /Delete /TN <旧名> /F`（查询存在才删）；
  同时保留 main.py 迁移提示已有指引（main.py:601-602）。清理后**仓库不再注册任何新系统定时任务**
  （verify 断言相应改造，见六）。
- CLI 交互入口（main.py `setup_auto*`/`try_register_task`）保留实现（verify 既有字面不破坏），
  但交互文案提示「多任务定时请在面板配置」，不再作为推荐路径。

### 4.8 RED 断言概念清单（字节级由 plan 落地，RED 态须 0 命中）

- 注入缝：panel.py 中 `trigger_run`/`_worker` 新参数形态 token、`cfg["targets"]` 注入 token、
  `persist_texts` 写回条件 token（新增 token；既有 token 全部保留）；
- 任务库：`scheduler_jobs.json` 路径/字段、`/api/jobs` 系列端点字面、面板页「新建定时任务」等
  页面 token（plan 定字，RED 态 grep 0 命中）；
- 守护：`scheduler_daemon.py` 存在、`DAEMON_STAGGER_MINUTES = 15`、心跳文件名、
  `CurrentVersion\Run` 自启键、`cancel_requested`、`fired` 补跑语义 token（概念，字节 plan 定）；
- douyin.py 零改动：现有 douyin 断言全量保留可复跑。

---

## 五、错误处理（场景 × 行为）

| 场景 | 行为 |
|---|---|
| 到点但账号未登录（browser_data 缺失） | 预检 skipped：「该号未登录，请先扫码」；队列继续下一条 |
| 目标不存在/会话失效 | 既有审计链（no_match/failed_targets）→ 该任务 last_result = partial/error + 失败目标名单（复用 run 层，不新造） |
| 守卫被占（手动/一键出发/另一任务在跑） | 排队等待不跳过；触发被拒重试 3 次后该任务 error（诚实记录），队列继续 |
| 守护进程崩溃 | 心跳停更 → 面板红点 + 一键重启；已发起任务（fired=running）重启后复核收尾，不重发；未发起任务自然补跑 |
| 任务文案/目标为空、账号被删 | 创建时拒绝；运行中遇到（任务被删后残留）→ skipped + reason，不自锁 |
| 电脑睡眠/关机错过时刻 | 当日恢复后补跑一次（fired 判定天然支持）；跨天不补 |
| 跨天 | `sched_state.date` 变化 → fired/queue 重置；last_results 保留最近一次供展示 |
| 状态/任务文件损坏或半写 | 读侧解析失败 → 视为空/None（不抛死循环）；写侧唯一 tmp + os.replace；守护读 jobs.json 失败 → 当轮无任务 + 心跳记 last_err，不自杀 |
| 队列运行中用户取消 | 当前任务自然收尾，队列剩余 skipped(用户取消)；不杀浏览器 |
| 手动跑完刚 10 分钟、定时到点 | 错峰公式 max(now, prev_run_end+15) → 定时任务自动等满 15 分钟再起（prev_run_end 启动时扫各号最新 run end） |
| 系统时间回拨 | 不做专门处理（HH:MM + 日期判定；fired 键含日期防同日重复），列入风险表 |

---

## 六、验证方案

### 6.1 基线（已实测）

2026-09-08 `./.venv/Scripts/python.exe verify.py`：**通过 121 / 失败 2**（exit 1）。
2 失败 = 「账号任务 DouyinAutoFire-<别名> 已注册」探测（本机无按号任务的环境态，证据 A9）。
新机制落地后第 3 节该组断言改造/移除 → 期望**全绿**（RED/GREEN 数字在 plan 中按实测重算）。

### 6.2 RED → GREEN 分层

- RED 先行独立提交：按 4.8 概念清单写断言（新增 token 在当前代码 0 命中；文件存在性断言用
  `read(f) if exists else ""` 守卫，防脚本崩）；既有断言不删改（除第 3 节注册探测按 plan 逐条处置）。
- 实现层 GREEN：注入缝 → 任务库模块 → 守护主循环 → 心跳/自启 → 面板 API/页面 → 迁移与清理。
- **单元级打桩冒烟**（守护状态机，配方沿 `references/red-green-smoke.md`）：monkeypatch 时间源/
  sleep/`panel.trigger_run`（写假 run meta，保留真 `_load_meta` 读文件轮询）、jobs 指向 tempfile
  假任务表 → 断言 `sched_state.json` 终态：到点触发、同刻多条按序顺延、错峰 15 生效、cancel、
  跨天重置、补跑一次不重复、崩溃后 fired=running 复核不重发。断言看状态文件 JSON 终态，不看日志。
- **功能冒烟**：面板 API curl 冒烟（jobs CRUD、scheduler start/stop/cancel/autostart 读写真实
  注册表 Run 键并还原）；守护真跑一轮（任务目标用假名/无害文案或临时停用真实任务）留心跳与状态证据。
- **真实发送冒烟**：对真实目标发送需用户逐次授权（提供目标名+无害文本），授权前只交付代码与
  演示级证据。
- 隐私红线：本 spec/plan/status/verify/代码注释/评审证据全程不得出现真实账号别名、真实目标名、
  真实文案；扫描命令不内联真实名（从 gitignored 数据动态读取再扫）。

---

## 七、风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 守护进程无人值守存活（挂了=当天不发） | 心跳落盘 + 面板红点提示 + 一键重启；自启兜底；主循环整轮 try/except 记 last_err 不自杀 |
| R2 | 崩溃/重启导致重复发送 | 触发成功即写 fired=running+run_id，重启复核既有 run 不重发（4.3⑤）；补跑仅 fired 未记时发生 |
| R3 | 定时文案写回账号配置污染手动文案 | `persist_texts=False` 注入缝默认隔离（4.4）；verify 断言锁定 |
| R4 | 睡眠/关机错过 | 已拍板补跑一次（拍板⑥）；整天关机则当日不发（用户接受） |
| R5 | 面板与守护双写状态竞态 | 写方职责划分（jobs.json 仅面板；state/heartbeat 守护，cancel 面板最小写集）；BAT 落盘铁律全沿用 |
| R6 | 双守护实例并发执行破坏串行纪律 | 心跳 pid 存活检测防双开 |
| R7 | verify 既有断言改造范围失控 | 仅第 3 节注册探测按 plan 逐条处置；其余断言全保留；改后跑全量比对 |
| R8 | 一键出发(batch)与定时队列同点竞争 | 同走全局守卫：先到先得，双方都排队不丢（batch 3 次放弃的既有语义保留）；面板状态互斥提示 |
| R9 | 守护进程运行中跨长时段（多任务错峰串联）静默 | 心跳含 current + 队列进度，面板可见；取消入口随时可停 |
| R10 | 系统时间回拨/时区变更 | 日期键防同日重复；极端回拨不做补偿（个人低频场景可接受） |

---

## 八、待确认

- 全部设计分叉已于 2026-09-08 会话拍板（头部评审拍板记录 ①~⑦），无剩余规格级问题。
- 遗留执行授权：真实发送冒烟需用户逐次授权（目标名+无害文本）；「一键迁移」与「清理旧系统任务」
  由用户在面板点击执行（agent 只交付代码与指令，不代跑涉及真实账号的动作）。
- verify 第 3 节既有断言的具体逐条处置（改/删/换探测对象）留 plan 定夺，spec 已给方向（守护
  心跳/自启探测取代按号 schtasks 注册探测）。

---

## 九、实施顺序（供 plan 参考）

1. 注入缝：`trigger_run/_worker` 加 `targets`/`persist_texts` + run meta targets 用参数 + verify
   RED/GREEN（既有调用方零感知复跑）；
2. jobs 存取模块（scheduler_jobs.json 读写、字段校验、原子写）；
3. 守护主循环 + 队列状态机（打桩冒烟先行：到点/顺延/错峰/取消/跨天/补跑/崩溃复核）；
4. 心跳 + 注册表自启 + 面板启停/取消端点；
5. 面板 /api/jobs CRUD + 「定时任务」页改造（状态卡/任务表/新建编辑表单）；
6. 迁移（一键迁移旧 schedule.time）与旧 schtasks 清理按钮；
7. verify 第 3 节断言改造 + 全量全绿；
8. 待用户授权的真实运行核验（日志/心跳/执行记录人工核对）。
