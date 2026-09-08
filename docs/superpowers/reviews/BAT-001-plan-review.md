# BAT-001 Plan Review（一键出发：全账号串行批量执行，号间强制错峰）

- 评审对象: `plans/2026-09-08-one-click-batch-all-accounts.md`（依赖 spec 已 APPROVED，`reviews/BAT-001-spec-review.md`）
- 评审日期: 2026-09-08（三轮：第一轮 CHANGES_REQUIRED → plan 修订 7a3667d → 第二轮 CHANGES_REQUIRED
  （仅 P2-F7 面板侧未闭合）→ plan 修订 f3c02f4 → 第三轮 APPROVED）
- 评审方式: 独立 Reviewer 子代理三轮（只读；不读 userdata/；不点名真实账号别名/会话名）
- **结论: APPROVED**（P0/P1 全程零漏网；P2×9 修订全部关闭；第三轮附 1 条 P3 可选兜底不阻塞）

---

## 第一轮评审（CHANGES_REQUIRED）

# BAT-001 Plan Review（一键出发：全账号串行批量执行，号间强制错峰）— 独立评审

- 评审对象：`docs/superpowers/plans/2026-09-08-one-click-batch-all-accounts.md`（BAT-001，状态：待用户签字）
- 依据 spec：`docs/superpowers/specs/2026-09-08-one-click-batch-all-accounts-design.md`（已 APPROVED，含 `reviews/BAT-001-spec-review.md` 两轮记录）
- 评审日期：2026-09-08　评审方式：独立 Reviewer 子代理（只读静态评审：16 条断言逐 token grep 实测 + 反查 GREEN 锚点 + verify.py 现状直读 + plan↔spec 逐章映射 + 时序/并发推演；全程未读 userdata/、不点名真实账号别名/会话名）
- 裁决：**CHANGES_REQUIRED** —— P0 无漏网；P1 × 2（均在 plan 三章 verify.py 断言代码块，导致 Task 1 RED 证据无法产出、Task 5 GREEN 目标不可达）；P2 × 7（伪码级/实现约束级，不 gate，逐条列明避免实现踩坑）

