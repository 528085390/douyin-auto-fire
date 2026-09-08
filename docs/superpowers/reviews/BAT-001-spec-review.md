# BAT-001 Spec Review（一键出发：全账号串行批量执行，号间强制错峰）

- 评审对象: `specs/2026-09-08-one-click-batch-all-accounts-design.md`
- 评审日期: 2026-09-08（两轮：第一轮 CHANGES_REQUIRED → spec 修订 0e85d25 → 第二轮 APPROVED）
- 评审方式: 独立 Reviewer 子代理两轮（只读；不读 userdata/；全程占位符，不点名真实账号别名/会话名）
- **结论: APPROVED**（第一轮 P1-F1 + P2-F2~F5 全部修订关闭，无新 P0/P1；第二轮附 1 条 P2 理论竞态观察
  → 处置为 plan 实现约束，不阻塞）

---

## 第一轮评审（CHANGES_REQUIRED）

# BAT-001 spec 独立评审结论：CHANGES_REQUIRED

- **评审对象**：`docs/superpowers/specs/2026-09-08-one-click-batch-all-accounts-design.md`（BAT-001，一键出发：全账号串行批量执行，号间强制错峰 ≥15 分钟）
- **评审日期**：2026-09-08
- **评审方式**：只读静态评审（证据表行号锚点逐一核对 + verify.py 实测 + RED 字面 grep 实测 + 时序/并发推演）。未修改任何文件；未读取 userdata/ 目录内容。

## 结论行

**CHANGES_REQUIRED** —— 证据表 A1–A10、基线 105/2、RED 诚实性、前端命名、隐私五类核验全部通过，独立进程执行器方案（4.1–4.4）在守卫等待、错峰、防双发、取消四条时序上整体自洽；但 4.2-②「等待守卫」的**被动轮询设计存在一处 P1 级可用性缺口**（陈旧守卫无自愈 → 批量无限等待），需在 spec 层面补明机制后再进入 plan。其余为 4 条 P2（不 gate）。

## 评审发现

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| F1 | **P1** | spec 4.2 执行器流程第 2 步（等待守卫）、4.1 时序图②、五-错误处理表 | 「轮询 userdata/.running（每 ~5s），空出即继续」只探测**文件存在性**，未处理**陈旧守卫**：`.running` 持有进程中途死亡（schtasks runner 被终止、面板重启脚本按 cmdline 杀 panel.py 进程、运行超 15 分钟 runner 退出时 daemon worker 的 finally 不保证执行）时守卫文件残留且 pid 已死。既有的陈旧自愈（main.py:337-344）只在 `acquire_run_guard` 的**创建尝试**里触发；而批量期间面板单号动作被 4.3 拒绝、执行器又停在被动等待循环不发起 acquire → 无人自愈，该号永久 `waiting_guard`，只能靠用户点取消脱困（五表「面板被关闭/重启」行只覆盖了「面板死而批量活」的反向场景，未覆盖「守卫持有者死而执行器活」）。佐证：守卫释放仅在各 worker 的 finally（panel.py:486/596/679），进程被杀即失效；runner.py:101-111 超时退出路径中 worker 为 daemon 线程（panel.py:538-540），进程退出时收尾不保证执行，仓库自身即能产出残留守卫 | 将 4.2-② 改为 **pid 感知轮询**：每次醒来读 `.running` 内记录 pid，pid 不存在（`_pid_alive` 探测，main.py:304-314 已有）则删除残留文件后继续；或周期性执行「probe acquire + 立即 release」复用既有自愈逻辑。同时在五-错误处理表补一行「等待期间守卫持有进程死亡（陈旧 .running）→ 自动清理接续」，并在 4.5 加一条意图级断言（锁「陈旧守卫 pid 探测清理」token）防回归 |
| F2 | P2 | spec 4.2 状态原子写 / 4.3 `/api/batch-cancel` | `batch_state.json` 有**两个写方**（执行器状态迁移 + 面板取消端点），整文件读-改-写并发存在 lost-update 窗口：面板读旧副本后执行器先写，面板再落盘会把 items 进度回退到旧值；最坏时横幅进度展示滞后至执行器下一次状态迁移（数分钟）。取消标志本身安全（执行器每轮 sleep 后重新从文件读 `cancel_requested`，不信任内存副本），取消生效延迟 ≤ 一个 wake + 一个 in-flight run，与「当前号跑完后停止」文案一致，可接受 | 建议取消端点采用**最小写集**（读最新 → 只改 `cancel_requested` → tmp + os.replace 落盘），并约定两写方均「先读最新再改」；横幅展示回退在实现期以「渲染以 active 快照为准」消化 |
| F3 | P2 | spec 目标 5 / 4.2-④ 防双发 / 3-非目标 | 防双发只比对「本批量 started_at 之后」，**首号与跨批量间隔不设下限**：上一批量刚结束（或某号刚被手动跑完）立即重按一键出发，首号可 <15 分钟重跑同号一轮。spec 已在非目标与五表披露「重按 = 与手动触发两轮等价，用户自决」，语义自洽不构成缺陷，但与本任务「避免同号无意重复」的动机有张力 | 可选廉价加固（不 gate）：首号 `next_start_at` 取下限 = max(now, 该号最近一次 run end + 15 分钟)，与防双发共用「读最近 run meta」逻辑，改动一行 |
| F4 | P2 | spec 4.2-⑤ 触发 / 4.6 文档 | 面板单号触发强制可见浏览器（panel.py:1227 `headless=False`），批量执行器传 `headless=None` 走 config（同 runner.py:90 先例）；若某号 config `headless:true`，批量内该号将以后台无头方式运行，needs_verify 等需人工处理的可见性弱于手动触发路径 | 语义与定时路径一致（可接受），但建议 4.6 文档同步清单注明「批量内以各号 config 的 headless 设置运行」 |
| F5 | P2 | spec 4.1 / 七-R2 | 仓库已知 `pythonw` 在部分后台托管/沙箱环境异常退出（docs/故障排查.md:88-91 明确记载），执行器恰为 `pythonw` 长时进程（半小时级）。设计已有 crashed 兜底（pid 死 + 中途态 → 横幅提示 + 允许重按），退路完整 | 建议 run.log `[BATCH]` 崩溃兜底行附「重按一键出发或单号补跑」指引文案；文档注明与面板相同的「前台 python.exe 备选启动」提示 |

