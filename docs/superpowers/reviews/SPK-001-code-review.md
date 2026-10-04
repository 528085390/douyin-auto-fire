# SPK-001 Code Review（火花天数展示）

> 独立 Reviewer 门禁裁决：**CHANGES_REQUIRED** —— P0×1 / P1×1 / P2×2 / P3×7。P0 为**已提交评审文档内嵌真实账号别名与真实会话名**（d911a61）；P1 为**「新建定时任务」的账号被 `api()` 静默覆盖为当前账号**。4 笔代码提交（douyin / panel / panel-ui）本体经实跑与逐行核验，采集—持久化—补全—展示—回归链路符合已批准 spec/plan，**代码本体 P0/P1 无**。

- 评审对象：基线 `26ddce0` → HEAD `d911a61`。`git log --oneline 26ddce0..HEAD` 共 **5 笔**：
  - `9802278` test(verify): SPK-001 RED 火花天数采集与展示断言（期望 150/17）
  - `5e8e6b3` feat(douyin): SPK-001 扫描会话时采集火花天数与状态
  - `587c18c` feat(panel): SPK-001 火花快照持久化、按名补全与只读缓存接口
  - `d3aec90` feat(panel-ui): SPK-001 火花徽标全列表展示与新建任务目标勾选录入
  - `d911a61` docs: SPK-001 设计/计划/评审/状态与用户指南更新（**评审期间合入**；任务书点名 4 笔代码提交，但授权 `git diff 26ddce0..HEAD`，故第 5 笔一并纳入）
- 评审日期：2026-10-04
- 评审方式：独立 Reviewer 子代理（**只读门禁**，未改任何源码 / verify.py / spec / plan）。实测重跑 `.venv\Scripts\python.exe verify.py`；逐行精读 `douyin.py` / `panel.py` / `panel.html` 全量 diff；17 条 ★SPK-001 断言逐条对照实现；对基线 `26ddce0` 三份 blob 逐条求值 17 条断言以复现 RED；对真实账号别名/会话名做 `git grep` 扫描（只报位置与计数，不复述真名）；核验 `/api/jobs`、`/api/runs`、`/api/conversations`、`/api/conversations-cache` 的数据流与全部既有调用方。
- 依据：spec `docs/superpowers/specs/2026-10-04-spark-days-display-design.md`（已批准）、plan `docs/superpowers/plans/2026-10-04-spark-days-display.md`（已批准）、`docs/superpowers/reviews/SPK-001-spec-review.md`、`docs/superpowers/reviews/SPK-001-plan-review.md`、`docs/superpowers/status/SPK-001.md`、`docs/superpowers/test-results/SPK-001-IMPL.md`
- **结论：CHANGES_REQUIRED** —— 阻塞项为 P0-1（隐私红线）与 P1-1（新建任务账号串号）；两者均为小改、不触发送链路与断言语义，修复后复审即可 APPROVED。

---