## 评审发现

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| F1 | **P1** | plan 三章断言块首行（plan:49） | `b = read("batch_runner.py")` 在 RED 态必然崩溃：verify.py:43-44 的 `read()` 是 `(BASE / name).read_bytes()` 直读，无缺文件容错，全文件亦无兜底 try/except（已通读 verify.py 核实）——Task 1 提交时 batch_runner.py 尚不存在 → FileNotFoundError 未捕获，脚本在汇总打印（verify.py:369）之前中断，「18 FAIL = 既有 2 + 新增 16」的 RED 证据与 Task 1 提交信息宣称的期望根本无法产出 | 改为 `b = read("batch_runner.py") if (BASE / "batch_runner.py").exists() else ""`（或给 `read()` 加缺省返回）；附：plan:44「5b 节 SIV-002 断言块后」描述有误——5b 是 verify.py:165 起的 douyin /chat 节，SIV-002 块实际在 357-366（MAI-001 段尾部），插入点应以「SIV-002 块后（366 之后、汇总节 368 之前）」为准 |
| F2 | **P1** | plan 三章断言 #16（plan:65） | `h` 在 verify.py 中从未绑定过 panel.html：全文件仅 143/149/155 三处 `h = panel.api_tasks("main")["health"]`（健康字典，键为 ok/problems），HTML 断言既有惯例是内联 `read("panel.html")`（verify.py:366）。断言 `"一键出发" in h and "loadBatchState" in h` 是对字典键做成员判断 → RED/GREEN 恒 False：RED 尚可（多计 1 条失败），GREEN 时第 16 条永远过不了，「仅剩既有 2 FAIL」验收口径（plan:19）不可达成，且实现者会误判为前端漏做而空改 panel.html | 断言块内（`b = read(...)` 旁）补一行 `h = read("panel.html")` 再断言；plan:44「沿用既有 p/h 变量」的说法对 h 不成立，需一并修正 |
| F3 | P2 | plan 4.4-② 守卫等待循环（plan:189-197）/ 4.5-③ 错峰等待循环（plan:218-223） | 两处等待循环用内存副本 st 判 `cancel_requested` 且每 ~5s `_write_state(st)` 整盘回写——面板 /api/batch-cancel 刚写入磁盘的 `cancel_requested=True` 会在 ≤5s 内被执行器自己的周期写覆盖回 False：守卫/错峰等待期（错峰最长 15 分钟）取消不生效甚至被吞，违反 spec 4.2「每轮 sleep 后从磁盘重读 cancel_requested（不信任内存副本）」「等待/错峰期间可取消」；取消点了无效果是最伤 UX 的路径 | 每次 wake 先 `st = _read_state() or st`（cancel_requested 以磁盘为准）再判退出/写盘；建议单元冒烟补「等待态取消」一例（现 Task 5 冒烟④只覆盖运行中取消） |
| F4 | P2 | plan 4.6-⑦ 单号收尾（plan:258-263） | 终态 item 更新与 `_prev_run_end` 落定后缺 `_write_state(st)` 显式落盘（spec 4.1 时序图第⑦步「更新 batch_state → 下一号」）：照抄伪码实现时磁盘上该号永久停在 running（末号终态不落盘），后序号从磁盘读不到 `_prev_run_end` → 号间错峰基准丢失，B 号可能立即触发（违反「上一号 end + ≥15 分钟」核心风控纪律，且 verify 断言锁不到这条）；另 `st["_cancel_after_run"]=True`（plan:256）只写不读，属死赋值（真正停批靠 run_batch 逐号磁盘 cancel 检查），徒增困惑 | ⑦ 尾必加显式原子写（终态 + `_prev_run_end` 一并落盘）；删 `_cancel_after_run` 或注明其语义 |
| F5 | P2 | plan 4.6-⑤ 触发重试（plan:239-248） | trigger_run 返回 None 的「重试」只是 3×5s 原地 sleep，未按 spec 4.2「返回 None → 回第 2 步（守卫等待）重试，上限 3 次」执行：守卫被 schtasks 长任务占用时 15s 后即误报该号 error「触发被拒（守卫被占/内部繁忙）」，与错误处理表「守卫被占 → 轮询等待自动接续」语义不一致；且 cancel 判断嵌在 continue 分支里，重试窗口内取消会被歪曲成 error | 实现时 None → 退回 ② 守卫等待循环（含磁盘 cancel 检查、陈旧清理）再触发，次数上限 3 |
| F6 | P2 | plan 4.3 `_stale_guard_cleanup`（plan:142-163） | spec 第二轮 P2 观察（守卫删除竞态）的处置定为「plan 实现约束」，但 plan 4.3 代码未携带该约束：单次「读 pid → unlink」窗口内，若另一路触发恰对同一陈旧文件做 acquire 自愈（先 unlink 再 O_EXCL 重建），等待方会误删重建后的活守卫，该轮弱化「绝不并发」硬兜底 | unlink 前复读确认文件内仍为同一死 pid，或 unlink 后文件再现且 pid 存活则退回等待（一行改动，落进 4.3 即闭环） |
| F7 | P2 | plan 5.3 cancel 写（plan:388-390）与 4.2 `_write_state`（plan:134-136） | 两写方共用同一 tmp 名 `batch_state.json.tmp`：并发时一方 os.replace 会把对方刚写好的 tmp 移走，另一方随后 os.replace 抛 FileNotFoundError（面板端点 500），且整文件回写仍可能短暂回退对方进度——正是 P2-F2 想消除的 lost-update 的另一入口 | 每写方用唯一 tmp（如追加 pid 后缀或 tempfile），保持「读最新 → 只改自己字段 → 原子 replace」约定 |
| F8 | P2 | plan 4.6-⑥ 轮询（plan:251-257） | 轮询无 deadline：run meta 若因 worker 异常卡在 running（浏览器崩溃、收尾未执行），批量将无限期等待、拖死后续全部账号；runner.py:101-111 先例明确有 15 分钟 deadline + run.log 留痕 | 镜像 runner 超时行为：超时记 [BATCH] 行、该号置 error/超时原因，继续下一号，不拖死整批 |
| F9 | P2 | plan 十一 待确认（plan:497-504） | spec 八-2「错峰间隔固定 15 分钟是否认可（如需 30/60 只改一处常量）」未在 plan 十一回带（十一只列功能冒烟授权 / plan 签字 / 遗留 2 FAIL）。spec 头部已记录错峰 ≥15 拍板且 APPROVED，可视为已决，但显式回带可免签字后返工 | plan 签字确认时顺带声明「固定 15 分钟 + CLI 测试覆盖参数，不做面板配置」已含于 spec 批准范围 |

