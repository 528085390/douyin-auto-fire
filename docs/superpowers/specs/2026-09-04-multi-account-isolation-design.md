# 多账号目录隔离：账号自定义别名 + 每账号独立环境/数据 + 面板账号切换 — 设计文档（spec）

- 日期：2026-09-04
- 版本：2（2026-09-05 按 MAI-001-spec-review 评审修订：P1×4 采纳 + P2×5 采纳，见「十、评审修订」）
- 状态：已批准（2026-09-05 Reviewer APPROVED，`reviews/MAI-001-spec-review.md`；按 `.hermes.md` 71481d5 spec 免签）
- 决策来源：2026-09-04 多账号需求咨询对话。用户确认：共 2 个抖音号都要每天自动续火花；
  采用「组合一：纯代码目录化 + 错峰」路线（登录态/目标/文案/审计按账号隔离，**不做**指纹浏览器/代理 IP）；
  管理面板需顶部账号切换并联动三块数据；按仓库 superpowers 流程出 spec → plan 再实施。
- 评审拍板（2026-09-04，用户逐项确认，见「八、评审拍板记录」）：① 账号别名**用户自定义**且**仅限
  英文/数字/下划线**（任务名/目录名直接用别名，规避中文任务名兼容性风险）；② 真实迁移/扫码等操作
  由用户在面板执行，agent 只交付代码；③ 面板账号栏交互草案照此实现；④ `--run-once` 无 `--account`
  且多账号时报错列账号（防串号）。

---

## 一、背景与问题

### 1.1 现状：全局单账号模型

当前整个代码库围绕「一份私有数据 + 一份登录态」的单一布局构建，不存在账号维度：

| 层 | 现状 | 证据 |
|---|---|---|
| 路径 | 全部是 main.py 模块级常量（user_data.yaml / runs / browser_data / 会话缓存），panel.py 导入复用 | main.py:31-37；panel.py:41-48, 101-114 |
| 私有配置 | 顶层 `userdata/user_data.yaml` 一份（targets/message/schedule 平铺） | main.py:42 `_PRIVATE_KEYS`，main.py:63-76 `load_config` |
| 登录态 | `userdata/browser_data/` 唯一一份 cookie | config.yaml:11；douyin.py:134-141 |
| 执行 | 全局串行锁 + 单一 runs/ + 单一会话缓存 | panel.py:107-114；panel.py:330-434 |
| API/UI | 所有端点与页面三块（一键触发/定时任务/执行记录）无账号参数 | panel.py:811-936；panel.html |
| 定时任务 | 固定任务名 `DouyinAutoFire` 一条 | main.py:39；panel.py:104 |

「多目标」只是**同一登录账号下多个会话**（私聊/群聊混合），不是多账号。

### 1.2 需求

1. 2 个抖音号各自每天自动续火花，账号之间完全隔离：登录态、目标会话、发送内容、发送时间、执行记录、会话缓存。
2. 账号别名叫**用户自定义**（非固定 default/账号A 之类），能区分出哪个号。
3. 管理面板增加账号切换：顶部切换当前账号，三个页签内容（会话勾选、发送内容、定时任务、执行记录）随账号联动。
4. 多账号之间的执行**错峰**（风控纪律），每账号一条独立定时任务。

### 1.3 差距与风险

任何一处路径/配置漏改，最坏后果不是报错而是**串号**：号 B 的定时任务拿着号 A 的登录态与 targets 去发消息。
`wrong_conversation` 复检只防「会话发错」，不防「账号用错」——串号是本改动最高优先级要防住的回归。

---

## 二、勘察结论（证据表）

| 编号 | 结论 | 证据 |
|---|---|---|
| E1 | 所有私有路径是 main.py 模块级常量，全局唯一 | main.py:33-37 |
| E2 | `load_config()` 只合并顶层 user_data.yaml，无账号维度 | main.py:63-76；panel.py:213-219（包装 main.load_config） |
| E3 | 写私有配置的三个函数无账号参数（面板直接导入） | main.py:124-148；panel.py:41-44 |
| E4 | runner.py 导入 main 常量并全链路单账号（--run-once → panel.trigger_run） | runner.py:30-34, 69-95 |
| E5 | 面板运行状态是全局变量（串行锁/登录/同步/会话缓存），import 期即初始化 | panel.py:107-114, 163 |
| E6 | 面板 API 全路由无账号参数（GET 不解析 query，POST 只读 body） | panel.py:811-936（do_GET 用 `urlparse(self.path).path`） |
| E7 | douyin.py 的浏览器目录来自 cfg.browser.user_data_dir 注入 → 发送核心与目录解耦，改造集中在配置/入口层，发送逻辑可零改动 | douyin.py:134-151 |
| E8 | verify.py 第 3 节探测**固定任务名** DouyinAutoFire；若任务改名/多任务化而 verify 不跟着改 → 自检永远红 | verify.py:82-105；panel.py:539 `query_system_task(name=TASK_NAME)` |
| E9 | 浏览器公开配置全局共享（channel=chrome/headless 等），两号指纹相同——已知的环境隔离局限（组合一） | config.yaml:5-28 |
| E10 | README / user_data.yaml.example / 五份 docs 全部单账号描述 | README.md:24-47；user_data.yaml.example |