## 评审发现

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| P0-1 | **P0** | `docs/superpowers/reviews/SPK-001-spec-review.md:42`、`:79`；`docs/superpowers/reviews/SPK-001-plan-review.md:65`（由 `d911a61` 提交） | **真实账号别名与真实会话名进入被提交文件**：两份前置评审文档在正文引用了真实账号别名 `<别名1>` 及多个真实会话名（含群聊名与含数字名），随 `d911a61` 进入版本库。任务书明定「代码/文档/注释里出现真实会话名即 P0」。此前 S-P1-1 已清理 spec 本体，但这两份「引用了原始证据」的评审文档仍内嵌真名 | 用占位（`<别名1>`/`<会话A>`/`<群聊A>`）改写相关行，或对敏感段落脱敏后重新提交；建议同时在评审清单/钩子里加一条「`docs/` 禁止真名」的检查 |
| P1-1 | **P1** | `panel.html:456` + `:461`；`panel.html:790`、`:795`；后端 `panel.py:1441` | **「新建定时任务」的账号选择被静默覆盖**：`api()` 取 `const acct = opts.account \|\| activeAccount;`（456）并在 POST 时执行 `payload.account = acct;`（461）。保存处 `api("/api/jobs", {method:"POST", body:{account, time, targets, texts}})`（795）**未传** `opts.account`，于是 `acct = activeAccount` **覆盖**掉 body 中来自 `#newJobAccount` 的 `account`；后端恰以 `body.get("account")` 为准（`panel.py:1441`）。多账号下「账号」下拉选 B、当前账号为 A 时，任务被创建到 **A 账号**，而目标取自 B 的会话缓存（`loadNewJobConversations` 走 `opts.account`，`panel.html:1037`，能正确取到 B）。若两号存在同名会话，定时任务会把发给 B 的文案发到 A —— 与 spec `:262`「使选择器能取**非当前账号**的会话缓存」的意图直接冲突 | 保存处显式传账号：`api("/api/jobs", {method:"POST", account, body:{account, time, targets, texts}})`；或把 `api()` 改成仅当 body 未带 account 时才覆盖（`if (acct && !payload.account) payload.account = acct;`）。修复后补一条断言锁定「picker 账号 ≠ activeAccount 时以 picker 为准」 |
| P2-1 | P2 | `verify.py` 第 9 节（17 条 ★SPK-001） | **断言为纯 token/字符串级，拦不住语义回归**：#4/#5 仅查字面量出现、#7/#10 仅查函数名存在、#16 仅查 `"opts.account" in html_txt`、#17 仅数 `sparkBadge(` ≥6 次。**P1-1 正是在 17 条全绿下通过的**（#16 锁的是写法，而非「保存时账号正确」）。列序、徽标绑定到哪个变量、`_item_spark` 是否真的无 pending 兜底，均不在射程内 | 至少补 2–3 条结构/行为级断言（保存处显式传 `opts.account`；`renderConvList` 中「名称→火花→类型」相邻顺序）。若维持静态 token 自检惯例，需在 plan/status 明确「不覆盖语义」 |
| P2-2 | P2 | `panel.html:1034-1042` `loadNewJobConversations`；`panel.html:395` | **选择器不展示缓存新鲜度**：`/api/conversations-cache` 已返回 `cache_mtime`（`panel.py:1146`），但 `loadNewJobConversations` 只取 `d.list`（1040），选择器不显示「上次同步时间」；用户无法判断勾选依据的新旧 | 在 `#newJobTargetsWrap` 顶部渲染 `cache_mtime`（或「尚未同步」），与 `#sparkAt` 口径一致 |
| P3-1 | P3 | `panel.py:440-442` `list_runs` | `smap` 同一字典对象被注入到每条 run 的 `"spark"`（别名共享）；当前无调用方改写，但未来对某条 run 的 `spark` 增删会串到全部 | 每条 run 注入 `dict(smap)` 副本 |
| P3-2 | P3 | `panel.py:1632-1641` `_jobs_with_spark` | 每次 `GET /api/jobs` 对每个任务解析一次 `conversations_cache.json`，无 memoization；多任务多号时重复 IO | 同一请求内按账号缓存一次解析结果 |
| P3-3 | P3 | `panel.py:1301-1335` `/api/save-targets` | 合并进缓存的新目标只带 `{name,type}`，导致 `conversations_cache.json` 条目键不一致（部分含 spark 键、部分无）；读取侧 `_normalize_conversations` 会补 `None`，无功能影响 | 落盘前统一补 `spark_days/spark_state=None`，保持文件同构 |
| P3-4 | P3 | `panel.html:27` `--spark-hot:#ff5e00`；`douyin.py:455` `"255, 94, 0"` | 同一橙色在两处硬编码（CSS 令牌与 Python 计算色比较），任一处调整即静默失配 | 抽为互相引用的常量/文档说明 |
| P3-5 | P3 | `douyin.py:433-461` `_item_spark` | 采集层整体吞异常（spec D3 要求，虚拟列表回收会抛 detached，方向正确），但**无日志/计数**；若抖音改版使选择器系统性失效，全表静默显示 `—`，无信号 | 可选：整轮 0 火花时打一条 warning（不阻断），或面板提示「本次未采到火花」 |
| P3-6 | P3 | `docs/superpowers/reviews/SPK-001-plan-review.md:45` | 文档算术与最终口径不一致：该行按 5+4+3+4=16 断言推算总数 166，实际/批准为 **17 断言 / 167 总数**（`status/SPK-001.md`、`CHANGELOG.md` 均为 167） | 更正为 167/17，避免后续读者误判 RED 期望 |
| P3-7 | P3 | `docs/superpowers/test-results/SIV-001-IMPL.md`、`SIV-002-IMPL.md` | 既有文件含真实会话名（出现在 `sent_<名>.png` 证据文件名中）；**非本次提交引入**（不在 `26ddce0..HEAD`），仅登记 | 后续统一脱敏，避免累积 |

