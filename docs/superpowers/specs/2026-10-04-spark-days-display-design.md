# SPK-001 火花天数展示：逐好友采集与全列表呈现设计

- 日期：2026-10-04
- 状态：**已批准（2026-10-04）→ 已实施（2026-10-04）**——4 笔提交 `9802278` / `5e8e6b3` / `587c18c` / `d3aec90`，`verify.py` 167/0、exit 0，真实浏览器「一键同步」实采成功（见 `docs/superpowers/status/SPK-001.md`、`docs/superpowers/test-results/SPK-001-IMPL.md`）。
- 原批准记录（保留）：**已批准（2026-10-04）**——用户 (m00429)：「你来修复分歧，然后开子代理去做，做完之后开管理面板页面给我确认火花天数是否正常」。首轮自审（`docs/superpowers/reviews/SPK-001-spec-review.md`）的 P1/P2/P3 已全部处置，Q1–Q4 全部拍板（见文末「修订记录」）。
- 决策来源：2026-10-04 用户会话（功能诉求 + 粒度澄清 + 展示范围拍板）；前置已完成只读探针（`probe_spark.py`，2026-10-04 实跑一个测试账号（下称账号 A），见本文件证据表 E1–E6）；前置已批准设计：PAN-001 面板账号工作区、SCH-001 定时任务条目库与常驻守护。
- 评审拍板记录（用户逐项确认的需求决策，2026-10-04 会话）：
  1. 功能诉求（用户原话，m00002）：「我想新增一个功能，在面板上能够看到对应账号的火花天数，你看看有没有什么方案，先告诉我」。
  2. 粒度澄清（用户原话，m00073）：「对应账号的火花天数指的是每个好友各自的天数，你可以先去跑探针，看能不能读到火花天数」——**逐好友（逐目标）**，不是账号级汇总数字。
  3. 展示范围与视觉（用户原话，m00131）：「全部列表一并显示，要上色，你写个spec文档先」——(a) 凡列出会话/目标的列表都要显示；(b) 按状态上色；(c) 先交付本 spec，未获批准不动实现代码。
  4. 探针授权：用户已批准跑只读探针（打开浏览器、只 dump DOM/接口结构，**绝不发送任何消息**），探针已完成。
  5. 无火花占位（2026-10-04 首轮评审回答）：显示 `—`，不显示「0天」。
  6. 范围追加（2026-10-04 首轮评审回答）：**「新建定时任务」的目标录入本次一并改造**为从该账号会话列表勾选（带火花显示），弃用手打 textarea。

---

## 一、背景与问题

面板目前的会话管理只有「名字 + 类型」两个维度（panel.html:927 表头三列：勾选/会话名称/类型）。
续火花这个核心动作的效果指标——**这个好友跟我连续聊了多少天**——在面板上完全不可见：

1. **无从判断该不该发**：断了一天火花就清零，用户需要知道哪些好友「今天还没续」（灰）以便优先补。
2. **无从判断策略是否生效**：连续天数是否在涨、有没有哪条被打断，面板不显示。
3. **数据其实就在页面上**：会话列表项内已经渲染了火花徽标与天数（探针 E1/E2），只是面板扫描时把它丢了。
4. **丢弃点明确**：`douyin.py:849 scan_conversations()` 只取 name/type（`douyin.py:878 return [{"name": n, "type": t} ...]`），`panel.py:129 _normalize_conversations()` 只保留 name/type，任何新字段都会被静默丢弃。

本次不改发送链路、不新增网络请求，只做「**把已经渲染在会话项里的火花天数采下来、存下来、在所有列表上显示出来**」。

## 二、勘察结论（证据表）

探针脚本 `probe_spark.py`（仓库根，只读）实跑一个测试账号（下称**账号 A**），落盘 `userdata/probe_spark/{items.json,responses.json,page.html,list.html}`。