---

## 三、目标与非目标

### 目标

1. **账号目录隔离**：每个账号独立目录 `userdata/accounts/<用户自定义别名>/`，内含自己的
   `user_data.yaml`、`browser_data/`（登录态）、`runs/`（执行记录+截图）、`conversations_cache.json`（会话缓存）。
   四类数据完全按账号分开，互不读写。
2. **现有单账号数据一次性迁移**：检测到旧顶层数据时，由面板/CLI 引导用户给现有号起别名并迁入
   `accounts/<别名>/`；迁移后顶层目录不再承担账号数据（仅剩基础设施日志）。
3. **面板账号切换**：标题下账号栏（下拉 + 当前运行账号徽标）；一键触发/定时任务/执行记录三块随当前账号联动；
   支持「+ 添加账号」；记住上次选择；旧数据迁移引导条（含「沿用旧定时时间注册新任务并删旧任务」一键操作）。
4. **CLI/定时任务账号化**：`--account <别名>`；交互模式先选账号；每账号一条独立计划任务
   `DouyinAutoFire-<别名>`，时间各自设定（UI/文档提示错峰 ≥15 分钟）。
5. **执行纪律不变（跨进程互斥升级为硬机制）**：进程内全局串行锁保留（同一时刻只跑一个号的浏览器），
   **新增 `userdata/` 级跨进程运行守卫文件**（`trigger_run` 入口独占创建 `userdata/.running`（含 account+pid+start），
   finally 释放；runner 定时任务 / 面板一键触发 / CLI 手动三路共用）——因为每账号一条独立 schtasks = 独立进程，
   进程内锁与「browser_data 目录锁」（改造后按账号隔离而消失）都管不住跨进程并发，守卫是 R7「同一时刻绝不并发」
   的机制保证；状态里明确当前在跑哪个账号；跨账号并发执行是**非目标**（风控纪律优先于吞吐）。
6. douyin.py 发送/校验/审计核心零改动；verify.py 全绿（exit 0）并新增防回归断言（先 RED 后 GREEN）。
7. 同步更新 config.yaml 注释、user_data.yaml.example 与五份 docs。

### 非目标（本次不做，另行排期/明确放弃）

- **指纹/IP 级环境隔离（组合二）**：不引入指纹浏览器、不按账号配代理。两号仍同设备同指纹同出口 IP，
  靠错峰 + 低频私信降险；如日后实测被风控再评估升级（目录化是升级的地基，不白做）。
- **账号删除/重命名 UI**：删除 = 手动删 `userdata/accounts/<别名>/`（文档说明）；重命名涉及目录+任务名联动，2 号场景不需要。
- `--all` 一键全账号、跨账号并行执行、每账号独立 run.log（保留全局 `userdata/run.log` 基础设施日志；
  账号级痕迹 = 各自 runs/ 下的 `<id>.json/.log/截图`）。
- 面板既有非目标清单（XSS 转义、CSRF/Origin、截图路径前缀陷阱等，见 2026-09-04 发送判定 spec 八）维持不变。

---

## 四、方案设计

### 4.1 账号目录布局与解析（main.py）

```
userdata/
├── .running                      # 跨进程运行守卫（独占文件：{account, pid, start}，运行结束 finally 删除）
├── accounts/<别名>/            # 每个账号一个目录（别名用户自定义，创建时校验）
│   ├── user_data.yaml           # targets / message / schedule（私有键，结构同现状）
│   ├── browser_data/            # 登录态（cookie），DouyinStreak 持久化目录
│   ├── conversations_cache.json # 会话列表缓存
│   └── runs/                    # 执行记录：<id>.json + <id>.log + 截图目录
├── panel_state.json             # {last_account: 别名}（面板记忆，轻量，gitignored）
├── run.log / panel.log          # 基础设施日志（保持全局，不进账号目录）
└── （旧顶层 user_data.yaml / browser_data / runs / conversations_cache.json 迁移后清空）
```

main.py 新增（模块级常量 `USERDATA_DIR` 等保留为基础设施用）：

