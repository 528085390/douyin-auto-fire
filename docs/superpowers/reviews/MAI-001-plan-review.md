# MAI-001 多账号目录隔离 — Plan 独立评审

- 日期：2026-09-05
- 评审对象：`docs/superpowers/plans/2026-09-04-multi-account-isolation.md`（commit 68934d7，1336 行）
- 对照基准：spec 版本 2（commit 0b20f8b/0d9824d，已 APPROVED）；真实代码 main.py/panel.py/runner.py/verify.py/douyin.py/config.yaml（当前 HEAD）；基线实测 `verify.py` exit 0（plan 第 140 行「全绿」属实，复核时重跑确认）
- 结论（版本 1，2026-09-05）：**CHANGES_REQUIRED**（P0 无漏网；P1 × 4；P2 × 6）
- **版本 2 复核结论（2026-09-05，commit fdb4352）：APPROVED** —— P1×4/P2×6 已全部逐条关闭；复核中未见新 P0/P1；1 条不阻塞建议见「五、版本 2 复核」。

---

## 一、P1 发现（须修订 plan 后才能进 IMPLEMENT）

### P1-1 切号后会话列表内存不随账号重载——spec 4.4（P2-3）「切号缓存重载」只落地了保存侧，展示/勾选侧仍是上一账号列表
- **位置**：plan Task 4 Step 4/6/7（panel.py `_conversations` 内存语义、`/api/select`、`api_conversations`）；spec 4.4「会话缓存内存态重载」要求
- **问题链**：内存 `_conversations` 只在面板启动时按 last/唯一账号种一次（Step 7）；`POST /api/select` 只写 `last_account` 且 plan 明言「后端无需额外重载（读取路径按 account 现读）」；但 `api_conversations(acc)`（Step 5）返回的是**内存** `_conversations`，不是按账号读文件。于是：启动在账号 A → 切到账号 B → B 未在本会话同步过 → `GET /api/conversations?account=B` 返回的仍是 A 的内存列表 → B 页签勾选区显示 A 的会话 → 用户照看到的内容勾选并保存 → B 的 `targets` 被写成 A 的会话名 → B 号按 A 的目标发送（spec 1.3 明言 wrong_conversation 不防账号目标错配）。「保存前重读文件合并」双保险只修正了文件写入，没修正数据源，P2-3 要防的串账号场景在展示链路原样存在。
- **必改**：plan 写明切号/读取路径重载内存——`/api/select` 生效时或 `api_conversations(acc)` 解析后，若 `acc` ≠ 内存当前归属账号，先 `_conversations = _load_conversations_cache(acc)` 再返回/允许勾选（并删掉「后端无需额外重载」的表述）。

### P1-2 Task 4 后 verify 第 4 节 `api_tasks()` 缺参 TypeError，plan 交叉引用指向错误步骤——Task 4 无法达到「近全绿无 traceback」
- **位置**：plan Task 4 Step 5（`api_tasks(account)` 必选 account）vs verify.py:112/118/124 三处 `h = panel.api_tasks()["health"]`；Task 1 Step 3 注「…见 Task 4 Step 6」→ 实际 Task 4 Step 6 是新端点，不含此适配；Task 4 Step 8 只回填 runner 与 verify.py:82
- **问题链**：Task 4 落地后 verify 顺序执行到第 4 节（第 4 节在 MAI 节之前），`api_tasks()` 缺必选参数直接 TypeError traceback → 后续 MAI 节与汇总不执行，违反「无 traceback」纪律，Task 4 Step 8 Expected 与 Task 6「失败 0、exit 0」均无法达成。plan 把 stub 参数化（`lambda *a, **k`）做对了，却漏了**调用点**也要传参。
- **必改**：Task 4 Step 8 显式加一条：verify.py 第 4 节三处调用改为 `panel.api_tasks("main")`（占位账号，stub 已 mock load_config/query_system_task，不触真实账号数据），并修正 Task 1 Step 3 的交叉引用为 Task 4 Step 8。

### P1-3 CLI `--setup-login` 不经跨进程守卫，违反 plan 自身 Global Constraints 21（A2）与 spec R7
- **位置**：plan Task 3 Step 4（`if args.setup_login: DouyinStreak(config).setup_login()` 直接调用、无守卫）；plan Global Constraints 21「runner/面板/手动（含 login/sync 窗口，评审 A2）全走守卫」
- **问题链**：main.py `--setup-login` 打开可见登录浏览器，绕过 `acquire_run_guard`。此时另一账号的定时任务进程触发（账号 browser_data 已隔离、目录锁兜底消失）→ 两个浏览器跨账号并存——正是 A2 声称已消除的边界，在 CLI 登录路径原样复现，R7「同一时刻绝不并发」不完整。
- **必改**：`--setup-login` 分支同样 `acquire_run_guard(alias)` + `finally: release_run_guard()`（与 Task 3 Step 3 手动路径一致）；或把约束 21 措辞明确限定为面板内 login/sync——plan 内必须自洽，不能既声称全走守卫又给出不走守卫的代码。