## 已核实安全（逐项核验）

1. **RED 诚实性（16 条逐 token grep 实测）**：panel.py 对 `/api/trigger-all`、`/api/batch-state`、`/api/batch-cancel`、`批量一键出发进行中`、`loadBatchState`、`一键出发`、`batch_state.json`、`batch_runner.py` 全 0 命中；panel.html 同批字面全 0 命中（含 `一键出发`；既有「一键触发」panel.html:252/304/309 与「一键同步」:336/338 为不同串，plan:75-76 声明属实）；全仓文件检索 batch_runner → 0 文件，`batch_runner.py` 不存在。→ 16 条新断言当前全部处于诚实 RED 态（断言 #16 在 RED 也失败，只是失败原因经 F2 修正后才是对的）。
2. **GREEN 可行性反查（16 条断言 token 逐条在 plan 自章代码中存在）**：#1-3 `/api/trigger-all|batch-state|batch-cancel` → 5.3/5.4；#4 `批量一键出发进行中` → 5.2 拒绝文案；#5-6 `batch_state.json` / `batch_runner.py` in p → 5.1 常量 + 5.3 Popen 参数；#7 `--batch-all` → 4.7 argparse；#8 `default=15` → 4.7；#9 `cancel_requested` → 4.4/4.5/4.7；#10 `os.replace(` + `batch_state.json` → 4.2（含 4.1 常量行）；#11 `waiting_stagger` / `waiting_guard` → 4.4-② / 4.5-③；#12 `def _stale_guard_cleanup` → 4.3；#13 `list_runs(acc, keep=1)` → 4.5 两处；#14 `api_state(acc)` → 4.6-⑤；#15 `panel.trigger_run(` / `panel._load_meta(` → 4.6；#16 `一键出发` / `loadBatchState` → 六章按钮文案与 JS。全部对齐，无「断言锁了实现里不会出现的字面」的空洞。
3. **import 面与 runner.py 先例一致**：runner.py:30 `from main import ensure_userdata, USERDATA_DIR`、:54 `import panel`、:90 `panel.trigger_run(texts, headless=None, account=account)`（与 plan 4.6 调用逐参一致）、:104 `panel._load_meta(run_id, account)`。main.py 符号全部真导出：`ensure_userdata`:59、`account_root`:119、`list_accounts`:124、`_pid_alive`:304、`RUN_GUARD_PATH`:51（USERDATA_DIR 为其基，panel.py:57 已从 main import）。panel.py 已具备 5.3 代码块全部引用面：`list_accounts`:48、`resolve_python`:63（from pyenv）、`_HIDDEN_STARTUP`:71-75、`BASE`:65、os/json/subprocess/sys/Path 均已 import，`_send_json` 为 handler 方法（:933），`_run_lock` 模块级（:117）——plan:394-395「均已 import」声明属实。
4. **面板 API 锚点**：`api_state(account)`（:815-830）含 `message_texts` 键（与 plan 4.6-⑤ `panel.api_state(acc).get("message_texts")` 匹配，runner.py:88 同源先例）；`list_runs(account, keep=3)`（:357-370）按 id 倒序切片，plan 用 `keep=1` 合法；`_load_meta(run_id, account)`:312；`load_config`:234；meta 时间戳为 `_now_iso` 格式 `%Y-%m-%d %H:%M:%S`（:281-282），与 plan 4.5-③ strptime 格式及 ④ 字典序比较自洽。
5. **三端点插入点成立**：`/api/trigger`:1220、`/api/setup-login`:1145、`/api/sync-conversations`:1168，三处均先 `_resolve_account(merged, action=True)`（:1221/1146/1169），plan 5.2「处理器开头、_resolve_account 之前」可执行；do_GET:992 / do_POST:1069 均为 path == 链式分发，plan 5.3/5.4 新分支形态一致；批量激活拒绝只落在面板 HTTP 路径，执行器直接调 trigger_run 函数不受误伤（spec 评审 #13 同源结论）。
6. **守卫机制与 P1-F1 处置**：main.py:317-348 `acquire_run_guard` O_EXCL 独占 + 陈旧 pid 自愈（337-344）只在创建尝试内触发，release 351-356——被动等待期确无自愈源，plan 4.3 主动 pid 感知清理是对 spec 4.2-②（P1-F1 修订）的正确落实，且「等待方删残留不改 acquire 语义」与 spec 三-非目标「守卫零改动」不冲突。
7. **前端锚点**：account-bar:260、addAccountBtn:264（一键出发按钮插入点）、refreshStatus:498（busy 置灰 528-532）、`setInterval(refreshStatus, 5000)`:1021、triggerBtn/saveMsgBtn/loginBtn/syncBtn:317-319/338——plan 六章按钮、横幅容器、轮询并入、置灰扩展全部可执行。
8. **spec 错误处理表 / 风险表 / 评审处置 → plan Task 全覆盖**：预检四类 skip → Task2-①；守卫被占/陈旧 → Task2-②/4.3；错峰/防双发 → Task2-③/④（R1/R4 兜底）；trigger None → Task2-⑤（实现口径偏差见 F5）；崩溃/被杀 → Task2 最外层兜底 + Task3 crashed 判定 + Task4 crashed 横幅（R2/R5/R9）；取消 → Task2 各等待点 + Task3 cancel 端点（最小写集，P2-F2 注释 plan:387）+ Task4 取消按钮；partial/error/needs_verify → Task2-⑥ + Task4 徽章/点击跳执行记录（R8/R10）；面板关/重启 → Task2 独立进程 + Task3 batch-state + Task6 文档「面板可关」；旧字段缺失 → Task3 `read_batch_state` 读侧兜底。P1-F1 → plan 4.3 + 断言 #12；P2-F2 → 5.3 最小写集（另有 F7 的 tmp 同名残余）；P2-F3 首号下限 → plan 4.5-③ 注释（评审 P2-F3 标注）；P2-F4 headless 语义 → Task6 指南注①；P2-F5 崩溃指引文案 → plan 4.7（「重按一键出发或单号补跑」，P2-F5 标注）。
9. **任务拆分覆盖 spec 九章实施顺序 1:1**：spec 九 ①RED→Task1、②执行器→Task2、③panel.py→Task3、④panel.html→Task4、⑤GREEN→Task5、⑥冒烟→Task5 单元（功能冒烟待授权，spec 六-4→plan 十一-1 回带）、⑦文档+status→Task6；提交粒度按任务分（六 commit，代码与文档分开，直接提交 main 符合仓库惯例）。验收清单十与 plan 各章承诺一一对应。
10. **verify 基线口径自洽**：基线 105 通过 / 2 失败（spec A8 + spec 评审第一轮「已核实安全」#8 当日实测复现；本评审不重跑——重跑会经 schtasks 任务名查询触碰账号名输出，按隐私约束回避）；RED 18 = 既有 2 + 新增 16，算式与 16 条 check() 计数一致；既有 2 FAIL = 每账号任务未注册环境态（verify.py:107/110-112，两账号两断言，与本任务无关）；GREEN 目标「仅剩既有 2」在 F1/F2 修正后可达成。
11. **隐私合规**：plan 全文（含三章断言注释、四章代码注释、十一遗留说明）仅用占位/通用词，无真实账号别名与会话名；九章隐私扫描命令用 `${n}` 动态取目录名、不内联任何真实名；spec 同前（<号A>/<号B>/<别名> 占位）。本评审全程未读 userdata/。
12. **verify.py 现状直读支撑 F1/F2 定位**：`read()` = read_bytes 无容错（:43-44）；`h` 三处赋值均为 api_tasks health 字典（:143/149/155）；HTML 断言既有惯例为内联 `read("panel.html")`（:366）；SIV-002 块 357-366、汇总节 368-375，全文件无兜底 try/except。