- `ACCOUNTS_ROOT = USERDATA_DIR / "accounts"`
- `account_root(alias) -> Path`：`ACCOUNTS_ROOT / alias`（调用方保证别名已校验）
- `list_accounts() -> list[str]`：扫描 `accounts/` 下含 user_data.yaml（或 browser_data）的子目录名，排序返回
- `create_account(alias) -> Path`：校验别名 → mkdir → 写 user_data.yaml 骨架 + browser_data/ + runs/ +
  conversations_cache.json `[]`（镜像现有 `ensure_userdata` 行为，骨架注释同款中文头部）
- **`ensure_userdata()` 语义收窄（评审 P1-3）**：只保证 `userdata/` 目录与基础设施日志（run.log/panel.log
  父目录）存在，**不再**自动创建顶层 `user_data.yaml / browser_data / runs / conversations_cache.json`
  ——这些私有骨架改由 `create_account` 在 `accounts/<别名>/` 内创建；panel.py:50 与 runner.py:33 的
  import 期调用因此不再制造「顶层空骨架」，新装机顶层恒空 → 不会误判 legacy。
- `load_config(alias=None)`（评审 P1-4）：**基础设施读取保留无账号入口**——`alias=None`（默认）只合并
  config.yaml 公开键（panel.port / logging / browser 全局设置），**不 ensure 顶层私有骨架、不碰任何账号
  私有文件**，面板启动读 port（panel.py:947）、空态引导前等零账号路径用它；传入 alias 才合并该账号私有键
  （targets/message/schedule）并覆盖 `browser.user_data_dir`。账户数据读写/运行路径一律**强制显式 alias**，
  **无隐式默认**（防串号的核心手段，见 4.6 断言）。
- `load_user_data(alias)` / `update_schedule_time(alias, ...)` / `update_message_texts(alias, ...)` /
  `update_targets(alias, ...)`：账户数据函数全部收 alias，读写 `account_root(alias)`
- `legacy_pending() -> bool`（评审 P1-3）：顶层 **存在真实数据**才算未迁移——`user_data.yaml` 存在（含
  targets/message/schedule 中任一非空键）**或** `browser_data/` 为非空目录；顶层**空骨架/空目录不算**。
  （配合 ensure_userdata 收窄：迁移成功后顶层不再被自动重建，引导条不会复现；新装机也永远不会 legacy=true。）
- `migrate_legacy_to_account(alias) -> dict`：见 4.2

**别名校验规则**（面板/CLI 共用同一函数，错误文案给全；评审拍板：仅英文/数字/下划线）：
1~24 个字符，`^[A-Za-z0-9_]+$`（首字符建议字母，纯数字/纯下划线虽合法但不推荐）；
不允许中文、空格、`-` 及 Windows 文件名字符 `\ / : * ? " < > |`、首尾点；
**并拒绝 Windows 保留设备名**（评审 P2-5）：`CON NUL PRN AUX` 及 `COM1`–`COM9`/`LPT1`–`LPT9`
（大小写不敏感）——否则 `accounts/CON` 这类 mkdir 会失败且报错文案与「非法别名」不符，
校验函数直接挡下并给可读文案。
目录名 = 别名原文（纯 ASCII，无编码风险）；任务名 = `DouyinAutoFire-<别名>`（纯 ASCII）。

`load_config(alias)` 的关键强制：合并后 **覆盖** `browser.user_data_dir =
str(account_root(alias) / "browser_data")`（config.yaml 里的旧 `user_data_dir` 键从此只是兜底注释值，
语义见 4.7 文档同步）。**运行/写入路径上 alias 一律显式传参，不设隐式默认**（防串号的核心手段，见 4.6 断言）。

**`real_chrome_profile` 互斥约束（评审 P1-2）**：多账号目录隔离的「登录态不可能串」保证**只在
`real_chrome_profile: false` 时成立**——douyin.py:135-140 在该键为真时会用真实 Chrome 登录态目录
**替换** `load_config(alias)` 覆盖后的 per-account `user_data_dir`，两号将共用同一份 Chrome 登录态
（A 的任务拿 B 的登录态 + A 的 targets，正是串号）。该键现状为 false 且用户已拍板关闭；**多账号期间
视为不支持、必须保持 false**（4.7 文档同步在 config.yaml/README/配置参考 三处加警告），R1 措辞相应收窄。
按账号映射真实 profile 的方案属范围外（组合二），不在本次实现。

### 4.2 旧数据迁移（一次性）

检测：`legacy_pending()` 为真且 `list_accounts()` 为空 → 面板顶部出现迁移引导条
「检测到现有单账号数据，为它命名以启用多账号：[别名输入] [开始迁移]」；CLI 提供
`python main.py --migrate <别名>`。

`migrate_legacy_to_account(alias)` 行为（幂等，可安全重跑）：

