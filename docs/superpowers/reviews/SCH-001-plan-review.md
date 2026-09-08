# SCH-001 Plan Review（定时任务条目库 + 常驻调度器）— 独立门禁评审

- 评审对象：`docs/superpowers/plans/2026-09-08-scheduled-jobs-daemon.md`（8 Task，状态：待用户签字）
- 依赖 spec：`docs/superpowers/specs/2026-09-08-scheduled-jobs-daemon-design.md`（已 APPROVED；F1–F4 并入 spec、F5–F7 移交 plan）
- 评审日期：2026-09-08　评审方式：独立 Reviewer 子代理（只读；23 条断言逐 token 双端 grep 实测〔源码 0 命中 / plan 实现块对齐〕+ 重跑 verify.py 复核基线〔输出当场脱敏〕+ 断言演进算术核验 + 插入点/变量锚点行号实测 + spec 四–九章与 F1–F7 覆盖映射 + import 面与打桩点可行性推演；未改任何文件，输出不点名真实别名/目标/文案）
- **结论：APPROVED**（P0 无；P1×1 建议改不 gate；P2×5 可选。数字口径、RED 诚实性、任务拆分、spec 覆盖全部核实成立，可进入用户签字）

---

## 评审发现表

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| F1 | **P1**（建议改，不 gate） | plan Task 3 函数契约；断言 4；Task 7 第 3 节改写 | 契约**缺 save_jobs 条目**：断言 4 锁 `def save_jobs`、Task 7 改写又锁 `hasattr(jobs, "save_jobs")`，但 Task 3 函数契约只列 load_jobs/_atomic_write/_validate_job/create_job/update_job/toggle_job/delete_job/has_legacy_schedule/migrate_from_legacy，写入口内部走 _atomic_write——按契约逐字实现出的 jobs.py 天然不含 save_jobs → 断言 4 在 Task 3 自检时仍红，需实现者临时自创该函数语义 | Task 3 契约补一行：save_jobs(jobs: list[dict]) -> None（公开原子写入口，内部走 _atomic_write）；断言为准绳不可改。随签字前修订即可 |
| F2 | P2 | plan Task 3 契约 / Task 4 函数清单 | 契约条目以裸名列出（load_jobs()、_recover_interrupted(st)、_reload_job(job_id)…），不带 def 前缀；而断言 4/6/11/12 锁含 def 的字节（def load_jobs/def _validate_job/def _recover_interrupted/def _reload_job）。实现必然写 def 故可自愈，但不符合字节对齐自查口径 | 契约/清单统一写成 def xxx(...) 形态（名称与断言逐字一致） |
| F3 | P2 | plan 9.1（第 3 节改写删除范围） | 「删除 :89-134 替换为」与替换块自带新节头并存：照字面删会残留旧节头注释与 _account_layer/aliases 死代码；若实现者按整节改写自然语义删 :79-134，则 :80 import panel 一并被删 → 第 4 节起仍用 panel → NameError，Task 7 全绿不可达 | 新块首行补 import panel（noqa: E402），并明示删除范围与死代码处理 |
| F4 | P2 | plan Task 4 守卫等待 | 只写 RUN_GUARD_PATH 存在 → pid 感知等待，未写明死 pid 陈旧守卫分支：panel 被强杀残留 .running 会让守护队列永久卡等待——batch_runner 有 _stale_guard_cleanup 主动清理先例，守护被动等待方需自清语义 | 补一句：守卫存在且 pid 亡 → 视为空闲继续（触发时 acquire_run_guard 自愈），或镜像 batch 主动清理；打桩冒烟加陈旧守卫不卡死场景 |
| F5 | P2 | plan 9.3 打桩点 | monkeypatch 清单只列 scheduler_daemon.JOBS_PATH → tempfile，但守护经 from jobs import JOBS_PATH, load_jobs 后调用 load_jobs() 读的是 jobs 模块内 JOBS_PATH（userdata 真路径）——只 patch 守护侧绑定对读任务表无效，假任务表预置会读真文件空转 | 打桩点补 jobs.JOBS_PATH → tempfile（同一 tmp 目录），或直接替换 sched.load_jobs = lambda: 假任务表；二选一写明 |
| F6 | P2 | 断言 10；Task 4 两段式落盘 | 断言第二半 `status": "running"` 只匹配字典字面含冒号或 JSON 文本形态；若实现用 entry.update(status="running")（无冒号形态）则恒红 | Task 4 注明 running 落盘须写字典字面 fired[job_id] = {…, "status": "running", "run_id": …}（plan 已用引号展示该字面，实现照抄） |