| # | 结论 | 证据锚 |
|---|---|---|
| E1 | 火花天数在 DOM 里，节点路径唯一且稳定 | 会话项内：`div[data-e2e="conversation-item"].conversationConversationItemwrapper` > `div.conversationConversationItemrowArea2` > `div.conversationConversationItemtitleWrapper` > `div.ConversationItemTagNextToTitlewrapper` > `div.ConversationItemTagNextToTitleleft` > `div.commonStreakstreakContainer` > [`img.commonStreakicon`, `div.commonStreaknormalText`]；探针 `items.json` |
| E2 | `div.commonStreaknormalText` 文本即天数，前后带空白 | 实测取到 `" 195 "`、`" 22 "`，需 `strip()`；探针 `items.json` |
| E3 | 状态二态可由图标文件名判定：`gray_normal`=今天未续、`normal_normal`=今天已续 | 橙：`.../flame_icon/normal/normal_normal.png` + 文字色 `rgb(255, 94, 0)`；灰：`.../flame_icon/normal/gray_normal.png` + 文字色 `var(--color-TextTertiary)`；探针 `items.json` |
| E4 | 无火花的好友**根本没有** `commonStreak*` 节点（不是 0 天） | 账号 A 共 15 项，其中 **7 项无节点**（真实会话名不入文档，见探针 `items.json`）；探针 `items.json` |
| E5 | 群聊同样有火花，不能按 type 过滤 | 有火花的会话里既有群聊（2 项：195 天橙、410 天橙）也有私聊（22 天橙、18 天灰、21 天灰等）；真实会话名不入文档，见探针 `items.json` |
| E6 | 接口路线不可行：会话列表走 protobuf，非 JSON | `POST https://imapi.douyin.com/v1/stranger/get_conversation_list`、`/v1/message/get_message_by_init`、`/v1/message/get_user_message`，content-type `application/x-protobuf`，`resp.text()` 无明文；`/aweme/v1/web/im/user/info/` 等 JSON 接口 grep `streak\|spark\|flame\|chat_days` 无逐好友命中；探针 `responses.json` |
| E7 | 扫描采集点唯一：`scan_conversations()` 已逐项持有 ElementHandle | `douyin.py:849-878`（`found.setdefault(name, self._item_kind(item))`、`douyin.py:878` 组装返回） |
| E8 | 归一函数会丢弃未知字段（必须同步改，否则重启面板丢数据） | `panel.py:129-148 _normalize_conversations()` → `out.append({"name": name, "type": ctype})`（`panel.py:147`） |
| E9 | 缓存读写在账号目录，且读取侧已走归一 | `panel.py:151-161 _load_conversations_cache()`（读 `account_root(account)/"conversations_cache.json"` → `_normalize_conversations(data)`）；`panel.py:164-174 _save_conversations_cache()`；`panel.py:177-186 _ensure_conversations_for()` |
| E10 | 已有「按会话缓存回填目标字段」的成熟范式可复用 | `panel.py:1546-1568 _enrich_target_types(account, targets)`：`conv_map = {str(c.get("name")): (c.get("type") or "private") for c in _load_conversations_cache(account)}`，按 name 精确匹配、未命中保留原值 |
| E11 | 需要显示会话/目标名的列表共三处（+1 详情），另有 1 处手打录入（无法显示火花） | ① 选会话表 `panel.html:920-951 renderConvList()`，表头 `panel.html:927`；② 定时任务列表 `panel.html:697` 表头、`panel.html:705` `const tgt = (job.targets \|\| []).map(t => esc(t.name \|\| t)).join("、")`、`panel.html:708` 截断 24 字；③ 执行记录列表 `panel.html:810-820`（`panel.html:813-815` 逐目标渲染、失败标红）；④ 执行记录详情弹窗 `panel.html:838` `目标：${(m.targets\|\|[]).join("、")` |
| E12 | 面板配色用三层语义令牌，无火花专用色 | `panel.html:11-29 :root`（`--txt:#f8fafc`、`--muted:#aab4c5`、`--brand:#fe2c55`、`--ok`、`--warn`、`--err`），无 `#ff5e00` |
| E13 | 自检基线：150 条断言全绿 | 2026-10-04 `\.venv\Scripts\python.exe verify.py` → exit code 0，`[ok]` 计数 150，无 FAIL（`verify.py` 节 1/2/3/4/5/5b/6/7/8 + 汇总在 `verify.py:384`） |

## 三、目标与非目标

### 目标
1. 「一键同步」扫描会话时，**顺带**采集每个会话项的火花天数与状态；不新增浏览器动作、不新增网络请求、不发送任何消息。
2. 采集结果随 `conversations_cache.json` 落盘，重启面板不丢。
3. 面板上**凡列出会话/目标名的列表**都显示火花天数，并按状态上色：
   - 橙（`--spark-hot`）= 今天已续；灰（`--spark-due`）= 今天还没续；`—` = 无火花或未知。
   - 覆盖：① 选会话表格（新列）；② 定时任务列表「目标」列；③ 执行记录列表「目标」列；④ 执行记录详情「目标」行；⑤ 新建定时任务的目标选择器。
4. 「新建定时任务」的目标录入从手打 textarea（`panel.html:384-385`）改为**从该账号会话列表勾选**（带火花显示与类型标签），顺带消除硬编码 `type: "private"`（`panel.html:768`）。
5. 会话卡上给出数据新鲜度（上次同步时间）与图例说明。

