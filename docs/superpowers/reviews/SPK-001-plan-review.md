# SPK-001 plan 评审（自审）

- 评审对象：`docs/superpowers/plans/2026-10-04-spark-days-display.md`（SPK-001 火花天数展示实施计划，499 行，头部状态：待用户签字）
- 评审日期：2026-10-04
- 评审方式：自审（逐项对码取证：grep / read / `verify.py` 实跑；全程未读 `userdata/`，未启动浏览器、未发送任何消息）
- 依赖 spec：`docs/superpowers/specs/2026-10-04-spark-days-display-design.md`（同轮评审结论 CHANGES_REQUIRED，见 `docs/superpowers/reviews/SPK-001-spec-review.md`）
- 代码基线：工作树实测 `.venv\Scripts\python.exe verify.py` → exit 0、`[ok]` 150、FAIL 0（2026-10-04 复核）
- 结论：**CHANGES_REQUIRED**（P1×1、P2×4、P3×3；无 P0）

## 一、核验清单逐项结果（取证实录）

### ① RED 诚实性（逐 token 实测现码命中数）

| # | 断言 token | 现码命中 | 归属 |
|---|---|---|---|
| 1 | `.commonStreaknormalText` | 0 | T1 |
| 2 | `.commonStreakicon` | 0 | T1 |
| 3 | `"gray" in src` | 0 | T1 |
| 4 | `"spark_days"` | 0 | T1 |
| 5 | `"spark_state"` | 0 | T1 |
| 6 | `x.get("spark_days")` / `x.get("spark_state")` | 0 / 0 | T2 |
| 7 | `def _spark_map(` | 0 | T2 |
| 8 | `"cache_mtime"` | 0 | T2 |
| 9 | `"/api/conversations-cache"` | 0 | T2 |
| 10 | `function sparkBadge(` | 0 | T3 |
| 11 | `--spark-hot` / `--spark-due` | 0 / 0 | T3 |
| 12 | `<span class="muted">—</span>` | 0 | T3 |
| 13 | `id="newJobTargets"` 退场 / `id="newJobTargetsWrap"` 在场 | 1（`panel.html:385`）/ 0 | T4 |
| 14 | `newJobTargets.length` / `"#newJobTargets"` 退场 | 0 / 1（`panel.html:768`） | T4 |
| 15 | `opts.account` | 0 | T4 |
| 16 | `sparkBadge(` 计数 ≥6 | 0 | T4 |

14 条新 token 全 0 命中，2 条负断言 token 各 1 命中 → 16 条在 RED 态全部 FAIL，**RED 诚实性成立**。

### ② 断言字节 ↔ GREEN 块双向对齐

- T1 五条：`SPARK_TEXT_SEL = ".commonStreaknormalText"`、`SPARK_ICON_SEL = ".commonStreakicon"`、`if "gray" in src:`、`"spark_days"`、`"spark_state"` 均在 §三 GREEN 代码块内逐字在场 ✓
- T2 四条：`x.get("spark_days")`/`x.get("spark_state")`（§四.2 归一放行）、`def _spark_map(`（§四.3）、`"cache_mtime"`（§四.7 `api_conversations` + §四.8 新端点）、`"/api/conversations-cache"`（§四.8 路由）✓
- T3 三条：`function sparkBadge(`（§五.3）、`--spark-hot`+`--spark-due`（§五.1 `:root`）、`<span class="muted">—</span>`（§五.3 无值分支）✓
- T4 四条：`id="newJobTargetsWrap"`（§六.1 替换 textarea）且 `id="newJobTargets"` 退场、`newJobTargets.length`（§六.4 校验）、`"#newJobTargets"` 退场（§六.4 改读写 `newJobTargets` 数组）、`opts.account`（§六.5 `api()` 改造）、`sparkBadge(` 共 6 处（§五.3 定义 1 + §五.4 四处接入 + §六.2 `renderNewJobTargets()` 一处）✓
- **子串安全**：`id="newJobTargetsWrap"` 的后续字符为 `W`，不含 `id="newJobTargets"`；`"#newJobTargetsWrap"` 不含 `"#newJobTargets"` → 断言 13/14 不自相矛盾 ✓

### ③ 演进表算术与 RED/GREEN 纪律

150（基线）+5（T1）+4（T2）+4（T3）+4（T4）= **167** ✓（第二轮把 `#sparkAt` 断言补进 T3，T3 由 3 条变 4 条；原文误记 166，此处更正）。各阶段 PASS/FAIL 自洽：T1 RED 150/5（总 155）→ GREEN 155/0 → T2 RED 155/4（总 159）→ GREEN 159/0 → T3 RED 159/4（总 163）→ GREEN 163/0 → T4 RED 163/4（总 167）→ GREEN 167/0 → T5 文档 167/0。

