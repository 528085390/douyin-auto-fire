# SPK-001 spec 评审（自审）

- 评审对象：`docs/superpowers/specs/2026-10-04-spark-days-display-design.md`（SPK-001 火花天数展示设计，361 行，头部状态：待评审）
- 评审日期：2026-10-04
- 评审方式：自审（逐项对码取证：grep / read / `verify.py` 实跑；全程未读 `userdata/`，未启动浏览器、未发送任何消息）
- 代码基线：工作树实测 `.venv\Scripts\python.exe verify.py` → exit 0、`[ok]` 150、FAIL 0（2026-10-04 复核，与 E13 一致）
- 结论：**CHANGES_REQUIRED**（P1×1 隐私红线必修；P2×3、P3×6 建议随修订一并处理；无 P0）

## 一、核验清单逐项结果（取证实录）

### ① 证据表 E1–E13 行号锚逐条复核（全部成立）

| 锚 | 实测 | 一致 |
|---|---|---|
| E7 `douyin.py:849-878`（`found.setdefault` :863、return :878） | `def scan_conversations(self) -> list[dict]:` 在 :849；`found: dict[str, str] = {}` :856；`found.setdefault(name, self._item_kind(item))` :863；`return [{"name": n, "type": t} for n, t in found.items()]` :878 | ✅ |
| E8 `panel.py:129-148` / `:147` | `def _normalize_conversations(raw: list) -> list[dict]:` :129；`out.append({"name": name, "type": ctype})` :147 | ✅ |
| E9 `panel.py:151-161` / `:164-174` / `:177-186` | `_load_conversations_cache` :151（内含 `_normalize_conversations(data)` :158）；`_save_conversations_cache` :164；`_ensure_conversations_for` :177 | ✅ |
| E10 `panel.py:1546-1568` | `def _enrich_target_types(account: str, targets: list) -> list:` :1546；`conv_map = {str(c.get("name")): (c.get("type") or "private") ...}` :1553 | ✅ |
| E11 `panel.html:697/705/708`、`:810-820/813-815`、`:838`、`:920-951/927` | 定时任务表头 :697；`const tgt = (job.targets \|\| []).map(t => esc(t.name \|\| t)).join("、")` :705；`tgt.slice(0, 24)` :708；执行记录表 :810-820、逐目标 :813-815；详情目标行 :838；`renderConvList()` :920-951、三列表头 :927 | ✅ |
| E12 `panel.html:11-29 :root`、`--muted:#aab4c5` | `:root` :11-29；`--muted:#aab4c5` :20；全文件 `#ff5e00` 0 命中 | ✅ |
| E13 基线 150/0 | 复核实跑 exit 0 / `[ok]` 150 / FAIL 0 | ✅ |
| E1–E6 | 探针产物内容（`userdata/probe_spark/`，未入库）；本次未打开该目录，仅作文本自洽核对：E3 的 `rgb(255, 94, 0)` 与 4.2 兜底字符串一致；E4「无节点」与 4.2 `if not t: return None, None` 一致；E6 protobuf 结论与非目标第 3 条一致 | ✅（文本自洽） |

### ② 断言可执行性（16 条 RED 诚实性）

16 条断言 token 实测：14 条为全新 token，现码 **0 命中**；2 条为负断言 token，现码各 1 命中（`id="newJobTargets"` = `panel.html:385` 的 textarea；`"#newJobTargets"` = `panel.html:768`）→ 16 条在 RED 态全部 FAIL，成立。

作用域：`d = read("douyin.py")` 在 `verify.py:118`、`p = read("panel.py")` 在 `:296`、`html_txt = read("panel.html")` 在 `:356`，均早于六节指定的插入点（`:382` 后、`:384` 汇总前）→ 成立。

### ③ 目标/非目标与用户拍板一致性

目标 1–4 与 m00002 / m00073 / m00131 及拍板 Q2/Q3 一一对应；非目标 6 条与「不改发送链路」「不做账号级汇总」「不碰 protobuf」一致。**目标 5（会话卡数据新鲜度）在六节 16 条断言中无任何覆盖**（见 S-P2-2）。