### 非目标（已拍板排除）
- **不做账号级汇总数字**（如「本号共 8 个火花」）——粒度是逐好友（m00073）。
- **不做历史趋势/曲线**：只存最近一次扫描快照，不建时间序列。
- **不碰 protobuf 接口**：E6 已证不可行，不引入 protobuf 依赖。
- **不改发送链路**：`douyin.py run()`、`batch_runner.py`、`runner.py`、`jobs.py` 零改动；`user_data.yaml` 的 `targets` 结构不变（不写入 spark 字段）。
- **不做定时/后台自动刷新**：火花只在用户点「一键同步」时更新（复用现成流程，避免常驻浏览器）。
- **不引入 PAN-001 的完整「统一目标选择弹层」**：本次只把「新建定时任务」的目标录入换成勾选式（复用选会话表的行样式），不重构「目标会话」折叠卡本身。

## 四、方案设计

### 4.1 数据流与信息架构

```
抖音 /chat 会话列表 DOM（每项已渲染 .commonStreaknormalText）
        │  scan_conversations() 逐项读取（零额外开销）
        ▼
douyin.py  →  [{"name","type","spark_days","spark_state"}]
        │
        ▼
panel.py _normalize_conversations() 放行新字段（否则丢弃，E8）
        │
        ▼
account_root(account)/conversations_cache.json   ← 唯一事实源（快照）
        │
        ├─► GET /api/conversations          → 选会话表（前端直接用 list）
        ├─► GET /api/conversations-cache    → 新建定时任务目标选择器（只读磁盘，不碰内存镜像）
        ├─► _scheduler_summary() GET /api/jobs    → 任务目标按名补全
        └─► list_runs() / api_run_detail()        → 执行记录目标按名补全
```

**关键决策 D1**：火花数据只做**读时按名补全**，不写回 `user_data.yaml`/`jobs.json`。
理由：缓存是快照，目标文件是配置；把易变数据混进配置会污染 PAN-001/SCH-001 已定的数据结构，且改名/删号时留下脏字段。

### 4.2 采集层（douyin.py）

新增类常量（与 `ITEM_SEL`/`LIST_SEL` 并列，`douyin.py:412-414` 一带），便于改版时集中修改：

```python
SPARK_TEXT_SEL = ".commonStreaknormalText"
SPARK_ICON_SEL = ".commonStreakicon"
```

新增方法（放在 `_item_kind` 之后，`douyin.py:429` 后）：

```python
def _item_spark(self, item) -> tuple[int | None, str | None]:
    """读会话项上的火花徽标。返回 (天数, 状态)。

    状态：'done'=今天已续（橙）、'pending'=今天未续（灰）、None=读不到。
    无火花的好友没有该节点 → (None, None)。只读，不点击、不滚动。
    """
    t = item.query_selector(self.SPARK_TEXT_SEL)
    if not t:
        return None, None
    raw = (t.text_content() or "").strip()
    days = int(raw) if raw.isdigit() else None
    icon = item.query_selector(self.SPARK_ICON_SEL)
    src = (icon.get_attribute("src") or "") if icon else ""
    if "gray" in src:
        state = "pending"
    elif src:
        state = "done"
    else:
        # 兜底：图标读不到时用文字色判定（探针实测橙=rgb(255, 94, 0)）
        try:
            color = t.evaluate("el => getComputedStyle(el).color") or ""
        except Exception:
            color = ""
        state = "done" if "255, 94, 0" in color.replace(" ", "") or "255,94,0" in color else None
    return days, state
```

`scan_conversations()` 改为同时收集火花（`douyin.py:856-878`）：

```python
found: dict[str, str] = {}
sparks: dict[str, tuple] = {}
...
    if name:
        found.setdefault(name, self._item_kind(item))
        sparks.setdefault(name, self._item_spark(item))   # 与 type 同口径：首次出现为准
...
return [{"name": n, "type": t,
         "spark_days": sparks.get(n, (None, None))[0],
         "spark_state": sparks.get(n, (None, None))[1]} for n, t in found.items()]
```

**决策 D2**：采集放在 `scan_conversations()` 内联，不新开页面/不二次遍历——每次扫描的 `self._list_conversation_items()` 循环已经持有 ElementHandle，读两个子节点是纯 DOM 查询，零额外浏览器开销。

**决策 D3**：异常一律吞掉（`query_selector` 在虚拟列表回收时可能抛 `Element is not attached`）→ 返回 `(None, None)`，绝不让火花采集失败导致整次扫描失败。扫描的既有语义（最多 60 屏、连续 3 屏无新 `data-index` 停止，`douyin.py:859-876`）完全不变。

