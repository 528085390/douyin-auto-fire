# MAI-001 多账号目录隔离 — Spec 独立评审

- 日期：2026-09-05
- 评审对象：`docs/superpowers/specs/2026-09-04-multi-account-isolation-design.md`（commit f70a18b）
- 评审方法：逐条核对 spec「二、勘察结论」引用的真实代码行号区间；核对 4.1/4.2/4.4/4.6 设计承诺与 `main.py / panel.py / runner.py / douyin.py / verify.py / config.yaml` 现状的相容性。
- 版本 1 结论（2026-09-05）：**CHANGES_REQUIRED**（P0 无漏网；P1 × 4；P2 × 5）
- **版本 2 复核结论（2026-09-05，commit 0b20f8b）：APPROVED** —— P1×4/P2×5 已全部逐条关闭；复核中未见新 P0/P1；3 条不阻塞建议项见「五」。按 `.hermes.md` 门禁，spec 经 APPROVED 即生效（无需用户签字），下一用户签字门禁在 PLAN。

---

## 一、P1 发现（须修订 spec 后才能进 plan）

### P1-1 跨进程「同一时刻绝不并发」无任何强制机制，且本次改动会移除现有唯一兜底
- **位置**：spec 三.5（执行纪律）、七.R7（同一时刻绝不并发）、四.3（每账号一条独立计划任务）
- **问题**：每条定时任务由 schtasks 各自拉起一个独立 `pythonw runner.py` 进程（runner.py:47-99），每个进程 `import panel` 后拿到**自己进程内**的 `_run_lock`（panel.py:107-112）。面板内的串行锁只在「面板进程内部」生效；两条独立定时任务 = 两个互不知晓的进程。现状单任务时代不构成问题（同一时刻只有一条任务），但 spec 把「A 号 12:00 跑、B 号 12:15 跑」变成两条独立任务后，A 号运行超时（>15 分钟或 B 准点触发而 A 的 runner 还在 15 分钟 deadline 内轮询）时，B 号照常启动——**串行纪律在定时任务主路径上落空**。
- **为什么严重**：更隐蔽的是，今天存在一个隐性的跨进程兜底：所有运行共享同一 `userdata/browser_data/`，Playwright persistent context 目录锁会让第二个并发浏览器**启动失败并留痕**（douyin.py:157-166 的占用提示）。本次改动把 browser_data 按账号隔离后，这个兜底**消失**：两个账号并发 = 两个浏览器同时打开、互不报错。R7 的「同一时刻绝不并发」从「机制保证」退化为「时间安排建议」，与 spec 自身「风控纪律优先于吞吐」的立场冲突（同设备同指纹两号同开，正是 R7 想防的连坐场景）。
- **必改**：spec 增加跨进程互斥机制条目（建议：`userdata/` 级全局运行守卫文件/锁——trigger_run 入口先独占创建 `userdata/.running`（含 account+pid+start），退出 finally 释放；runner/面板/交互手动三路共用；verify 4.6 增加对应结构断言），或明确改写 R7/三.5 为「仅面板进程内串行，跨任务并发靠时间错峰且无硬兜底，接受偶发重迭风险」。当前文字两者都不是。

### P1-2 `real_chrome_profile: true` 可绕过账号 browser_data 隔离，R1 的「登录态不可能串」保证不成立
- **位置**：spec 四.1（load_config(alias) 覆盖 browser.user_data_dir）、七.R1（browser_data 目录隔离让登录态不可能串）；真实代码 douyin.py:135-140
- **问题**：douyin.py `_open_browser` 中，`real_chrome_profile` 为真时 `user_data_dir` 被**直接替换为真实 Chrome 目录**（douyin.py:135-140），发生在 load_config 覆盖之后，per-account `browser_data` 完全失效。真实 Chrome profile 是单份登录态：两号各自定时跑时**共用同一个 Chrome 登录态**，正是串号本身（A 的任务拿 B 的登录态 + A 的 targets）。该键当前为 false（config.yaml:28，且注释记录用户已拍板关闭），但代码分支完整保留、配置注释描述其为「可选启用」，spec 全篇未约束该键与账号隔离的交互，4.7 文档同步清单也未列入。
- **必改**：spec 明示该键与账号隔离的互斥语义并写入 4.7：多账号期间 `real_chrome_profile` 视为不支持/必须保持 false（config.yaml 注释 + README 配置参考同步警告），R1 保证措辞收窄为「在 real_chrome_profile 关闭前提下登录态不可能串」；若允许保留则须给出按账号映射真实 profile 的方案（属范围外，建议直接禁）。

