# PAN-001 面板前端重构：按账号划分的任务工作区（手动/定时/执行记录一体化）设计

- 日期：2026-09-09
- 状态：待评审（Reviewer APPROVED 后生效，spec 免签）
- 决策来源：2026-09-09 用户会话讨论 + 现网面板实测勘察（panel.html / panel.py / scheduler_daemon.py / verify.py）；前置已批准决策：MAI-001 多账号隔离、SCH-001 定时任务条目库与常驻守护、BAT-001 一键出发串行批量。
- 评审拍板记录（用户逐项确认的需求决策，2026-09-09 会话）：
  1. 重构方向（用户原话）：整体按账号划分；每个账号下再分「手动任务 / 定时任务 / 执行记录」；统一以「任务」为对象创建/执行；每次执行把参数固化到记录中。
  2. 手动任务形态：**每账号一条**「手动任务」卡（可保存/修改/立即执行/复制为定时任务），不建多条手动任务库（贴合现有数据模型，日常续火花为单套内容）。
  3. 「一键出发」跨账号批量：**保留**（BAT-001 串行/错峰 ≥15 分钟语义零改动），从顶部横幅按钮迁到账号导航区作「全部账号执行」入口，进度横幅压缩；不再与单号触发抢视觉入口。
  4. 账号导航：**左侧窄栏常驻账号列表**（状态点直接标在账号上；单账号时自动隐藏），弃顶部下拉+账号栏。
  5. 目标选择统一：手动任务与定时任务共用同一目标管理弹层（会话同步/勾选/类型小标签点切），定时任务不再手打目标文本。
  6. 目标类型控件降噪：类型从每行自定义下拉改为「识别结果小标签，点一下切换」，默认展示扫描识别类型。
  7. 执行记录显示任务来源（手动/定时/批量）与固化参数摘要。
  8. 先出静态 HTML 布局预览再落 spec：2026-09-09 用户对 `examples/example-D-account-workspace.html` 预览确认「可以」（该预览文件为临时产物，不提交 git，废弃后删除）。

---

## 一、背景与问题

面板功能按任务驱动演进（MAI-001 多账号 → SCH-001 定时条目库+守护 → BAT-001 一键出发批量），
功能完整但**信息架构没有随之重构**，页面逐次叠加出现杂乱：

1. **目标概念存在两套编辑 UI**：一键触发页的「目标会话」折叠卡（同步扫描+勾选+每行类型下拉）与
   定时任务「新建定时任务」的手打目标文本（每行一个会话名，隐含强制 `type: "private"`）。
   同一概念两种录入方式，用户心智负担翻倍。
2. **一键触发页职责双载**：既是执行器（文案+触发）又是整套会话管理器，页面主体承载扫描表格与
   行内控件，折叠卡展开时占据整个工作区。
3. **顶部全局条堆叠**：header（状态胶囊+运维按钮）+ 账号栏（账号下拉+运行徽标+一键出发按钮）+
   批量横幅 + 迁移横幅多行常驻；「运行中」状态在 header 状态胶囊与账号栏徽标两处显示。
4. 用户原话（2026-09-09）：「页面有点过于杂乱，触发页面又能选目标，私聊又能选目标」。

## 二、勘察结论（证据表）