1. 校验别名；`account_root(alias)` 已存在 → 拒绝（提示换名或先手动处理）。
2. mkdir `accounts/<别名>/`。
3. 逐项移动（源存在才移，`shutil.move` 同盘 rename 速度快）：
   `user_data.yaml`、`conversations_cache.json`（文件），`browser_data/`、`runs/`（目录）。
4. 任一步失败不中断整体：记录失败项，返回剩余未迁移清单；重跑续迁。
5. 成功后日志提示：旧任务 `DouyinAutoFire` 仍在，建议用面板「同步注册新任务并删除旧任务」按钮收尾（见 4.5）。
6. 调用前提：面板无运行/登录/同步进行中（复用全局锁判断）。

### 4.3 CLI / runner / 定时任务

- `main.py` argparse 新增：`--account <别名>`、`--migrate <别名>`、`--list-accounts`。
- 账号解析规则（非交互）：`--account` 显式给 → 用之；未给且 `list_accounts()` 恰 1 个 → 自动用该账号
  （单账号用户零打扰）；未给且多个 → 报错并列出可用别名（exit 2）；未给且 `legacy_pending()` → 提示先
  `--migrate`。`--test` 免账号。
- **跨进程守卫入口（评审 P1-1）**：`trigger_run(...)` 最先独占创建 `USERDATA_DIR/.running`（内容 JSON：
  `{account, pid, start_ts}`，`O_CREAT|O_EXCL` 语义；已存在则读其内容判断——同账号重复触发也拦，
  cross-account 更拦），`finally` 块删除；进程内 `_run_lock` 继续管面板内并发，**守卫管跨进程**
  （runner 独立进程与面板/手动互斥）。守卫被占时的报错文案带「账号 <X>（pid <Y>）正在运行中」。
  **陈旧守卫自愈**：创建时若 `.running` 已存在，先检查其记录的 pid 是否存活（Windows 用
  `tasklist /FI "PID eq <pid>"` 或等价探测）；pid 已不存在 → 视为上次进程崩溃的残留，删除后重试一次
  （正常路径跑不到重试，残留自动清理，不会永久锁死）；pid 存活 → 拒绝并报运行中。
- 交互模式：开头若需账号且未指定 → 列表选择（`[1] main  [2] backup`，占位示例），再进原 1/2 菜单。
- `task_name(alias) = "DouyinAutoFire-" + alias`（`TASK_NAME` 常量语义改为「旧单账号任务名/前缀」，仅迁移收尾用）。
- `try_register_task(time_str, alias)`：`schtasks /Create /TN <task_name(alias)> /TR "<pythonw> <runner.py> --run-once --account <别名>" /SC DAILY /ST <time>`。
- runner.py：解析 `--account`（缺省同 main 规则，但**迁移完成后的单账号场景旧任务自动沿用唯一账号属预期
  （P2-2），不报错留痕**；仅多账号（>1）且无 `--account` 时才 exit 2 报错留痕）；`trigger_run(texts,
  headless=None, account=…)`；轮询 `_load_meta(run_id, account)`。

### 4.4 面板数据层与 API（panel.py）

- **路径函数账号化**：`_meta_path/_log_path/_run_dir/list_runs/prune_runs`、
  `_load_conversations_cache/_save_conversations_cache` 全部改为按 `account_root(account)` 解析；
  run meta 增加 `"account"` 字段（写回 meta 时带出）。run_id 时间戳全局唯一不变。
- **锁语义：进程内锁 + 跨进程守卫双层**（评审 P1-1）：`_current_run/_login_running/_sync_running` 保持全局
  （面板进程内串行纪律），另按 4.3 的守卫文件管跨进程；新增 `_current_run_account`（本次运行属哪个号，
  api_state 返回），另一账号页面上按钮同样置灰，文案说明「账号 <X> 正在运行中」。
- **worker 账号化**：`_worker/_login_worker/_sync_worker` 携带 account：
  `cfg = load_config(account)`；`update_message_texts(account, ...)` 回写；截图目录在账号 run 目录内；
  会话缓存读写账号文件。progress 回调不变（全局串行所以无歧义）。
- **账号解析统一入口**：`_resolve_account(query/body)`——GET 用 `urlparse` + `parse_qs` 取 `account`，
  POST 取 body/query；缺省 = `last_account`（panel_state.json）→ 仍无则唯一账号 → 仍无则报错
  「请先添加账号」。**只读查询允许缺省；触发/扫码/同步/保存/注册等动作路径一律要求显式 account**。