### P1-3 `ensure_userdata()` 仍自动创建顶层骨架 → `legacy_pending()` 恒真，迁移引导条迁移后复现、新装机死循环
- **位置**：spec 4.1（legacy_pending 探测条件「顶层 user_data.yaml 或 browser_data 存在即提示」，R3）、4.2；真实代码 main.py:45-60（ensure_userdata 缺失即写顶层骨架），panel.py:50 与 runner.py:33 在 import 期无条件调用 ensure_userdata
- **问题链**：按 spec 现状描述改造后，若 `ensure_userdata()` 行为不变，则**每次**面板/runner 启动都会在顶层重新生成 `user_data.yaml`（空骨架）+ `browser_data/`。于是：
  1. 老用户迁移成功后顶层文件被移走 → legacy 清除；但下一次启动 ensure_userdata 又重建空骨架 → `legacy_pending()` 复真 → **迁移引导条在成功迁移后永久复现**，永远无法「直到迁移完成」。
  2. 全新用户（本无旧数据）首次启动即被判定 legacy=true，被迫先走一次「迁移空骨架」；若先点了「＋ 添加账号」再迁移，则 migrate 目标别名与已建账号冲突被拒（4.2 规则「account_root 已存在 → 拒绝」），UI 进入无出口状态。
- **必改**：spec 明确多账号后 `ensure_userdata()` 的边界——只保证 `userdata/` 目录与基础设施日志（run.log/panel.log）存在，**不再**自动创建顶层 `user_data.yaml/browser_data/runs/conversations_cache.json`（这些改由 `create_account` 在账号目录内创建）；或 legacy 判定改为「顶层含真实数据」（如 user_data.yaml 的 targets/message/schedule 非空、browser_data 非空目录、runs 非空），二选一并写死探测语义。

### P1-4 「load_config(alias) 一律显式、无隐式默认」与零账号/基础设施读路径冲突，面板首次启动即可能崩
- **位置**：spec 4.1（alias 一律显式传参，不设隐式默认）、4.6-5（AST 断言 load_config/update_* 定义收 alias）；真实代码 panel.py:944-950（`main()` 启动先 `cfg = load_config()` 读 `panel.port`）、panel.py:213-219（包装 `_main_load_config`）
- **问题**：用户升级后第一次启动面板时必然处于「零账号」（旧数据未迁移或全新装）状态；若按 4.6 把 `load_config` 锁成**必须收 alias 且无默认**，panel 启动读端口、以及空态引导前任何读取都会因无账号可用而抛错/崩溃——恰是该仓库真实踩过的「启动路径 AttributeError 型」故障类别（verify.py 模块 API 契约检查就是为了防这类）。spec 未划清「账户数据读写」与「基础设施读（config.yaml 公开键：panel.port/logging/browser 全局）」的界线。
- **必改**：spec 明确基础设施读取保留无账号入口（如 `load_config(alias=None)` 只合并 config.yaml 公开键、不碰任何账号私有文件；账户数据读写路径才强制显式 alias），并注明 4.6 断言应锁定「账户数据函数收 alias」而不把纯公开配置读取一并锁死。

---

## 二、P2 发现（不阻塞签字，但建议一并修订）