## P2 处置

F3-F9 共 7 条均不 gate 本次评审：F3/F4 是「照抄伪码会破坏 spec 核心语义（取消响应、号间错峰）」的实现踩坑点，务必在 Task 2 编码时按建议落实（建议同步落进 plan 4.4-4.6 伪码）；F5/F8 为与 runner.py / spec 4.2 语义对齐的偏差；F6 即 spec 第二轮 P2 观察的既定处置落点（plan 实现约束，plan 4.3 需补复读一行）；F7 属两写方约定的工程细节；F9 为签字流程补充确认项。以上均为文档/实现层小改，不改变方案结构。

— Reviewer

---

## 第二轮复审（CHANGES_REQUIRED：仅 P2-F7 面板侧未闭合）

# BAT-001 plan 第二轮复审 — 裁决：CHANGES_REQUIRED

- 评审对象：docs/superpowers/plans/2026-09-08-one-click-batch-all-accounts.md（修订提交 7a3667d，80+/29-）
- 评审日期：2026-09-08（第二轮聚焦复审，只读，未改任何文件）
- 评审方式：逐条核 P1×2 / P2×7 处置 + 错峰基准参数化 + 新问题扫描；证据全部对照真实代码（verify.py / panel.py / runner.py）与 git 取证，未读 userdata/
- 结论行：**CHANGES_REQUIRED** —— P1-F1/P1-F2 与 P2-F3/F4/F5/F6 及追加参数化修订均已妥善关闭并逐字核验；唯一未闭合项为 P2-F7 的**面板侧**（5.3 取消端点 tmp 未唯一化，只改了执行器侧）。修订一行即可，修订后复审一次即可 APPROVED，无需重跑全量评审