- **新端点**：
  - `GET /api/accounts` → `{accounts: [{alias, has_task?}], legacy: bool, last_account}`（首次加载/轮询）
  - `POST /api/accounts {alias}` 添加账号（409 已存在 / 400 非法别名）
  - `POST /api/migrate {alias}` 迁移旧数据（成功后若检测旧任务存在，返回 `legacy_task: true` 供前端亮出收尾按钮）
  - `POST /api/tasks/adopt-legacy {alias}`：读该账号 user_data 的 schedule.time/message.texts →
    注册 `DouyinAutoFire-<别名>` → 成功后删除旧 `DouyinAutoFire`（幂等：旧任务不存在则直接 ok）
  - `POST /api/select {alias}` 记忆 last_account
- **既有端点**：`/api/state` `/api/runs` `/api/conversations` `/api/runs/<id>[/screenshots]`、
  `/api/tasks`（GET/POST）、`/api/tasks/disable|enable|delete`、`/api/setup-login`、`/api/run-reset`、
  `/api/login-reset`、`/api/sync-conversations`、`/api/save-targets`、`/api/save-message`、`/api/trigger`
  全部按账号作用（account 来自 query/body）。
  **runs 明细/截图按 run_id 的 meta.account 反查目录**（评审 P2-4：run_id 全局唯一且 meta 带 account
  字段 → 只读也不依赖 last_account/当前账号，切号后旧列表请求仍指向原账号目录，不跨号猜）；
  截图文件服务 `_send_screenshot` 相应按 meta.account 解析路径，原路径穿越防护逻辑不放宽。
- **会话缓存内存态重载（评审 P2-3）**：切号成功（POST /api/select 生效）后**必须先把新账号的
  conversations_cache.json 重载进内存 `_conversations`，之后才允许勾选/保存**——否则内存里残留的 A 号
  会话列表会在保存时并入 B 号缓存文件（勾选数据串账号）。保存路径双保险：保存前重新读取该账号缓存文件合并，
  不直接信内存全局列表。

### 4.5 面板 UI（panel.html）

```
┌────────────────────────────────────────────┐
│ 抖音自动续火花 · 管理面板            [就绪]  │
│                                            │
│   当前账号:  [ main ▾ ]     运行中: backup  │   ← 新增账号栏
│   [一键触发]  [定时任务]  [执行记录]          │
│   ……当前账号 main 的数据……                   │
└────────────────────────────────────────────┘
```

- 账号栏位于标题下、页签上：账号下拉（仅一个账号且无 legacy 时隐藏）+ 运行徽标。
- 下拉底部「＋ 添加账号…」（弹输入框 → `POST /api/accounts` → 自动切换到新账号并引导扫码）。
- **迁移引导条**（`/api/accounts` 返回 legacy=true 时置顶显示，直到迁移完成）；
  迁移成功后若 `legacy_task` → 显示「同步注册 <别名> 的定时任务并删除旧任务」按钮（`/api/tasks/adopt-legacy`）。
- 空态（无账号无 legacy）：整页中央「添加第一个账号」引导。
- 所有 fetch 统一带当前账号（JS 变量 `activeAccount` + 一个 `api(path, opts)` 封装自动附 `account`）；
  切换账号先 `POST /api/select` 再全量刷新当前停留页签；切换后记住停留 tab。
- 三块联动：会话勾选/保存（当前账号缓存）、发送内容预填、执行记录列表/详情/截图、
  定时任务注册与启停状态，全部只反映当前账号；切号即换数据源。

### 4.6 verify.py 防回归断言（先 RED，plan 内定字节级形态）

沿用仓库「字符串/AST 断言」惯例，只锁保证形态、不锁行号。概念清单：

1. 账号布局与解析在 main.py：去注释后含 `ACCOUNTS_ROOT`、`account_root(`、`"userdata/accounts"`；含 `migrate_legacy_to_account`。
2. CLI：main.py 含 `"--account"`、`"--migrate"` argparse 定义；注册命令形态 `'"schtasks", "/Create"'` 保留（既有断言）。
3. runner.py：含 `"--account"` 解析且保留既有断言（`panel.trigger_run`、`headless=None`、`--run-once`）。
4. panel.py：含 `"/api/accounts"`、`"/api/migrate"`；账号解析统一入口存在（如 `_resolve_account`）。
5. **防串号守卫**：写/运行路径必须显式账号——断言形态示例：main.py 的 `update_*` 与账户数据函数
   （`load_user_data` 等）定义收 `alias` 参数（AST 查参数名）；**`load_config` 是基础设施+账户双入口
   （alias=None 合法，P1-4），只断言账户数据函数与运行路径显式传参**，如 `trigger_run` 定义收 `account`
   参数；凡 `DouyinStreak(cfg)` 构造处 cfg 必经 `load_config(...account...)`（plan 选可断言的形态，如
   panel.py `_worker` 内 `load_config(account)` 字样）。**新增跨进程守卫断言（P1-1）**：main/panel 含
   `.running` 字面、创建用独占语义（`O_EXCL` 或等价）、删除在 `finally`、`trigger_run` 入口调用守卫。
   **新增 real_chrome_profile 断言（P1-2）**：config.yaml 该键注释含「多账号」互斥警告字样（4.7 同步后）。