### P2-1 verify.py 第 4 节 monkeypatch stub 随签名变化会自爆，「既有断言全部保留」表述不准确
- verify.py:108-122 用 `panel.load_config = lambda: {...}`、`panel.query_system_task = lambda *a, **k: ...` 打桩后调用 `panel.api_tasks()`；若 `api_tasks`/`load_config` 改为收 account，零参 stub 直接 TypeError（verify 自己变红且原因与「新保证未实现」无关，污染 RED 阶段判定）。4.6-7 应注明：断言保留 ≠ stub 不改，verify 内部打桩需随签名同步适配。

### P2-2 五、错误处理「旧任务残留 → runner 报错」与 4.3「恰 1 账号自动用」表述打架
- 单账号场景下（迁移完成、旧任务未删），按 4.3 规则旧任务会**自动沿用唯一账号继续跑**（设计意图的零打扰），并不报错；五、该行只有「多账号（>1）时 runner exit 2 报错留痕」才成立。行文应限定为多账号场景，避免 plan 在单账号残留分支误加报错。

### P2-3 切号后内存 `_conversations` 重载时机未定，存在把 A 号会话名并入 B 号缓存的风险
- 4.4 只写了缓存函数按账号解析、save-targets 路径强制 account；但保存逻辑（panel.py:896-904）会把内存 `_conversations` 列表并入缓存文件。若切号后未先按新账号重载内存列表，A 号列表会并入 B 号文件（数据不串号但会话勾选数据串账号）。plan 必须把「切号 → 重载该账号缓存进内存 → 才允许勾选/保存」写成显式步骤（或改为保存时直接读账号缓存文件合并）。

### P2-4 截图 URL 无 account 参数，切号后陈旧 DOM 请求可能错读目录
- `/api/screenshots/<rid>/<file>`（panel.py:836-840）若按 GET 缺省解析（last_account）服务，切号后旧列表里的 img 请求会指向当前账号目录。run_id 全局唯一且 meta 将带 account 字段——建议截图/明细解析按 run_id 的 meta.account 反查目录（只读查询也不依赖 last_account），比「默认账号」更稳，且不破坏路径穿越防护。

### P2-5 别名校验未挡 Windows 保留设备名
- `^[A-Za-z0-9_]{1,24}$` 允许 `CON/NUL/PRN/AUX/COM1…/LPT1…`（大小写不敏感），Windows 上 `accounts/CON` mkdir 会失败且报错文案与「非法别名」不符。校验函数应一并拒绝保留设备名（或文档登记该错误为预期并给可读文案）。

---

## 三、已核实安全（供 plan 直接引用，避免复审返工）

- **E1–E10 全部属实**：main.py:33-37 模块级私有路径常量、main.py:42 `_PRIVATE_KEYS`、main.py:63-76 `load_config` 分层合并、main.py:124-148 三个 update_* 无账号参数、panel.py:41-48 直接导入 main 私有函数、panel.py:101-114 全局运行状态与 TASK_NAME、panel.py:213-219 包装 load_config、panel.py:330-434 worker/trigger_run、panel.py:539 `query_system_task(name=TASK_NAME)`、verify.py:82-105 第 3 节固定任务名探测、panel.py:811-936 路由无账号参数（GET 取 path 忽略 query）、douyin.py:134 user_data_dir 来自 cfg 注入（发送核心与目录解耦成立）、config.yaml:5-28 浏览器公开配置全局共享——与 spec 引用一致。
- **目录化改造点可行**：douyin.py 唯一目录耦合点 = `_open_browser` 的 `user_data_dir`（douyin.py:134-151）；`load_config(alias)` 合并后覆盖该键的注入点正确，发送/校验/审计核心可零改动，与 E7 结论一致。
- **迁移文件清单与现状布局吻合**：顶层现存文件/目录 = user_data.yaml / conversations_cache.json / browser_data/ / runs/ / run.log / panel.log（main.py:31-37、panel.py:101-114、runner.py:34），4.2 移动清单与「基础设施日志留全局」的划分干净。
- **run_id 时间戳全局唯一设计不因账号化退化**：同一账号串行触发下同秒碰撞需单次运行 <1s 才可能（现状同样存在），跨账号目录隔离后碰撞也不可能交叉写文件，可接受。
- **R1 目录物理隔离方向正确**：即便某路径 cfg 读错账号，browser_data 目录隔离在 real_chrome_profile 关闭时保证登录态不串（P1-2 修掉后成立）。
- **别名字符集/任务名 ASCII 化**（评审拍板 ②）与 verify 第 3 节按账号探测的改造方向自洽；4.6 的 RED→GREEN 顺序与仓库 verify.py 惯例一致。