### ④ 隐私红线扫描

见 S-P1-1：spec 正文含真实账号别名与真实会话名（含群名与逐项天数）。

## 二、评审发现表

| 编号 | 级别 | 位置 | 问题 | 建议处置 |
|---|---|---|---|---|
| SPK-001-S-P1-1 | P1 | spec:5、:30、:37、:38 | 提交文档出现真实账号别名与真实会话名：:5/:30「实跑 zhu 号」；:37 E4 列 7 个真实无火花会话名；:38 E5 列「猪胶的学习群 / 305业主群 / 小小小 / 2.0 / 云韵」及各自天数。仓库纪律（PAN-001 spec 评审 §五 已立：提交文档不得出现真实别名/会话名/发送内容）被破坏 | 占位化：账号称「账号 A」，会话称「会话甲 / 乙…（群聊）=N 橙」；证据仍指向 `userdata/probe_spark/items.json`（未入库），保留「15 项中 7 项无节点」「群聊同样有火花」等结论与数量关系 |
| SPK-001-S-P2-1 | P2 | 4.4 第 1 条（:189） | jobs 补全形态与 plan 互斥：spec 要求「为 `job["targets"]` 每项补 `spark_days`/`spark_state`」（写进 targets 数组元素）；plan 落地为独立 `job["spark"]` 映射（`_jobs_with_spark()`），前端按 `job.spark[n]` 取值。若按 spec 实现，plan 的前端取值全落空 → 定时任务列全 `—` | 定稿为 plan 形态（不动 `targets` 形状、与 `list_runs` 同口径），同步改 spec 4.1 数据流图与 4.4 第 1 条 |
| SPK-001-S-P2-2 | P2 | 目标 5（:57）、4.5（:232）、R2（:333） | 「上次同步时间」三处要求展示（4.5 明写 `<span id="sparkAt">—</span>`），但六节 16 条断言无一条覆盖 `sparkAt`，plan 也未实现该元素 → 目标与风险缓解无门禁，易静默丢失（plan §九 Q1 却自称已按「展示上次同步时间」实现） | 二选一：(a) 补断言 `'id="sparkAt"' in html_txt`（断言变 17 条，六节总数与 plan 演进表 166 需同步改），plan Task3 补元素与 `cache_mtime` 回填 JS；(b) 降级为「只给静态图例」，删 4.5 的 `#sparkAt`、改目标 5 与 R2 |
| SPK-001-S-P2-3 | P2 | 4.6（:249） | `#newJobPickHint` 元素在 4.7 / 五 / 六 / plan 均无对应（plan Task4 未实现）→ 幽灵元素 | 删除该 span，或 plan Task4 补 `#newJobPickHint` 与「已选 N 个」提示（与 plan 评审 P-P3-2 同源） |
| SPK-001-S-P3-1 | P3 | R2（:333） | 引「决策 D4 的 `cache_mtime`」错位：D4（:170）是「净化放读侧」，`cache_mtime` 由 4.3（:172）定义，与 D4 无关 | 改为「4.3 的 `cache_mtime`」 |
| SPK-001-S-P3-2 | P3 | 4.5（:201） vs R6（:337） | 4.5 新增 `--spark-due:#aab4c5`，R6 却写「灰用 `--muted` 既有令牌」——两者同值但口径矛盾（plan 采用 `--spark-due`） | 统一为新增令牌；R6 改为「`--spark-due` 复用 muted 值，已满足 4.5:1」 |
| SPK-001-S-P3-3 | P3 | 4.5（:217） | `${days}天` 直接插值，非数字会原样渲染（后端已净化，属防御性）；plan 用 `Number(days)` 收紧 | spec 对齐为 `Number(days)` |
| SPK-001-S-P3-4 | P3 | 4.5（:225） | 只说「行 `panel.html:934-945` 加 `<td>`」，未定列序；plan 把行 td 钉在 `:936`（名称后）而表头钉在「类型」后 → 列序错位（plan 评审 P-P1-1） | spec 显式写明列序：「火花列在类型列之后；行 `<td>` 加在类型单元格之后（`panel.html:944` 后）」 |
| SPK-001-S-P3-5 | P3 | 4.4（:189） | `_scheduler_summary()` 锚写 `panel.py:1590-1607`，函数 def 实际在 `panel.py:1571`（1590-1607 是其 return dict） | 锚改 `panel.py:1571-1607` |
| SPK-001-S-P3-6 | P3 | Q4（:349） | Q4 建议「放宽到 32 字」，plan 采「不按字符截断 + CSS 省略号 + `title` 全文」→ spec 待定项未随 plan 收敛 | 随批准把 Q4 结论改为 plan 口径 |