6. 定时任务升级后 verify 第 3 节同步改造：遍历 `list_accounts()` 逐号探测任务（断言 runner 入口/exe 存在/
   无 `cmd /c`），账号为空则按现状报「未注册」；不再只查固定名 `DouyinAutoFire`。
7. 单账号旧行为不被破坏的既有断言全部保留（main.py schtasks/runner 合流/面板健康/headless 风控等）。
   **注意（P2-1）：「断言保留」≠「stub 不改」**——verify 第 4 节对 `panel.load_config` 等的零参
   monkeypatch stub 需随签名同步适配（收 alias/account 后给默认参数），否则 verify 自己 TypeError 变红且
   污染 RED 判定，此改动属 RED 阶段本分。
8. 别名校验统一入口在 main.py（如 `VALID_ALIAS_RE` 正则或等价校验函数，plan 定形态），panel/CLI 共用；
   校验含 Windows 保留设备名拒绝（P2-5）。

### 4.7 文档同步清单

| 文件 | 改什么 |
|---|---|
| `config.yaml` | `browser.user_data_dir` 注释：改为「账号层解析覆盖，实际目录 = userdata/accounts/<别名>/browser_data；此处为旧版单账号兜底值，多账号下无需修改」；`real_chrome_profile` 注释加警告（P1-2）：「多账号目录隔离下必须保持 false，为 true 时登录态会指向真实 Chrome 目录、绕过账号隔离（串号）」 |
| `user_data.yaml.example` | 头部说明：多账号下私有配置位于 `userdata/accounts/<别名>/user_data.yaml`（由面板添加账号/迁移自动生成），本文件保留为结构与字段参考 |
| `README.md` | 目录结构加 `accounts/` 与 `.running`；「核心特性」多账号说明；快速开始补「添加第二个账号/切换账号」步骤；配置一节加 real_chrome_profile 多账号警告（P1-2） |
| `docs/配置参考.md` | 私有数据章节改为账号布局；user_data_dir 语义；real_chrome_profile 表行加「多账号下必须 false」警告（P1-2） |
| `docs/管理面板使用指南.md` | 新增「账号」一节：账号栏/切换/添加/迁移引导/每账号三块数据；执行记录按账号 |
| `docs/命令行与定时任务.md` | `--account`/`--migrate`/`--list-accounts`；任务名 `DouyinAutoFire-<别名>` 每账号一条、错峰建议；启用/禁用/删除按账号 |
| `docs/工作原理与架构.md` | 模块职责加账号层；单次运行数据流补账号解析；目录布局图（含 .running 跨进程守卫）；执行纪律段改写「进程内锁 + 跨进程守卫」 |

---

## 五、错误处理

| 场景 | 行为 |
|---|---|
| `--account` 指向不存在的别名 | 明确报错 + 列出可用别名，exit 2（不静默 fallback） |
| 别名非法字符 / 超长 / 已存在 / Windows 保留设备名 | 面板 400 带完整规则文案；CLI 同文案 |
| legacy 未迁移就 --run-once / --setup-login / 交互 | 提示先 `--migrate <别名>` 或开面板走迁移条 |
| 迁移中途失败（权限/占用） | 已移项保留，返回未迁移清单，重跑续迁（幂等）；browser_data 被占用时提示关闭浏览器/等运行结束 |
| 旧任务 `DouyinAutoFire` 残留（多账号 >1 场景，无 --account 的 runner） | runner 报错并写入 run.log（`trigger_run` 返回 None 分支同理留痕），提示到面板重新注册对应账号任务；**单账号场景不报错**——旧任务自动沿用唯一账号属预期零打扰（P2-2） |
| 跨进程并发触发（定时任务撞车/面板与 runner 同时） | 守卫文件被占：报「账号 <X>（pid <Y>）正在运行中」，本次跳过并留痕 run.log；守卫为 O_EXCL 独占创建 + finally 删除，无并发窗口（P1-1） |
| 上次进程崩溃留下陈旧 `.running` | 下次触发探测 pid 存活：pid 不存在 → 视为残留，删除守卫后正常继续（自愈，不永久锁死）；pid 存活才拒绝（P1-1） |
| 面板运行中切号 | 允许切换查看（只读），触发按钮对运行中的账号置灰；对另一账号点击触发 → 守卫/全局锁拦截（文案带运行账号名） |
| 添加账号后未扫码就触发 | 走 DouyinStreak 现状逻辑：检测未登录 → 等待扫码窗口（机制不变） |
| 每账号任务注册失败（schtasks 拒绝访问等） | 沿用 create_task 现状错误映射与提示 |
| `prune_runs` 只清当前账号目录 | 每账号 runs/ 独立，天然不误删他号记录（函数按 account 收目录） |