评审发现合计：P0 = 0；P1 = 1（建议改，不 gate 本次裁决）；P2 = 5。

---

## 已核实安全（逐项核验）

### ① 数字与口径（重跑实测）
- 基线实测：`./.venv/Scripts/python.exe verify.py` → 通过 121 / 失败 2、exit 1（本评审实跑，FAIL 明细当场脱敏）。2 FAIL 均为第 3 节按号注册探测（账号任务已注册，环境态，与 spec 及 spec review 当日实测一致）。
- RED 口径成立：23 条断言中 #1–#21 面向新字面/新文件（RED 全红 = 新增 21 失败），#22/#23 未接新参数 not-in 锁定断言 RED 态即绿 → RED FAIL = 既有 2 + 新增 21 = 23、PASS = 121 + 2 = 123。锁 22/23 现源 grep 实测：runner.py / batch_runner.py 对 persist_texts、targets= 均 0 命中，锁定断言成立且 Task 2–8 不改这两个文件 → 恒绿。
- 演进表加法逐行验算：23→20（-3 断言 1–3）→16（-4 断言 4–7）→7（-9 断言 8–16）→5（-2 断言 17–18）→2（-3 断言 19–21）→0（Task 7 删 2 条注册探测 FAIL）；PASS 123→126→130→139→141→144→148 同步 +3/+4/+9/+2/+3/+4，无一处加法错误。
- final 148 口径：148 = 121（基线通过）+ 21（SCH 断言转绿）+ 2（锁定断言即绿）+ 4（第 3 节改写新增守护自检）。减法侧核对：Task 7 删除范围在本机环境恰含 2 条执行中的 check（每账号 1 条注册探测、0 条通过），删后 -2 check、新块 +4 check → 146−2+4 = 148 自洽。
- 断言数 = 23：plan 断言代码块含 1 处续行（/api/scheduler 一条跨行）→ 恰 23 条 check。