### P1-4 verify 断言 `'"userdata/accounts"' in m` 与 Task 2 提供的实现永不匹配——该断言永久红，Task 6「exit 0」死锁
- **位置**：plan Task 1 MAI 断言第 222 行 `check("main.py 引用 userdata/accounts", '"userdata/accounts"' in m)`；Task 2 Step 1/4 提供的代码
- **问题链**：断言要求 main.py 源码含**带双引号字符**的完整字面 `"userdata/accounts"`（引号紧跟 userdata 前后）。但 Task 2 实现是 `ACCOUNTS_ROOT = USERDATA_DIR / "accounts"`（路径由常量拼接），create_account 注释里的 `userdata/accounts/<别名>/` 前无引号字符——所有 plan snippet 均不产生该字面。该断言从 Task 1 红到 Task 6 永远不绿 → 「失败 0、exit 0」死锁；若实现者为过测试硬塞一个装饰性字面，则落入 V2「焊死契约」反模式。
- **必改**：断言与实现二选一对齐。推荐：断言改为 `"userdata/accounts" in m_no`（去引号的子串，Task 2 create_account 写入的注释天然含 `userdata/accounts/`，语义成立）；或改为组合断言 `'"accounts"' in m and "ACCOUNTS_ROOT" in m`。若保留带引号断言，则 Task 2 必须明确在 docstring/注释产出该字面（如 account_root docstring 写 `USERDATA_DIR / "accounts"` 的完整路径说明）。spec 4.6-1 的引号是行文记号，不是要求源码含引号字面。

---

## 二、P2 发现（不阻塞签字但建议修订，避免实现期踩坑）

### P2-1 Task 2 Step 7 期望与断言时序不符 + 「finally in main」断言过弱
- Task 2 守卫 snippet（acquire/release）本身无 `finally`；`"finally" in m` 断言要到 Task 3 手动路径 `finally: release_run_guard()` 落地才转绿。Task 2 Step 7 期望文字「守卫等已实现」应注明该条 Task 3 才绿。且该断言只查词法 `finally`，不验证释放形态——建议追加 `"release_run_guard()" in m` 或注明接受弱断言。

### P2-2 trigger_run 守卫获取与进程内锁检查顺序未定义，早退路径释放语义缺失
- Task 4 Step 4 先写「进入函数先 acquire_run_guard」，再保留进程内锁检查；若守卫获取成功后才因进程内锁早退 return None，守卫无人释放（活 pid 残留，同面板会话内后续触发全被拒，reset 不删守卫）。建议：进程内锁检查在前、守卫获取在后，守卫获取失败直接 return None（无残留窗口），plan 写明顺序与早退释放责任。

### P2-3 adopt-legacy 在账号无 schedule.time 时静默删旧任务不注册新任务
- 若 legacy 判定命中在 browser_data/runs 而顶层 user_data.yaml 缺失（migrate 后账号目录无 user_data.yaml），`tm` 为空 → 跳过注册仍删除旧任务并返回成功文案 → 用户每天定时静默消失。建议：tm 缺失时返回明确提示（不删旧任务或提示手动）；migrate 后若账号缺 user_data.yaml 补 create_account 同款骨架。

### P2-4 迁移路径未查跨进程守卫
- `/api/migrate`（Task 4 Step 6）与 CLI `--migrate`（Task 3 Step 4）只查进程内 `_current_run/_login_running/_sync_running`，spec R2 修订后为「检查守卫 + 全局锁」。现依赖浏览器目录占用安全失败，可接受但应补守卫检查或明示该依赖。

### P2-5 Task 4 Step 2 文字自相矛盾
- 「`_save_meta(meta)`（meta 含 account，路径从 meta["account"] 推）签名统一为显式 account」——两句冲突，plan 定一个形态（建议 `_save_meta(meta)` 从 meta["account"] 推，与 run meta 携带 account 一致）。