## 已核实安全（逐项核验）

1. **A1（main.py:119-131）属实**：`account_root` 在 119-121、`list_accounts` 在 124-132（排序 + 含 `user_data.yaml` 或 `browser_data` 判定，129-131）。锚点与代码一致。
2. **A2（main.py:317-356；panel.py:116-119）属实**：`acquire_run_guard` 317-348（`os.open(O_CREAT|O_EXCL)` 独占 + 写入 account+pid+start_ts，陈旧残留按 pid 存活探测删除重试，337-344），`release_run_guard` 351-356；panel.py 116-121 为全局串行锁变量（`_run_lock`/`_current_run`/`_current_run_account`/`_login_running`/`_sync_running`）。「进程内锁 + 跨进程守卫双保险」描述准确。
3. **A3（panel.py:259-275、:1220、:1145、:1168）属实**：`_resolve_account` 259-275（action=True 无 account 即 None）；`/api/trigger` 1220、`/api/setup-login` 1145、`/api/sync-conversations` 1168，三端点均走 `_resolve_account(merged, action=True)`，无账号 400——「动作路径无账号即拒绝」属实。
4. **A4（panel.py:491-515）属实**：`trigger_run` 491-548；None 语义实测于 508/511/515——进程内 `_current_run`/`_login_running` 占用或 `acquire_run_guard` 被占均返回 None，不排队。login/sync 两路同样先进程内检查再取守卫（562/639）。
5. **A5（panel.py:524-533、:441-461）属实**：meta 初始字段 524-533 含 id/account/start/end/status/texts/targets/error；终态判定 441-461（needs_verify 442 / partial|error 449 / success 457 / 异常 error 458-461）；`end` 落盘 466、prune 至 3 条 476——「running/success/partial/error/needs_verify 全生命周期落盘」属实。
6. **A6（runner.py:47-111）属实**：main 47 起；54 `import panel`；90 `panel.trigger_run(texts, headless=None, account=account)`；95-97 None → `_crash` 记日志退出；101-111 轮询 meta 至非 running。「独立进程 import panel → trigger_run → 轮询 meta」先例确凿。
7. **A7（panel.html:419-425、:526-530、:1021）属实**：419-424 fetch 封装自动带 account（GET 拼 query / POST 塞 body）；526-528 busy 判定（running || login_running || 他号运行）置灰 triggerBtn/saveMsgBtn；1021 `setInterval(refreshStatus, 5000)` 确认。5s 轮询并入点与 spec 4.4 描述一致。
8. **A8 基线实测复现**：今日实跑 `./.venv/Scripts/python.exe verify.py`，输出 `[ok]` × **105**、`[FAIL]` × **2**，与 spec「105 通过 / 2 失败」完全一致；2 条 FAIL 均为「账号任务 DouyinAutoFire-<别名> 已注册」断言（任务未注册的环境态，与本 spec 无关，别名不点名）。注意 verify 进程 exit code 为 0，spec 若在验证方案引用 exit 语义需以「FAIL 计数」为准（既有惯例，非本 spec 引入）。
9. **A9（MAI-001 spec:76-81、:90）属实**：76-81 行含「每账号独立计划任务、UI/文档提示错峰 ≥15 分钟」「进程内全局串行锁保留」「userdata/.running 跨进程守卫」「R7『同一时刻绝不并发』」「跨账号并发是非目标」；90 行将「`--all` 一键全账号、跨账号并行执行」明确列为非目标。BAT-001「把错峰从 UI 提示升级为号间强制 ≥15 分钟」是对 MAI-001 的强化而非推翻，引用准确。
10. **A10（load_config / panel.py:815-830）属实**：`api_state` 815-830，message_texts 与 targets 同源读自 `load_config(account)`（823-824）；`load_config` 主实现在 main.py:70，panel.py:234 为包装——「批量无需面板输入框，直接读账号配置」成立。
11. **独立进程执行器方案成立（4.1）**：panel.py 的 HTTP 服务仅在 `if __name__ == "__main__": main()`（1318-1319）启动，import panel 无副作用（仅 logging.basicConfig）——执行器进程 import panel 调用 `trigger_run` 可行，与 runner.py 生产先例一致；`resolve_python(windowless)`（pyenv.py:77-90，优先 pythonw）+ create_task 同款形态（panel.py:730-761，schtasks /TR 即 `pythonw runner.py ...`）在 4.3-④ 可复用。
12. **面板/执行器触发互斥边界正确**：`_current_run` 等进程内全局锁是**每进程独立**的（panel.py:117-121 模块级全局，执行器进程自持一份恒为 None/自己的 run），执行器 `trigger_run` 不会被面板进程的 `_current_run` 拦截；跨进程互斥唯 `.running` 文件（O_EXCL 原子性，main.py:327-331）——「两进程各自独立，不会误拦」推理核实成立。
13. **4.3 批量期拒绝单号动作不误伤执行器**：拒绝点位于三个 HTTP 端点分发（1145/1168/1220），执行器在独立进程直接调 `trigger_run` 函数、不经 HTTP——「拒绝只作用于面板 HTTP 路径」推理成立，无路径交叉。
14. **时序自洽性（守卫等待/错峰/防双发/触发/取消）**：触发竞争（等待空出瞬间被 schtasks 抢占）由 trigger_run 内部 acquire 原子性兜底（None → 回第 2 步重试 ≤3 次 → error，不整批中断）；错峰以「上一号实际运行 end +15 分钟」起算（meta.end 在 finally 第 466 行先于守卫释放 486 落盘，语义无歧义）；防双发「end 晚于 started_at → skip」对「等待窗口内 schtasks 抢先跑完该号」的兜底在重试环中必然复检（第 2→3→4 步回流），无遗漏路径；取消在守卫/错峰等待中即时生效、运行中号自然收尾、退出前标 cancelled 并 skipped(cancelled) 剩余号——不杀浏览器的纪律一致。
15. **RED 诚实性实测**：对 panel.py/panel.html/main.py/douyin.py/runner.py/verify.py/pyenv.py 逐一 grep `trigger-all|batch_state|batch_runner|waiting_stagger|waiting_guard|cancel_requested|一键出发|批量一键出发进行中|batch-cancel|batch-state` → **全部 0 命中**；全仓 .py/.html 合计 0 命中（命中仅存在于 spec 自身）；`batch_runner.py` 文件不存在（实测 ls 无此文件）；`userdata/batch_state.json` 亦不存在。**「一键触发」（tab 名与页面文案，panel.html:304/336）与「一键同步」（syncBtn 338）为既有字样，不算冲突**——spec 4.5 断言规划的新字面全部处于诚实 RED 态。
16. **前端命名无冲突（4.4）**：账号栏 259-265（accountSelect/runBadge/addAccountBtn/accountHint），「一键出发」按钮拟置于 addAccountBtn 旁——既有 id 无 batch 相关命名（triggerBtn 317 / syncBtn 338 / loginBtn 319 / triggerBadge 317），4.4 拟定「按钮 id + 横幅容器」均为新名，无覆盖风险。
17. **隐私合规**：spec 全文（含 JSON 示例与文档同步清单）仅用 `<号A>/<号B>/<别名>` 占位符，无真实账号别名/会话名；本评审输出亦全程占位代称。评审全程未读取 userdata/ 目录内容。

