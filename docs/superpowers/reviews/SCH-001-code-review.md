# SCH-001 Code Review 归档（两轮；终轮裁决 APPROVED 2026-09-08）

> 首轮 CHANGES_REQUIRED（P0 无；P1×3/P2×3/P3×1）→ 处置提交 f05ced6 → 第二轮聚焦复审 **APPROVED**（P0/P1/P2 全 0；P3×4 建议，N1/N2/N3/N4 处置见 status 与下方附录）。

---

# SCH-001 Code Review（定时任务条目库 + 常驻调度守护）

- 评审对象：提交 284ff6c→6f9bf1c（RED 23 断言 + 注入缝 + jobs.py + scheduler_daemon.py + panel API/页面改造 + verify 第 3 节改写 + 冒烟证据归档；runner.py/batch_runner.py 零改动锁定）
- 评审日期：2026-09-08
- 评审方式：独立 Reviewer 子代理（只读门禁，未改任何文件）。实测重跑 `./.venv/Scripts/python.exe verify.py` 与 `./.venv/Scripts/python.exe userdata/_smoke_sch001.py`；逐文件精读 jobs.py(220 行)/scheduler_daemon.py(553 行)/panel.py 与 panel.html 全量 diff/verify.py 第 3 节与 SCH 尾块；23 条断言逐 token 对照实现 grep；并发写方与状态机逐行核验；隐私别名扫描（不改名、不读 userdata/accounts/*/user_data.yaml 内容）
- 依据：spec（已 APPROVED，含评审 F1–F4 并入）、plan（用户签字 APPROVED，F5–F7 落点）、reviews/SCH-001-spec-review.md、reviews/SCH-001-plan-review.md、test-results/SCH-001-IMPL.md
- **结论：CHANGES_REQUIRED** —— P0 零漏网（无重复发送/无杀浏览器/无自锁/无跨号并发破坏）；P1×3（F1 任务上次结果数据流断头、F2 执行期心跳停更致面板误判已停止、F3 panel.html 残留对已删除 loadTasks 的调用，违反评审清单「0 命中」）；P2×3 可选。三处 P1 均为小改、不触断言与核心状态机语义，修复后可复审 APPROVED

---

## 评审发现

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| F1 | **P1** | panel.py:1546-1583 `_scheduler_summary()`；panel.html:699 | **任务「上次运行」数据流断头**：spec 4.5 明定 GET /api/jobs「返回 jobs + 合并 last_results + 守护心跳/状态摘要」，spec 目标 3「面板实时显示…任务上次结果」；守护侧 `_record` 每轮把终态写进 state.last_results（scheduler_daemon.py:191-198），但 `_scheduler_summary()` 载荷只有 jobs/migrated/legacy/scheduler，**不含 last_results（也不含 fired）**。前端 loadJobs 已在读 `j.last_results[job.id]`（panel.html:699）→ 恒 undefined → 「上次运行」列永远「—」，成功/失败/错误文案（含失败目标）对用户永不可见，plan Task 6 表格该列实为死代码。属 spec 承诺功能的静默缺失（守护照常执行、结果照常落盘，只是面板无出口） | _scheduler_summary 增补 `"last_results": st.get("last_results", {})`（+ 如需展示失败红字再带 fired/run 映射）；前端渲染已就绪，后端补字段即闭环。一行级、零行为面影响 |
| F2 | **P1** | scheduler_daemon.py:476-531（run_daemon）；129-137（_write_heartbeat） | **执行期心跳停更 → 面板误判守护「已停止」**：心跳只在「队列空(idle)」「每任务起点(running_job)」「退出/崩溃」时写（502/514/491/530/548），而守卫等待（5s 循环，可无限长）、错峰等待（最长 ~15min+）、`_poll_run`（最长 15min，3s 步长）期间**均不写心跳**。面板判停阈值 60s（F7，>3×20s 周期）→ 守护正排队/正跑任务超过 60s 后，状态卡即翻红显示「守护进程已停止」，与实际执行相悖（spec 4.5 状态卡 + R9「心跳含 current/队列进度面板可见」的目的恰在执行期）。错峰等待属常态路径（手动刚跑完 10 分钟→定时任务等满 15 分钟，全程误报已停止） | 在各 sleep 循环（守卫/错峰/_poll_run）内每 ≤~20s 补一次 `_write_heartbeat`（或把心跳 ts 刷新并入 `_write_state` 主路径）。不影响状态机语义 |
| F3 | **P1** | panel.html:1180、1246 | **残留对已删除函数 loadTasks() 的调用**：旧 loadTasks 已随整页改造删除，但 `setActiveAccount`（切号时定时任务页激活）与 adopt-legacy 回调两处仍调 `loadTasks()` → ReferenceError，截断刷新链（1180 行后 refreshStatus() 不执行；靠 5s 轮询自愈）。评审清单「全局搜 loadTasks/taskEnable/sysTaskInfo/saveTaskBtn 应 0 命中」**未达标（2 命中）**；taskEnable/taskDisable/taskDelete/sysTaskInfo/saveTaskBtn/timeInput/taskMsg/「系统定时任务」「设置每日定时」则全部 0 命中 | 两行改为 `loadJobs()`（或随旧流程一并删除）；顺带确认无其他已删 id 引用 |
| F4 | P2 | panel.html 任务表/新建表单（672-800）；panel.py /api/jobs/update | spec 4.5「每条可编辑」+「新建/编辑表单：从该号会话勾选目标（默认该号全量，可含私聊/群聊）」未落地：页面仅有 新建/删除/启用开关，无编辑态（update API 完整但零 UI 消费）；目标为手输会话名文本框且固定 `type:"private"`（逐行 split 生成），非 spec 4.2 会话缓存多选（丢失群聊类型保真、无默认预填——名字匹配不受影响，群聊目标会按 private 记但 douyin 按名查找仍可命中）。删了重建可绕行，无数据风险 | 补行内编辑（复用新建表单进编辑态调 /api/jobs/update），或按仓库惯例在 plan/spec 标注裁剪；目标选取如需群聊保真再接入 conversations cache |
| F5 | P2 | scheduler_daemon.py:487-531；129-137 | spec R1/4.3「主循环整轮 try/except 记 last_err 不自杀」未全落地：只有 `_execute_job` 有局部 try（515-522），idle 分支心跳/状态写异常（磁盘满/杀软锁文件）会穿出 run_daemon → main() 兜底记 crash 退出；心跳字段缺 spec 4.3 所列 `last_err`；jobs.json 损坏被读成 [] 时守护空转且无任何记录（写侧原子性使概率低）。退出本身诚实（crash log + 心跳 crashed），但违背「不自杀」条款 | idle 分支补整轮 try/except 记 last_err；心跳加 last_err 字段；可选：jobs 解析失败轮次写 last_err 提示 |
| F6 | P2 | scheduler_daemon.py:251-260 `_recover_interrupted` | dispatching 无 run_id 残留需同时满足「>120s 陈旧 && 守卫空闲」才移除重跑：若崩溃（ms 级两段式窗口内）后 <120s 内重启、或重启时守卫恰被其他运行占用，条目滞留 fired → 当日该任务不再补跑且无 last_results 记录（静默丢当日任务）。守护崩溃必杀其进程内 worker 线程，理论上 dispatching-无-run_id 不存在存活中的发送，重入队总会被守卫等待兜住，陈旧/守卫条件偏保守 | 维持现状可接受（窗口极窄、防重发优先），但建议滞留分支至少记一条 `last_results=skipped/error(崩溃未确认)` 供面板可见，避免无声丢失 |
| F7 | P3 | 仓库根 error.log（2026-08-21 遗留，内容为无关历史日志，非本任务产物） | 未纳入 .gitignore → `git status` 持续 `?? error.log`，与 plan 十「无新增未跟踪文件」收尾口径不符 | 加入 .gitignore 或删除；与 SCH-001 代码无关，不阻塞 |

评审发现合计：P0 = 0；P1 = 3（阻塞本次 APPROVED）；P2 = 3；P3 = 1。

---

## 已核实安全（逐项核验，对应评审清单 ①–⑦）

### ① 全量自检（评审实跑）
- `./.venv/Scripts/python.exe verify.py` → **通过 148 / 失败 0、EXIT=0**（当场输出，无别名泄露；通过项含 4 条守护自检 + 23 条 ★SCH-001）。
- `./.venv/Scripts/python.exe userdata/_smoke_sch001.py` → **通过 15 / 失败 0、EXIT=0**（8 场景 S1–S8 全部命中：两号同刻错峰 gap=900s、同号同刻并存、两段式中间态、running 复核不重发、dispatching 陈旧补跑、cancel 剩余 skipped、stop rc=0 优雅退出、跨天「跨天未及触发」、删后不发送、死 pid 守卫自清）。冒烟脚本打桩核查：tempfile 化全部状态/心跳/守卫/jobs 路径、假时钟（2026-09-08 21:00 起拨钟，错峰 15 分钟无需真等）、FakePanel 只写 tmp 假 run meta、假别名 accA/accB——**不触真实账号/浏览器/真实 .running**；`git check-ignore` 确认 `userdata/` 规则覆盖（不入库）。两输出引用已用假名，无脱敏负担。

### ② 注入缝正确性（panel.py:457-460/471-475/521-524/578-596）
- `_worker` 新增 `targets: list | None = None, persist_texts: bool = True`；`cfg["targets"] = targets` 严格包在 `if targets is not None:` 内（475 行）；写回条件改 `if persist_texts and texts:`（524 行，定时文案不污染账号手动文案——R3 落点）。
- meta 目标源：`tgt_list = targets if targets is not None else cfg.get("targets", [])` → `meta_targets`（578-584），默认形态与旧推导逐字等价。
- thread args 6 参透传 `(run_id, texts, headless, account, targets, persist_texts)` 与 _worker 签名对齐（593-596）。
- 默认路径零感知核实：既有调用方 4 处（runner.py:90 / batch_runner / /api/trigger / main CLI）均不传新参 → targets=None → cfg 注入不触发、persist_texts=True → 写回照旧，行为与以前完全一致。
- **runner.py / batch_runner.py 零改动确认**：`git log -3` 两文件最近提交止于 BAT-001（17ec7c0/fbb153e/9cd6ecf）；`git diff 284ff6c~1..6f9bf1c -- runner.py batch_runner.py` 输出为空。

### ③ 多写方/并发纪律（spec 4.1 / plan 十一）
- jobs.json 唯一写方 = 面板 CRUD/迁移：grep scheduler_daemon.py 无任何 save_jobs/JOBS_PATH 写路径（仅 `from jobs import load_jobs`）；运行结果一律进 state（_record 双写 fired/last_results），展示期面板合并——虽 F1 指出合并载荷漏了 last_results，但写方职责划分本身成立。
- scheduler_state 写方 = 守护（_write_state 全字段）+ 面板 cancel/stop 最小写集（panel.py 先 `sd._read_json` 读最新 → 只置标志 → `sd._write_json`，两端点均为 if-flag-absent 守卫防重复写）。
- 原子写纪律：scheduler_daemon._write_json（76-89）与 jobs._atomic_write_doc（47-61）均唯一 tmp 带 pid（`{name}.{pid}.tmp`）+ os.replace + Errno 13 3×0.05s 重试；两写方 pid 不同 → tmp 不撞名。
- 读侧兜底：_read_json 缺失/解析失败→{}（66-73）；jobs._read_doc→默认文档（35-44）；load_state 与磁盘合并逐字段类型守卫（140-161）——损坏/半写文件全链不抛不自杀。
- 重试耗尽诚实报错：panel cancel/stop 写耗尽 → _write_json 第 4 次裸 os.replace 抛 OSError → do_POST 外层 except → 500（诚实失败，不假成功——BAT F2 教训同款）；jobs._atomic_write_doc 耗尽 raise → 端点 500；守护侧异常逐任务/主循环兜底记 crash 日志。
- **F2（spec 评审）核实：/api/scheduler/stop 与 cancel 零 taskkill/零 kill/零 terminate**（全新增代码 grep 无命中）；stop = 置标志等当前 run 自然收尾 → 心跳 stopped → return 0（daemon 526-531）。
- cleanup_legacy_tasks（panel.py:1507-1523）：只对 query_system_task 探测存在的旧名走 `schtasks /Delete /TN /F`，**不触碰注册表 Run 自启值**，与「守护自启=注册表、清理=仅 schtasks」边界一致；异常逐项 continue 不拖垮。

### ④ 守护状态机与 F1–F7 闭环（对照 spec 4.3 + 双评审处置）
- 两段式落盘：触发前写 `{status:"dispatching", at}`（402-405）→ trigger_run 成功后同条目补 run_id + 字典字面 `"status": "running"`（434-438）→ 轮询终态后 `st=_load_state()` **以磁盘最新为基合并**再单次原子落盘（441-453，冒烟缺陷 1 修复点）；收尾带 failed_targets/end/error，prev_run_end 更新。
- _recover_interrupted（227-263）：running+run_id → _poll_run 收尾不重发（冒烟 S4 复核不重新触发 ✓）；dispatching 无 run_id → 陈旧 >120s 且守卫空闲才移除放行补跑（冒烟 S4 ✓；残余静默窗口见 F6）。
- _reload_job 出队重读（201-208 + 主循环 507-512 + _execute_job 351-355）：删除/停用 → skipped「任务已删除/停用」，防「删了还跑、改了还发旧的」（冒烟 S7 ✓）。
- 跨天重置（174-188）：date 变化 → 队列未 fired 条目记「跨天未及触发」→ 即时落盘（冒烟 S6 ✓，缺陷 2 修复点）；last_results/prev_run_end 跨天保留。
- cancel/stop：守卫/错峰等待每 5s 磁盘重读（_wait_guard_free 308-319、stagger 循环 380-398）；单任务收尾后主循环重读磁盘（524-531）→ 剩余队列 skipped + cancel 消费清除；stop 后主循环 return 0（冒烟 S5 ✓）。执行期（_poll_run）不轮询标志 = 按 spec「当前任务自然收尾」语义，正确。
- 错峰：DAEMON_STAGGER_MINUTES=15 固定常量（冒烟 monkeypatch 非运行时参数）；公式 end→start；prev_run_end 启动基线扫各号 `list_runs(acc, keep=1)` 最新 end（322-334/483，覆盖手动刚跑完）；单任务完成后更新（451）。
- 陈旧守卫：_clean_stale_guard 复读确认同一死 pid 才 unlink（282-305），等待与触发重试两处消费（冒烟 S8 死 pid 自清且照常触发 ✓）。
- 心跳/防双开：心跳含 pid/ts/boot_at（F7 ✓）；面板判停 = pid 存活 && ts ≤60s（_scheduler_summary，阈值 = 3×20s 周期 ✓）；daemon main() 启动读心跳 pid 存活即退出（534-541）；面板 start 端点同款 409 防双开。**执行期心跳停更见 F2**。
- 崩溃复核语义、触发被拒重试 3 次诚实 error（427-433）、守护 import 无主循环副作用（if __name__ 守卫 552-553）——全部核实。

### ⑤ RED/断言诚实与回归
- 23 条断言全部对应真实实现 token（逐条 grep 抽查全命中，无自欺）：注入缝 3 条（panel.py:475/524/581）、jobs 4 条（def load_jobs/def save_jobs/def delete_job、scheduler_jobs.json+os.replace(、def _validate_job+def create_job、migrated_from_legacy）、守护 9 条（DAEMON_STAGGER_MINUTES = 15、两状态文件名、dispatching+`"status": "running"` 字典字面 437 行、def _recover_interrupted、def _reload_job、「跨天未及触发」、stop_requested、cancel_requested、CurrentVersion\Run+DouyinAutoFireScheduler）、API 2 条（/api/jobs/update/toggle/delete 与 /api/scheduler/start/stop/cancel/autostart 均在 do_POST 真实路由）、页面 3 条（中文 token 在 panel.html 真实存在）。
- **「未接新参数」锁定断言形式诚实**：verify.py:379-382 用 `", targets="`（非 `targets=`）规避 failed_targets= 子串误伤；实测 runner.py/batch_runner.py 对 persist_texts 与 `, targets=` 均 0 命中且两文件确实未接新参——断言锁真实形态而非玩文字。
- 第 3 节改写（verify.py:79-93）：整节重写后**保留 import panel**（80 行，第 4 节起 api_tasks 健康自检依赖，无 NameError 回归——评审 P1-F3 落点）；runner 两条基线断言语义保留（复用 panel.trigger_run 合流、不再旁路 main.job）；jobs/scheduler_daemon 模块 import 实测无副作用（148/0 全绿即证）。
- 页面 token 与旧区块：`新建定时任务/loadJobs/开机自启/下次触发/一键迁移/清理旧系统任务` 均在 panel.html 存在；旧「系统定时任务/设置每日定时」区块与 taskEnable/taskDisable/taskDelete/sysTaskInfo/saveTaskBtn/timeInput/taskMsg 全部删除且 0 命中；**loadTasks 残留 2 处见 F3**。
- 计数口径：SCH 块 check( 恰 23 条；148 = 121 基线 + 21 转绿 + 2 锁定即绿 + 4 守护自检，与 plan 演进表一致。

### ⑥ 隐私
- 别名扫描（Python 全词正则，8 个变更文件逐一比对 userdata/accounts 实际目录名，只输出命中计数不输出名字）：**ALIAS_HITS = 0**。
- 全程未读 userdata/accounts/*/user_data.yaml 等真实内容（仅目录名 glob 用于扫描）；冒烟假别名 accA/accB 与假目标「目标-jA」等全为 ASCII/占位；IMPL.md 证据已用假名。本报告不点名任何真实别名/目标/文案。