评审发现合计：**P0 = 1；P1 = 1；P2 = 2；P3 = 7**。

---

## 已核实（正面证据）

### ① 断言零迁就（17 条逐条对照真实实现）

对 17 条 ★SPK-001 断言逐条核对：**每一条都对应真实落地行为，无「把常量写成字符串只为命中 token」、无空壳函数**。

| # | 断言 | 落地位置 | 真实行为 |
|---|---|---|---|
| 1 | `".commonStreaknormalText" in d` | `douyin.py:415` `SPARK_TEXT_SEL` | 真常量，被 `:442` `query_selector` 使用 |
| 2 | `".commonStreakicon" in d` | `douyin.py:416` `SPARK_ICON_SEL` | 真常量，被 `:447` 使用 |
| 3 | `'"gray" in src' in d` | `douyin.py:449-450` | 真分支：gray→pending |
| 4 | `'"spark_days"' in d` | `douyin.py:913` `"spark_days": sparks.get(n,(None,None))[0]` | 真字段写入扫描结果 |
| 5 | `'"spark_state"' in d` | `douyin.py:914` `[1]` | 真字段写入扫描结果 |
| 6 | `x.get("spark_days")` 且 `x.get("spark_state")` in p | `panel.py:160-161` | 真读入 dict 分支 |
| 7 | `"def _spark_map(" in p` | `panel.py:1618` | 真函数，构造 name→spark 映射 |
| 8 | `'"cache_mtime"' in p` | `panel.py:1017`、`:1146` | 两处响应字段，取自文件 mtime |
| 9 | `'"/api/conversations-cache"' in p` | `panel.py:1133` | 真只读路由 |
| 10 | `"function sparkBadge(" in html_txt` | `panel.html:927` | 真函数 |
| 11 | `"--spark-hot"` 且 `"--spark-due"` in html_txt | `panel.html:27-28` | 真 CSS 令牌（`:183-184` 使用） |
| 12 | `'<span class="muted">—</span>' in html_txt` | `panel.html:928` | sparkBadge 空态回落 |
| 13 | `'id="sparkAt"' in html_txt` | `panel.html:344` | 真节点，`loadConversations` 写入 mtime |
| 14 | `'id="newJobTargets"' not in html` 且 `'id="newJobTargetsWrap"' in html` | `panel.html:395` | 旧 textarea 已删、新 wrap div 存在 |
| 15 | `'newJobTargets.length' in html` 且 `'"#newJobTargets"' not in html` | `panel.html:794`、`:1017` | 真用于保存校验/计数，无残留选择器 |
| 16 | `'"opts.account" in html_txt` | `panel.html:456` | 真写法；**但该写法对 POST 会覆盖 body.account → 见 P1-1** |
| 17 | `html_txt.count("sparkBadge(") >= 6` | 定义 `:927` + 调用 `:720/:842/:866/:975/:1012` | 恰 6 处，5 个展示位全部接入 |

### ② spec/plan 一致性（重点条款）