### 4.3 持久化与归一（panel.py）

`_normalize_conversations()`（`panel.py:129-148`）放行新字段，并做类型净化：

```python
def _clean_spark_days(v):
    try:
        n = int(v)
        return n if n >= 0 else None
    except (TypeError, ValueError):
        return None

def _clean_spark_state(v):
    s = str(v or "").strip()
    return s if s in ("done", "pending") else None
```

- `isinstance(x, str)` 分支（旧缓存）：`spark_days=None, spark_state=None`。
- `isinstance(x, dict)` 分支：`out.append({"name": name, "type": ctype, "spark_days": _clean_spark_days(x.get("spark_days")), "spark_state": _clean_spark_state(x.get("spark_state"))})`。

**决策 D4**：净化在**读侧**（归一函数）做，不在写侧。理由：E9 显示磁盘缓存读取必经 `_normalize_conversations`，一处收口即可同时防住旧格式缓存与手改文件。

`api_conversations()`（`panel.py:974-986`）增补 `"cache_mtime"`：缓存文件 `stat().st_mtime` 格式化为 `"YYYY-MM-DD HH:MM"`，读不到则 `None`。用于前端展示数据新鲜度。

### 4.4 后端读取侧补全（三处列表）

新增与 `_enrich_target_types` 同口径的辅助（紧邻 `panel.py:1546` 放置）：

```python
def _spark_map(account: str) -> dict[str, dict]:
    """该号会话缓存里的 name → {"spark_days": int|None, "spark_state": str|None}。"""
    try:
        return {str(c.get("name")): {"spark_days": c.get("spark_days"),
                                     "spark_state": c.get("spark_state")}
                for c in _load_conversations_cache(account)}
    except Exception:  # noqa: BLE001
        return {}
```

1. **`_scheduler_summary()`（`panel.py:1571-1607`）**：`jobs.load_jobs()` 后逐 job 按其 `job["account"]` 取 `_spark_map`，挂到**独立键 `job["spark"]`**（`{name: {"spark_days":…, "spark_state":…}}`），**不改 `job["targets"]` 元素形状**——与 `list_runs`/`api_run_detail` 同口径（决策 D10）。`jobs.load_jobs()` 每次从 JSON 重新加载，原地改写安全。
2. **`list_runs(account)`（`panel.py:407`）**：每条 run 增补 `"spark"`: `{name: {"spark_days":…, "spark_state":…}}`（run 的 `targets` 是名字串列表，故用映射而非数组）。
3. **`api_run_detail(run_id)`（`panel.py:929`）**：由 `_find_run_account(run_id)` 拿账号（`panel.py:373`）后，给 `meta` 增补同样的 `"spark"` 映射。

**决策 D5**：补全只增字段、不改既有字段名与顺序；账号无缓存/名字不匹配一律留 `None`，前端显示 `—`，不报错、不阻塞列表。

**决策 D10**（2026-10-04 自审定稿）：火花补全一律挂在**独立映射**上（`job["spark"]`、`run["spark"]`、`meta["spark"]`），不写进 `targets` 数组元素。理由：`targets` 是 PAN-001/SCH-001 已定的配置数据结构（`{name, type}`），混入展示态字段会污染配置语义与 `POST /api/jobs` 的保存体形状；三处统一映射口径，前端按名字取值、未命中回落 `—`。

### 4.5 前端展示与配色（panel.html）

新增 CSS 令牌（`panel.html:11-29 :root` 内，跟随三层令牌注释）：

```css
--spark-hot:#ff5e00;     /* 火花已续（抖音橙，对 --bg #020617 对比度 ≈5.9:1，达 AA） */
--spark-due:#aab4c5;     /* 火花待续（复用 muted，弱化但不消失） */
```
```css
.spark{font-size:12px;font-weight:600;margin-left:6px;white-space:nowrap}
.spark.hot{color:var(--spark-hot)}
.spark.due{color:var(--spark-due)}
```

新增统一渲染函数（紧邻 `escapeHtml`，`panel.html:898` 前）：

```js
// SPK-001：火花徽标。days 为 null/undefined 或 state 缺失 → 返回占位
function sparkBadge(days, state){
  if (days === null || days === undefined || !state) return ' <span class="muted">—</span>';
  const cls = state === "done" ? "hot" : "due";
  const zh  = state === "done" ? "今天已续" : "今天还没续";
  return ` <span class="spark ${cls}" title="${zh}">${Number(days)}天</span>`;
}
```

五处接入：