---

## 六、验证方案

项目无测试套件，沿用「verify.py 自检 + ad-hoc + 真实操作人工核对」双轨（与仓库先例一致）。

1. **RED**：按 4.6 新增/改造 verify.py 断言 → 跑 `verify.py` → 确认 FAIL（失败原因是「新保证未实现」而非笔误）。
2. **GREEN（分 Task 提交）**：main.py 账号层 → runner/CLI → panel 数据层 → panel API → panel.html →
   verify 全绿（exit 0）→ 4.7 文档同步（docs 与代码分开提交，中文 conventional commits）。
3. **无法自动化的部分（如实声明）**：真实迁移、双号各扫码一次、双号错峰定时、次日两号真实发送
   ——依赖用户真实抖音账号与真实运行，verify.py 只能锁代码结构。收尾以「用户人工核对清单」交付
   （操作全部发生在 gitignored 的 userdata/ 内；真实会话名/内容不进任何 git 文件，占位符只进文档）。
   备注：别名已按评审拍板限制为 ASCII（英文/数字/下划线），无中文任务名兼容性问题，无需额外探针。

---

## 七、风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | **串号**：某写/运行路径漏传账号，隐式回落导致 A 配置发 B 的号 | 运行/写入路径 alias 强制显式（无隐式默认）；load_config(alias) 覆盖 browser.user_data_dir 指向账号目录；4.6 防串号结构断言；账号目录物理隔离，即便配置错也最多「配置读错」；**在 real_chrome_profile=false 前提（P1-2 互斥约束）下** browser_data 目录隔离让登录态不可能串 |
| R2 | 迁移半途失败/重复触发 | 幂等设计（源存在才移、目标已存在即拒、失败留清单可重跑）；触发前检查守卫 + 全局锁 |
| R3 | 旧任务/旧顶层残留造成双跑或迷惑 | 迁移引导收尾按钮（adopt-legacy 注册新删旧）；legacy_pending() 只认**顶层真实数据**（P1-3：配合 ensure_userdata 收窄不再重建顶层骨架，迁移后引导条不复发、新装机不误判）；文档写明手动清理 |
| R4 | 面板请求漏带 account 读错号 | 只读查询可缺省但解析唯一确定（last/唯一），动作路径强制显式；runs 明细/截图按 meta.account 反查（P2-4）；`_resolve_account` 单一入口 |
| R5 | 账号隔离后 verify 第 3 节固定任务名失效 | 4.6-6 随任务命名升级同步改造 verify（RED 先行） |
| R6 | 别名与任务名编码风险（中文/保留字符） | 评审拍板：别名仅 `^[A-Za-z0-9_]{1,24}$`，任务名 `DouyinAutoFire-<别名>` 纯 ASCII，风险整体消除；校验函数统一入口（main.py）并拒绝 Windows 保留设备名（P2-5），panel/CLI 共用 |
| R7 | 同设备同指纹两号被抖音关联（连坐） | 已知局限（组合一非目标项）：错峰 ≥15 分钟、低频私信、**同一时刻绝不并发由 .running 跨进程守卫机制保证（P1-1）**；如实测被风控再评估升级组合二 |
| R8 | 跨进程守卫下 A 号任务超时阻塞 B 号定时 | 与现状单号行为一致（15 分钟超时兜底已有；崩溃残留由陈旧守卫自愈——pid 探测清理，见 4.3/五）；错峰间隔 > 单次运行时长即可规避 |
| R9 | verify 断言过细绑实现形态 | 遵循仓库惯例只锁保证形态（AST 参数名/端点字面/关键 marker），不锁行号与内联文案 |

---

## 八、评审拍板记录（2026-09-04，用户 clarify 逐项确认）

| # | 拍板项 | 结论 |
|---|---|---|
| 1 | 真实数据迁移授权边界 | 接受：真实操作（迁移起别名 / 添加第二号 / 双号各扫码 / 错峰定时 / 次日核对）由用户在面板执行，agent 只交付代码，不直接触碰 userdata 真实内容 |
| 2 | 别名与任务名 | **限制别名仅英文/数字/下划线**（`^[A-Za-z0-9_]{1,24}$`），任务名 `DouyinAutoFire-<别名>` 直接用别名——中文任务名兼容性风险整体消除，无需 R6 探针 |
| 3 | 面板账号栏交互草案（4.5） | 照此实现（顶部下拉 + 运行徽标 + 添加账号 + 迁移引导条 + 记住上次账号） |
| 4 | `--run-once` 无 `--account` 且多账号 | 直接报错并列出可用别名（不默认跑第一个），exit 2 |