## 复审核验表

| # | 核查项 | 结果 | 实测证据 |
|---|--------|------|----------|
| 1 | P1-F1 断言块存在性守卫 + 插入点描述 | ✅ 已关闭 | plan:48/55 首行已为 `b = read("batch_runner.py") if (BASE / "batch_runner.py").exists() else ""`。verify.py:43-44 read() 实为 `(BASE / name).read_bytes().decode(...)`，全文件 grep `exists()` 0 命中、无模块级 try/except（:375 直接 sys.exit）→ RED 态缺文件必崩，守卫确属必要。插入点：plan:44「verify.py:357-366 之后、汇总节之前」——实测 SIV-002 块 verify.py:357-366、:368 为 `# --- 汇总 ---`，描述准确 |
| 2 | P1-F2 断言 #16 内联 read(panel.html)，不再用 h | ✅ 已关闭 | verify.py:143/149/155 三处 h 均为 `panel.api_tasks("main")["health"]` 健康字典（plan:49-50 描述属实，原 `in h` 实为查 dict keys，GREEN 永不绿）；#16（plan:71-72）已为 `"一键出发" in read("panel.html") and "loadBatchState" in read("panel.html")` |
| 3 | P2-F3 守卫/错峰等待循环逐 wake 磁盘重读；冒烟补错峰中取消一例 | ✅ 已关闭 | 4.4-②（plan:206-217）与 4.5-③（plan:238-245）每 wake `st = _read_state() or st` + 重绑 item + 判 cancel + _write_state；Task 5 冒烟④（plan:503-504）已含「错峰等待中置 cancel_requested → 等待立即退出（验证磁盘重读语义）」 |
| 4 | P2-F4 4.6-⑦ 显式原子落盘；删 _cancel_after_run 死赋值 | ✅ 已关闭 | ⑦ 收尾链（plan:301-310）：磁盘重取 item → 终态 update → st 重读 → 写 _prev_run_end → _write_state；取消语义移交 run_batch 逐号读盘 break（4.7）。全 plan grep _cancel_after_run 仅 :286 注释唯一命中，无活代码引用 |
| 5 | P2-F5 触发 None → 回守卫等待语义重试 ≤3，非原地空等 | ✅ 已关闭 | 4.6-⑤（plan:263-281）for (1,2,3) 内：重读 → cancel 检查 → 守卫存在且活 → waiting_guard 落盘 + sleep5 + continue；3 次失败 → error 落盘 return；无原地空等分支 |
| 6 | P2-F6 unlink 前复读确认同一死 pid + 外层重探测说明 | ✅ 已关闭 | 4.3（plan:157-179）unlink 前 cur2 复读、`int(cur2.get("pid") or 0) != pid → return False` 不删；:178 注释明示外层循环回循环头重探测、文件再现且 pid 活则正常等待 |
| 7 | P2-F7 两写方 tmp 唯一化（执行器 + 面板双侧同步核验） | ⚠️ 未完全闭合（gate） | 执行器侧 4.2 _write_state 已改 `.tmp.{os.getpid()}`（plan:143）✅；面板侧 5.3 /api/batch-cancel 仍 `Path(str(BATCH_STATE_PATH) + ".tmp")` 裸 tmp（plan:436）**未同步** ✗。panel.py:30/1304 实证 ThreadingHTTPServer → 面板内并发双取消仍共享同名 .tmp，互截断/发布半截 JSON 窗口仍在（读侧 try/except 自愈、取消可重按，P2 级）。跨写方（执行器 vs 面板）同名冲突主风险已消除（pid 后缀后与面板裸 .tmp 不同名），故属**部分处置**：逐字执行契约下 Task 3 会把裸 .tmp 原样写进代码。附带：4.2 注释（:141-142）「两写方…tmp 带 pid 后缀」对面板侧已失准，建议随修订改口径 |
| 8 | 追加修订：4.5 错峰基准参数化 + 签名/调用点贯通（--stagger-minutes 1 冒烟真实性） | ✅ 已关闭且真实有效 | 4.5-③ `timedelta(minutes=stagger_minutes)`（plan:237），plan 内无 timedelta(minutes=15) 残留；_execute_account 签名带 stagger_minutes（:185）→ run_batch(stagger_minutes)（:316）→ 调用点传参（:322）→ main `return run_batch(args.stagger_minutes)`（:351）→ argparse default=15（:338，与断言 #8 对齐）；面板 spawn 路径（:419）不传该参数 → 默认 15。`--stagger-minutes 1` 冒烟链路全通，真实有效 |
| 9 | 新问题扫描（修订引入的矛盾/死代码/未定义变量；重点 4.4-② item 再绑定、4.6-⑦ 磁盘重取一致性） | ✅ 指定两处无新 P0/P1；另发现 P2×2 见文末 | 4.4-② item 再绑定：磁盘 items 键由 main 建档（:348）且两写方均全量保留 → `st["items"][acc]` 无现实 KeyError 路径；_read_state() 为 None 时回退内存 st（含 :188 setdefault）兜底。4.6-⑦ 两次读盘间仅 cancel_requested 可能变化（items 保留）→ 终态不丢、run_batch 下轮读盘 cancel 收口。修订引入的 _cancel_after_run 已清、run_id 初始化与 ⑥ 引用一致，无新死代码/未定义变量 |