| 位置 | 改动 |
|---|---|
| 选会话表格 | 列序定稿（决策 D11）：**名称 → 火花 → 类型**。表头 `panel.html:927` 在「会话名称」th 与「类型」th **之间**插入 `<th style="width:96px">火花</th>`；行在名称单元格 `panel.html:936` **之后**、类型单元格 `panel.html:937-944` **之前**插入 `<td>${sparkBadge(c.spark_days, c.spark_state)}</td>`（`c` 即 `convCache` 项） |
| 定时任务列表「目标」列 | `panel.html:705` 改为逐目标拼名字 + `sparkBadge`；`title` 仍保留完整纯文本名串（`panel.html:708`） |
| 执行记录列表「目标」列 | `panel.html:813-815` 逐目标拼名字 + `sparkBadge(r.spark?.[t]?.spark_days, r.spark?.[t]?.spark_state)`；失败标红逻辑保留 |
| 执行记录详情 | `panel.html:838` 目标行同上（读 `m.spark`） |
| 新建定时任务目标选择器 | `panel.html:384-385` 换为 `#newJobTargetsWrap`（见 4.6）；`renderNewJobTargets()` 每行名字 + `sparkBadge(c.spark_days, c.spark_state)` |

会话卡说明文案（`panel.html:339` 提示行）追加：
「火花：**橙=今天已续 / 灰=今天还没续 / —=无火花**；数据来自上次同步（<span id="sparkAt">—</span>），点「一键同步」刷新。」

**决策 D6**：`—` 而不是「0天」。E4 已证「无火花」与「0 天」语义不同（无火花者根本没有节点），统一显示 `—` 避免误读。
**决策 D7**：上色用 CSS 令牌而非内联 `style`，与 E12 既有令牌体系一致，且便于以后换主题。

**决策 D11**（2026-10-04 自审定稿）：火花列固定在**名称之后、类型之前**（第 3 列）。理由：(a) `thead` 与 `tbody` 必须同序——首轮 plan 把表头写在「类型」后、行 `<td>` 写在名称后，会直接错列；(b) 火花是对「这个人」的度量，紧跟名字可读性最好，类型是次要属性放最后。新建任务选择器沿用同序（`renderNewJobTargets()`）。

### 4.6 新建定时任务目标选择改造（本轮追加）

现状（E11/证据）：`panel.html:384-385` 手打 textarea；`panel.html:768` `const targets = $("#newJobTargets").value.split("\n")...map(name => ({name, type: "private"}))` —— 名字靠人记，类型硬编码 private。

改造为勾选式（复用选会话表的视觉与交互，不新建弹层组件）：

```html
<label style="margin-top:8px">目标（从该账号会话列表勾选；类型随扫描结果）</label>
<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:8px">
  <button id="newJobPickBtn" class="btn ghost sm">加载会话列表</button>
  <button id="newJobSelAllBtn" class="btn ghost sm">全选</button>
  <button id="newJobSelInvBtn" class="btn ghost sm">反选</button>
</div>
<div id="newJobTargetsWrap"><div class="muted">选择账号后点「加载会话列表」。</div></div>
```

- 前端状态：`let newJobTargets = [];`（元素 `{name, type}`），渲染函数 `renderNewJobTargets()` 输出与 `renderConvList()`（`panel.html:920-951`）同构的表格，多一列火花（`sparkBadge`），类型用只读标签（不再逐行下拉，降噪）。
- 数据来源：新增**只读**接口 `GET /api/conversations-cache?account=X`（见 4.7），**不触碰内存镜像 `_conversations`**，避免与「一键触发」页的 `_ensure_conversations_for`（`panel.py:177-186`）互相抢账号归属。
- 账号联动：`#newJobAccount`（`panel.html:377`）`onchange` → 清空 `newJobTargets` 与 `#newJobTargetsWrap`，提示「点『加载会话列表』」。
- 保存：`panel.html:768` 改为 `const targets = newJobTargets.map(t => ({name: t.name, type: t.type}));`；校验合并为一次（`!account || !time || !newJobTargets.length || !texts.length`）→ `toast("请填完整：账号/时间/目标/文案", "err")`。后端 `POST /api/jobs`（`panel.py:1392-1412`）已有 `_enrich_target_types` 兜底，类型传错也会被缓存纠正。
- `api()` 辅助（`panel.html:443-457`）增补显式账号覆盖：`const acct = opts.account || activeAccount;`，使选择器能取**非当前账号**的会话缓存。

**决策 D8**：新增只读接口而不是复用 `/api/conversations`。理由：后者经 `_ensure_conversations_for` 会改写全局内存镜像（P1-1 的账号归属），跨账号读会让「一键触发」页的列表归属抖动；只读接口直接读磁盘缓存，零副作用。