### P2-6 实施窗口（Task 2–4 之间）旧定时任务行为退化
- Task 2 起旧任务经 `load_config()`（无 alias）只拿公开键 → 0 targets 空跑；Task 3 起 `resolve_account` 对未迁移旧数据 exit 2 → 旧任务当日发送失败。属重构期固有窗口，但 plan 未提示。建议：Task 2–4 在同一会话连续完成勿跨夜留中间态，并在 Task 7/提交说明提示用户该窗口旧任务不可用。

---

## 三、已核实安全（供实现直接引用）

- **基线属实**：plan 第 140 行「本机 verify 全绿 exit 0」复核实测 EXIT=0。
- **Task 1 RED 诚实性**：逐条核对当前代码——main.py 无 finally/O_EXCL/ACCOUNTS_ROOT/account 字样（`grep -c` = 0）；panel.py/runner.py/config.yaml 目标字面（_resolve_account/端点/load_config(account)/--account/account=/多账号注释）均不存在 → 预判失败真实，非空真。唯一例外是 P1-4（该条永不转绿）与 P2-1（finally 延后到 Task 3）。
- **第 3 节改造兼容**：退回旧分支调 `panel.query_system_task()`（现签名 `name: str = TASK_NAME`，后续 `name=None` 兼容语义成立）；`_probe_task` 显式传名当前已支持。
- **守卫闭环**：runner 15 分钟 deadline 退出/daemon worker 被终止 → 无 finally 删除 → 陈旧守卫由 pid 探测自愈覆盖；run meta.account + `_find_run_account` 遍历定位（run_id 唯一）可行；reset 不删守卫的语义与自愈一致。
- **runner texts 链路安全**：即便 api_state 默认解析拿到空列表，`trigger_run(account)`/`_worker` 按 account 重载 cfg 私有键，实际发送内容出自该账号配置（runner.py:72 回填属 Task 4 Step 8 已列事项）。
- **截图路径穿越防护保留**（meta.account 反查 + resolve/startswith 前缀不放宽）；`_send_screenshot` 按账号 run_dir 解析与 spec 4.4 一致。
- **A1 legacy 锚定、A2 login/sync 面板侧走守卫、保留设备名校验、config 注释断言（Task 6 转绿）、单账号零打扰/多账号 exit 2/`--migrate` 出口**均与 spec 一致，无新洞。
- 别名校验/任务名纯 ASCII、`task_name(alias)` 前缀语义、TASK_NAME 仅迁移收尾用等常量设计自洽。

---

## 四、版本 1 结论（2026-09-05，已被版本 2 修订关闭，保留作记录）

Plan 结构（Task1 RED → Task2-5 分步实现 → Task6 文档 → Task7 人工核对）与仓库惯例一致，绝大多数断言字面经核对可按时序转绿；但 P1-1（spec 4.4 P2-3 未真正落地，展示/勾选链路仍会串账号会话列表）、P1-2（verify 第 4 节调用点漏改 → TypeError）、P1-3（CLI --setup-login 绕过守卫，违反 plan 自身约束与 R7）、P1-4（一处断言与实现永不匹配 → Task 6 无法 exit 0）须修订后再进 IMPLEMENT。P2×6 建议一并采纳，避免实现期踩坑。

---

## 五、版本 2 复核（2026-09-05，commit fdb4352，APPROVED）

### 5.1 关闭核验（对照版本 1 各评审项）