## 结论

**CHANGES_REQUIRED** —— 第一轮 P1×2 已全部妥善关闭；P2×7 中 F3/F4/F5/F6 与追加参数化修订全部关闭并逐字核验；F7 仅执行器侧落实、面板侧 5.3 未同步（ThreadingHTTPServer 下面板内并发仍共享同名 .tmp），按「只改执行器侧 = 未闭合」口径计入本轮 gate。修订成本约一行：5.3 tmp 补 pid 后缀（或抽两写方共享的唯一 tmp 辅助），并顺带修正 4.2 注释机理口径。修订后再复审一次即可 APPROVED。

## 新发现（不 gate 终裁；建议随下次修订顺带落）

1. **P2-a | plan 4.4-① 预检早退路径不落盘**（round-1 已报，本轮复读确认仍在）：账号不存在/读配置失败/未保存文案/未配置目标/尚未登录五条早退均 `item.update(...)` 后裸 return、无 _write_state；run_batch 每号传新读盘副本（:322），内存改动随函数返回丢弃 → 该号在磁盘滞留 pending 至批末；取消终态会把早退号误标「用户取消」，正常终态留 pending 残行。修复：早退前补 _write_state(st)，或抽统一收尾辅助。P2（状态文件真实性问题，无浏览器/安全后果）。
2. **P2-b | batch_runner 骨架未显式声明 _crash 来源**：4.6-⑥ 超时路径调用 _crash（:293），而 4.1 import 清单无 runner、骨架亦无 def —— 项目同构体在 runner.py:37（def _crash 实证存在，仅写日志不退出）。属隐含依赖：实现须在 batch_runner 自带同构 _crash（记 error 继续下一号、不抛不退），否则该路径 NameError 被顶层兜底接住 → 整批 crashed，与 ⑥ 注释「记 error 继续下一号」矛盾。建议 plan 4.1 或 4.7 兜底段补一句显式声明。P2。
3. **P2-c | 4.7 run_batch 首行 `_read_state().get(...)` 无 None 兜底**：姊妹点（:307/:317/:322/:323）全为 `_read_state() or st`，唯 :320 裸调 `_read_state().get("cancel_requested")`；读盘失败（文件瞬时不读/解析异常）→ None.get → AttributeError → 顶层兜底整批 crashed=True，而非优雅跳过。一行修复：`(_read_state() or {}).get("cancel_requested")`。P2。
4. **P2-d | 4.5-③→④ 边界陈旧 st 回写窗口**：③ 循环退出时内存 st 为末次 wake 读（≤5s 陈旧）；④ 防双发命中早退分支（:250-251）用该陈旧 st 整写，恰在窗口内面板置的 cancel_requested 会被覆盖回 false → 该轮取消丢失（需重按，无自愈）。正常流经 ⑤ 顶格重读不受影响；仅 ④ skip 分支 + ≤5s 精确窗口叠加时触发。修复：④ 入口补 `st = _read_state() or st; item = st["items"][acc]`（与 ②③⑤⑦ 同构）。P2。