**决策 D9**：类型在新建任务页只读展示（默认取扫描识别值），不再逐行下拉。理由：与 PAN-001 决策 6「类型控件降噪」方向一致，且勾选来源就是扫描结果，类型本就已知。

### 4.7 后端增量（最小面）

| 文件 | 增量 |
|---|---|
| `douyin.py` | 2 个类常量；`_item_spark()`；`scan_conversations()` 返回值加 2 字段 |
| `panel.py` | `_clean_spark_days`/`_clean_spark_state`；`_normalize_conversations` 放行；`_spark_map()`；`api_conversations` 加 `cache_mtime`；`_scheduler_summary`/`list_runs`/`api_run_detail` 补全 |
| `panel.html` | 2 个 CSS 令牌 + `.spark` 规则；`sparkBadge()`；5 处接入；新建任务目标选择器（含 `renderNewJobTargets()`/`#newJobPickBtn`/`#newJobSelAllBtn`/`#newJobSelInvBtn`/`#newJobTargetsWrap`）；`api()` 增 `opts.account` 覆盖；1 处说明文案 |
| `panel.py`（接口） | 新增 `GET /api/conversations-cache`（只读磁盘缓存 + `cache_mtime`，不碰内存镜像） |
| 其余（`runner.py`/`batch_runner.py`/`jobs.py`/`scheduler_daemon.py`） | **零改动** |

## 五、错误处理（场景 × 行为）

| 场景 | 行为 |
|---|---|
| 会话项无 `.commonStreak*` 节点（无火花，E4） | `spark_days=None, spark_state=None` → 前端 `—`，无色 |
| `.commonStreaknormalText` 文本非数字 | `spark_days=None`；状态仍按图标判定并保留 |
| 图标 `src` 与文字色都读不到 | `spark_state=None` → 前端 `—`（不猜状态） |
| 虚拟列表节点回收导致 `query_selector` 抛异常 | `_item_spark` 吞异常返回 `(None, None)`，不影响该会话的 name/type，也不中断整次扫描 |
| 缓存文件缺失/损坏/旧 `list[str]` 格式 | E9 既有兜底：返回 `[]` 或 name/type；火花字段全 `None` → 全 `—` |
| 账号已删除 / 新号无缓存 | `_spark_map` 返回 `{}` → 任务/记录目标全 `—`，列表照常渲染 |
| 任务/记录的目标名与扫描名不一致（手输、改名） | 按 name 精确匹配失败 → 该目标 `—`（已知限制，见 R3） |
| 用户从未点过「一键同步」 | `list` 为空 → 表格显示既有「尚未同步」提示；任务/记录目标全 `—` |
| 面板长时间未同步，数据过期 | 不自动刷新；会话卡标注上次同步时间，文案提示点「一键同步」刷新 |
| 抖音改版导致类名变化 | 采集全空 → 全 `—`；`verify.py` 节 9 断言锁死选择器字面量，回归即红 |
| 新建任务目标选择器：所选账号无会话缓存 | `#newJobTargetsWrap` 显示「该账号尚未同步会话，请到「一键触发」页切到该账号点『一键同步』」；保存时因 `newJobTargets` 为空而 `toast` 拦截 |
| 新建任务目标选择器：切换账号后未重新加载 | `onchange` 清空已选与表格，避免把 A 号会话存进 B 号任务 |
| `/api/conversations-cache` 传入不存在账号 | 返回 `{"list": [], "cache_mtime": null}`，前端提示未同步，不 500 |
| 新建任务勾选了「无火花」会话 | 允许（无火花 ≠ 不可发送），列表里显示 `—` |

## 六、验证方案（RED / GREEN）

`verify.py` 新增一节（置于 `verify.py:238` 节 8 之后、`verify.py:384` 汇总之前）：

```python
# --- 9. 火花天数采集与展示（SPK-001） -----------------------------------------
```

新增断言（**先写断言并跑出 RED，再动实现代码**；`d` = `read("douyin.py")`，`p` = `read("panel.py")`，`html_txt` = `read("panel.html")`）：