## 三、已核实安全（隐私红线）

1. 本次评审未读取 `userdata/` 任何文件；未启动浏览器、未发送任何消息；实跑 `verify.py` 为纯文本断言。
2. 评审输出与修订建议均使用占位（「账号 A」「会话甲」）。
3. 未修改任何文件。
4. spec 的隐私缺口为本次唯一 P1（S-P1-1）；修订前不应把头部状态改为「已批准」。

## 四、处置建议

1. **S-P1-1 必修**：占位化改写 :5 / :30 / :37 / :38，独立 `docs:` 提交，修订后复审。
2. S-P2-1 / S-P2-2 / S-P2-3 与 plan 评审的 P-P2-4 / P-P2-3 / P-P3-2 同源，建议与 plan 一次性定稿，避免 spec↔plan 双口径。
3. P3 各项随修订顺手改（行号锚、令牌口径、列序、`Number(days)`、Q4 结论）。
4. 复审 APPROVED 后再与 plan 一起交用户签字；签字前不得进入 IMPLEMENT。

---

评审证据摘要：E7–E13 锚点逐条 grep/read 命中；16 条断言 token 14 条 0 命中、2 条负断言各 1 命中；`verify.py` 实跑 exit 0 / 150 / 0；隐私扫描命中 4 行（见 S-P1-1）。

---

## 五、第二轮复审（2026-10-04 修订后）

用户 (m00429) 指示「你来修复分歧」后，spec 已按本评审逐项修订（spec 文末「修订记录」为证）。逐项复核：

| 编号 | 处置 | 复核 |
|---|---|---|
| S-P1-1 | E4/E5 与决策来源的真实别名、会话名已占位化 | ✅ 全文再扫 `zhu`/`小小小`/`猪胶`/`云韵`/`每天都想赚钱`/`ccccc`/`zzzzz` 均 0 命中 |
| S-P2-1 | 4.4 第 1 条改独立 `job["spark"]` 映射（决策 D10）并补理由 | ✅ 与 plan §四.6 `_jobs_with_spark()` 一致 |
| S-P2-2 | Q1 拍板「要展示」；断言 17 落地 `#sparkAt`；16→17、166→167 | ✅ 断言表 / RED-GREEN / §九 三处数字同步 |
| S-P2-3 | 删除 `#newJobPickHint`；label/toast 对齐 plan | ✅ 全文 `newJobPickHint` 0 命中 |
| S-P3-1 | R2 改指 4.3 的 `cache_mtime` | ✅ |
| S-P3-2 | R6 改 `--spark-due` 新增令牌口径 | ✅ |
| S-P3-3 | 4.5 改 `${Number(days)}天` | ✅ |
| S-P3-4 | 4.5 明确列序（决策 D11） | ✅ 与 plan Task 3 §五.4① 同序 |
| S-P3-5 | `_scheduler_summary()` 锚改 `panel.py:1571-1607` | ✅ |
| S-P3-6 | Q4 拍板采 plan 口径（CSS 省略号 + `title` 全文） | ✅ |

**第二轮结论：APPROVED**（P1 已清零，P2/P3 全部处置；spec 头部状态已改为「已批准（2026-10-04）」）。

