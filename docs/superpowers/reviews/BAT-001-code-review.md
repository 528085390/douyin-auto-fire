# BAT-001 Code Review（一键出发：全账号串行批量执行，号间强制错峰）

- 评审对象: 提交 f9295a6→9cd6ecf（BAT-001 实现 + Code Review F1-F3 处置）
- 评审日期: 2026-09-08（两轮：第一轮 CHANGES_REQUIRED → 修复提交 9cd6ecf → 第二轮 APPROVED）
- 评审方式: 独立 Reviewer 子代理两轮（只读；未读 userdata/ 真实内容；不点名真实账号别名/会话名）
- **结论: APPROVED**（P0 全程零漏网；P1×1 + P2×2 于 9cd6ecf 关闭；二轮附 P3 观察 ×2 不阻塞）

---

## 第一轮评审（CHANGES_REQUIRED）

# BAT-001 Code Review — 一键出发:全账号串行批量执行(号间强制错峰 15 分钟)

- 评审对象:提交 f9295a6→3c64fcb 共 6 笔(test 1 + feat 2 + fix 1 + docs 2);HEAD 另含 bf34bd7(证据归档,BAT-001-IMPL.md/status,文档类,不计代码评审,仅作测试证据引用)
- 评审日期:2026-09-08 | 评审方式:独立 Reviewer 子代理只读静态评审(git show/diff、逐 token grep 行号实测、plan↔实现逐条语义对照、node --check、py_compile、verify 断言静态计数);未重跑 verify.py、未读 userdata/ 真实内容、不点名真实账号别名/会话名,以提交物与 BAT-001-IMPL.md 交叉审计代替
- 依据:specs/2026-09-08-one-click-batch-all-accounts-design.md(APPROVED)、plans/2026-09-08-one-click-batch-all-accounts.md(用户已签字)、reviews/BAT-001-spec-review.md、reviews/BAT-001-plan-review.md、test-results/BAT-001-IMPL.md
- **结论:CHANGES_REQUIRED** —— P0 无漏网;P1×1(fbb153e 把状态文件读侧兜底收窄后,batch_state.json 损坏/半写时无代码内自愈,执行器与面板双双锁死,属 spec 评审 P1-F1「残留永久卡死」同族 + plan 4.2 原语义回归);P2×2(取消端点重试耗尽仍报成功;终态行点击跳转未实现)。修复 1~2 行级,不动断言与行为面,修复后复审即可 APPROVED。

---

## 评审发现

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| F1 | **P1** | batch_runner.py:57-67(_read_state)、295-330(_try_claim);panel.py:239-248(_read_batch_json) | **状态文件损坏即永久自锁,无代码内恢复路径**。fbb153e 把读侧兜底从 plan 4.2 原码(plan:134-137 except Exception: return None;读到 None → pid=0 → unlink → O_EXCL 重建自愈)收窄为仅 FileNotFoundError/OSError,json.JSONDecodeError(ValueError 子类)不再被吸收。batch_state.json 唯一非原子写是 _try_claim 的 O_EXCL 直接 json.dump(314-318,无 tmp+replace,fdopen 缓冲),该 ms 级窗口内执行器被杀/崩溃会留空或半截文件。此后:① _try_claim 的 FileExistsError 分支(cur = _read_state() or {})在 main() 的 try(349)之外 → JSONDecodeError 穿出 → pythonw 静默退出(无 [BATCH][FATAL] 日志),重按一键出发永不成功;② 面板 _batch_active()(panel.py:253)抛错 → /api/trigger、/api/setup-login、/api/sync-conversations、/api/trigger-all、/api/batch-state、/api/batch-cancel 全部 500,单号发送也被锁死;③ 唯一恢复 = 手动删 userdata/batch_state.json,面板无提示。无意的自愈属性回归,与 spec 评审 P1-F1 同族纪律 | 三处读侧把 ValueError 并入重试分支(except (OSError, ValueError): sleep 0.05,3 次后返回 None);_try_claim 随即对损坏文件走 pid=0 → unlink → 重建;活进程半写文件 Windows 上 unlink 失败返回 False(诚实退出+日志)。一行级改动,零断言/零行为面影响 |
| F2 | P2 | panel.py:1347-1372(/api/batch-cancel) | 取消 os.replace 3 次重试耗尽后 break 退出,无条件返回 ok「已请求取消」——标志实际未落盘,用户以为当前号跑完后停止,剩余账号仍全部继续。取消在发送类工具上是安全关键动作,虚假成功不可接受(对照 batch_runner._write_state 78-85:重试耗尽后还有一次不带保护的最终 replace,失败即抛错走 crashed 诚实路径) | 去掉 break,让重试耗尽后最后一次 os.replace 自然抛错(do_POST 外层 except 落 500 与日志),或显式 500 取消失败。与 F1 同批修复 |
| F3 | P2 | panel.html renderBatch/loadBatchState(959-1030) | 横幅交互落差 vs plan 六.2(plan:482「终态行点击 → 切该号 + 跳执行记录页签」)与 spec 4.4「终态横幅汇总」:实现中徽章为纯文本 span 无 onclick,且 show = active||crashed,phase=finished/cancelled 后横幅即刻隐藏,终态汇总永不可见(spec 4.4 自身两处表述矛盾,实现择一可理解,但 plan 六.2 点击句是明确落差)。功能正确性不受影响,属体验裁剪 | 二选一:① 补终态行 onclick(复用既有切号+切 tab 逻辑);② 若认定裁剪,在 plan 六.2 加注「终态即隐藏、点击跳转不做」,避免后续按 plan 空找 |