| # | 断言 | 判据 |
|---|---|---|
| 1 | ★SPK-001 douyin 采集火花天数节点 | `".commonStreaknormalText" in d` |
| 2 | ★SPK-001 douyin 采集火花图标节点 | `".commonStreakicon" in d` |
| 3 | ★SPK-001 火花状态灰色判定 | `'"gray" in src' in d` |
| 4 | ★SPK-001 扫描结果携带 spark_days | `'"spark_days"' in d` |
| 5 | ★SPK-001 扫描结果携带 spark_state | `'"spark_state"' in d` |
| 6 | ★SPK-001 面板归一放行火花字段 | `'x.get("spark_days")' in p and 'x.get("spark_state")' in p` |
| 7 | ★SPK-001 面板按名补全火花映射 | `"def _spark_map(" in p` |
| 8 | ★SPK-001 会话接口带缓存时间 | `'"cache_mtime"' in p` |
| 9 | ★SPK-001 页面火花渲染函数 | `"function sparkBadge(" in html_txt` |
| 10 | ★SPK-001 页面火花配色令牌 | `"--spark-hot" in html_txt and "--spark-due" in html_txt` |
| 11 | ★SPK-001 各处列表均渲染火花 | `html_txt.count("sparkBadge(") >= 6`（1 处函数定义 + 5 处调用：选会话表/定时任务列表/执行记录列表/执行记录详情/新建任务目标选择器） |
| 12 | ★SPK-001 无火花显示占位 | `'<span class="muted">—</span>' in html_txt` |
| 13 | ★SPK-001 新建任务目标改为勾选式（textarea 退场） | `'id="newJobTargets"' not in html_txt and 'id="newJobTargetsWrap"' in html_txt` |
| 14 | ★SPK-001 新建任务保存用勾选结果 | `"newJobTargets.length" in html_txt and '"#newJobTargets"' not in html_txt` |
| 15 | ★SPK-001 会话缓存只读接口（不切内存镜像） | `'"/api/conversations-cache"' in p` |
| 16 | ★SPK-001 api() 支持显式账号覆盖 | `"opts.account" in html_txt` |
| 17 | ★SPK-001 会话卡展示上次同步时间 | `'id="sparkAt"' in html_txt` |

**基线（E13）**：改前 `verify.py` = 150 条 `[ok]` / 0 FAIL / exit 0（2026-10-04 实测）。
**RED**：加断言后跑 → 新增 17 条全部 FAIL，总数 167，exit 非 0。
**GREEN**：实现完成后跑 → 167 条全 `[ok]`，exit 0。

**人工验证（真实浏览器，GREEN 后一次）**：面板点「一键同步」→ 对照抖音 /chat 页面逐项核对橙/灰与天数；确认选会话表、定时任务列表、执行记录列表、执行记录详情、新建任务目标选择器**五处**均显示且颜色正确；确认无火花项为 `—`；确认新建定时任务可跨账号勾选目标并成功保存、守护能按新任务正常触发。

## 七、风险

| # | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | 抖音改版改掉 `commonStreak*` 类名 | 采集全空，全 `—` | 选择器集中为类常量（`douyin.py:412` 一带）；采集失败静默；`verify.py` 断言 1–3 锁死字面量，回归即红 |
| R2 | 用户长期不点「一键同步」，显示旧值 | 误判「今天已续」 | 会话卡标注上次同步时间（4.3 的 `cache_mtime` → `#sparkAt`，断言 17 门禁）+ 文案提示 |
| R3 | 任务/记录目标是手输名，与扫描名不一致 | 该目标显示 `—` | 已知限制；`_enrich_target_types`（E10）已是同一套匹配口径，问题同源同解（PAN-001 统一目标弹层时一并消除） |
| R4 | 忘记改 `_normalize_conversations`（E8） | 重启面板后火花全丢，且不易察觉 | 断言 6 专门覆盖；`_save_conversations_cache` 写的是内存态，内存态经归一 → 一处漏改即全链失效，断言即门禁 |
| R5 | 群聊与私聊同名 | 补全错配到另一个会话 | `_normalize_conversations` 已按 name 去重（`panel.py:145-146 seen`），沿用现状；与 type 补全同风险同现状 |
| R6 | `--spark-hot:#ff5e00` 在深色底对比度不足 | 可读性/无障碍 | 对 `--bg:#020617` 对比度 ≈5.9:1，达 WCAG AA（4.5:1）；灰用新增令牌 `--spark-due:#aab4c5`（与 `panel.html:20 --muted` 同值，复用其已满足的对比度；语义独立，便于以后单独调） |
| R7 | 扫描耗时增加 | 同步变慢 | 每项 2 次 `query_selector` 纯 DOM 查询，相对既有 0.4–0.8s/屏滚动（`douyin.py:876`）可忽略 |
| R8 | 改造「新建定时任务」录入会动到 SCH-001 的保存路径（`panel.html:764-779` → `POST /api/jobs`） | 可能破坏既有建任务流程 | 后端 `POST /api/jobs`（`panel.py:1392-1412`）与 `jobs.py` **零改动**，只换前端目标来源；保存体仍是 `{account, time, targets:[{name,type}], texts}` 同一形状；断言 13/14 锁住 textarea 退场与勾选结果生效；人工验证含「新建任务能保存并按时触发」 |
| R9 | `api()` 增加 `opts.account` 覆盖可能影响既有调用 | 误把别的账号写进请求 | 覆盖仅在**显式传入** `opts.account` 时生效（`const acct = opts.account \|\| activeAccount;`），既有调用不传则行为不变；断言 16 锁住该写法 |

