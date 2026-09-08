# 一键出发：全账号串行批量执行（号间强制错峰）— 设计文档（spec）

- 日期：2026-09-08
- Task-ID：BAT-001
- 状态：待评审
- 决策来源：2026-09-08 用户需求「目前有两个账号，想在首页添加一个『一键出发』，
  同时触发两个账号的私聊任务」。需求澄清（会话拍板，见下「评审拍板记录」）：
  ① 执行方式 = **串行排队 + 号间强制错峰 ≥15 分钟**（沿用 MAI-001 拍板的风控纪律，
  不是字面同时开两个浏览器）；② 各号发送**各自已保存的文案**。
  MAI-001 已批准 spec（`2026-09-04-multi-account-isolation-design.md`:90）曾把
  「`--all` 一键全账号、跨账号并行执行」列为非目标——本任务只做其中的「一键全账号
  （串行+错峰）」半，**并行仍是非目标**。
- 评审拍板记录：（待 Reviewer APPROVED 后补）

---

## 一、背景与问题

### 1.1 用户需求

首页现有「一键触发」**只作用于当前选中账号**：顶部账号栏切号（当前 2 个账号，
示例 <号A>/<号B>），触发按钮、会话勾选、内容输入、定时任务、执行记录全部随号联动。
用户每天要给两个号各自私聊一轮，现在要手动切号点两次；希望**一个按钮把全部已添加
账号顺次跑完**（「同时」经澄清 = 串行错峰，见头部决策来源）。

### 1.2 现状约束（全部有代码锚，见二）

1. **全局串行是硬机制**：进程内 `_run_lock` + 跨进程守卫文件 `userdata/.running`
   （MAI-001 spec:77-81「同一时刻绝不并发，风控纪律优先于吞吐」；UI/文档提示
   错峰 ≥15 分钟）。任何一路触发（面板手动 / 扫码窗口 / 会话同步 / 每号 schtasks 定时
   runner）都先过守卫，同一时刻只允许一个号跑一个浏览器。
2. **账号数据已完全隔离**（MAI-001 已交付）：每号 `userdata/accounts/<别名>/` 下各自
   `user_data.yaml`（targets/文案/定时）、`browser_data/`（登录态）、`runs/`（执行记录）。
   `runner.py` 早已证明「独立进程 import panel → trigger_run(account) → 轮询 run meta」
   的旁路执行模式可行且不依赖面板常驻（定时任务即此模式）。
3. **面板触发链路**：`POST /api/trigger` → `trigger_run(texts, account)` → `_worker`
   起 daemon 线程（强制可见浏览器）→ `DouyinStreak.run()` → 写 run meta
   （id/account/status/targets/texts/failed/failed_targets/error/start/end）→
   收尾回写该号文案、prune 该号 runs 至 3 条。

### 1.3 隐藏动机（推测，已在需求澄清中确认方向）

两个号的 schtasks 定时任务若设同一时刻，到点各自触发时**后到者守卫被占会直接跳过、
不排队补跑**（`runner.py` 收到 `trigger_run` 返回 None 即记 run.log 退出）。「一键出发」
可视为用户要一个**可靠地『把全部号都跑完一轮』的入口**——由它代替对「同点定时」的依赖。

---

## 二、勘察结论（证据表）