### ⑦ 已知风险点核实
- 循环 import 安全：panel.py 顶部 import jobs（jobs→main，无环）；scheduler_daemon 仅在函数/handler 内被 panel import（/api/scheduler/start/stop/cancel/autostart、_autostart_enabled、_scheduler_summary 均为函数内 import），模块级无 panel↔scheduler_daemon 环。
- GET /api/jobs 调 _scheduler_summary：定义在 Handler class 之后（panel.py:1546 vs do_GET 1056），模块级 def 先于 main()/serve 执行完毕，请求时运行时解析安全。
- scheduler_daemon 模块 import 无副作用：仅 ensure_userdata()（幂等建目录）+ if __name__ 守卫，verify/smoke 直接 import 均验证通过。
- 冒烟脚本 gitignored：`git check-ignore -v` 命中 .gitignore:2 userdata/ 规则。

---

## 处置
- P0：0。
- P1（F1–F3，阻塞本次裁决）：三处均为小改、不触断言与核心状态机语义——F1 后端补一个 last_results 字段即闭环（前端已就绪）；F2 在等待/轮询循环内补心跳刷新；F3 两处 loadTasks 残留改 loadJobs/删除。修复后建议单 fix 提交 + verify 复跑 148/0 + 复审。
- P2（F4–F6）：可选，可随 P1 同批或 Lead 逐条裁决记录后关闭。
- P3（F7 error.log）：记录备查。
- 结论：**CHANGES_REQUIRED**——实现主体（注入缝、写方纪律、两段式、崩溃复核、出队重读、跨天、取消/停止优雅语义、错峰、防双开）经实跑与逐行核验全部符合已批准 spec/plan 及评审 F1–F7 处置；三处 P1 属「面板可见性/状态卡真实反映」层的缺口与残留引用，不涉及发送安全与数据完整性的 P0 级缺陷，修复后复审即可 APPROVED。