## 已核实安全

- 16 条断言逐条对照 plan 实现块 token：panel 侧 5.1-5.3 提供全部 p-token、执行器侧 4.1-4.7 提供全部 b-token、Task 4 提供 html 两 token；断言可 GREEN、无自锁死；计数 16 与 RED 期望 18=既有 2+新增 16 自洽。
- RED 诚实性（本轮抽查）：verify.py 现文件 grep `exists()`/`loadBatchState`/`panel.html` 均 0 命中（batch_runner.py 未建、断言 token 未泄入既有代码）；「一键出发」与既有「一键触发/一键同步」不同串，互不干扰。
- SIV-002 块真实边界（verify.py:357-366）与汇总节（:368）实测，plan 插入点描述准确；h 三处（:143/149/155）均 api_tasks("main")["health"]，plan 行号引用属实。
- 取消时序修订后自洽：取消标志唯一来源为磁盘；②③⑤ 每 wake 重读，运行中号收尾后 run_batch 下轮 break 并整批改终态；防双发与错峰基准共用 list_runs(acc, keep=1) 同源读取。
- 4.6-⑥ deadline 兜底语义（超时记 error 继续下一号）优于 runner 进程退出；runner._crash 存在性经 verify.py:69 探针与 runner.py:37 双重实证。
- 隐私：本轮未读 userdata/；全文未点名真实账号别名/会话名；基线口径（plan:85 引用 2026-09-08 实测 105 通过/2 失败）与历史评审一致。

— Reviewer

---

## 第三轮收尾复审（APPROVED）

# BAT-001 plan 第三轮收尾复审（提交 f3c02f4）

## 结论：**APPROVED**（P2-F7 面板侧已闭合；单行改动未引入新问题，可进入用户签字）

- 评审对象：`docs/superpowers/plans/2026-09-08-one-click-batch-all-accounts.md` @ f3c02f4（只读复核，未读 userdata/）
- 评审方式：`git show f3c02f4` 单 hunk diff 核对 + 全 plan grep 枚举 `.tmp.` 写入口与断言 token + 代码块行级确认
- 评审范围：第三轮聚焦复审——P2-F7 面板侧闭合核验 + 断言 #10 不受影响 + 新问题扫描（本轮 diff 仅 5.3 一处 +3/-1，范围极小）

## 核验表