## P2 处置

F2–F5 四条均不 gate 本次评审：F2 建议在 plan 期以「读最新再改 + 取消端点最小写集」约定消化；F3 为可选加固（一行改动，实现顺手可做）；F4/F5 走 4.6 文档同步清单与 run.log 文案落实。P1（F1）须在 spec 修订后复审通过，方可进入 plan。

— Reviewer

---

## 第二轮复审（APPROVED，F1-F5 处置核验）

# BAT-001 spec 第二轮复审（F1-F5 处置核验 + 新问题扫描）— 裁决：APPROVED

- 评审对象：docs/superpowers/specs/2026-09-08-one-click-batch-all-accounts-design.md（修订提交 0e85d25，24+/6- 仅改该文件；spec 无未提交改动，读到的即落盘修订版）
- 日期：2026-09-08　方式：独立 Reviewer 子代理第二轮聚焦复审（只读；不读 userdata/；不点名真实账号别名/会话名）
- 结论行：**APPROVED**（第一轮 CHANGES_REQUIRED 的 P1-F1 与 P2-F2~F5 均已妥善处置，无新 P0/P1；新发现 1 条 P2 级理论竞态观察，不阻塞，处置见文末）

## 复审核验

| # | 核查项 | 结果 | 实测证据 |
|---|---|---|---|
| F1(P1) | 4.2-② 已写明 pid 感知轮询、语义完整 | ✅ 已关闭 | spec:155-159：每次醒来读守卫文件内 pid → 文件存在但 pid 已死（含 schtasks runner 被终止 / 面板重启清理进程 / runner 超时退出而 daemon worker 收尾未执行三例）→ 删除残留继续；文件不存在或 pid 存活 → 继续等；并明示「既有自愈 main.py:337-344 只在创建尝试时触发，被动等待期无人调用它，不处理就会该号永久 waiting_guard」。触发条件 / 动作 / 两分支 / 后果链齐全；另补错误处理表行(spec:289)与 verify 断言 #12(spec:264-265) |
| F1 代码一致 | 「acquire 时自愈(337-344)」「release 在 worker finally」描述与代码一致 | ✅ 一致 | 直接读码：main.py:325-345 自愈（337-344：读 pid → `_pid_alive` 活则返回占用、死则 unlink 后 continue 重试）只存在于 O_EXCL 创建尝试循环内，即仅「有人主动 acquire」才触发；main.py:351-356 release 为 unlink。release-in-finally 实测：main.py:420（运行 worker）/598（迁移）/641（登录），panel.py:486（_worker，注释「跨进程守卫与 _current_run 同一 finally 释放（P1-1）」）/596（_login_worker）/679（_sync_worker）/1103（路由守卫），docstring panel.py:501/603 明示「获取成功后守卫只经 worker finally 释放」。被动轮询等待期无任何 acquire 调用方 → 确无自愈源，修订必要且建模正确 |
| F2(P2) | 两写方 lost-update 约定已写明 | ✅ 已关闭 | spec:185-189：执行器状态迁移与面板 /api/batch-cancel 两写方一律「先读最新 → 只改自己的字段 → tmp + os.replace 落盘」；取消端点取最小写集（只改 cancel_requested，不整文件回写进度）；执行器每轮 sleep 后从磁盘重读 cancel_requested（不信任内存副本）。与 4.3 取消端点(spec:217)、4.2 取消段(177-179)、原子写段(183-184)、R5(329) 自洽 |
| F3(P2) | 首号错峰下限已写明 | ✅ 已关闭 | spec:160-165 第 3 步：「第一号无前置，但启动时刻取下限 max(now, 本号最近一次 run 的 end + 15 分钟)（评审 P2-F3 加固：紧接上一批量结束/手动触发后重按一键出发时，不让首号 <15 分钟重跑同号一轮——与防双发共用『读该号最近 run meta』逻辑）」。与 4.2-④(166-168) 衔接：后序号自身间隔恒 ≥15 分钟，语义无洞 |
| F4(P2) | headless 语义文档化 | ✅ 已关闭 | spec:273 4.6 管理面板行注明：①批量内每号按该号 config 的 headless 设置运行（同定时任务语义，与手动触发强制可见不同，无头账号遇安全验证需留意横幅提示）；②执行器异常中断时重按一键出发或单号补跑。与 4.2-⑤ headless=None=配置(169-172)、R10(334) 一致 |
| F5(P2) | pythonw 异常兜底指引 | ✅ 已关闭 | 五-错误处理表 crash 行(spec:285)：run.log [BATCH] 行 + 「重按一键出发或单号补跑」指引；七-风险表 R9(spec:333) 引用 docs/故障排查.md:88-91 —— 逐行核实属实（该文件 §9 第 88-91 行确为「pythonw 后台启动失败」：pythonw 沙箱环境异常退出 + 改 python.exe 前台启动备选） |