---

## 四、版本 1 结论（2026-09-05，已被版本 2 修订关闭，保留作记录）

spec 大方向（目录化 + 显式账号 + 面板联动）与代码现状吻合、可实施；但 P1-1~P1-4 涉及「并发纪律机制保证」「登录态隔离保证」「迁移探测语义」「零账号启动」四处 spec 级承诺与真实代码/自身要求矛盾或悬空，须修订后再进入 plan 编写。建议由 @lead 采纳本评审修订 spec 后重新提交复核（可逐条对照本文件确认关闭）。

---

## 五、版本 2 复核（2026-09-05，commit 0b20f8b，APPROVED）

### 5.1 关闭核验（对照版本 1 各评审项）

| 评审项 | 版本 2 修订落点 | 复核判定 |
|---|---|---|
| P1-1 跨进程并发无强制机制 | 三.5 升级为「.running 跨进程守卫」硬机制；4.1 目录图；4.3 O_EXCL 独占创建（account+pid+start_ts）/finally 删除/陈旧守卫按 pid 存活探测自愈（tasklist）/占用文案带账号+pid；4.4 进程内锁+守卫双层；4.6-5 新增守卫断言；五 增两行错误处理；R7/R8 改写；九-2/4 入实施顺序 | **已关闭**：从「时间安排建议」升级为独占文件机制 + 崩溃残留自愈；runner/面板/手动三路均经 `trigger_run` 汇聚，守卫覆盖三路。原「browser_data 目录锁兜底消失」问题由机制性守卫替代。 |
| P1-2 real_chrome_profile 绕过隔离 | 4.1 新增互斥约束段（引用 douyin.py:135-140 证据链）；R1 措辞收窄（加前提从句）；4.7 config.yaml/README/配置参考三处加警告；4.6-5 断言注释含互斥字样 | **已关闭**：R1 不再过度声称；约束+文档+断言齐备，与「用户已拍板关闭该键」事实一致；按账号映射真实 profile 明确划入范围外（组合二）。 |
| P1-3 ensure_userdata 重建顶层骨架 | 4.1 ensure_userdata 语义收窄（只保证 userdata/ 与基础设施日志父目录，不再建顶层 user_data.yaml/browser_data/runs/cache；panel.py:50、runner.py:33 import 调用不再制造空骨架）；create_account 在账号目录内建骨架；legacy_pending 改为内容判定（空骨架/空目录不算）；R3/九-2 同步 | **已关闭**：迁移后顶层文件移走且不再被自动重建 → 引导条不复发；新装机顶层恒空 → 不误判 legacy。原「迁移后复现/新装死循环」链条被切断。 |
| P1-4 load_config 无账号路径崩溃 | 4.1 `load_config(alias=None)` 双入口（None=只合并 config.yaml 公开键、不 ensure 顶层骨架、不碰账号私有文件；面板启动读 port panel.py:947 等零账号路径可用）；4.6-5 断言范围收窄（只锁账户数据函数与运行路径显式传参，不再锁 load_config 本体） | **已关闭**：零账号/基础设施读有明确无账号入口；防串号断言与双入口语义不再冲突。 |
| P2-1 verify stub 自爆 | 4.6-7 注明「断言保留 ≠ stub 不改」，stub 适配属 RED 本分 | **已关闭** |
| P2-2 单账号自动沿用表述打架 | 4.3 runner 行 + 五 错误处理行均限定「多账号（>1）场景报错；单账号自动沿用唯一账号不报错」 | **已关闭** |
| P2-3 切号内存缓存未重载 | 4.4 新增「会话缓存内存态重载」：切号后先重载新账号缓存进内存才允许勾选/保存；保存路径双保险（重读账号缓存文件合并） | **已关闭** |
| P2-4 截图 URL 无 account | 4.4 runs 明细/截图按 run_id 的 meta.account 反查目录（不依赖 last_account/当前账号）；R4 同步 | **已关闭** |
| P2-5 Windows 保留设备名 | 4.1 别名校验增拒 `CON NUL PRN AUX COM1-9 LPT1-9`（大小写不敏感）；五/4.6-8/R6 同步 | **已关闭** |