17 条全为**新增**断言，无替换类断言，与「无替换类例外」声明一致；「火花徽标五处接入」（`>=6`）在 T3 GREEN 后实际为 5，故 T4 RED 必 FAIL；即使执行顺序颠倒，计数只会更低，不会假绿 ✓。

### ④ 作用域与插入点

`verify.py` 节 9 插入点（`:382` 之后、`:384` 汇总之前）晚于 `d = read("douyin.py")`（`:118`）、`p = read("panel.py")`（`:296`）、`html_txt = read("panel.html")`（`:356`）的定义 ✓；节 8 的 `for f in BASE.glob("*.vbs")` 循环在 :382 前结束，插入不会破坏既有块 ✓。

### ⑤ 实现锚点逐条实测（全部命中）

- `douyin.py`：412 `ITEM_SEL`、413 `LIST_SEL`、414 `ZWSP`、416 `_list_conversation_items`、420 `_item_title`、425-429 `_item_kind`（429 `return "private"`）、431 `_find_rendered_item`、849 `def scan_conversations(self) -> list[dict]:`、856 `found: dict[str, str] = {}`、863 `found.setdefault(name, self._item_kind(item))`、877 `self._progress(...)`、878 `return [{"name": n, "type": t} for n, t in found.items()]` → 常量插 `:414` 后、`_item_spark` 插 `:429` 后（`:431` 前）成立
- `panel.py`：129 `_normalize_conversations`（147 `out.append({"name": name, "type": ctype})`）、151/164/177 `_load`/`_save`/`_ensure_conversations_for`、373 `def _find_run_account(run_id: str) -> str | None:`、407-420 `list_runs(account, keep=3)`（唯一调用点 :1094）、929-953 `api_run_detail`（931 `acc = _find_run_account(run_id)`）、974-986 `api_conversations`、1056 `do_GET`（1060 `params`）、1064/1073/1085/1095/1101/1103/1106 各路由、1392-1412 `POST /api/jobs`（1402 `_enrich_target_types`）、1546-1568 `_enrich_target_types`、1571-1607 `_scheduler_summary`（1591 `"jobs": jobs.load_jobs(),`）→ `_spark_map` 插 `:1568` 后、新端点插 `:1100` 后成立
- `panel.html`：11-29 `:root`、442 `const qs = (obj) => ...`、443-457 `api()`（448 `if (activeAccount)`、449 GET 走 `qs({account: activeAccount})`）、466 `function toast`、676 `function esc`、697 定时任务表头、705 `const tgt = ...`、708 `tgt.slice(0, 24)`、764-779 保存（768/770）、810-820 执行记录表（812/813-815）、829-853 `showDetail`（838）、898 `escapeHtml`、903-918 `loadConversations`、920-951 `renderConvList`（927 三列表头、928 `convCache.forEach((c, i) => {`、929 `const name = typeof c === "string" ? c : c.name;`、934-945 行、948 计数）、953-967 `pollConv`

### ⑥ 依赖函数存在性（plan 新增代码引用者）

`qs()`（`panel.html:442`，为箭头常量而非 `function qs`）、`toast()`（:466）、`esc()`（:676）、`escapeHtml`（:898）、`api()`（:443-457）、`_resolve_account(params, *, action=False)`（`panel.py:309`）、`datetime`/`account_root` 已在 `panel.py` 导入 ✓；`list_runs(` 唯一调用点 `panel.py:1094` → 给每 run 挂 `m["spark"]` 无旁路 ✓

### ⑦ 隐私红线

plan 全文对真实别名/会话名 **0 命中**（扫描模式取自 `userdata/accounts/` 目录名与未跟踪 `runs/*.png` 文件名，此处不复述），示例一律用占位 ✓。与 spec 评审 S-P1-1 形成对比：隐私缺口只在 spec，不在 plan。

### ⑧ 任务拆分与提交纪律

T1→T4 按「采集层 → 持久/读取/接口层 → 展示层 → 录入改造」递进，依赖方向正确（T3/T4 依赖 T2 的字段与接口）；每个 Task 均「RED 断言 + GREEN 改动点 + 验收」三段，RED/GREEN 分开提交，符合仓库 TDD 纪律 ✓。

## 二、评审发现表