| # | 结论 | 证据锚 |
|---|---|---|
| E1 | 现面板为 3 页签：一键触发/定时任务/执行记录 | panel.html:306-310（nav.tabs） |
| E2 | 「一键触发」页内嵌「目标会话」可折叠卡，含一键同步/全选/反选/保存所选与逐行会话表格 | panel.html:330-349（卡片结构）；CSS 折叠上限 max-height:1200px（panel.html:102） |
| E3 | 会话表格每行一个「私聊/群聊」自定义下拉（dselect）与隐藏类型输入 | panel.html:927-946（renderConvList） |
| E4 | 定时任务「新建」目标为手打 textarea；JS 保存时硬编码 type:"private" | panel.html:384-385（textarea）；panel.html:768 `.map(name => ({name, type: "private"}))` |
| E5 | 顶部全局元素：header（logo/标题/状态胶囊/重置/退出）→ 账号栏（账号下拉/运行徽标/添加账号/一键出发）→ 批量横幅 → 迁移横幅 | panel.html:248-278 |
| E6 | 「运行中」状态双处展示：header `#statusPill`（statusText 运行中:current_run）与账号栏 `#runBadge`/`#accountHint` | panel.html:527-575（refreshStatus） |
| E7 | run meta 建档已固化 account/texts/targets（名字串）/起止/status/error；终态补 failed/total/failed_targets | panel.py:586-595（建档 meta 初始 dict）；panel.py:491-512（终态）；panel.py:351-359 `_save_meta` 由 meta["account"] 推路径 |
| E8 | run meta **无来源标记**：手动/定时/批量无法从记录本身区分；调度器在 scheduler_state 的 fired/last_results 里以 job_id 记 run_id 反查（记录与任务来源靠状态文件二次关联） | scheduler_daemon.py:410-463（两段式落盘+收尾 _record）；batch 同理存 batch_state.json |
| E9 | run 列表与详情读 meta.targets 名字串，无目标类型（无法展示私聊/群聊） | panel.py:929-956 一带 api_run_detail 链路（前端 panel.html:836-841）；meta 类型仅名字（panel.py:582-585） |
| E10 | /api/accounts 返回 accounts=[{alias, has_task}]、last_account、legacy；无 per-account 登录状态字段（左栏状态点需补 has_login） | panel.py:1067-1068 |
| E11 | 自检断言锁 HTML 文案 token，重构改名会踩：`一键出发`+`loadBatchState`（verify.py:348-349）、`新建定时任务`+`loadJobs`（:376）、`开机自启`+`下次触发`（:377）、`一键迁移`+`清理旧系统任务`（:378）、`failed_targets` in panel.html（:325） | verify.py:325/348-349/376-378 |
| E12 | SCH-001 锁定 runner.py/batch_runner.py **未接** persist_texts/targets 参数（默认语义保留）；scheduler_daemon.py 不在该锁定内 | verify.py:379-382（仅 rsrc 与 b）；scheduler 调用点在 scheduler_daemon.py:429-433（逐参 targets/persist_texts=False） |
| E13 | 调度触发调用形态：`panel.trigger_run([texts], headless=None, account=..., targets=[dict], persist_texts=False)`；批量调用：`panel.trigger_run(...)`（batch_runner.py:226 起，走账号已存配置） | scheduler_daemon.py:429-433；batch_runner.py:226 |
| E14 | 每账号 runs/ 保留最近 3 条、更早连同截图删除；详情弹窗/截图灯箱/阶段大字 liveLog 均已具备 | panel.py:407-454（list_runs/prune_runs）；panel.html:646-672/829-893 |
| E15 | 《管理面板使用指南.md》仍描述旧 4 页签（①一键触发②选会话③定时任务④执行记录），与现 3 页签代码不一致 | docs/管理面板使用指南.md:80-129 |
| E16 | verify.py 当前基线：**通过 148 / 失败 0**（2026-09-09 实测，exit 0） | `./.venv/Scripts/python.exe verify.py` |
| E17 | douyin.py 执行链（targets 读取/发送/审计）与 jobs.py 数据结构、守护状态机为本次非目标，零改动 | douyin.py:78-85（config targets 读取）；jobs.py 不变 |

## 三、目标与非目标

### 目标
1. 面板信息架构改为**账号优先**：左侧账号列表 + 当前账号工作区（手动任务/定时任务/执行记录）。
2. 手动任务与定时任务共用一套目标选择能力（同一弹层组件、同一会话同步来源），消灭「手打目标」。
3. 目标类型控件降噪：识别结果即展示，点标签才切换。
4. 每次执行记录固化参数（含来源、任务 ID、目标类型快照），列表与详情展示。
5. 顶部杂乱收敛：账号切换/运行状态/一键出发归位，运维入口收起；指南文档同步。

### 非目标（含已拍板排除项）
1. 不引入「多条命名手动任务库」——每账号一条手动任务卡（拍板 #2）。
2. **不取消**跨账号一键出发批量：串行、绝不并发、号间错峰 ≥15 分钟纪律不变（BAT-001 拍板），
   仅迁移 UI 位置与改名（拍板 #3）。BAT 徽标仍显示账号数，批量激活期单号按钮置灰规则不变。
3. 不动 douyin.py 发送/审计/截图链路；不动 jobs.py 任务条目数据结构与守护进程状态机；
   SCH-001「任务目标/文案独有副本、保存后不影响手动配置」语义不变。
4. 每账号执行记录保留最近 3 条、越旧连同截图删除的清理策略不变。
5. 不重做登录/扫码/迁移账号数据流程；不改变「真实账号操作由用户在可见浏览器执行」的边界。
6. 目标管理不恢复为独立页签（维持弹层形态，拍板 #5）。
7. 老记录（缺 source/targets_detail 字段）不迁移回填，仅前端兜底展示（新字段从重构后落盘）。

## 四、方案设计

### 4.1 总体信息架构（账号优先工作区）