## 新问题扫描（简要）

- 4.5 断言清单：12 条编号与 spec:267「新增约 12 条」文字同步（diff 确认仅新增第 12 条 F1 断言 + 计数 11→12，前 11 条未动）；六-验证方案 RED/GREEN 期望(302-304)与 A8 基线（既有 2 FAIL，spec:60）一致，无编号/计数错位。
- 五-错误处理表与七-风险表：crash 行↔R9、needs_verify 行(291)↔R8(332)/R10(334)、陈旧守卫行(289)↔F1 机制、守卫被占行(288)↔R4(328，O_EXCL 原子性 + 重试) 均为「行为描述 vs 风险+缓解」互补，无重复冲突；两表引用同一机制时措辞一致。
- JSON 示例(spec:193-206)与 4.2 描述一致：pid/started_at/stagger_minutes/accounts/cancel_requested/phase/finished_at/crashed/items 字段齐备；next_start_at 仅 waiting_stagger 态出现(202-203)，与 4.2-③(164-165)及 4.4 前端倒计时(234)同源；status 取值表(208-209)为示例超集。
- F1 修订与其余章节无矛盾：4.1 图(118-119「② 只等 .running 释放」为示意，4.2-② 细化之)；三-非目标「守卫与进程内锁语义零改动」(87-88) 不受影响——等待方删残留不改 acquire 自身语义，批量触发仍全经 trigger_run → acquire O_EXCL 路径(4.2-⑤/spec:169)。
- 头部「状态：待评审」(spec:5) 与「评审拍板记录：待 Reviewer APPROVED 后补」(spec:13) 为批准前状态，与本次裁决流程一致。隐私终扫通过：全文占位符 <号A>/<号B>；batch_state 声明于 gitignored 的 userdata/ 下(spec:191)；本轮未读 userdata/。
- 唯一新观察（P2 级、理论、不阻塞）：4.2-② 等待方「删除残留守卫」是本设计中唯一「unlink 后不跟进自有 O_EXCL 仲裁」的写者——毫秒级窗口内若恰有另一路触发对同一陈旧文件做 acquire 自愈（先 unlink 再 O_EXCL 重建），等待方可能误删重建后的活守卫，该轮运行期间守卫缺失会弱化「绝不并发」硬兜底。触发需三重巧合（陈旧守卫存在 × 读写落在毫秒窗口 × 运行期间再有第三路触发；批量激活期面板单号动作已被 4.3 拒绝，外部源仅 schtasks 分钟级对齐），实际概率可忽略。处置建议（不阻塞 APPROVED）：列入 plan 实现约束——unlink 前复读确认仍为同一死 pid、unlink 后文件再现且 pid 存活则退回等待；或实现时补一行至 4.2-②。