| 编号 | 结论 | 证据 |
|---|---|---|
| A1 | 每号独立目录（配置/登录态/执行记录），两号已建好 | `userdata/accounts/<别名>/{user_data.yaml,browser_data,runs}`；main.py:119-131 `account_root`/`list_accounts` |
| A2 | 跨账号强制串行：全局守卫文件 + 进程内锁双保险 | main.py:317-356 `acquire_run_guard`（`userdata/.running` 独占，含 account+pid）；panel.py:116-119 全局锁变量 |
| A3 | 面板所有「一键触发/扫码/同步」动作按**当前账号**解析，动作路径无账号即拒绝 | panel.py:259-275 `_resolve_account`；:1220 `/api/trigger`、:1145 `/api/setup-login`、:1168 `/api/sync-conversations` |
| A4 | 触发被占用时返回 None（不排队），调用方记日志跳过 | panel.py:491-515 `trigger_run`（`_current_run`/`_login_running` 或守卫被占 → None） |
| A5 | 单次运行全生命周期已有完整落盘：meta JSON + log + 截图；状态含 running/success/partial/error/needs_verify | panel.py:524-533 meta 初始字段、:441-461 终态判定 |
| A6 | 独立进程执行已有仓库先例：runner.py import panel → trigger_run → 轮询 meta 至非 running | runner.py:47-111（schtasks 定时路径，与面板进程无关） |
| A7 | 前端所有请求自动携带当前账号（`activeAccount`）；触发/登录/同步按钮在 `running || login_running || 他号运行` 时置灰 | panel.html:419-425 fetch 封装；:526-530 refreshStatus 置灰逻辑；:1021 `setInterval(refreshStatus, 5000)` |
| A8 | verify.py 基线：2026-09-08 实测 **105 通过 / 2 失败**（2 失败 = 账号任务未注册的环境态，与本任务无关） | `./.venv/Scripts/python.exe verify.py` 实测 |
| A9 | MAI-001 拍板：错峰 ≥15 分钟、绝不并发、串行锁保留、`--all` 全账号当时列为非目标 | `docs/superpowers/specs/2026-09-04-multi-account-isolation-design.md`:76-81、:90 |
| A10 | 每号已保存文案/目标可从账号配置直接读（批量无需面板输入框） | `load_config(account)` 返回 `message.texts`/`targets`；panel.py:815-830 `api_state` 同源 |

---

## 三、目标与非目标

### 目标

1. **首页一键出发**：面板新增全局「一键出发」按钮，点击后把**全部已添加账号**
   （点击时刻快照）顺次跑完各自私聊任务——每号用自己的已保存文案与已保存目标会话。
2. **串行 + 强制错峰**：一次只跑一个号（沿用现有守卫，零并发语义变更）；号间
   **结束→启动间隔 ≥15 分钟**（上一号运行实际结束后再等满 15 分钟才启动下一号，
   从「上一号 run meta 的 end」起算，比 start 起算更严格、语义无歧义）。
3. **独立执行器进程**：批量由新模块 `batch_runner.py`（镜像 runner.py 模式）在
   **面板进程之外**顺序驱动，面板关闭/崩溃不影响已排队列；面板只负责启动执行器与
   展示进度。面板在批量期间可正常开关。
4. **进度全程可见**：批量横幅实时显示每号状态（等待守卫 / 错峰等待倒计时 / 运行中 /
   成功 / 部分失败 / 失败 / 需人工验证 / 已跳过），最终汇总指向各号执行记录。
5. **防双发**：某号在本批量启动后已被任何来源执行过（如定时任务恰巧到点），批量
   触发前检出任一即跳过该号并明示原因，避免同号一天两轮的无意重复。
6. **可取消**：批量等待/错峰期间可取消（当前正在跑的号自然跑完，号间停止）。
7. `verify.py` 新增防回归断言（先 RED 后 GREEN）；同步用户文档。

### 非目标（本次不做）

- **不做跨账号并行/真·并发**（MAI-001「绝不并发」不因本任务改变；守卫与进程内锁
  语义零改动）。
- 不做 `--all` 的 CLI/定时入口（本任务只做**面板首页**一键出发；执行器是独立模块，
  「定时全号批量」未来可薄薄复用，另行排期）。
- 不做批量中断断点续跑：执行器进程异常退出后，剩余号需用户重按/单号补跑（横幅明示
  「已中断」，前端提示重按会令已完成号再发一轮——与今天手动触发两轮等价，用户自决）。
- 不做单号子集勾选、不做失败号自动重试、不做号内失败目标重发（沿用单次运行现有
  语义：failed_targets 记录，用户自行处理）。
- 错峰间隔不做面板配置项：常量 15 分钟（本次拍板值），`batch_runner` 提供仅供测试/
  演示的 CLI 覆盖参数（默认仍 15）。