评审后无遗留待确认项，plan 编写条件满足。

---

## 九、实施顺序（供 plan 参考）

1. `verify.py` 先 RED：4.6 新断言（账号层/CLI/runner/panel/防串号/跨进程守卫 + 第 3 节按账号探测改造）→ 跑红确认
2. `main.py` 账号层：ACCOUNTS_ROOT/account_root/list_accounts/create_account/legacy_pending/migrate_legacy_to_account
   + load_config(alias=None 双入口)/ensure_userdata 收窄/update_*(alias)/别名校验（含保留设备名）+
   browser.user_data_dir 覆盖 + 跨进程守卫（.running 独占创建 + finally 删除 + pid 存活陈旧自愈）
3. `main.py` CLI + `runner.py`：--account/--migrate/--list-accounts、task_name(alias)、runner 解析透传
4. 面板数据层与 API（panel.py 4.4）+ 旧任务 adopt-legacy 收尾（含别名校验错误文案）；切号缓存重载（P2-3）、
   截图按 meta.account 反查（P2-4）
5. `panel.html` 账号栏/迁移引导/空态/fetch 封装（4.5）
6. `verify.py` 转 GREEN + 全绿（exit 0）
7. 4.7 文档同步（README/配置参考/管理面板使用指南/命令行与定时任务/工作原理与架构/config 注释含
   real_chrome_profile 警告/example）
8. 收尾人工核对清单交付（用户在面板执行迁移+双号配置+错峰定时+次日核对），verify 全绿 + `git status` 干净即收尾

---

## 十、2026-09-05 评审修订采纳记录（MAI-001-spec-review，CHANGES_REQUIRED → 已逐条修订）

| 评审项 | 修订内容 | 落点 |
|---|---|---|
| P1-1 跨进程并发无强制机制（含 browser_data 目录锁兜底消失） | 新增 `.running` 跨进程守卫：`trigger_run` 入口 O_EXCL 独占创建（account+pid+start_ts）、finally 删除、陈旧残留按 pid 存活探测自愈；进程内锁管面板、守卫管跨进程（runner/面板/手动三路） | 三.5、4.1 目录图、4.3、4.4、4.6-5、五、R7、R8 |
| P1-2 `real_chrome_profile: true` 绕过账号 browser_data 隔离 | 明示该键与账号隔离互斥：多账号期间必须保持 false（用户已拍板关闭），R1 保证措辞收窄；4.7 三处文档加警告；verify 断言注释含互斥字样 | 4.1（新增互斥约束段）、4.6-5、4.7、R1 |
| P1-3 `ensure_userdata()` 每次重建顶层骨架 → legacy 恒真/死循环 | ensure_userdata 语义收窄：只保证 userdata/ 目录与基础设施日志，不再自动建顶层私有骨架（改由 create_account 在账号目录内建）；legacy_pending() 只认顶层真实数据（user_data.yaml 非空键 或 browser_data/ 非空） | 4.1、R3、九-2 |
| P1-4 「load_config 一律显式 alias 无默认」与零账号/基础设施读冲突 | load_config(alias=None) 双入口：None 只合并 config.yaml 公开键（面板启动读 port 等零账号路径），账户数据读写/运行路径才强制显式 alias；4.6 断言只锁账户数据函数与运行路径 | 4.1、4.6-5 |
| P2-1 verify 第 4 节 stub 随签名自爆 | 4.6-7 注明「断言保留 ≠ stub 不改」：verify monkeypatch stub 随签名同步适配属 RED 本分 | 4.6-7 |
| P2-2 错误处理与 4.3 单账号自动沿用打架 | 五、该行限定为多账号（>1）场景；单账号旧任务自动沿用唯一账号不报错 | 五、4.3 runner 行 |
| P2-3 切号后内存 _conversations 未重载 → 会话勾选数据串账号 | 4.4 新增「会话缓存内存态重载」：切号后先重载新账号缓存进内存才允许勾选/保存；保存路径双保险（读文件合并） | 4.4 |
| P2-4 截图 URL 无 account 参数可能错读目录 | runs 明细/截图按 run_id 的 meta.account 反查目录，不依赖 last_account/当前账号 | 4.4 |
| P2-5 别名校验未挡 Windows 保留设备名 | 校验规则增拒 `CON NUL PRN AUX COM1-9 LPT1-9`（大小写不敏感），错误文案可读 | 4.1、五、4.6-8、R6 |