## 八、待确认

| # | 问题 | 结论 / 建议 |
|---|---|---|
| Q1 | 是否要展示「上次同步时间」？ | **已拍板（2026-10-04）：要展示**——`cache_mtime` → `#sparkAt`（4.5），断言 17 门禁 |
| Q2 | 无火花显示 `—` 还是 `0天`？ | **已拍板（2026-10-04）：显示 `—`**（E4：无火花 ≠ 0 天） |
| Q3 | 「新建定时任务」手打目标是否本次一并改为带火花的勾选？ | **已拍板（2026-10-04）：本次一并改造**，见 4.6 |
| Q4 | 定时任务列表目标列已截断 24 字（`panel.html:708`），加了火花徽标后更挤 | **已拍板（2026-10-04）：不按字符截断**，改 `td.cell-tgt` 的 CSS 省略号 + `title` 全文。理由：火花徽标是 HTML，按字符 `slice` 会把标签截断 |

## 九、实施顺序（供 plan 参考）

1. **RED**：`verify.py` 加节 9 的 17 条断言 → 跑出 17 FAIL（167 总数）→ 提交。
2. **采集层**：`douyin.py` 加 2 常量 + `_item_spark()` + `scan_conversations()` 返回值扩字段。
3. **持久层**：`panel.py` 加 `_clean_spark_days`/`_clean_spark_state`，`_normalize_conversations` 放行。
4. **读取层**：`panel.py` 加 `_spark_map()`；`_scheduler_summary`/`list_runs`/`api_run_detail` 补全；`api_conversations` 加 `cache_mtime`；新增只读接口 `GET /api/conversations-cache`。
5. **展示层**：`panel.html` 加 CSS 令牌与 `.spark` 规则、`sparkBadge()`、五处接入、说明文案。
6. **录入改造**：`panel.html` 新建任务目标选择器（`renderNewJobTargets()` 等）、`api()` 增 `opts.account` 覆盖、`panel.html:768` 保存改用 `newJobTargets`。
7. **GREEN**：`verify.py` 167 条全 `[ok]`、exit 0。
8. **人工验证**：真实浏览器一次全量核对（见第六节）。
9. **文档**：本 spec 状态更新为已批准；`CHANGELOG.md` 增条目；`docs/` 用户指南（管理面板使用指南.md）补「火花天数」说明；`docs/superpowers/status/` 落 SPK-001 状态。

---

## 修订记录

### 2026-10-04 自审修订（首轮评审 → 定稿）

首轮自审（`docs/superpowers/reviews/SPK-001-spec-review.md`，结论 CHANGES_REQUIRED）发现的问题及处置：

| 编号 | 级别 | 处置 |
|---|---|---|
| S-P1-1 | P1 | **已修**：E4/E5 与决策来源中的真实账号别名、真实会话名全部占位化（账号 A；数量与天数关系保留） |
| S-P2-1 | P2 | **已修**：4.4 第 1 条改为独立映射 `job["spark"]`（决策 D10），与 plan 定稿一致，不再改写 `job["targets"]` 元素 |
| S-P2-2 | P2 | **已修**：Q1 拍板「要展示」，4.5 的 `#sparkAt` 落地为断言 17；断言总数 16 → 17，收尾 166 → 167 |
| S-P2-3 | P2 | **已修**：删除 4.6 的 `#newJobPickHint` 幽灵元素；label 与 toast 文案对齐 plan |
| S-P3-1 | P3 | **已修**：R2 的「决策 D4」改指 4.3 |
| S-P3-2 | P3 | **已修**：R6 改为 `--spark-due` 新增令牌口径 |
| S-P3-3 | P3 | **已修**：4.5 的 `${days}天` 改 `${Number(days)}天` |
| S-P3-4 | P3 | **已修**：4.5 明确列序（决策 D11：名称 → 火花 → 类型），与 plan Task 3 同序 |
| S-P3-5 | P3 | **已修**：`_scheduler_summary()` 锚改 `panel.py:1571-1607` |
| S-P3-6 | P3 | **已修**：Q4 拍板采 plan 口径（CSS 省略号 + `title` 全文） |

同轮 plan 自审的 P-P1-1/P-P2-1/P-P2-2/P-P2-3/P-P3-3 属 plan 侧措辞，已同步修入 plan；两份评审文件均追加「第二轮复审」并给出 APPROVED。