- 不改每号 schtasks 定时任务（同点冲突现状不变）；不改 douyin.py 发送核心
  （零改动，批量只是触发层组合）；不新增审计 tag。
- 不处理既有基线 2 FAIL（账号任务注册属用户在面板操作，MAI-001 遗留核对项）。

---

## 四、方案设计

### 4.1 总体架构：独立子进程批量执行器

```
面板进程 (panel.py)                    独立子进程 (batch_runner.py)
─────────────────────                  ─────────────────────────────
POST /api/trigger-all                  pythonw batch_runner.py --batch-all
  ├ 校验：无批量激活 + 面板无运行     （resolve_python windowless 同 create_task）
  ├ 防双启：batch_state 存在且 pid 存活 → 拒绝
  ├ Popen 启动执行器（脱离面板生命周期，CREATE_NO_WINDOW）
  └ 立即返回 {ok}
GET /api/batch-state  ◄────轮询────    userdata/batch_state.json（执行器原子写）
  └ 渲染批量横幅 / 置灰单号按钮         ┌ 循环 list_accounts 快照：
POST /api/batch-cancel                 │   ① 预检该号（目录/文案/目标/登录态）
  └ batch_state.cancel_requested=true  │   ② 等待守卫空闲（进程内 _run_lock 无关，
                                       │      只等 .running 释放）
                                       │   ③ 错峰等待：距上一号 end ≥15 分钟
                                       │   ④ 防双发复查：本批量 started_at 后该号
                                       │      已有 run 结束 → skip
                                       │   ⑤ panel.trigger_run(该号文案, account)
                                       │      （复用完整运行链路，headless=None=配置）
                                       │   ⑥ 轮询该号 run meta 至非 running
                                       │   ⑦ 更新 batch_state → 下一号
```

选**独立进程**而非面板内调度线程的理由（决策记录）：

1. 一个批量 ≈ 每号运行几分钟 + (号数-1)×15 分钟 ≈ 半小时级。面板内 daemon 线程方案
   下面板一关，未排到的号**静默丢失**（线程随进程消亡）——违背本仓库「执行不留静默
   缺口」的一贯纪律（SIV-002 failed_targets 同源动机）；独立进程无此问题，面板开关自如。
2. 与既有 `runner.py`（定时执行也走独立进程 import panel）哲学一致：**执行与展示分离**，
   面板进程只是「启动器 + 只读状态源」。
3. 执行器进程内 import panel 调用 `trigger_run` 的路径已被 runner.py 实证可靠
   （A6）；run 记录、截图、failed_targets、prune 等全链路零改动复用。

### 4.2 batch_runner.py 执行器流程（新文件，根目录，与 runner.py 并列）

入口：`pythonw batch_runner.py --batch-all [--stagger-minutes N]`。

- `--stagger-minutes`：默认 15；仅测试/演示覆盖用（verify 冒烟与功能冒烟缩短等待）。
- 启动即写 `userdata/batch_state.json`（独占语义：`os.open(O_CREAT|O_EXCL)` 同守卫
  模式；已存在且 pid 存活 → 报「已有批量在跑」退出 exit 2；陈旧残留（pid 不存在）
  删除后重试一次）。