- **D10 火花独立映射**：`job["spark"]`（`panel.py:1635`）、`run["spark"]`（`panel.py:441-442`）、`meta["spark"]`（`panel.py:969`）均为**独立键**；`_enrich_target_types`（`panel.py:1593-1615`）与 `/api/save-targets`（`panel.py:1314`）都只产出 `{name,type}`，火花**从未写进 targets 元素**。✓
- **D11 列序 名称→火花→类型**：`renderConvList`（`panel.html:957-990`，火花 th 在 `:964`、徽标 td 在 `:975`）与 `renderNewJobTargets`（`:996-1032`）均为「勾选/会话名称/火花/类型」。✓
- **D8 只读缓存接口**：`GET /api/conversations-cache`（`panel.py:1133-1147`）直接 `_load_conversations_cache`，**不调用** `_ensure_conversations_for`，无内存副作用；账号不存在返回 `{"list":[],"cache_mtime":null}` 而非 500。✓
- **P-P2-2 无「任意颜色判 pending」兜底**：`_item_spark`（`douyin.py:440-461`）中 `gray→pending`、有 src 非 gray→done、无 src 时仅当计算色含 `255, 94, 0` 才 `done`（`:453-456`）；**没有任何分支写 pending**。✓
- **sparkBadge 空态回落 `—`**：`panel.html:928` `if (days===null||days===undefined||days===""||!state) return ' <span class="muted">—</span>';`。✓
- **零新增浏览器动作**：`scan_conversations` 仅在既有会话项 DOM 上读文字/图标，无新点击/网络/发送；`scan()` 唯一调用方为 `panel.py:757`。✓
- **发送链路零改动**：`git diff 26ddce0..HEAD -- runner.py batch_runner.py jobs.py` 为空（`jobs.py` 无改动；`panel.py` 对 jobs 只读）。✓

### ③ 回归风险

- `_normalize_conversations`（`panel.py:144-168`）**只新增字段** `spark_days/spark_state`，不改既有 `name/type` 的名称与顺序（D5）；`str` 分支照旧、`dict` 分支新增两行读取。既有调用方（`_load_conversations_cache`、`_sync_worker`、`_ensure_conversations_for`、`/api/save-targets`）都只消费 `name/type`，多字段无感。
- `list_runs`（`panel.py:427-443`）新增 `run["spark"]`：调用方 `panel.py:1126`（`GET /api/runs`）、`scheduler_daemon.py:336`、`batch_runner.py:175/:199`（防双发）均只读 `id/targets/end` 等，无影响；**磁盘 run JSON 从不回写**，旧 JSON 无 `spark` 字段时前端 `r.spark||{}`（`panel.html:836`）安全降级。
- `api_run_detail`（`panel.py:952-977`）`meta["spark"]` 是在**新载入的 meta 副本**上加键，不回写；旧 meta 无 `spark` 时前端 `(m.spark||{})`（`panel.html:866`）安全。
- `_scheduler_summary`（`panel.py:1664`）把 `jobs` 换成 `_jobs_with_spark()`：`jobs.load_jobs()`（`jobs.py:64-66`）每次 `json.loads` 出**全新文档**，`j["spark"]=...` 只改这份一次性副本，**绝不落盘**（D1）；旧 jobs.json 无 `spark` 字段同样安全。
- **旧缓存 `list[str]` 兼容**：`_normalize_conversations` 的 `str` 分支把每项变成 `{name,type,spark_days:None,spark_state:None}`，全显示 `—`，不抛异常（spec 错误表落点）。✓
- **targets 永不污染**：`/api/jobs` POST（`panel.py:1449`）经 `_enrich_target_types` 只保留 `{name,type}`；`/api/save-targets`（`panel.py:1314`）只 `clean.append({"name":...,"type":...})` → `update_targets` 写 `user_data.yaml` 的目标结构不变（D1）。✓
- **`api()` 账号注入对既有端点的实际影响**：`acct = opts.account || activeAccount` 使所有 GET 带 `?account=`、所有 POST 带 `body.account`。逐一核对：`/api/state`(1105)、`/api/runs`(1117)、`/api/conversations`(1127) 用 `_resolve_account`，显式账号 == 原 fallback 结果（activeAccount 即当前账号），行为等价；`/api/batch-state`(1148) 完全忽略参数；`/api/trigger`(1340)/`/api/save-message`(1353) 用 `_resolve_account(merged, action=True)`，等价；`/api/accounts`(1194)/`/api/migrate`(1206)/`/api/tasks/adopt-legacy`(1227) 只读 `alias`，忽略多余 `account`；`/api/trigger-all`(1387)/`/api/scheduler/*` 忽略。**唯一被覆盖语义破坏的是 `/api/jobs` POST（body.account 与 activeAccount 故意不同）→ P1-1**。
- **`renderConvList` 兼容旧字符串项**：`panel.html:974` `const sp = (typeof c === "object" && c) ? c : {};`，`null` 与字符串都安全。