| 评审项 | 版本 2 修订落点 | 复核判定 |
|---|---|---|
| P1-1 切号后会话列表内存不随账号重载 | 新增模块级 `_conversations_account` + `_ensure_conversations_for(account)`（读前/保存前/`/api/select` 切号时统一按账号重载内存；sync 后置归属；启动种子置归属）；删除「后端无需额外重载」表述 | **已关闭**：api_conversations 读路径每次先 ensure（归属不符即重载），即使 select 请求丢失/乱序，读路径也自愈；保存前 ensure + 重读文件合并双保险。spec 4.4 P2-3 落地完整。 |
| P1-2 verify 第 4 节 `api_tasks()` 缺参 TypeError + 交叉引用错 | Task 4 Step 8 显式加「verify 第 4 节调用点适配（必做）」：verify.py:112/118/124 → `api_tasks("main")`；Task 1 Step 3 交叉引用改指 Task 4 Step 8；Task 4 Step 9 提交含 verify.py | **已关闭**：调用点与签名变更同 Task 4 一步提交（Task 1-3 期间 api_tasks() 仍无参可跑，旧节保持绿）；占位 `"main"` 不会触真实数据（stub mock；未 mock 也只读）；第 124 行健康检查在无 `DouyinAutoFire-main` 任务时仍绿（health 只查「存在且坏」的任务），与真实账号任务校验（MAI 第 3 节 `_probe_task`）职责不重叠。 |
| P1-3 CLI `--setup-login` 绕过守卫 | Task 3 Step 4 `--setup-login` 分支改 `acquire_run_guard(alias)` + try/finally `release_run_guard()` | **已关闭**：与 Global Constraints 21/手动路径自洽；异常路径 finally 释放。 |
| P1-4 断言 `'"userdata/accounts"' in m` 永不匹配 | 断言改为 `"ACCOUNTS_ROOT" in m and '"accounts"' in m`（与 Task 2 `USERDATA_DIR / "accounts"` 字面一致），删除原不可能字面 | **已关闭**：RED 期当前 main.py 无 `"accounts"` 字面（真红）；Task 2 落地即转绿；Task 6 exit 0 无死锁。 |
| P2-1 finally 断言时序 + 过弱 | 断言升级为 `"release_run_guard()" in m and "finally:" in m`；Task 2 Step 7 期望注明该条 Task 3 手动路径落地才转绿 | **已关闭**：Task 3 的 CLI `--migrate` try/finally 与手动路径 finally 同批落地；释放形态断言比纯 `finally` 词法更有意义。 |
| P2-2 trigger_run 守卫与进程内锁顺序 | Task 4 Step 4 锁定顺序：进程内锁检查 → 守卫获取 → 起线程；守卫失败直接 return（无早退残留窗口）；线程启动异常 try/except 释放后 re-raise；login/sync 同序 | **已关闭**：消除了「守卫已获但函数早退」残留窗口。 |
| P2-3 adopt-legacy 无 schedule.time 静默删旧任务 | 无 tm → 400 明确提示（先设时间注册，再删旧任务），不删旧任务；`migrate_legacy_to_account` 迁移后补全账号骨架（user_data.yaml/browser_data/runs/conversations_cache） | **已关闭**：不再静默丢任务；browser_data-only legacy 迁移后账号具备四类标准件，adopt/面板读取自洽。 |
| P2-4 迁移路径未查跨进程守卫 | CLI `--migrate` 与 `/api/migrate` 均 `acquire_run_guard` + finally release（进程内锁 + 跨进程守卫双查） | **已关闭**：与 spec R2 一致。 |
| P2-5 `_save_meta` 表述矛盾 | Task 4 Step 2 统一形态：读 `_load_meta(run_id, account)` 显式收 account；写 `_save_meta(meta)` 从 `meta["account"]` 推路径 | **已关闭**。 |
| P2-6 实施窗口旧任务退化未提示 | Global Constraints 新增「实施窗口提示」（Task 2-4 连续完成勿跨夜、交付说明向用户明示）+ 风险节同步 | **已关闭**。 |

### 5.2 复核中新检查点（无新 P0/P1）

- ensure-on-read 自愈：sync 线程与切号并发时，即使 sync 完成晚于切号把内存写回旧账号，下一次 `api_conversations`/保存前 ensure 会按归属校正——读路径是最终防线，无展示串号窗口。
- 新断言 `"ACCOUNTS_ROOT" in m and '"accounts"' in m` 在当前 main.py 为真红；其余改动未引入新的不可能字面。
- Task 4 Step 8 的 `api_tasks("main")` 在「无 main 账号 + 无 DouyinAutoFire-main 任务」的开发机上第 124 行健康检查仍绿（health 语义只拦「存在且坏」的任务），与真实账号任务校验职责分离。
- verify 第 4 节三处调用点适配与 `api_tasks` 签名变更同 Task 4 提交，Task 1-3 期间无 TypeError 窗口。
- CLI `--migrate` 守卫持有期间会拦任何运行/登录/同步（跨进程），与 R2「守卫 + 全局锁」一致；迁移过程无浏览器并发。

### 5.3 不阻塞建议项（可自愿采纳，无需再走 plan 修订）

- **B1**：migrate 补骨架写入默认 `schedule.time: "21:30"` 与 `texts: ["在吗"]` 后，browser_data-only legacy 账号执行 adopt-legacy 会直接按 21:30 注册任务——符合「补全骨架」语义但默认值即生效；建议 Task 7 核对清单或文档提示用户迁移后核对「定时任务」页时间与内容是否为自己真实值（当前清单第 3/4 步已覆盖，仅提示更明确）。

---

## 六、最终结论

**APPROVED**（版本 2 plan，commit fdb4352）。版本 1 的 P1×4/P2×6 全部关闭，复核未发现新 P0/P1；B1 为不阻塞建议项。按 `.hermes.md` 流程，plan 待用户签字后进入 IMPLEMENT。