### 5.2 复核中新检查点（无新 P0/P1）

- runner 定时路径取 texts（现 runner.py:72 `panel.api_state()`）改为账号化后即使默认解析拿到空列表，`trigger_run(account)` 与 `_worker` 均会按 account 重载 cfg 私有键（texts 为空时不覆盖），实际发送内容仍出自该账号配置 → 无串号路径。
- 守卫与迁移并发：迁移触发前提仍写「全局锁判断」，跨进程运行中迁移会因 browser_data 目录被占用而安全失败并留未迁移清单（4.2 幂等续迁），可接受。
- 陈旧守卫在「runner 15 分钟 deadline 退出、daemon worker 被进程终止」场景下无 finally 删除 → 残留由 pid 探测自愈覆盖，闭环自洽。
- run_id 时间戳全局唯一 + meta.account 反查：URL 无 account 时需遍历账号目录定位 meta（run_id 唯一，至多命中一个），实现可行。
- RED 阶段 verify 第 3 节改造需对尚未实现的 `list_accounts()` 做存在性探测（hasattr/容错），否则 RED 会以 AttributeError 崩溃而非预期 FAIL——属 plan 编写时 RED 诚实性本分（沿用仓库惯例），不阻塞。

### 5.3 不阻塞建议项（可自愿采纳，建议 plan 吸收，无需再走 spec 修订）

- **A1（P1-3 关闭项加固）**：legacy_pending 内容判定「user_data.yaml 含 targets/message/schedule 任一非空键」仍会把旧版 ensure_userdata 生成的默认骨架（`message.texts: ["在吗"]`、`schedule.time: "21:30"` 均非空，仅 targets 为空）判为 legacy。新版不再生成顶层骨架后影响收敛为「曾运行旧版/降级」场景且空壳迁移无害；建议判定锚定 `targets` 非空 **或** `browser_data/` 非空 **或** `runs/` 非空，与骨架默认值语义彻底解耦。
- **A2（P1-1 边界说明）**：守卫只在 `trigger_run` 创建；`trigger_login`/`trigger_sync` 的浏览器窗口不受跨进程守卫约束（同账号撞目录仍会安全失败；跨账号会短暂并存两个浏览器，初始扫码期由用户在场约束）。建议 login/sync worker 也检查/持有守卫，或至少在文档注明边界。
- **A3（流程文书）**：spec 头部仍为「状态：待用户签字」，与 `.hermes.md:82-83`（spec 免签：Reviewer APPROVED 即生效，头部应为「状态:待评审」；用户签字门禁在 PLAN）不一致；MAI-001.md「Plan: 未开始（spec 签字生效前禁止编写）」同口径。建议 @lead 放行门禁时同步头部与状态文件，直接进入 PLAN 编写（本次无需再等 spec 签字）。

---

## 六、最终结论

**APPROVED**（版本 2 spec，commit 0b20f8b）。版本 1 的 P1×4/P2×5 全部关闭，复核未发现新 P0/P1；A1–A3 为不阻塞建议项。门禁放行后按 `.hermes.md` 进入 PLAN（plan 的用户签字门禁保留）。