- **账号快照**：启动时 `list_accounts()` 拷贝（运行中新增账号不纳入本期）。
- 每号处理（顺序按 list_accounts 排序，当前 2 号即其自然序）：
  1. 预检并落状态：无 `user_data.yaml`/目录被删 → `skipped`（reason=账号不存在）；
     无已保存文案 → `skipped`（reason=未保存内容）；无 targets → `skipped`
     （reason=未配置目标会话）；无 `browser_data` → `skipped`（reason=尚未登录，
     请先扫码）；——预检命中任一跳过项即进入下一号（**不占错峰等待**，无浏览器动作）。
  2. 等待守卫：轮询 `userdata/.running`（每 ~5s），空出即继续——覆盖「批量启动瞬间
     另一号正被定时/手动跑」的场景（该轮结束后自动接续）。等待期间状态=`waiting_guard`。
  3. 错峰等待：`next_start_at = 上一号实际运行 run meta 的 end + 15 分钟`；未到则
     sleep 轮询（每 ~5s 检查取消标志）。第一号无前置，直接进入触发。期间状态
     `waiting_stagger`，state 写 `next_start_at` 供前端倒计时。
  4. 防双发复查：读该号最近一次 run meta（`runs/<最新>.json`），若其 `end` 晚于
     **本批量 started_at** → `skipped`（reason=本批量开始后已执行过，防同号双发）。
     这是关键兜底：15 分钟错峰等待窗口内若 schtasks 恰好把该号跑了，执行器不再补发。
  5. 触发：`panel.trigger_run(该号已存文案, account=该号, headless=None)`
     ——文案来自 `load_config(account)["message"]["texts"]`；headless=None 走
     config（同 runner.py 语义，有头可见浏览器、指纹正常）。返回 None（守卫又被占等
     极端竞争）→ 回第 2 步重试（上限 3 次后该号 `error`）。
  6. 轮询该号 run meta 至非 running（每 ~3s），收终态：
     `success / partial（failed_targets 随行）/ error / needs_verify`，写该号行
     （run_id + end + failed 名单，供横幅直接展示，无需二次请求）。
  7. 循环内任何单号异常（load_config 抛错等）→ 该号 `error`+原因，**不中断整批**。
- **取消**：每轮 sleep 醒来先查 `batch_state.cancel_requested`——错峰等待中立即退出；
  运行中号自然跑完（第 6 步收尾）后退出；退出前 state 标 `cancelled` + 剩余号
  `skipped(cancelled)`。不中途杀浏览器（遵守「绝不留下半截运行」纪律）。
- **收尾**：全部号终态后 state 标 `finished`（写各号结果 + finished_at）。进程退出。
- 全程向 `userdata/run.log` 留痕（`[BATCH]` 前缀行：启动/每号开始结束/取消/崩溃），
  崩溃由最外层 try/except 兜底写 run.log（镜像 runner.py:37-45 `_crash`）。
- **状态文件原子写**：每次更新先写 `batch_state.json.tmp` 再 `os.replace`，
  防面板读到半个 JSON；仅状态迁移时写（每秒倒计时由前端本地算，后端不刷盘）。

`batch_state.json` 字段（userdata/ 下，gitignored，含真实别名无隐私问题）：

```json
{
  "pid": 12345, "started_at": "2026-09-08 12:00:00",
  "stagger_minutes": 15, "accounts": ["<号A>", "<号B>"],
  "cancel_requested": false, "phase": "running",
  "finished_at": null, "crashed": false,
  "items": {
    "<号A>": {"status": "success", "run_id": "…", "start": "…", "end": "…",
              "failed_targets": [], "reason": null},
    "<号B>": {"status": "waiting_stagger", "run_id": null,
              "next_start_at": "2026-09-08 12:19:00", "reason": null}
  }
}
```

`status` 取值：`pending / waiting_guard / waiting_stagger / running / success /
partial / error / needs_verify / skipped / cancelled`；`reason` 仅 skipped/error 用。

### 4.3 面板 API（panel.py 新端点 ×3，均与账号无关，忽略前端自动附加的 account 参数）

| 端点 | 方法 | 行为 |
|---|---|---|
| `/api/trigger-all` | POST | ① 本进程 `_current_run/_login_running/_sync_running` 任一占用 → 423「面板当前有任务/登录/同步在运行，结束后再一键出发」；② batch_state 激活（pid 存活）→ 423「批量一键出发已在运行」；③ 无账号 → 400；④ resolve_python(windowless) 探测（复用 create_task 同款）→ 失败 500；⑤ Popen 启动 `pythonw batch_runner.py --batch-all`（cwd=BASE、隐藏窗口）→ 200 `{ok, accounts:N}` |
| `/api/batch-state` | GET | 读 batch_state.json → 200 `{active, pid_alive, phase, items 数组…}`；无文件 → `{active:false}`。pid 已死且 phase 非终态 → 返回 `{active:false, crashed:true, …}`（前端横幅显示「批量已中断」并允许重按） |
| `/api/batch-cancel` | POST | batch_state 存在 → 置 `cancel_requested=true` → `{ok}`；不存在/已终态 → 400「无进行中的批量」 |