| 编号 | 级别 | 位置 | 问题 | 建议处置 |
|---|---|---|---|---|
| SPK-001-P-P1-1 | P1 | Task3 §五.4① | **列序错位**：表头把「火花」加在「类型」之后（第 4 列），而行 `<td>${sparkBadge(sp.spark_days, sp.spark_state)}</td>` 钉在 `panel.html:936`（名称单元格）之后（第 3 列）→ thead 与 tbody 列序不一致，火花值会渲染在「类型」列下 | 行 td 改插在 `panel.html:944`（类型单元格）之后；或表头 th 改插在名称 th 之后（二选一，须与 spec 4.5 列序定稿一致） |
| SPK-001-P-P2-1 | P2 | Task3 §五.3 | `sparkBadge` 只判 `days`，当 `state` 为 `null`/`undefined`（后端净化后可能）时仍走 `cls = "spark"`（橙）+ `tip = "今天已续"` → 与 spec 五节错误处理表第 3 行「`spark_state` 为 `None` → 前端 `—`（不猜状态）」及决策 D5 冲突，会把状态未知的项误标为已续 | 条件补 `|| !state`（照 spec 4.5:214 的写法），未知状态一律回落 `—` |
| SPK-001-P-P2-2 | P2 | Task1 §三.2（`_item_spark` 兜底分支） | 兜底 `elif color: state = "pending"`：当图标 `src` 与橙色都读不到、仅文字色非空时判为「今天还没续」（灰），与 spec 4.2 的 `state = "done" if "255, 94, 0" in color else None` 及错误表第 3 行冲突 → 会把读不准的项误标成灰 | 改为 `elif "255, 94, 0" in color: state = "done"`，否则 `None`；保持「读不到就不猜」 |
| SPK-001-P-P2-3 | P2 | Task3 §五.5 / §九 Q1 | 「展示上次同步时间」未真正落地：spec 4.5:232 要求 `<span id="sparkAt">—</span>` 由 `cache_mtime` 填充，plan §九 Q1 自称「本 plan 按展示上次同步时间实现」，但 Task3 第 5 点只加静态文案，无 `#sparkAt` 元素、无回填 JS → 后端 `cache_mtime` 成为死字段，且断言 8 只验后端字段存在、验不到前端展示 | Task3 第 5 点补 `#sparkAt` 元素 + `loadConversations()` 成功回填 `cache_mtime` 的 JS；或明说 Q1 采用「不展示」并同步改 spec 4.5 / 目标 5 / R2 |
| SPK-001-P-P2-4 | P2 | Task2 §四.3 / §四.6 | jobs 载荷形态与 spec 4.4 第 1 条互斥（同 spec 评审 S-P2-1）：plan 用独立 `job["spark"]` 映射（`_jobs_with_spark()`），spec 要求写进 `job["targets"]` 每项。两文档必须一处定稿，否则实现者按 spec 落地会让前端 `job.spark[n]` 全落空 | 建议采 plan 形态（不动 `targets` 形状、与 `list_runs`/`api_run_detail` 同口径），只改 spec 4.1/4.4；plan 不动 |
| SPK-001-P-P3-1 | P3 | Task3 §五.1 | `--spark-due:#aab4c5` 与既有 `panel.html:20 --muted:#aab4c5` 同值重复；spec R6 又写「灰用 `--muted` 既有令牌」→ 三处口径不一 | 二选一并同步 spec R6（建议保留 `--spark-due`，语义更清晰） |
| SPK-001-P-P3-2 | P3 | Task4 §六.1 / §六.4 | 与 spec 4.6 三处不一致：spec 有 `#newJobPickHint` 而 plan 无、label 文案不同、toast 文案不同（plan「请填完整：账号/时间/目标/文案」vs spec「请至少勾选一个目标」） | 以 plan 为准改 spec 4.6（与 spec 评审 S-P2-3 同源），避免幽灵元素 |
| SPK-001-P-P3-3 | P3 | Task1 §三.2 | plan 的 `_item_spark` 用 `if days is None and state is None: return None, None`，且无 `if not t: return None, None` 短路；当无文本节点但有图标时会返回 `(None, state)`，与 spec 4.2 的返回语义略异（前端 `days` 为空即 `—`，无用户可见差异） | 记录备查；若要严格对齐，可把首个分支改为 `if not t: return None, None` |

## 三、已核实安全（隐私红线）

1. 本次评审未读取 `userdata/` 任何文件；未启动浏览器、未发送任何消息；实跑 `verify.py` 为纯文本断言（只读）。
2. plan 全文真实别名/会话名 0 命中，示例均为占位 ✓。
3. 未修改任何文件。
4. 评审输出均使用占位（「账号 A」「会话甲」）。

