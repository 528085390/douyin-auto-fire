# SCH-001 Spec Review（定时任务条目库 + 常驻调度器）

- 评审对象: `specs/2026-09-08-scheduled-jobs-daemon-design.md`（Task SCH-001，348 行）
- 评审日期: 2026-09-08
- 评审方式: Reviewer 读 spec 全篇 + 逐行核对证据代码（panel.py / main.py / runner.py / batch_runner.py / douyin.py / panel.html / verify.py）+ grep 核实 RED 诚实性 + 实测 verify.py 基线与任务计划程序状态；未读 userdata/accounts/*/user_data.yaml 等真实数据
- **结论: APPROVED**（P0 无；P1×2 建议改，不阻塞；P2×5 列入 plan 实施注意）

## 评审发现

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| 1 | P1 | spec 4.3⑤「先落盘再跑」+ R2 | 防重发只覆盖「fired=running 已落盘」之后的崩溃；**触发成功（worker 线程已启动、浏览器已开）到 fired 落盘之间的崩溃窗口**，重启后该任务不在 fired → 重新入队补跑 → 已发目标可能重复发送。且该窗口内崩溃同时杀死守护进程内的 _worker 线程，半截 run 的 meta 会永久卡 running | 改为两段式：触发**前**先写 `fired[job_id]={status:"dispatching", at}` → 调 trigger_run → 成功后在原条目补 run_id/status=running；重启复核对「dispatching 且无 run_id」条目按时间戳陈旧（且该账号无对应 in-flight run）判定为未触发，允许重试。至少应在 spec 补一句把残余窗口与处置写死，plan 实现时落实 |
| 2 | P1 | spec 4.5 `/api/scheduler/stop`（按心跳 pid taskkill）+ 五节「队列运行中用户取消」行 | stop 与 cancel 并发语义未区分：cancel 已定义为「当前任务自然收尾不杀浏览器」（4.3⑦、错误表），而 stop=裸 taskkill 会把正在真实发送的 worker 线程连同浏览器一起杀掉——与仓库「执行不留静默缺口」「不中途杀浏览器」纪律（BAT-001 Code Review 固化）冲突；被杀 run 的 meta 卡 running，需等重启复核 15 分钟才收尾，期间面板显示永久「运行中」 | spec 应明确 stop 的并发行为：队列空闲/无 running 任务时直接退出；fired=running 存在时先置 cancel/stop 标志等当前 run 自然收尾再退出（或拒绝停止并提示）。与 cancel 的关系（stop 隐含 cancel 剩余队列）也应在 4.5 写清 |
| 3 | P2 | spec 4.3 主循环跨天重置（fired/queue 清零） | 边界丢任务：任务时刻 23:45–23:59 且因前一任务错峰/守卫排队**未触发（未写 fired）**就跨了午夜 → 重置清掉队列条目，而次日 00:01 起 `HH:MM(now)>=HH:MM(job.time)` 不成立 → 该任务当日静默丢失（不补跑、无记录）。仅当任务时刻 ≥23:45 且排队跨午夜时发生，概率极低 | 4.3 补一句：跨天重置时对「已入队未触发」条目记 `last_results={status:"skipped", reason:"跨天未及触发"}`（或明确接受该窗口并写注释），不静默丢 |
| 4 | P2 | spec 4.3 ①预检 / 五节错误表「任务被删后残留」行 | 队列条目携带的是**入队快照还是出队时重读 jobs.json** 未写明：若用入队快照，任务在入队后被删除/停用/编辑，条目仍会按旧数据执行（编辑目标后旧目标照发）；错误表只暗示了「残留→skipped」 | 显式写明「出队执行前按 job_id 重读 jobs.json：不存在/已停用 → skipped（任务已删除/停用），字段以最新为准」，防「删了还跑、改了还发旧的」 |
| 5 | P2 | spec 4.7 一键迁移（245-248）+ 4.5 迁移引导 | 迁移不改写 user_data.yaml → 历史 `schedule.time` 永远在；用户一键迁移后若删光任务库，引导横幅复活、可重复迁移，与用户「删除」意图冲突（生成重复任务） | 迁移完成后在 scheduler_jobs.json 记 `migrated_from_legacy: true`（或 state 记迁移标记），横幅条件加「且未迁移过」；顺带补：历史账号 message.texts 为空时迁移产物 texts 为空会被空校验拒绝，需明确该号跳过并提示 |
| 6 | P2 | spec 4.3 触发判定（165-168 行） | 新任务创建时刻已过当日 HH:MM（如 22:00 建 21:30 任务）→ 判定 now>=job.time 且未 fired → 下一轮扫描即触发发送，用户可能遭遇「建完即发」意外 | 语义上与拍板⑥「错过补跑」一致可保留，但表单/文档应提示「当日已过时刻的任务保存后会立即补跑一次」；不需要则先 enabled=false |
| 7 | P2 | spec 4.3 心跳（195-197）+ 4.5 状态卡 | 心跳「新鲜度」判定运行中/已停止的阈值未定；pid 复用风险未提（心跳含 boot_at 可区分重启后的新实例，但面板判停逻辑未写） | 建议面板判停阈值 ≥3× 主循环周期（~60s），心跳含 boot_at，防「启动 20s 内误判已停止」与 pid 复用误判存活 |

## 已核实安全（逐项核验）

- **① 证据表行号比对（A1–A12 逐条打开真实代码核对，全部准确）**：
  - A1 ✓ panel.py:1274-1286 `/api/trigger`；:458-536 `_worker`；:469 `load_config(account)`、:472-474 覆盖 `message.texts`、:480-481 `DouyinStreak(cfg).run()` 全中；
  - A2 ✓ panel.py:567-571 meta `targets` 由 cfg targets 快照；A3 ✓ panel.py:517-521 finally 内 `if texts:` → `update_message_texts` 写回（实际调用在 519）；
  - A4 ✓ douyin.py:78-85 `self.targets` 读取、:926-968 run 循环、:943 `self.failed_targets=[]` 重置、:967-968 append，与「_worker 覆盖 cfg[targets] 即注入、发送核心零改动」结论吻合；
  - A5 ✓ panel.py:812-818 为 create_task 内的 schtasks 命令拼装段（814 = pythonw runner.py `--run-once --account`，816-817 `/SC DAILY /ST`）；main.py:443-480 `try_register_task`、:359-361 `task_name` 全中。微调建议：`create_task` 函数定义实为 panel.py:778，812-818 是函数体内命令拼装段；
  - A6 ✓ runner.py:47-111（:88-89 取 api_state message_texts、:90 触发、:101-111 15min 轮询兜底）；A7 ✓ batch_runner.py:121-270 ①-⑦ 逐段吻合、`batch_state.json`/`.running` 路径属实；`--stagger-minutes default=15` 实为 337-338 行（spec 引 335-338 含 --batch-all，微调建议）；
  - A8 ✓ panel.py:1255-1267（update_targets + conversations cache 落盘）；A11 ✓ main.py:364-386 `resolve_account`（381-382 多账号 exit 2 列别名）、:601-602 迁移提示；A12 ✓ panel.py:1336-1342 Popen batch_runner、:1102 GET /api/tasks、:1161 adopt-legacy、:1306-1320 disable/enable/delete。
- **② 基线复核**：实测 `./.venv/Scripts/python.exe verify.py` = **通过 121 / 失败 2、EXIT=1**，与 spec A9/6.1 一致；2 失败均为按号任务 `DouyinAutoFire-<别名>`（别名已脱敏）「已注册」探测（verify.py:95-112 `_probe_task(task_name(a))`），环境态，spec 已声明。另实查任务计划程序：仅遗留 `DouyinAutoFire` 一条（无按号任务），与 A10 一致；
- **③ RED 诚实性（逐 token grep 实测 0 命中）**：仓库根/userdata 均无 `scheduler_daemon.py`、`scheduler_jobs.json`、`scheduler_state.json`、`scheduler_heartbeat.json`；panel.py 中 `/api/jobs`、`scheduler_jobs`、`scheduler_state`、`scheduler_heartbeat`、`CurrentVersion`、`DAEMON_STAGGER`、`persist_texts` 全部 **0 命中**（panel.py 内 `cancel_requested` 2 处命中属既有 BAT-001 batch-cancel 最小写集，与守护无关）；panel.html 中「新建定时任务」/`scheduler_jobs`/`/api/jobs`/`persist_texts` **0 命中**（现有页为单号「系统定时任务」区块，panel.html:352-377，与 4.5「整页改造」现状吻合）；
- **④ 设计漏洞扫描**：跨进程边界——守护/面板/runner/batch 共用 `.running` 守卫（main.py:51/317、batch ⑤ 守卫等待 + `_stale_guard_cleanup` pid 感知自愈，panel.py:534 finally 释放）与 run meta 读写，spec 4.3 ①-⑦ 镜像 batch_runner 状态机且补了 fired 先落盘/复核收尾/取消最小写集/错峰 prev_run_end 初值（守护启动时扫各号 `list_runs(keep=1)` 取最新 end，与 batch_runner:175 同语义）/跨天重置，覆盖完整；多写方竞态——jobs.json 单写方=面板、state/heartbeat=守护、cancel=面板最小写集（panel.py:1355 既有同款先例），符合 BAT 铁律（唯一 pid 后缀 tmp + os.replace + Errno13 重试 + 解析失败视为 None + 耗尽诚实报错）；崩溃恢复——心跳 pid 防双开、fired 复核不重发、jobs 读失败当轮无任务记 last_err 不自杀；双击防重由 schtasks 残留风险转移为心跳 pid 存活检测（R6）；睡眠唤醒/跨天补跑语义自洽（fired 键含日期、跨天重置、不跨天补）。**4.4 注入缝零感知核实成立**：现存 trigger_run 调用方共 4 处——runner.py:90（texts 位置参 + headless/account 关键字）、batch_runner.py:226-228（同）、main.py:619 `--run-once`（同）、panel.py:1283 `/api/trigger`（同）——新增 `*, targets=None, persist_texts=True` 纯关键字参数对全部调用方零影响；verify.py 既有断言（:126-129、:330、:388 等）均为文本/形态断言，不锁签名，不被破坏。spec 4.4 未列 main.py:619（CLI `--run-once`）这第 4 个调用方，但不影响零感知结论，建议实施顺序 1 复跑时一并覆盖；
- **⑤ 隐私**：全程未读 userdata/accounts/*/user_data.yaml 等真实数据；本报告全部使用 `<别名1>`/`<别名2>` 占位，未出现任何真实账号别名/目标/文案；
- **⑥ 结构与流程合规**：头部含日期/Task-ID/状态/决策来源/评审拍板记录（①-⑦ + MAI-001 保留项声明 + 取代 schtasks 形态的追溯）；正文节序一背景→二证据表→三目标与非目标→四方案→五错误处理→六验证→七风险→八待确认→九实施顺序，与仓库固定骨架一致；与既有已批准决策无冲突——跨账号并行仍非目标（沿 MAI-001:90/BAT-001 头部）、错峰 ≥15 固定不可配置（沿 MAI-001 目标 4/BAT-001 拍板①，且 4.3 用 DAEMON_STAGGER_MINUTES 常量 + 冒烟 monkeypatch 而非运行时参数，符合「覆盖参数贯通」教训）、串行锁/全局守卫保留（MAI-001 目标 5 R7「同一时刻绝不并发」）；「每号一条 schtasks」实现形态的替换有 2026-09-08 用户会话拍板记录（头部 ⑤/⑦）支撑，verify 第 3 节断言改造方向（6.1/A9/4.7）与 verify.py:79-134 现状核对无误。

## 处置

P0 无。P1×2（F1 fired 落盘窗口、F2 stop 并发语义）为建议性必读：两者均可在 plan/实现层以明确条款落实，不构成规格级自相矛盾，**不阻塞 APPROVED**；spec 四节第 4.3⑤/4.5 stop 两处在 plan 动笔前按 F1/F2 补一句写死语义即可。P2×5（F3-F7）列入 plan 实施注意，其中 F4（出队重读校验）与 F2 建议合并到 4.3 状态机描述。无需第二轮评审。

— Reviewer（独立门禁）