- **批量激活期间单号动作拒绝**：`/api/trigger`、`/api/setup-login`、`/api/sync-conversations`
  入口统一加查——batch_state 激活（pid 存活）→ 拒绝并回「批量一键出发进行中，请先
  取消或等待结束」。定时任务（schtasks → runner.py 独立进程）**不读面板**，无法拦截，
  由 4.2 第 4 步防双发兜底。
- `/api/select`（切号）、执行记录/会话/定时任务**只读路径不拦**（批量期间可自由查看）。

### 4.4 前端（panel.html）

- **按钮**：顶部账号栏右侧（`addAccountBtn` 旁）加「一键出发」主按钮，副标实时
  `→ N 个账号`（N=list_accounts）。点击 → `POST /api/trigger-all` → 成功后轮询
  `/api/batch-state`。无账号时按钮隐藏；批量激活或面板有运行/登录/同步时置灰
  （并入既有 `refreshStatus` busy 判定，:526-530 扩展）。
- **批量横幅**（账号栏下方，任意页签可见，仅 `active || crashed` 时显示）：
  - 逐号一行：别名 + 状态徽章（复用 `.badge` 配色：运行中 brand / 等待 muted /
    成功 green / 失败 red / skipped gray）+ 行内说明（错峰等待显示
    「距启动 00:12:34」本地倒计时，源 `next_start_at`；失败显示 failed_targets 名单）。
  - 头部一行：进度「第 i/N 号」+ 预计完成时刻（估算 = 当前号 next_start_at + 剩余
    号数×(均时 + 15 分钟)，仅展示）+「取消」按钮（确认后 POST /api/batch-cancel；
    取消后文案提示「当前号跑完后停止」）。
  - 终态横幅：汇总（成功/部分/失败/跳过各几）+ 每号点击行 → 自动切该号并跳
    「执行记录」页签（复用既有 runs 渲染，无需新详情视图）。
  - crashed 态：红色提示「批量执行器已中断，已完成 i/N 号；重按一键出发会令已完成
    的号再发一轮」。
- **轮询并入现有 5s timer**（panel.html:1021 `refreshStatus` 内追加
  `loadBatchState()`）；倒计时每秒 tick 用本地 `setInterval(1s)` 仅更新数字。

### 4.5 verify.py 防回归断言（先 RED 后 GREEN，意图级；精确字面在 plan 落定）

新增断言规划（全部用占位符/通用词，不出现真实别名）：

1. `panel.py` 提供 `/api/trigger-all` 路由（锁路由分发处字面）。
2. `panel.py` 批量激活拒绝单号动作（锁 `/api/trigger` 入口处批量检查字面，如
   `"批量一键出发进行中"` 独立 token）。
3. `panel.py` 启动执行器复用 `resolve_python`（锁调用形态）且命令含 `batch_runner.py`。
4. `batch_runner.py` 文件存在且含 `--batch-all` 解析（文件级断言，同 panel/douyin 断言惯例）。
5. `batch_runner.py` 错峰常量：锁 `stagger_minutes` 与 `15` 关联字面
   （如 `default=15` / `15 * 60`，plan 定形）。
6. `batch_runner.py` 防双发复查：锁「读最近 run meta 的 end 与本批量 started_at 比较」
   关键实现字面（如 `started_at` 比较 token）。