## 已核实安全

- 提交 0e85d25 存在（f3899dbc…），提交信息与内容相符，`git show --stat` 确认仅改 spec 一文件 24+/6-；diff 全文核对 F1（4.2-② 重写 + 错误表新行 + 断言 #12 + 计数 11→12）、F2、F3、F4、F5 全部落盘。git status 无 spec 未提交改动；另有 1 个未跟踪文件 error.log（非本次修订产生、与 spec 无关，不影响结论；上轮「git 干净」表述据此修正口径）。
- 代码锚全部直接读码核实（main.py:304-348/337-344/351-356、release-in-finally 各调用点、panel.py:486/596/679/1103 及 docstring 501/603），非转述 spec 自述。
- 文档引用 docs/故障排查.md:88-91 行号属实。
- 隐私终扫通过；未读 userdata/。

## P2 处置确认

- F2 两写方并发约定：✅ 处置完整（4.2-185-189，含最小写集 + 磁盘重读取消标志）。
- F3 首号错峰下限：✅ 处置完整（4.2-160-165）。
- F4 headless 语义文档化：✅ 处置完整（4.6-spec:273 注①②，R10 联动）。
- F5 pythonw 异常兜底：✅ 处置完整（五-crash 行 spec:285 + 七-R9 spec:333，引用行号已核实）。
- 新 P2 观察（守卫删除竞态）：已记录，处置 = 列入后续 plan 实现约束（或实现时补一行 spec），不阻塞本次批准。

— Reviewer（第二轮，独立子代理）