### ② RED 诚实性 + 字节对齐（23 条断言逐 token 双端 grep 实测）
- 源码 0 命中（全部成立）：panel.py / panel.html / runner.py / batch_runner.py / main.py / douyin.py / verify.py 对以下 token 全 0 命中——注入缝 persist_texts、cfg["targets"] = targets、if persist_texts and texts:、tgt_list = targets if targets is not None；API /api/jobs(/update//toggle//delete)、/api/scheduler(/start//stop//cancel//autostart)；daemon DouyinAutoFireScheduler、DAEMON_STAGGER、scheduler_jobs.json、scheduler_state.json、scheduler_heartbeat.json、CurrentVersion\Run、dispatching、stop_requested、def load_jobs 等全系、migrated_from_legacy；页面中文 新建定时任务/开机自启/下次触发/一键迁移/清理旧系统任务/loadJobs。既有 cancel_requested 命中（panel.py/batch_runner.py/panel.html/verify.py）属 BAT-001 batch 机制，断言 15 查的是新文件故不冲突；一键触发/一键同步 与 一键迁移 为不同串（plan 声明属实）；/api/tasks 与 /api/jobs 不同串。磁盘存在性：jobs.py / scheduler_daemon.py / 三个 json 数据文件均不存在（ls 实测）。
- plan 实现块对齐（逐条 grep plan 文件）：#1–#3 → Task 2 代码块；#5–#7/#8–#16 → Task 3/4 骨架与函数清单（scheduler_jobs.json、os.replace、migrated_from_legacy、DAEMON_STAGGER_MINUTES = 15、两文件名、dispatching/status running、跨天未及触发、stop/cancel_requested、CurrentVersion\Run + DouyinAutoFireScheduler）；#17/#18 → Task 5 端点清单；#19–#21 → Task 6 页面 token 行。对齐缺口已列入发现表 F1（save_jobs 契约缺条目）/F2（函数名缺 def 前缀）/F6（running 落盘须冒号字典形态）——三者均属实现块措辞与断言字节不完全兼容，按仓库断言为准绳规则 GREEN 期可自愈，建议随签字前小修订闭环。

### ③ 规格覆盖与分叉闭环（spec ↔ plan 逐章映射）
- spec 4.1 架构 → Task 3/4；4.2 数据模型 → Task 3（json 结构/写方唯一/空校验/同号同刻不拦截）；4.3 守护主循环+状态机 → Task 4 函数清单逐条（预检/守卫/错峰/两段式/轮询/取消/stop 隐含取消）；4.4 注入缝 → Task 2；4.5 面板/API → Task 5+6；4.6 自启与心跳 → Task 4 set_autostart/心跳 + Task 5 autostart 端点 + Task 6 状态卡开关；4.7 迁移与旧机制收尾 → Task 3 migrate_from_legacy + Task 5 migrate 端点 + Task 6 一键迁移/清理旧系统任务；4.8 RED 概念清单 → Task 1。
- spec 五错误处理、六验证（基线/分层/冒烟/隐私）、七风险 R1–R10（缓解内建于 Task 4 心跳/防双开/整轮 try-except/最小写集/出队重读）、八待确认 → plan 对应章节（真实发送逐次授权、迁移与清理由用户面板执行、自启默认关）、九实施顺序 → Task 1–8 1:1，顺序依赖成立：daemon(Task 4) 依赖 trigger_run 新参(Task 2) 与 jobs(Task 3)；API(Task 5) 依赖 daemon 产物；页面(Task 6) 依赖 API；第 3 节改写(Task 7) 依赖全部新文件已存在。
- 评审 F1–F7 落点：F1 两段式 dispatching+崩溃复核 → 断言 10/11 + Task 4 两段式与 _recover_interrupted + 冒烟场景 4；F2 stop 优雅隐含取消 → 断言 14 + Task 4 + Task 5 stop 置标志最小写集 + 冒烟场景 5；F3 跨天未及触发 → 断言 13 + _reset_if_new_day + 冒烟场景 6；F4 出队重读 → 断言 12 + _reload_job + 冒烟场景 7；F5 migrated_from_legacy 幂等 → 断言 7 + Task 3 契约（有任务/已迁移→置标志返回现状防横幅复活）+ Task 6 引导条件；F6 已过时刻补跑提示 → Task 5 POST /api/jobs catchup_today + Task 6 弹提示；F7 心跳判停 ≥3×周期 → POLL_SECONDS=20 + Task 6 状态卡 ≤60s 判停。全部有明确落点。

### ④ 结构与可行性（锚点行号实测）
- verify.py 插入点与变量全部核实：read() 为 read_bytes 直读无缺文件容错、全文件无兜底 try/except → RED 态 j/s 必须存在性守卫（写法正确，含 BAT-001 同款教训）；rsrc/b/p/m/d 赋值点与消费点实测，h 健康字典最后消费于当前工程状态健康处，SCH 块内 h = read(panel.html) 其后无健康字典消费点 → 重绑定安全（plan 自查注记属实）；插入点位于 ★BAT-001 块尾之后、# --- 汇总 --- 之前，与现文件逐行吻合；23 条断言所用变量全部在插入点作用域内。
- 第 3 节既有断言不受 Task 2/5 改动牵连：verify 既有断言 grep 实测不锁将被替换的形态（if texts:、cfg targets 列表推导、meta 构造、def trigger_run/_worker、args 元组均 0 命中；load_config(account) 与 update_message_texts 在改动后仍保留）→ 注入缝改造零回归。
- import 面与模块骨架一致：scheduler_daemon 骨架含 if __name__ == "__main__" 守卫 → verify/冒烟可 import；模块级仅 ensure_userdata()（幂等建目录，无实质副作用，import 无副作用声明基本成立）；所依赖符号 main.py 全部真导出（USERDATA_DIR/RUN_GUARD_PATH/ensure_userdata/account_root/list_accounts/_pid_alive 实测）；panel 侧 list_runs/_load_meta/load_config 均在；jobs.py 依赖同源成立。守护触发调 panel.trigger_run(texts, headless=None, account, targets=..., persist_texts=False) 与 Task 2 签名一致；spawn 先例 panel.py Popen pythonw + CREATE_NO_WINDOW 核实存在，Task 5 start 端点可照抄。
- 行号引用准确性：panel.py _worker/trigger_run/路由区/Popen、batch_runner 状态机、verify 第 3 节/★BAT-001/汇总——plan 全部引用与实际行号吻合。
- 打桩冒烟可执行性：场景矩阵（两号同刻顺延错峰/同号同时刻并存/两段式中间态/崩溃复核不重发/cancel/stop/跨天/出队重读）与 scheduler_state.json/heartbeat 终态断言法可行（monkeypatch 模块级路径/sleep 压短/假别名 tmp 账号目录）；唯一缺口 = jobs 读路径打桩点（见发现 F5，P2）。场景压 15 → monkeypatch DAEMON_STAGGER_MINUTES=1 与 spec 固定 15、冒烟可 monkeypatch 常量一致，不引入运行时参数。

### ⑤ 隐私
- 本评审重跑 verify.py 输出中的真实任务名已在产生即脱敏为 <别名1>/<别名2>；全程未读账号数据目录；plan 全文仅用占位词，无真实别名/目标/文案；本报告同。

### ⑥ 流程
- plan 头部含 日期/Task-ID/状态（待用户签字）/依赖的 approved spec（含 spec review 引用与 F1–F4 并入、F5–F7 移交说明）——与 .hermes.md 门禁（plan 需 Reviewer APPROVED 后用户签字才实现）及 Plan Gate 一致；status 文件阶段 = PLAN（待用户签字）与头部同步。归档路径按仓库实况为 docs/superpowers/reviews/SCH-001-plan-review.md（仓库 reviews 目录在此）。

---

## 处置
- P0：0。
- P1：F1（save_jobs 契约缺条目）建议改——一行修订即可，不 gate 本次 APPROVED；若采纳，随 plan 签字前修订一并落（Task 3 契约补 save_jobs(jobs) -> None 一行，注明内部走 _atomic_write）。
- P2：F2–F6 共 5 条可选，实现 Tip/契约表述级，不影响结构、数字口径与验收可达性；建议 Task 3/4/7 编码前把 F1/F2/F6 措辞修订并入 plan，F4/F5 落进 Task 4/9.3 实现注意。
- 结论：**APPROVED** —— 数字口径（RED 23/123 → 逐 Task 演进 → GREEN 148/0）实测自洽，23 条断言 RED 诚实（源码 0 命中）+ GREEN 可对齐（除 F1/F2/F6 措辞缺口，断言为准绳可自愈），spec 四–九章与评审 F1–F7 全覆盖，插入点/变量/行号锚点全部核实无误，隐私全程合规。plan 头部状态可更新为「待用户签字（2026-09-08 Reviewer APPROVED，docs/superpowers/reviews/SCH-001-plan-review.md；签字后方可 IMPLEMENT）」。

— Reviewer（独立门禁）