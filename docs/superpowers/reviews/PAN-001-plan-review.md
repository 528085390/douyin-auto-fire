# PAN-001 plan 评审（独立门禁）

- 评审对象：docs/superpowers/plans/2026-09-09-panel-account-workspace.md（PAN-001，状态：待用户签字）
- 评审日期：2026-09-09
- 评审方式：独立 Reviewer 子代理实码取证（grep/read/verify.py 文本断言，全程未读 userdata/）
- 结论：**APPROVED**（P3 文档精度建议不阻塞；可进入用户签字环节）

---

# PAN-001 plan 评审（独立门禁）

- 评审对象：`docs/superpowers/plans/2026-09-09-panel-account-workspace.md`（PAN-001 实施计划，最新提交 4ef0099「plan 初稿建档」，头部状态：待用户签字）
- 评审日期：2026-09-09
- 评审方式：独立 Reviewer 子代理实码取证（真实 grep / read / verify.py 运行，全部命令输出见下），全程未读 userdata/；对照依赖 spec（reviews/PAN-001-spec-review.md 两轮终轮 APPROVED，与 plan 头部声明一致，git log 证实）
- 结论：**APPROVED**（2 条 P3 文档精确化建议 + 1 条归档动作，均不阻塞；可进入用户签字环节）

## 一、核验清单逐项结果（取证实录）

### ① RED 诚实性（逐条 grep 实测）

新增类断言 token 在现码 **0 命中**（RED 应失败，成立）：
| token | 扫描文件 | 命中 |
|---|---|---|
| `"source": source` / `meta["source_id"] = source_id` / `meta["targets_detail"]` / `"has_login":` | panel.py | 0 |
| `source="scheduled"` / `source_id=job_id` | scheduler_daemon.py | 0 |
| `source="batch"` | batch_runner.py | 0 |
| `id="accountRail"` / `data-ws=`(任意值) / `srcTimeMap` / `function srcZh` / 管理目标 / 复制为定时任务 / 从手动任务带入 / 全部账号执行 | panel.html | 0（现页签用 data-tab="trigger"，无 data-ws 机制；`全部账号执行` 在 p/s/b/html 四文件均为 0）|

替换/负断言类旧 token 现码命中（RED 失败成立）：`一键出发` panel.py 7 处、scheduler_daemon.py 1 处(:6)、batch_runner.py 5 处、panel.html 10 处；`前台触发` panel.html :320/583/612/849；`一键触发` panel.html :92/252/307/312/339/485/1253 等多处。T2/T3 负断言在 RED 态必然失败，设计成立。

### ② 断言字节 ↔ GREEN 块双向对齐

- T1 六个断言字面量在 §三 GREEN 代码块内逐字可 grep：meta 增行 `"source": source,`、`if source_id:` 块 `meta["source_id"] = source_id`、`meta["targets_detail"] = meta_detail`、accounts 项 `"has_login": bool(...)`、scheduler 调用块 `source="scheduled", source_id=job_id)`、batch 调用块 `source="batch"` —— 全对齐 ✓
- T2 :335 替换：verify.py:335 实测原文与 plan「旧形」逐字一致；新 token `（全部账号执行）进行中` 逐字出现在替换文案 `批量（全部账号执行）进行中，请先取消或等待结束。`（清单 :1216/1241/1295 行）内 ✓
- T3 :348-349 替换：verify.py:348-349 实测原文与 plan 旧形一致；新形保留 `loadBatchState` 子句，GREEN §五.2 壳层含「⚡ 全部账号执行」按钮（新 token 字节在场）✓
- 字节简写 3 处见发现表 F1（id=`accountRail`/data-ws=manual 等/srcZh(src) 与断言字节非逐字同形，语义无二义，RED/GREEN 循环可兜底）。

### ③ 演进表算术