```
┌ header：logo+标题 ｜ 单处运行状态 ｜ ⋯（运维：退出/重置运行） ┐
├──────────────┬───────────────────────────────────────────┤
│ 左账号栏      │  工作区（当前账号）                          │
│ · 账号行(状态点)│  [手动任务] [定时任务] [执行记录]            │
│ · ＋添加账号   │   (当前页签内容区)                          │
│ ────────────  │                                           │
│ ⚡全部账号执行  │                                           │
└──────────────┴───────────────────────────────────────────┘
```

- 左侧栏 `aside`：账号行 = 头像/别名/一句副信息（定时 N · 上次状态）+ 状态点（红脉冲=该号运行中、
  琥珀=未登录、绿=就绪，取 `/api/state` 的 running_account 与 `/api/accounts` 新增 has_login）。
  单账号且无 legacy 时整个 aside 自动隐藏（沿用 MAI-001「单号收敛」思路：主区不显账号栏）。
  底部固定「⚡ 全部账号执行」按钮（=现「一键出发」，徽标显示账号数）与「＋ 添加账号」。
- 工作区页签即三视图（下文 4.2/4.3/4.4）。切号 = 切 aside 高亮 + 重载当前视图数据（沿用现
  setActiveAccount 数据源切换逻辑，panel.html:1170-1183）。
- header 只保留标题、**单处**运行状态胶囊（merge 掉账号栏 runBadge/accountHint）、运维「⋯」菜单
  （含退出面板/重置运行/强制重置登录窗口等低频项，常态不占版面）。批量横幅保留但压缩为
  header 下细条（仅激活/终态时出现，取消与「知道了」按钮保留，进度 per-账号 chip 可点击跳该号
  执行记录）。

### 4.2 手动任务视图（每账号一条任务卡）

- 标题「手动任务」+ 语义说明（保存后自动带出；该卡即本账号当前手动配置）。
- 目标区：摘要 chips 行（名称 + 私聊/群聊小标签）；「管理目标」按钮打开目标弹层（4.5）。
- 文案区 textarea +「保存」（写回账号配置，语义=现 /api/save-message）。
- 主按钮「立即执行」（=现 /api/trigger 前台触发，徽标「→ N 会话」）；辅按钮「打开浏览器」。
- 「复制为定时任务」：切到定时任务页签并把当前目标/文案预填进新建表单（**不自动建任务**，
  用户定时刻后点保存）；与新建表单里的「从手动任务带入」同一动作语义。
- 触发后阶段大字与结果提示沿用 liveLog（panel.html:646-672 startPoll 逻辑保留）。

### 4.3 定时任务视图

- 顶部守护状态卡（沿用现卡：运行/停止、下次触发、队列、启动/停止/取消、开机自启——保留
  「开机自启」「下次触发」字样以满足 verify:377）。
- 任务列表表去掉「账号」列（工作区已按账号隔离）；行内目标以同名/同类型 chips 摘要展示。
- 新建表单：目标区用摘要 chips +「管理目标」弹层（同 4.5 组件，面板复用同一 DOM 弹层，两个入口
  设置同一弹层上下文）；文案区与现一致；「每天时间」输入；保存仍走 /api/jobs POST（jobs.py
  独有副本语义零改动，目标对象保留 {name,type}，不再有 JS 侧硬编码 private 的文本路径）。
- 「旧版迁移与清理」卡保留在本页底部但仅在 legacy 存在时展示内容（token「一键迁移」「清理旧
  系统任务」仍在 HTML 中，满足 verify:378；平时收起减少噪点）。

### 4.4 执行记录视图（来源 + 固化参数）

- 行字段：时间 / 来源徽标 / 固化参数摘要 / 状态 / 查看。
  - 来源徽标：`meta.source` → manual=「手动」、scheduled=「定时 21:30」（取 source_id 对应任务时刻，
    无则泛称「定时」）、batch=「批量」；老记录无 source → 兜底按「手动」展示并弱化样式（E7/E8 兼容）。
  - 固化摘要：`目标 N · 文案「截断」`；有 failed_targets 时红字「未送达：…」（保留 verify:325 链路）。
- 详情弹窗沿用现结构，新增「固化参数」区：目标逐行（名称 + 类型标签，读 targets_detail）+
  文案原文 + 来源与触发时刻 + 错误/未送达 + 日志 + 证据截图（原 detailVerify/needs_verify 引导保留）。
- 批量/定时执行后自动刷新逻辑保留（loadRunsSilent 等）。

### 4.5 目标管理弹层（共用组件）