## 四、处置建议

1. **P-P1-1 必修**：列序错误会直接导致火花值渲染错列，属用户可见缺陷；修 plan Task3 §五.4①，并与 spec 4.5 的列序描述一并定稿。
2. P-P2-1 / P-P2-2 均为「状态读不准时猜状态」，与 D5「读不到就不猜」冲突，建议一并修（改动各一行）。
3. P-P2-3 与 P-P2-4 需在 spec/plan 间定稿：建议采 plan 的 `job["spark"]` 形态；「上次同步时间」则需用户确认（spec Q1）——若采「展示」，补 `#sparkAt` + 断言 17（总数 166→167，演进表与六节同步改）。
4. P3 各项随修订顺手改。
5. 修订完成并复审 APPROVED 后，plan 才可交用户签字；签字前不得进入 IMPLEMENT。

---

评审证据摘要：16 条断言 token 现码 14 条 0 命中 / 2 条负断言各 1 命中；演进表 150+5+4+3+4=166 复核算术成立；`douyin.py`/`panel.py`/`panel.html` 全部实现锚点 grep 命中；`verify.py` 实跑 exit 0 / 150 / 0；plan 隐私扫描 0 命中；作用域、子串安全、依赖函数与插入点逐项通过。

---

## 五、第二轮复审（2026-10-04 修订后）

用户 (m00429) 指示「你来修复分歧」后，plan 已按本评审逐项修订（plan 文末「十、修订记录」为证）。逐项复核：

| 编号 | 处置 | 复核 |
|---|---|---|
| P-P1-1 | Task 3 §五.4① 明确列序（名称 → 火花 → 类型）：表头 th 插在名称/类型之间、行 td 插在 `panel.html:936` 之后 | ✅ 与 spec 决策 D11 一致，thead/tbody 同序 |
| P-P2-1 | `sparkBadge` 补 `|| !state` | ✅ 与 spec 4.5 写法一致 |
| P-P2-2 | `_item_spark` 删 `elif color: state = "pending"` | ✅ 与 spec 4.2 一致 |
| P-P2-3 | Task 3 §五.5 落地 `#sparkAt` + `loadConversations()` 回填；新增第 17 条断言 | ✅ 断言 16→17；演进表 150+5+4+4+4=167；§八 167/0 同步 |
| P-P2-4 | 定稿采 plan 的 `job["spark"]` 映射（spec 已同步改，D10） | ✅ |
| P-P3-1 | 保留 `--spark-due`（spec R6 已同步） | ✅ |
| P-P3-2 | 以 plan 4.6 为准（spec 已删幽灵元素、对齐文案） | ✅ |
| P-P3-3 | `_item_spark` 首分支改 `if not t: return None, None` | ✅ 与 spec 4.2 语义一致 |

**第二轮结论：APPROVED**（P1 已清零；断言与演进表算术复核 150+5+4+4+4=167；plan 头部状态已改为「已批准（2026-10-04）」）。

---

## 六、第三轮复核（2026-10-04 代码评审修复后）

独立代码评审（`docs/superpowers/reviews/SPK-001-code-review.md`）在**实现后**发现两项阻塞：P0-1（已提交文档隐私泄露）、P1-1（`panel.html` 的 `api()` 账号被 `activeAccount` 覆盖 → 新建任务跨账号串号）。本 plan 随之更新：

| 项 | 处置 | 复核 |
|---|---|---|
| 断言 17 → 18 | 新增「★SPK-001 接口封装账号优先级(不覆盖显式账号)」：`"opts.account \|\| payload.account \|\| activeAccount" in html_txt` | ✅ RED 167/1 → GREEN 168/0、exit 0 |
| §七 演进表 | 新增「评审 / RED 1 条 / GREEN 后」两行 | ✅ 算术 150+5+4+4+4+1 = 168 |
| §八.1 | 167/0 → **168/0** | ✅ |
| 头部/§二.2 | 167 → **168** | ✅ |
| §十 新增第三轮修订记录 | 记 P0-1/P1-1 修复、断言 18、未采纳项 | ✅ |

**第三轮结论：APPROVED（附条件）**——P0-1 与 P1-1 均已修复并留证；剩余 P2-1/P2-2 与 P3-1…P3-7 为**已知局限/技术债**，已在 spec 修订记录与 `status/SPK-001.md` 遗留项中登记，不阻塞发布。