| # | 核验项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 5.3 `/api/batch-cancel` 端点 tmp 行已带 pid 后缀 | ✅ 通过 | plan:438 `tmp = Path(str(BATCH_STATE_PATH) + f".tmp.{os.getpid()}")`；f3c02f4 diff 仅 1 hunk（+3/-1，只触 5.3 代码块约 :433-441），改动最小化 |
| 2 | 该行带「P2-F7 面板侧」注释 | ✅ 通过 | plan:436-437「唯一 tmp（评审 P2-F7 面板侧）：与执行器 _write_state 一样带 pid 后缀，两写方不再共用同名 tmp → 无互相 os.replace 丢失窗口」 |
| 3 | 两写方 tmp 全部唯一化（无遗漏写入口） | ✅ 通过 | 全 plan grep `.tmp.` 仅 4 行：注释 :141/:436 + 赋值 :143/:438 → 状态写入口恰 2 处——执行器 4.2 `_write_state`（tmp 在 :143，注释 :141-142，os.replace 在 :145）+ 面板取消端点（:438）；两处均带 pid 后缀 → 跨进程共用同名 tmp 互相 os.replace 的 lost-update 窗口关闭 |
| 4 | 三章断言 #10 不受影响 | ✅ 通过 | plan:65 `check("★BAT-001 状态文件原子写", 'os.replace(' in b and "batch_state.json" in b)` 锁 b（batch_runner.py 执行器代码块）：`os.replace(` 仍在 :145、「batch_state.json」仍在 :124（:99 为 prose 说明）；f3c02f4 单 hunk 仅触及 5.3 面板代码块，执行器块（:100-146）零改动 → #10 与上轮同状态（通过），tmp 后缀变化不触碰任一被锁 token |
| 5 | os.getpid 依赖的 import 成立 | ✅ 通过 | 执行器代码块 `import os` 在 :106；5.3 端点与执行器骨架同文件作用域，os/json/Path 均已就位（面板段 BATCH_STATE_PATH 定义于 :365），无新增 import 需求 |

## 新问题扫描（唯一改动 = 5.3 行内 tmp 加 `os.getpid()` 后缀）

- **跨进程碰撞（原缺陷本体）**：执行器由面板独立拉起（不同进程）→ 两写方 pid 恒不同 → 本轮修复彻底排除原「面板与执行器共用 `batch_state.json.tmp` 互相 os.replace」的缺陷。修复方向正确、覆盖完整。
- **同进程并发两次 POST /api/batch-cancel（评审点 3）**：HTTP handler 内 os.getpid = 面板进程 pid → 两次请求 tmp 同名（`batch_state.json.tmp.<面板pid>`）。**判断：可接受，无需 uuid 调用级唯一化。** 理由：① 两写内容同构且同值——都只把 `cancel_requested` 置 True（最小写集，评审 P2-F2），最坏 lost-update 也是「同字段同值互相覆盖」，终态等价、无取消丢失；② 最差交错（A 写 tmp → B 写并 replace → A replace 时源 tmp 已被消费）仅致第二次 `os.replace` 抛 FileNotFoundError → 该请求单次 500，但此刻状态文件已含取消标志、取消已生效，客户端重试即幂等成功——无状态损坏、无半截 JSON；③ 面板侧无第二并发写方（状态读端点只读），执行器侧单线程顺序写；④ 危害上限为「一次多余 500」，远低于并发文件损坏阈值。可选 P3 兜底（不阻塞）：给 os.replace 包 `try/except OSError` 吞掉 FileNotFoundError 即可零瑕疵收口。
- **残留 tmp 孤儿文件**：write_text 与 os.replace 之间进程崩溃会遗留 `batch_state.json.tmp.<pid>`——两写方同源、非本次引入；userdata/ 已被 gitignore、文件单行极小，记录不处置。

## 评审发现汇总

- P0：0
- P1：0
- P2：0 未闭合（P2-F7 面板侧于本提交闭合，执行器/面板两写方 tmp 唯一化闭环）
- P3（可选，不阻塞）：同 pid 并发取消理论窗口的 os.replace 500 可加 try/except OSError 兜底

## 处置

plan 头部状态可更新为「待用户签字（2026-09-08 Reviewer 第三轮 APPROVED，f3c02f4；签字后方可 IMPLEMENT）」；本轮无需再改任何代码块。

— Reviewer