### ④ 健壮性

- **采集层吞异常恰当**：`_item_spark` 整段包 `try/except`（`douyin.py:441-458`），虚拟列表回收导致的 `detached` 只让**当前项**返回 `(None,None)`，不中断整轮扫描（spec D3）；代价是无日志（P3-5）。
- **面板侧 `_spark_map` 安全**：`panel.py:1618-1629` 整段 `try/except → {}`；账号不存在时 `account_root("")` 指向 `ACCOUNTS_ROOT`，无 `conversations_cache.json` → 空 dict；坏缓存由 `_load_conversations_cache` 兜底返回 `[]`。✓
- **`_clean_spark_days/_clean_spark_state`**（`panel.py:129-141`）：非法天数/状态一律 `None`，读侧卫生（D4）。✓

### ⑤ 测试证据

- 实跑（`$env:PYTHONIOENCODING='utf-8'`；`.venv\Scripts\python.exe verify.py`，cwd `D:\ai_project\douyin-auto-fire`）：末行 `通过 167 / 失败 0`，**EXITCODE=0**；17 条 ★SPK-001 全部 `[ok]`。
- RED 可复现：对基线 `26ddce0` 的 `douyin.py` / `panel.py` / `panel.html` 三份 blob 逐条求值 17 条断言，**全部为 False**；`9802278` 的 `verify.py` diff 恰好新增 17 条 `check(`，且全部属第 9 节 ★SPK-001。故任务书记录的 RED「通过 150 / 失败 17 / 总数 167，exit 1」可复现，**无需重跑**。

### ⑥ 隐私扫描

命令（模式串以占位表示；实际 9 个模式取自 `userdata/accounts/` 下的真实目录名与未跟踪 `runs/*.png` 文件名，本报告不复述真名）：

```powershell
git grep -n -I -F -e "<别名1>" -e "<会话A>" -e "<会话B>" -e "<群聊A>" -e "<会话C>" -e "<会话D>" -e "<会话E>" -e "<会话F>" -e "<数字名>" HEAD -- docs/ CHANGELOG.md
```

结果（只报位置与计数，不输出命中文本）：

- **在本次区间（`d911a61`）内命中 3 行 / 2 文件**：`SPK-001-spec-review.md:42`、`SPK-001-spec-review.md:79`、`SPK-001-plan-review.md:65` → **P0-1**。
- 区间外命中 4 行 / 2 文件：`test-results/SIV-001-IMPL.md`、`SIV-002-IMPL.md`（非本次提交）→ P3-7。
- `spec` 本体、`plan` 本体、`status/SPK-001.md`、`test-results/SPK-001-IMPL.md`、`CHANGELOG.md` **零命中**；4 笔代码提交（`douyin.py`/`panel.py`/`panel.html`/`verify.py`）**零命中**（早前对 4 个 sha 的逐行扫描仅见 `elif src`/`list`/`pick` 等子串误报与被删占位 `目标A/目标B`）。
- 未读任何 `userdata/accounts/*/user_data.yaml` 内容；本报告与所有示例均用占位。