7. `batch_runner.py` 原子写：锁 `batch_state.json.tmp` + `os.replace`（或等价形态）。
8. `batch_runner.py` 取消标志：锁 `cancel_requested` 消费处字面。
9. `batch_runner.py` 状态落盘：锁 items 状态机字面（如 `waiting_stagger` / `waiting_guard`）。
10. `panel.py` 提供 `/api/batch-state` 与 `/api/batch-cancel` 路由。
11. `panel.html` 含「一键出发」按钮与批量横幅渲染函数（锁按钮 id 与横幅容器/状态徽章
    复用字面）。

RED 期望 = 既有 2 FAIL（A8）+ 新增约 11 条；GREEN 期望 = 仅剩既有 2 FAIL。

### 4.6 文档同步清单

| 文件 | 现状 | 改为 |
|---|---|---|
| `docs/管理面板使用指南.md` | 三块页签 + 账号栏说明，无全账号批量 | 新增「一键出发（全部账号）」节：位置、串行+错峰 15 分钟语义、批量横幅各状态含义、取消、批量期间单号按钮禁用、执行器独立进程（面板可关）说明 |
| `docs/工作原理与架构.md` | 目录布局/执行纪律节，无 batch 模块 | 模块职责补 `batch_runner.py`；目录布局补 `userdata/batch_state.json`；执行纪律段补「一键出发 = 号间错峰 ≥15 分钟的串行队列」 |

---

## 五、错误处理

| 场景 | 行为 |
|---|---|
| 批量激活中再点一键出发 / 重复 spawn | batch_state 独占创建失败（pid 存活）→ 执行器 exit 2 + run.log；面板 423 提示已有批量在跑 |
| 批量启动瞬间面板有运行/登录/同步 | 面板端 423 拒绝（不让两路同时等守卫制造混乱）；执行器自身的守卫等待只覆盖「面板外的运行」 |
| 面板被关闭/重启，批量仍在跑 | 执行器独立进程不受影响；面板重开后 `/api/batch-state` 恢复横幅渲染（pid 存活判定）；批量期间 `/api/shutdown` 不禁用 |
| 执行器进程异常退出（崩溃/被杀） | 最外层 try/except 写 run.log；state 停在中途态 → 面板 GET 时 pid 已死 → 前端 crashed 横幅 + 允许重按（新批量覆盖旧 state） |
| 执行器等待期间该号被 schtasks 抢先跑了一轮 | 触发前防双发复查命中 → skipped（reason 明示），不补发 |
| 该号文案/目标为空、未登录、目录被删 | 预检跳过该号（不占错峰等待），reason 进横幅；批量继续其余号 |
| 守卫被占（定时任务或另一手动运行进行中） | waiting_guard 轮询等待（~5s），该轮结束后自动接续 |
| trigger_run 返回 None（极端竞争） | 回退守卫等待重试，≤3 次后该号 error（不整批中断） |
| 某号运行 partial / error / needs_verify | 该号如实记录（failed_targets 名单随行），**继续下一号**（号间错峰照常）；needs_verify 号横幅提示需人工处理 |
| 用户点取消 | 错峰/守卫等待中立即停；运行中号自然收尾后停；state=cancelled，剩余号 skipped(cancelled) |
| 旧 batch_state.json 字段缺失（版本演进） | 前端/后端读侧统一兜底（`|| []` / `get` 缺省），参考既有 run meta 兼容先例 |
| 15 分钟倒计时期间用户手动跑其他号 | 允许（守卫语义不变）；可能使后序该号防双发 skip——语义一致，横幅原因可见 |

---

## 六、验证方案

项目无测试框架，沿用「verify.py 自检 + 冒烟」双轨（仓库先例）。

1. **RED**：按 4.5 新增 verify.py 断言 → 跑 verify → 确认 FAIL = 既有 2 + 新增 N，
   新增失败原因均为「保证未实现」。
2. **GREEN**：按 4.1-4.4 实现 → 跑 verify → 新增全过、仅剩既有 2 FAIL。
3. **单元级冒烟（可自动化，不动真实浏览器/网络）**：直接 import batch_runner 打桩——
   假账号目录（userdata 外临时目录 + monkeypatch main.USERDATA_DIR/ACCOUNTS_ROOT）、
   `--stagger-minutes 0`、`panel.trigger_run` 打桩为「写个假 run meta 并 sleep 0.5s」，
   断言执行器按序处理两号、state 终态齐全、取消路径生效。留 test-results 证据。