— Reviewer（独立门禁 Code Review）


---

## 第二轮聚焦复审（2026-09-08，终轮 APPROVED）

# SCH-001 Code Review 第二轮聚焦复审（处置核验）

- 评审对象：处置提交 f05ced6 `fix(sched): SCH-001 Code Review 处置`（4 文件：.gitignore / panel.html / panel.py / scheduler_daemon.py，+54/−6），前置提交历史不变；另核首轮评审归档 `docs/superpowers/reviews/SCH-001-code-review.md`（CHANGES_REQUIRED，P0=0、P1×3、P2×3、P3×1）
- 评审日期：2026-09-08
- 评审方式：独立 Reviewer 子代理第二轮聚焦复审（只读门禁，未改任何文件）。逐项对照首轮 F1–F7 处置与真实代码（行号核对）；全仓 token grep 残留扫描；实跑 `./.venv/Scripts/python.exe verify.py` 与 `./.venv/Scripts/python.exe userdata/_smoke_sch001.py`；全程未读 userdata/accounts/*/user_data.yaml（仅代码语义核验）
- 依据：首轮评审归档、处置提交 f05ced6 diff、spec（2026-09-08-scheduled-jobs-daemon-design.md）、plan（2026-09-08-scheduled-jobs-daemon.md）
- **结论：APPROVED** —— P1×3 全部真落地且经实跑回归验证（verify 148/0、冒烟 15/0，均为当场输出）；P2×3 按首轮建议落地（F4 数据保真部分落地、编辑 UI 缺口未裁剪留痕，属 Lead 关闭裁决范畴，不阻塞）；P3 处置完成；新问题扫描无 P0/P1

---

## 处置核验（逐项对照 F1–F7）

| # | 级别 | 核验结果 | 证据 |
|---|---|---|---|
| F1 | P1 | ✅ 真落地 | panel.py:1592 `_scheduler_summary()` 返回体新增 `"last_results": st.get("last_results", {})`；GET /api/jobs → `_scheduler_summary()`（panel.py:1103-1105）；前端 panel.html:699 `const last = (j.last_results && j.last_results[job.id]) || {}` 已在消费（`|| {}` 兜底旧 run 无该字段），渲染 status + end_at + error。守护侧 `_record` 双写 fired/last_results（scheduler_daemon.py:193-200）→ 数据流闭环，「上次运行」列不再是死代码 |
| F2 | P1 | ✅ 真落地 | 心跳 last_err 字段：scheduler_daemon.py:137；`_poll_run` 长轮询循环内补 `_write_heartbeat("running_job", None)`（286，3s 步长）；`_wait_guard_free` 守卫等待循环内补（326，5s 步长）；`_execute_job` 错峰等待循环内补（401，5s 步长）。面板判停阈值 60s（panel.py:1586），三处长等待的心跳 ts 均持续刷新 → 不再误判「已停止」。所有新增心跳调用点均落在 run_daemon 既有 per-job try（532-539）或 main 兜底（563-566）覆盖范围内 |
| F3 | P1 | ✅ 真落地 | panel.html:1180（setActiveAccount 切号）与 1246（adopt-legacy 回调）均已改为 `loadJobs()`；全仓 grep `loadTasks|taskEnable|taskDisable|taskDelete|sysTaskInfo|saveTaskBtn|timeInput|taskMsg` → panel.html 0 命中、全部代码文件 0 命中（剩余命中仅在 docs/ 评审归档与历史 plan 存档，属预期）；tab 切换（480）、初始化（797）本就使用 loadJobs |
| F4 | P2 | ◐ 部分落地（数据保真 ✅ / 编辑 UI ❌） | POST /api/jobs 创建路径已走 `_enrich_target_types`（panel.py:1402）：按该号会话缓存回填 type（1552-1568），缓存命中即覆盖前端默认 `type:"private"`（群聊保真），未命中保留 private；create_job 校验在 enrich 之后执行。**未落地部分**：spec 4.5「每条可编辑」与 plan「行点击/编辑按钮进编辑态」仍为空白，且 spec/plan 未见任何裁剪标注（grep「裁剪/行内编辑」无记录）——首轮建议二选一（补 UI 或标注裁剪）均未执行。P2 可选、无数据风险（删了重建可绕行），不阻塞本次裁决，建议 Lead 在 spec/plan 补裁剪留痕或后续补 UI |
| F5 | P2 | ✅ 真落地 | idle 分支 try/except（scheduler_daemon.py:512-519）：写心跳异常 → `_crash` 留痕 run.log → 尝试补写 `"error"` 心跳带 last_err（失败静默）→ 继续主循环不退出（不自杀达成）；心跳结构新增 `last_err` 字段（137）；main() 崩溃路径带 last_err（565）。边界观察：队列补货处 `_write_state`（509）不在该 try 内（磁盘满时仍穿出由 main 兜底退出），属极小概率场景，首轮定位即「idle 分支」，非阻塞 |
| F6 | P2 | ✅ 真落地 | `_recover_interrupted` 滞留分支（scheduler_daemon.py:263-267）：非「>120s 陈旧 && 守卫空闲」的 dispatching 无 run_id 条目 → `_record(st, job_id, {status: skipped, reason: 守护中断未确认（不重发，请人工检查执行记录）})` + changed → 原子落盘。fired 条目就地转 skipped 且保留在 fired（当日不再补跑、面板可见，不静默丢失）；后续重启时该条目 status 已非 dispatching → 分支不再触发，不会每次重启重复写；崩溃循环窗口（dispatching 写盘后、recover 落盘前再次崩溃）内重复 _record 为同 key 覆盖、无增长。语义权衡（以「立即记 skipped」取代「等下次重启陈旧+守卫空闲后补跑一次」）与首轮建议完全一致（不重发优先 + 人工核查），非回归 |
| F7 | P3 | ✅ 真落地 | .gitignore 新增 `error.log` / `run.log` / `*.log`；仓库根遗留 error.log（104B，8月22日）仍存盘但已不被 git 追踪（git ls-files 无命中），`git status` 不再报 `?? error.log` |

处置核验结论：F1–F7 全部有真实代码落地（F4 为数据保真半程，见上），无「只改注释/只写文档」式空处置。

---

## 新问题扫描（修复是否引入回归）

1. **心跳写盘频率（F2 实现方式）**：三处循环心跳每轮都写（3s/5s），而非首轮建议的「每 ≤20s 一次」——15 分钟错峰等待约 180 次、15 分钟轮询约 300 次原子写（唯一 tmp 带 pid + os.replace）。单写方无 tmp 撞名；面板读侧 `_read_json` 全异常兜底（偶发 Errno13 只导致瞬时 running=false 闪断，概率极低）。属性能/磨损观察项，非缺陷，不阻塞。
2. **enrich 与 create_job 校验交互（F4 实现方式）**：`_enrich_target_types` 在 create_job 校验前过滤非 dict/空名——纯字符串型 targets 会被全滤掉后报「至少选择一个发送目标」（原为「目标格式不正确」），错误文案变化无功能回归（前端始终发 dict）；不去重（与既有行为一致）；conv_map key 未 strip（缓存名带首尾空格时匹配不上、退化为保留 private）——边缘场景，非阻塞。`/api/jobs/update` 不经过 enrich，编辑路径目标 type 原样保留，无破坏。
3. **F6 留痕重启语义**：如上，skipped 就地落盘且 fired 保留 → 当日不再补跑。若守护在「触发已实际开始但 run_id 未落盘」窗口崩溃，条目被记 skipped 而真实发送可能进行中——但守护崩溃必杀其进程内 worker 线程（首轮已论证无存活发送者），记录文案「请人工检查执行记录」即为此兜底，诚实无误导。
4. **回归断言缺口（P3 建议）**：处置提交未改 verify.py（148/0 持平即证无断言漂移），但 F1（`"last_results" in p`）、F6（`"守护中断未确认"`）、F5（idle try）、F2（三处循环心跳）均无 verify token 锁定，smoke S4 只覆盖 stale+guard-free 正向分支、未覆盖 F6 滞留分支——建议补 1~2 条断言防重构回退，非阻塞。
5. **状态卡 current 展示**：`hb.get("current") or st.get("current")`（panel.py:1600）优先取心跳字符串，等待期显示 "waiting_stagger" 而非含 next_start_at 的 st.current dict——既有形态（修复前等待期心跳停更更糟），非本次回归。
6. **仓库卫生**：`git status` 现仅剩 `?? docs/superpowers/reviews/SCH-001-code-review.md`（首轮评审归档文件未提交）。非代码问题，建议 Lead 随归档 docs 提交清账（对齐 plan 十「无新增未跟踪文件」收尾口径）。

---

## 回归（当场实跑）

- `./.venv/Scripts/python.exe verify.py` → **通过 148 / 失败 0、EXIT=0**（含 4 条守护自检 + 23 条 ★SCH-001，计数与首轮一致，无新增失败）
- `./.venv/Scripts/python.exe userdata/_smoke_sch001.py` → **通过 15 / 失败 0、EXIT=0**（S1–S8 全命中：错峰 gap=900s、两段式、复核不重发、陈旧补跑、cancel/stop、跨天、删后不发送、死 pid 自清；假别名 accA/accB/假目标，无真实账号/浏览器接触）

---

## 评审发现（本轮回合计）

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| N1 | P3 | scheduler_daemon.py:286/326/401；panel.py:1592；verify.py | F1/F2/F5/F6 处置无回归断言锁定（verify 无 last_results/守护中断未确认 等 token；smoke S4 未覆盖 F6 滞留分支） | 补 1~2 条 verify token 断言或扩展冒烟，防重构回退 |
| N2 | P3 | spec 4.5 / plan Task 6；panel.html 任务表 | F4 编辑 UI 缺口未补做、spec/plan 亦无裁剪标注（处置只落地群聊保真半程） | Lead 在 spec/plan 记录裁剪或后续补行内编辑，二选一留痕 |
| N3 | P3 | 仓库根 | `docs/superpowers/reviews/SCH-001-code-review.md` 未提交（git status 显示 ??） | Lead 随归档 docs 提交清账 |
| N4 | P3 | scheduler_daemon.py:509 | 队列补货 `_write_state` 不在 idle try/except 内（磁盘满极端场景仍可能穿出退出，与 F5 同族但首轮定位为 idle 分支） | 可选：同款兜底 |

P0 = 0；P1 = 0（首轮 3 项全部闭环）；P2 = 0（首轮 3 项按建议落地，F4 见 N2）；P3 = 4（均为建议性）。

---

## 隐私

全程未读 userdata/accounts/*/user_data.yaml 等真实数据（_enrich_target_types / _load_conversations_cache 仅做代码语义核验，未执行读取）；冒烟证据为假别名 accA/accB 与假目标；本报告不点名任何真实别名/目标/文案。

— Reviewer（独立门禁 Code Review 第二轮聚焦复审）