- 标题「选择目标」+ 上下文行（手动任务 / 新建定时任务 · 当前账号）。
- 顶部动作：一键同步（=现 /api/sync-conversations + pollConv 轮询，弹层内展示扫描中状态）/
  全选 / 反选；会话行 = 复选框 + 名称 + **类型小标签按钮**（默认扫描识别结果；点击在
  私聊/群聊间切换，样式区分；不再每行一个展开式下拉）。
- 底部计数（共扫描 N · 已选 M）+「保存所选」（手动入口走 /api/save-targets 写账号配置；
  定时任务入口把所选目标写回弹层上下文表单暂存，随任务保存进 /api/jobs）。
- 复用点：panel.html 现有 modal/.dselect 之外新增 typetgl 形态；E3 的行内 dselect 从会话行移除
  （dselect 控件可整体退役或保留给其它需要处，不锁 token）。

### 4.6 后端增量（最小面，douyin.py 零改动）

1. `trigger_run` 增加关键字参数 `source: str = "manual"`、`source_id: str | None = None`
   （panel.py:547-550 签名区），建档 meta（panel.py:586-595）补 `meta["source"]=source`，
   有 source_id 时补 `meta["source_id"]=source_id`。缺省 manual → 现 /api/trigger（panel.py
   手工触发端点）、runner.py CLI、main.py CLI 行为不变。
2. `targets_detail` 固化：meta 增 `meta["targets_detail"]` = 逐目标 `{name, type}` 规范化快照
   （保留现 `meta["targets"]` 名字串字段不动，兼容 E9 既有展示与断言）。取值归一：t 为 dict 取
   name/type，为 str 则 type 记 "unknown"。
3. 调用点打标：scheduler_daemon.py:429-433 传 `source="scheduled", source_id=job_id`；
   batch_runner.py:226 起调用传 `source="batch"`。**不得**引入 `persist_texts`/`targets` 新词到
   runner.py 或 batch_runner.py 的既有锁定面（verify.py:379-382 token 不触碰：batch 调用只加
   source，不带 targets/persist_texts）。
4. `/api/accounts`（panel.py:1067-1068）返回数组项补 `has_login`（browser_data 目录存在性），
   供 aside 状态点；字段只增不改，老前端字段读取零影响。
5. 目标类型进入 run meta 的快照由 4.6.2 承担；jobs 创建端点与 jobs.py **零改动**（前端按
   4.5 传 {name,type}，不再经 JS 硬编码 private 文本路径）。

### 4.7 文案与命名收敛

- UI 规范用名：批量动作 =「全部账号执行」（原「一键出发」文案退场，见 E11 同步替换 verify token
  为 `全部账号执行`，保留 `loadBatchState` 函数名）；页签 =「手动任务 / 定时任务 / 执行记录」；
  目标统一称「目标会话」或「目标」；按钮 =「立即执行 / 保存 / 管理目标 / 打开浏览器 / 复制为
  定时任务 / 从手动任务带入」。
- verify.py:325/376-378 的 token（failed_targets、新建定时任务、开机自启/下次触发、一键迁移/
  清理旧系统任务）在新 HTML 中**继续存在**，断言不动。

## 五、错误处理（场景 × 行为）

| 场景 | 行为 |
|---|---|
| 账号未选目标即「立即执行」 | 前端禁用提示「先在目标里选至少一个会话」；后端既有拒绝语义保持（空 targets 报错路径不变），不做假成功 |
| 会话同步中再点同步/执行 | 沿用现 busy 置灰与 409 语义（sync_running/批量激活期），同步轮询仅弹层内提示 |
| 批量激活期操作单号按钮 | 沿用 busy 置灰 + 后端 409（panel.py 文案「批量一键出发进行中」保留，verify:335 不动） |
| 老记录缺 source / targets_detail | 前端兜底：source 按「手动」弱化展示；目标摘要回落 meta.targets 名字串；不迁移回填 |
| 浏览器环境 file:// 打开 | badEnv 错误提示保留 |
| 零账号 / 未迁移 legacy | 空态整页引导与迁移横幅保留（aside 空态隐藏自身，主区居中引导）；「旧版迁移与清理」内容仅在 legacy 出现 |
| 运行/登录/批量进行中切号 | 沿用现跨账号 busy 与 running_account 提示（refreshStatus otherRunning 语义），切号不改执行中的 run |
| 需要安全验证 / 部分失败 | 沿用 needs_verify/partial 状态、detailVerify 引导文案与「打开浏览器」处理路径 |
| 守护停止/未启 时看定时任务 | 守护状态卡红色提示+启动按钮；任务保存等不受守护运行态影响（沿用） |
| 弹层打开期间同步完成 | pollConv 收尾刷新列表与计数，不关闭弹层 |