### ⑦ 未发现的其他风险

- 无新增未跟踪文件被本次提交引入（`.dsh/`、`examples/example-D-account-workspace.html`、`probe_spark.py` 为任务前既存未跟踪项）。
- `/api/conversations-cache` 与既有 `/api/conversations` 路由判定为精确 `==`（`panel.py:1127/1133`），无前缀误吞。

---

## 处置

- **P0-1（阻塞）**：改写 `SPK-001-spec-review.md:42/:79` 与 `SPK-001-plan-review.md:65` 为占位后重新提交；这是唯一需要「改已提交内容」的项。
- **P1-1（阻塞）**：`panel.html:795` 显式传 `opts.account`（或在 `api()` 内改为仅当 body 未带 account 时覆盖），并补一条断言锁定 picker 账号优先。
- P2（P2-1/P2-2）：可选，建议随 P1 同批或由 Lead 记录后关闭。
- P3（P3-1…P3-7）：记录备查，不阻塞。
- **结论：CHANGES_REQUIRED** —— 4 笔代码提交的火花链路（采集无新动作、独立映射、列序、只读缓存、无 pending 兜底、`—` 回落、旧缓存/旧 run/旧 jobs 兼容、targets 不污染）经实跑 167/0 与逐行核验全部符合已批准 spec/plan；阻塞项为**已提交文档的隐私泄露**与**新建任务账号串号**，二者均为小改、不触发送安全与核心状态机。

— Reviewer（独立门禁 Code Review）

---

## 处置记录（Lead，2026-10-04 修复后回填）

| 编号 | 级别 | 处置 | 证据 |
|---|---|---|---|
| P0-1 | P0 | **已修**：`SPK-001-spec-review.md:42/:79`、`SPK-001-plan-review.md:65` 中的真实账号别名与真实会话名全部占位化（改为「<账号别名>」「若干真实群名/会话名」+ 说明扫描模式来源） | 修复后 `git grep -E '<别名>|<会话名>' -- docs/ CHANGELOG.md README.md` → worktree **0 命中** |
| P1-1 | P1 | **已修**：`panel.html:456-460` 账号优先级由 `opts.account \|\| activeAccount` 改为 `opts.account \|\| payload.account \|\| activeAccount`；`opts.account` 显式传入时仍优先，body 已带 `account` 时不再被 `activeAccount` 覆盖 | `panel.html:460`；断言 18 |
| P1-1 门禁 | — | **已补**：`verify.py` 节 9 新增「★SPK-001 接口封装账号优先级(不覆盖显式账号)」；RED **167/1** → GREEN **168/0**、exit 0 | `verify.py` 节 9；`test-results/SPK-001-IMPL.md` §七 |
| P2-1 | P2 | **不采纳（记为已知局限）**：`verify.py` 是静态 token 断言，无法执行 JS；引入 JS 测试框架超出本特性范围。已登记到 `status/SPK-001.md` 遗留 6 | spec 修订记录第三轮；status 遗留 6 |
| P2-2 | P2 | **不采纳**：picker 不重复显示 `cache_mtime`——「上次同步时间」已在「一键同步」会话卡 `#sparkAt` 展示，同一信息不在两处重复 | spec 修订记录第三轮 |
| P3-1…P3-7 | P3 | **记录备查（技术债，不阻塞）**：`list_runs` 各 run 共享同一 `smap` 对象引用；`_jobs_with_spark` 每 job 重解析一次缓存；save-targets 落盘键不一致；橙色值两处硬编码；采集吞异常无日志；plan-review 算术 166 已更正为 167 | `status/SPK-001.md` 遗留 7 |

**处置后结论：P0/P1 清零，评审项全部关闭（P2-1/P2-2 与 P3 为登记在案的技术债）。**
最终 `verify.py`：**通过 168 / 失败 0**，exit 0。