---

## 已核实安全(实测证据)

1. **断言零迁就**:git diff f9295a6..3c64fcb -- verify.py 输出为空;git show f9295a6:verify.py 与工作树 diff 为空(IDENTICAL)。RED 提交后 verify.py 0 改动,16 条断言文本逐字保留,无改断言迁就实现。
2. **16 条断言 token 全部真实落盘**(grep -n 实测):batch_runner.py — --batch-all:333、default=15:335、cancel_requested:154/185/215/276/283/306、os.replace(:80/85、batch_state.json:31、waiting_stagger:189、waiting_guard:162/220、def _stale_guard_cleanup:88、list_runs(acc, keep=1):173/197、api_state(acc):225、panel.trigger_run(:224、panel._load_meta(:246/253;panel.py — /api/trigger-all:1319、/api/batch-state:1083(GET 只读链)、/api/batch-cancel:1347、批量一键出发进行中×3(1195/1220/1274)、batch_state.json:237、batch_runner.py:1335;panel.html — 一键出发:265、loadBatchState:959、batchBtn/batchBadge/batchBanner 齐备;verify.py ★BAT-001 标记恰 16 处(grep -c=16)。
3. **执行器状态机 vs plan 修订后语义逐条一致**:① 预检四跳过(账号不存在/未保存/未配会话/未登录,不占错峰、无浏览器动作)② 守卫等待 pid 感知(_stale_guard_cleanup 88-116 复读确认同一死 pid 才 unlink,评审 P2-F6 已落实)③ 错峰用参数 stagger 非写死;strptime ValueError 兜底 nxt=now ④ 防双发 end >= started_at ⑤ 触发返回 None 回守卫等待语义重试上限 3(评审 P2-F5 已落实)⑥ 轮询 15min deadline 兜底 ⑦ 单号收尾显式原子落盘 + _prev_run_end 含末号。取消一律以磁盘为准:各阶段 wake 先 _read_state() 重读,无内存副本信任;run_batch 271-292 收尾 phase=finished/cancelled + 剩余号 skipped;main() 349-358 crashed=True + [BATCH][FATAL] 日志 + 重按/单号补跑指引。
4. **O_EXCL 独占建档 + 陈旧 pid 自愈删除重建**(_try_claim 295-330);防双发双保险:面板 _batch_active 409 + 执行器侧 pid 存活即拒绝退出(main 346)。
5. **两写方唯一 tmp + os.replace**:batch_runner.py:76 与 panel.py:1359 均带 pid 后缀(评审 P2-F7 已落实);fbb153e 读/写 Errno13 小重试两写方同款(读 3×50ms、写 3×50ms);批内写保留最终不带保护 replace → 失败走 crashed 诚实路径(78-85)。
6. **panel 守卫顺序与路由**:/api/trigger-all = _batch_active 409 → _run_lock 内 _current_run/_login_running/_sync_running 423 → 无账号 400 → resolve_python(windowless) 500 → Popen(pythonw, batch_runner.py --batch-all, cwd=BASE, CREATE_NO_WINDOW, _HIDDEN_STARTUP)。GET /api/batch-state 在 do_GET 只读链;两 POST 在 do_POST 尾部。批量期拒绝覆盖 /api/trigger(1274)/api/setup-login(1195)/api/sync-conversations(1220),均在 _resolve_account 之前;不误伤执行器:batch_runner 经 panel.trigger_run 直接函数调用不经 HTTP,且 trigger_run(panel.py:537)内部无 _batch_active 检查,拒绝只拦 HTTP 入口。
7. **前端**:panel.html 内联 script 单块 29395 字符,node --check 通过(node v24.16.0 rc=0);按钮/徽章/横幅 id 唯一;busy 置灰扩展覆盖 trigger/saveMsg/login/sync/再次一键出发(531-542,后端 409 双保险);5s 轮询并入(1133-1134)+ 本地 1s tick 只刷倒计时;crashed 红横幅文案与 plan 逐字一致;取消 confirm 文案与后端「当前号跑完后停止」语义一致。
8. **回归面**:verify.py:268-276 模块 API 契约扫描仍只扫 main.py/runner.py(未扩入 batch_runner,既有断言零扰动);batch_runner 引用的 panel 属性逐一存在(trigger_run:537/api_state:861/list_runs:403/_load_meta:358/load_config);BATCH_STATE_PATH 仅 batch_runner.py:31 与 panel.py:237 各自模块作用域,无跨模块/既有名冲突;「一键出发」与既有「一键触发/一键同步」不同串互不干扰。
9. **计数自洽(静态审计替代重跑)**:verify.py check( 静态 121 调用点 + 循环展开 = 123 次运行时断言,与 IMPL.md 实测 RED 105/18、GREEN 121/2 逐位吻合;新增恰 16 条;中间态 114/9、120/3 与断言分批结构自洽;f9295a6 提交信息「18 FAIL = 既有 2 + 新增 16」可信;py_compile batch_runner.py/panel.py 通过。
10. **隐私终扫**:git grep HEAD 全树对三个 pattern(账号前缀/accounts 路径/裸词)的命中全部落在 2026-09-07 SIV-001/002 前序历史存档(评审范围外,按仓库惯例不改历史);BAT-001 全部代码+spec+plan+review+IMPL+status 0 命中(grep rc=1);IMPL.md FAIL 行已用占位符。本评审输出全程未点名真实别名。
11. **测试证据抽查**:BAT-001-IMPL.md 的 RED/GREEN 数字、S1/S2 冒烟断言(success 落盘/末号 _prev_run_end/顺序性/错峰中取消以磁盘为准)与代码语义自洽;冒烟真实暴露 Windows Errno13 竞态,已由 fbb153e 修复,修复后冒烟 exit 0;功能级冒烟未授权已如实声明为遗留,不阻塞验收。

---

## P2/P3 处置

- F2/F3(P2):建议与 F1 同批处理(一个 fix 提交 + verify 复跑仍应 121/2 全绿 + 复审),或 Lead 逐条裁决记录后 APPROVED——均不阻塞核心语义正确性。
- P3(可选,不阻塞,记录备查):
  1. verify.py:271-272 模块 API 契约元组未含 batch_runner.py(本次已人工核对 panel.* 引用全存在;建议扩入,让结构性防线覆盖新模块)。
  2. 轮询以独立 setInterval(loadBatchState, 5000) 实现而非 plan 所述 refreshStatus 内追加——效果等价,仅实现形态偏离;空闲期每 5s 本地 GET 开销可忽略。
  3. 防双发 end >= started_at:started_at 缺失时 end >= 空串恒真 → 跳过而非双发,安全方向;state 建档必含 started_at,实际不可达。
  4. XSS 面评估:renderBatch 以 innerHTML 拼接 alias/reason/run_id/failed_targets——alias 服务端 VALID_ALIAS_RE 限 ASCII 1-24 位(无 HTML 元字符);reason 为后端常量文案+本地配置异常文本;failed_targets 为会话目标名,与既有 runs 列表/详情弹窗同款未转义渲染同级别,本地面板无新增攻击面扩张;建议统一用既有 escapeHtml 渲染动态字段(一致性加固,非必修)。
  5. run_batch(accounts, stagger_minutes) 签名与 plan 4.4 的 run_batch(stagger_minutes) 不同——claim 预置 accounts 快照 + 显式传参,语义等价且符合 spec 4.2「启动快照」,注记即可。
  6. spec 4.2 JSON 示例 items 行含 start 字段,实现未写(前端未消费,无影响);首号错峰基准 strptime ValueError 已被实现兜底为 nxt=now(改进项)。

---

— Reviewer(Code Review)

---

## 第二轮复审（APPROVED）

# BAT-001 一键出发 Code Review（二轮）— 9cd6ecf F1-F3 处置复审

**评审对象:** commit `9cd6ecf`（fix(batch): BAT-001 Code Review 处置 — batch_runner.py / panel.py / panel.html，仅本轮改动 31 行）
**日期:** 2026-09-08
**方式:** 只读复审（单 commit diff + 改动区全上下文精读 + 语义链闭合核对 + verify.py 实跑回归）；未读 userdata/ 真实内容
**结论: APPROVED**

## 核验表

| # | 项 | 结果 | 证据 |
|---|---|---|---|
| F1-1 | 读侧加 except ValueError → return None（batch_runner 侧） | ✅ 按语义落地 | batch_runner.py:67-68 `except ValueError:` 注释「损坏/半写文件 → None → 走重建自愈」+ `return None`；与 FileNotFoundError → None、OSError → sleep 0.05 并列，位于 3 次重试 for 内 |
| F1-2 | 读侧加 except ValueError → return None（panel 侧） | ✅ 按语义落地 | panel.py:250-251 同构（损坏/半写文件 → None → 面板视为无批量，不 500 锁死） |
| F1-3 | 损坏 → None 自愈链在执行器侧闭合 | ✅ 闭合 | _try_claim（batch_runner.py:314-330）：FileExistsError → `_read_state() or {}`（322）→ 损坏读 None → {} → pid=0（323）→ 非存活 → unlink（327）→ for (1,2) 次轮 O_EXCL 重建（316-320）返回 True。O_EXCL 直接 dump 被杀造成的半写文件经 ValueError → pid 0 → unlink → 重建全链打通；附注：UnicodeDecodeError 同为 ValueError 子类，半写 UTF-8 断字节亦被吸收，覆盖宽于仅 JSONDecodeError |
| F1-4 | 损坏 → None 自愈链在面板侧闭合 | ✅ 闭合 | panel.py:271-276 read_batch_state 读 None → `{active:False, crashed:False}`；trigger-all 防双发判定 _batch_active()（257-266）读 None → False → 重按放行 → spawn 执行器重建文件，双侧不再锁死 |
| F2-1 | cancel 重试耗尽后不再假报成功 | ✅ 按语义落地 | panel.py:1361-1370：for (1,2,3) `try: os.replace; break` / `except OSError: sleep 0.05`，循环后 `else:` 内裸 `os.replace(tmp, BATCH_STATE_PATH)`（1370） |
| F2-2 | for/else 语义正确（无残留 break 使 else 永不触发） | ✅ 确认 | for 体内唯一 break 在成功分支（1364，成功即退出，else 被跳过、正常返回 ok）；3 次全 OSError 耗尽 → 无 break → else 执行裸 replace 抛 OSError |
| F2-3 | 抛错落入 do_POST 外层 500 | ✅ 确认 | do_POST try 起于 1124；外层 except Exception（1375-1377）logger.exception + _send_json({'ok': False, 'error': str(e)}, 500)；1370 裸 replace 异常无中间 except 截获，直达 500 |
| F3-1 | terminalPhase 时横幅保留至「知道了」隐藏 | ✅ 齐备 | panel.html:976-977 `terminalPhase`（finished/cancelled）+ show = s.active || s.crashed || (terminalPhase && !batchDoneHidden)；1026-1027 终态非 crashed 渲染「知道了」按钮；1031-1032 onclick → batchDoneHidden=true + 隐藏 → 此后轮询 show=false 保持隐藏（无回闪） |
| F3-2 | 终态 chip（有 run_id）可点 → goAccountRuns（切号+点 runs tab） | ✅ 齐备 | 1016-1021 clickable = success/partial/error/needs_verify/skipped 且 it.run_id，chip 带 data-alias + cursor:pointer；1033-1035 onclick → goAccountRuns；945-950 函数体：alias !== activeAccount 才 setActiveAccount + nav.tabs button[data-tab='runs'] click（与真实 DOM、页签监听吻合，触发 loadRuns） |
| F3-3 | 终态汇总可见性回归安全 | ✅ 确认 | skipped（预检/用户取消）无 run_id → 不可点不误跳；running/pending/waiting_* 不在 clickable 集；crashed 走原 hint 分支不带「知道了」（与既有 crashed 常显语义一致） |
| R-1 | verify.py 16 条 BAT-001 断言锁字面不受影响 | ✅ 逐条快扫无命中 | 锁 panel.py：/api/trigger-all、/api/batch-state、/api/batch-cancel、批量一键出发进行中、batch_state.json、batch_runner.py；锁 batch_runner.py：--batch-all、default=15、cancel_requested、os.replace(+batch_state.json)、waiting_stagger/waiting_guard、def _stale_guard_cleanup、list_runs(acc, keep=1)、api_state(acc)、panel.trigger_run(/panel._load_meta(；锁 html：一键出发、loadBatchState —— 本轮增删行均未触碰任一被锁字面 |
| R-2 | verify.py 实跑回归 | ✅ 通过 121 / 失败 2 | .venv/Scripts/python.exe verify.py 实跑输出「通过 121 / 失败 2」；2 失败均为账号任务未注册（环境态，非本轮回归，与 RED 基线一致） |
| N-1 | batchDoneHidden 在新批量激活时重置 | ✅ | panel.html:975 `if (s.active) batchDoneHidden = false;` — 新一批 active 即恢复终态汇总显示（「知道了」隐藏后重按一键出发 → 新批量 active → 重置 → 横幅再现） |
| N-2 | chip onclick 依赖的 setActiveAccount 可用 | ✅ | panel.html:1065 顶层 function declaration（声明提升）；goAccountRuns 仅在点击时执行，脚本早已整体求值，无 TDZ/未定义风险 |
| N-3 | 内联 onclick 闭包 dataset 读取正确 | ✅ | 1033-1035 forEach 参数 el 每轮独立捕获，el.dataset.alias 点击时读取不串值；每轮 innerHTML 重建 + onclick 重新绑定 → 无重复监听残留 |

## 已核实

- F1 双侧读兜底、执行器 FileExistsError → pid 0 → unlink → 重建、面板 None → active False → 重按覆盖的自愈链在代码里真实闭合（读侧行号见上）。
- F2 for/else 无 break 残留，耗尽后裸 replace 抛错确实落 do_POST 外层 except → 500 + 日志，不再假报成功。
- F3 横幅终态保留/「知道了」/chip 点击跳转三件套齐备，新批量激活重置、函数提升、闭包 dataset 均无问题；verify.py 121/2 与基线一致，无被锁字面受影响。

## 非阻塞备注（P3，不要求修改）

1. 切号场景下 goAccountRuns 会触发两次 /api/runs（setActiveAccount 内部 loadRunsSilent + 页签点击 loadRuns），同 tick 双发为冗余请求；与既有下拉切号模式同构，非本轮新引入，功能无影响。
2. /api/select 与 /api/runs 均为 fire-and-forget，理论存在先按旧 last_account 读到旧号记录的超窄窗口；同源单连接 FIFO 下实际稳定，且同上属既有模式，观察项即可。

— Reviewer（Code Review 二轮）