## 六、验证方案（RED / GREEN 分层）

- 基线：verify.py 通过 148 / 失败 0（2026-09-09 实测，E16）。
- 断言策略（文本断言语义按仓库纪律：独立 token / 带引号字面量 / 边界形态，见 douyin-auto-fire
  skill；RED 期望按「基线 + 新增 - 结构替换」口径，最终数字由 plan 定稿）：
  - **替换类**：`一键出发` → `全部账号执行`（verify.py:348-349 同步；两者 RED 态一旧一新增，
    演进表按替换对计）；断言仍含 `loadBatchState`。
  - **保留类（断言不动）**：failed_targets（HTML 未送达展示）、新建定时任务 + loadJobs、
    开机自启/下次触发、一键迁移/清理旧系统任务、批量一键出发进行中（panel.py 拒绝文案）。
  - **新增类（锁新形态）**：panel.py `"source": source`（或等价独立字面量）、`"source_id":`
    与 `targets_detail` 词、`has_login`（accounts 端点）；panel.html 锁「管理目标」、
    「复制为定时任务」、aside 结构标记（`data-ws` 或等价的唯一 class/id，plan 定字节）、
    来源徽标渲染函数名（如 `srcZh`/`renderSource`，plan 定名）。每个断言字节须与 plan 的
    GREEN 实现块预对齐（提交 RED 前 grep 双向核对）。
  - 非目标面零扰动断言维持（douyin.py/jobs.py/scheduler 各节不动，runner/batch 锁定断言保持）。
- 功能冒烟（无真实发送）：verify.py 全绿；面板服务真实启动 + 只读接口链（/api/accounts、
  /api/state、/api/jobs、/api/runs）用 curl 抽查返回新字段；浏览器人工核验清单（给 Tester）：
  左栏切号数据联动、手动卡「管理目标」增删保存、复制为定时任务预填、定时任务保存后列表与
  独有副本、执行记录来源徽标与老记录兜底、批量横幅压缩形态。
- 真实运行验证（含 scheduled/batch 来源落盘）需用户逐次授权，计划中列为收尾待办不默认执行。

## 七、风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | HTML 大改引入 JS 回归（轮询/弹层/切号状态联动） | verify 锁关键 token + 人工浏览器冒烟清单覆盖主路径；DOM id 尽量沿用（liveLog/statusPill/convListWrap 等）降低回归面 |
| R2 | 改名后 verify 替换 token 与其它断言互扰 | 替换前对 verify.py:325-383 逐条盘点（已做，E11/E12），只动 348 一处 |
| R3 | 老 run meta 无 source/targets_detail | 前端兜底 + 不迁移；新字段仅新记录落盘 |
| R4 | 批量横幅压缩后丢失取消/进度可读性 | 保留取消按钮、per-账号 chip 与跳转；仅视觉压缩 |
| R5 | 双命名残留（一键出发/全部账号执行并存） | 统一文案（4.7）；verify token 替换为唯一词，防回潮 |
| R6 | 弹层复用导致手动/定时上下文串扰 | 弹层打开时按来源设置上下文并记录目标暂存区；保存目标只写入调用上下文，互不覆盖 |
| R7 | docs 指南再次漂移 | 指南重写与 HTML 重构同 plan；文档与代码独立 docs 提交 |

## 八、待确认

1. examples/example-D-account-workspace.html（布局预览，临时产物）评审期间保留供对照，spec
   APPROVED 后由用户决定删除或保留（**默认不进 git**，本 spec 不依赖其入库）。
2. 执行记录详情弹窗展示完整固化文案原文（默认）；若担心隐私展示可只显示前 N 字，未拍板前按默认。

## 九、实施顺序（供 plan 参考）

1. RED：verify.py 替换与新增断言（docs 提交先行不适用——verify.py 属 test 代码，随 Task 提交；
   顺序按 TDD：RED test 提交 → GREEN 实现提交）。
2. GREEN-A（panel.py 最小增量）：trigger_run source/source_id/targets_detail + scheduler_daemon /
   batch_runner 打标 + /api/accounts has_login（独立 test/fix 提交，跑既有 verify 保持零破坏）。
3. GREEN-B（panel.html 重构）：壳层 + 三工作区 + 目标弹层 + JS 联动 + 文案收敛。
4. docs：管理面板使用指南.md 重写（四页签→账号工作区；含新字段说明）。
5. 收尾：verify 全绿 + git status 干净 + 人工浏览器冒烟 + 真实运行来源落盘验证（需授权）。