4. **功能级冒烟（需用户授权，见八-1）**：`--stagger-minutes 1` 对两个真实账号各发一轮
   无害文本（各号 1 个既有目标），验证：一键按钮 → 横幅两号行推进（运行→错峰倒计时→
   运行）→ 各号 run meta 落盘 → 终态汇总 → 取消按钮路径。整体 ~8-10 分钟。
   冒烟间隔参数仅 CLI 覆盖，面板默认始终 15 分钟。
5. **未授权冒烟时的收尾核对**：下次真实使用一键出发后人工核对横幅/执行记录。

**无法自动化的部分（如实声明）**：verify.py 只能锁结构（token/路由/调用形态）；
「15 分钟等待真实发生」「面板关闭后批量继续跑完」这类时序行为由功能冒烟或真实使用
弥补。

---

## 七、风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | 批量期间 schtasks 定时到点与批量错峰窗口竞争（同号双发或互相拖延） | 防双发复查（4.2-④）只拦「已跑过」；定时跑在批量等待窗口只会被检测为已执行→skip，不会并发（守卫硬拦） |
| R2 | 半小时级批量中用户关面板，横幅消失引发「任务去哪了」困惑 | 执行器独立 + run.log `[BATCH]` 痕迹 + 面板重开恢复横幅；文档写明「面板可关，执行继续」 |
| R3 | 两个号错峰 15 分钟仍显「不够错峰」（同 IP 连坐担忧升级） | 本任务严格沿用 MAI-001 拍板值；若用户日后要加大间隔，常量/CLI 参数即改（非目标内不做 UI 配置） |
| R4 | 批量触发瞬间与手动/定时「双路同时等守卫」，释放瞬间竞争 | 守卫文件 O_EXCL 原子性保证只有一个赢家；输家退回避守卫等待重试（≤3 次） |
| R5 | batch_state.json 并发写撕裂 / 面板读到半截 | 全量原子写（tmp + os.replace）；面板读侧 try/except 兜底视为 inactive 并提示刷新 |
| R6 | 新端点/按钮字面与既有 verify 断言冲突 | 新断言独立成块（4.5）；路由插入位置避开既有锁定字面（plan 逐处核对，SIV 先例） |
| R7 | 冒烟/演示用 `--stagger-minutes` 被误用于生产 | 面板启动路径不传该参数（固定默认 15）；参数仅在手动 CLI 出现，文档标注「测试用」 |
| R8 | 批量中某号 needs_verify，浏览器已关，用户不知要处理 | 横幅终态醒目提示 + 该号行提供「去处理」引导（扫码/单号触发），沿用既有 needs_verify 语义 |

---

## 八、待确认

1. **功能级冒烟授权**（实现全绿后）：用 `--stagger-minutes 1` 对两个真实账号各发一条
   无害文本验证全链路？按仓库纪律必须用户明确点头才执行。
2. **错峰间隔确认**：按拍板「≥15 分钟」，本期实现固定 15 分钟（常量+测试覆盖参数），
   不做面板配置——是否认可？（如需 30/60 分钟请直接说，只改一处常量。）

---

## 九、实施顺序（供 plan 参考）

1. `verify.py` 先 RED：新增 4.5 断言块 → 跑红确认（既有 2 + 新增 N）
2. `batch_runner.py` 新建：4.2 执行器（独占 state → 逐号 预检/守卫/错峰/防双发/触发/轮询 → 收尾）
3. `panel.py`：4.3 三端点 + 批量激活期单号动作拒绝
4. `panel.html`：4.4 一键出发按钮 + 批量横幅 + busy 置灰扩展 + 轮询
5. `verify.py` 转 GREEN（仅剩既有 2 FAIL）
6. 单元级冒烟（六-3）→ 功能级冒烟（待授权，六-4）
7. 文档同步（4.6）+ status 推进