- 基线实测：venv 实跑 verify.py →「通过 148 / 失败 0」exit 0，与 plan 基线一致（148 为运行时执行数；脚本内 check( 文本 135 处，差值来自循环内 check，无异常）
- HTML 锁定面全量清点：verify.py 触碰 panel.html 的检查仅 :325（failed_targets）、:348-349（一键出发+loadBatchState → T3 替换）、:376-378（新建定时任务/loadJobs、开机自启/下次触发、一键迁移/清理旧系统任务）——plan §五.1 保留清单（loadBatchState/loadJobs/failed_targets/新建定时任务/开机自启/下次触发/一键迁移/清理旧系统任务）逐一覆盖，**无漏锁** ✓
- :379-382 not-in 锁定面：batch_runner.py 唯一 `targets=` 子串为 :266 `failed_targets=list(meta...)`（数据字段，非 trigger_run kwargs 调用点），`, targets=` 边界形态不误伤；T1 GREEN 对 batch 仅追加 `source="batch"`（不带 targets/persist_texts，plan 明示），锁面不破 ✓
- 算术复核：148 → T1 RED 总量 154、6 FAIL(148 PASS) → GREEN 154/0 → T2 RED 总量 157(154+3)、4 FAIL(153 PASS) → GREEN 157/0 → T3 RED 总量 167(157+10)、11 FAIL(156 PASS) → GREEN 167/0。T2/T3 替换为 1:1 换断言（:335、:348-349），新增 6+3+10=19，167=148+19 ✓ 各 Task FAIL 组成（6=6 新增；4=:335 替换 1 失败+3 负断言；11=:348 替换 1 失败+10 新断言）与加法全自洽。

### ④ 改名清单完整性

现码 grep 与 plan §四清单逐行对照：panel.py 7 处 = :234(注释)/1216/1241/1295/1342/1346/1366；scheduler_daemon.py 1 处 = :6(注释)；batch_runner.py 5 处 = :1(docstring)/334(argparse)/350/354/361 —— 行号与现文案逐字一致（抽查 panel.py:1366「一键出发已启动：全部账号将顺次执行…」、batch_runner.py:1 docstring、:354 crash 提示等），**清单无漏点**；三文件残留计数 7/1/5 恰等于清单行数。替换文案（§四「替换为」列 + §五.7）均不含旧词 → p/s/b 负断言可绿；注释一并清（严于 spec 4.7 豁免）已在 plan 明示目的。

### ⑤ 变量作用域与插入点

verify.py 实测：`b` = batch_runner 文本（:331 存在性守卫）、`j` :354、`s` = scheduler_daemon 文本（:355 守卫）、`html_txt` = read(panel.html)（:356）、「# --- 汇总 ---」:384。三个新断言块插到 :382 之后、:384 之前 → p/s/b/html_txt 全在作用域内 ✓（T1 断言用到 s，:355 定义在插入点之前；b 虽在 :307 被 config.yaml 复用，:331 起为 batch 文本，插入点在其后无误用）。

### ⑥ Task 顺序与纪律、例外文档化

T1→T4 顺序合理（meta 固化 → 文案收敛 → HTML 重构 → 文档）；每 Task RED/GREEN 独立中文 conventional 提交、文档独立 docs 提交（§二表）。实现锚点行号抽查全部命中现码：trigger_run def panel.py:547-550（plan 称 :549-550 一带）、meta 建档 :582-595（_save_meta :596，新增写入插在 dict 闭合后、_save_meta 前，与现结构相容）、/api/accounts :1066-1072（has_task :1068）、scheduler_daemon trigger_run 调用 :429-433（实含 targets=[dict(t)...]、persist_texts=False，与 GREEN 块形态一致）、batch_runner trigger_run :226-228（现仅 texts/headless/account 三参，追加 source= 不触碰锁面）；account_root 由 panel.py 自 main 导入（:47 一带），GREEN #3 作用域前提成立。T1 改动面仅 panel.py/scheduler_daemon.py/batch_runner.py，douyin.py/jobs.py/main.py/runner.py 零改动承诺与任务描述一致。错误处理无回退：meta 只增不改、老 run 无 source/targets_detail 由前端兜底（§五.5、§七.2），batch 返回 None 重试语义不动。**「断言为准绳」+ 替换类（:335/:348-349）为例外的正式修订条款已文档化**（§六）✓

## 二、评审发现表

| 编号 | 级别 | 位置 | 问题 | 建议 |
|---|---|---|---|---|
| F1 | P3 | plan §五.2/3/4/5 | GREEN 正文用简写 `id=`accountRail``、`data-ws=manual/sched/runs`、`srcZh(src)`，与断言字节 `id="accountRail"`、`data-ws="manual"` 等、`function srcZh` 非逐字同形（HTML 属性/JS 函数定义只有该规范字节形态，语义无二义；即便实现走样，断言为准绳 + RED/GREEN 循环可兜底） | 顺手把 GREEN 正文补成断言字节形态（引号与 function 前缀），消除实现期推断负担，零成本 |
| F2 | P3 | plan §五 RED 期望 | 「10 条新断言失败（其中 3 条为负断言）」措辞含糊：负断言为 2 条 check（:173「一键出发 not in」1 条、:174「前台触发+一键触发 not in」合并 1 条），负断言词为 3 个；FAIL 11 组成不受影响 | 改为「10 条新断言全失败（负断言 2 条 check / 3 个旧词，现码均在）」 |
| F3 | P3 | plan 头部状态行（归档动作） | 依仓库惯例 Reviewer APPROVED 后头部应更新为「待用户签字（2026-09-09 Reviewer APPROVED，reviews/PAN-001-plan-review.md；签字后方可 IMPLEMENT）」并推进 status | Lead 归档本评审时同步更新头部与 status/PAN-001.md 阶段 PLAN APPROVED |

无 P0/P1/P2。F1/F2 为可选的文档精确化，F3 为 Lead 归档动作，均不阻塞签字。

## 三、已核实安全（逐项）

1. 全程未读 userdata/、未触碰账号配置/运行数据；本评审输出不含真实账号别名/会话名/发送内容。
2. plan 全文扫视无真实别名/会话名（占位与脱敏符合仓库纪律）。
3. examples/example-D-account-workspace.html 实测处于未跟踪态（git status ??），plan §八明确默认不入 git，与隐私红线一致。
4. 实跑 verify.py 输出 148/0（0 FAIL，无 FAIL 行携带敏感名）；git HEAD=4ef0099 与 plan 建档提交一致。
5. 评审命令均为只读（grep/read/verify.py 文本断言），未修改任何文件。

## 四、处置建议

1. 归档 reviews/PAN-001-plan-review.md（本评审全文 + 取证命令摘要：grep 0 命中清单、verify.py 行号锚、148/0 实跑输出）。
2. plan 头部状态行与 status 文件按 F3 推进（Lead 执行，独立 docs 提交）。
3. 等待用户会话明确「批准」后方可进入 IMPLEMENT；执行时 T1 RED 块插入「# --- 汇总 ---」之前（:382 后），按实际 verify 输出核对 FAIL/PASS，不以本评审数字替代实跑。
4. F1/F2 属文档精度，可在执行期随行留意，不阻塞。

评审证据摘要：verify.py 关键行 325/331/335/348-349/354-356/376-382/384 与 plan 引用逐一吻合；改名清单 13 行（7+1+5）与 grep 全量一致；T1/T2/T3 全部新断言 token 四文件 0 命中、全部旧 token 现码在位。