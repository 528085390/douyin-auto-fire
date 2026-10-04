# SPK-001 火花天数展示：逐好友采集与全列表呈现 — 实施计划（plan）

- 日期：2026-10-04
- Task-ID：SPK-001
- 状态：**已批准（2026-10-04）**——用户 (m00429)：「你来修复分歧，然后开子代理去做，做完之后开管理面板页面给我确认火花天数是否正常」；首轮自审的 P1/P2/P3 已全部处置（见十、修订记录）
- 依赖的 spec：`docs/superpowers/specs/2026-10-04-spark-days-display-design.md`（SPK-001，状态=已批准；Q1/Q4 已拍板，决策 D10/D11 已回写）
- 基线：2026-10-04 实测 `.venv\Scripts\python.exe verify.py` → 通过 150 / 失败 0，exit 0（spec E13）
- 纪律：先 RED 后 GREEN，每 Task 独立中文 conventional 提交；代码与文档分开提交；隐私红线（提交文件不得出现真实账号别名/会话名/发送内容，示例一律占位）

---

## 一、目标与验收

按 spec 四章实现：一键同步扫描时**顺带**采集每个会话项的火花天数与状态（DOM `.commonStreaknormalText` / `.commonStreakicon`；零新增浏览器动作、零新增网络请求、不发任何消息）；随 `conversations_cache.json` 落盘；面板凡列出会话/目标名的列表（5 处）显示火花并按状态上色（橙=今天已续、灰=今天还没续、`—`=无火花或未知）；「新建定时任务」目标录入由手打 textarea 改为按该号会话缓存勾选，顺带消除硬编码 `type:"private"`。

验收标准（全绿条件）：

1. verify.py 基线 2026-10-04 实测**通过 150 / 失败 0**（spec E13）。
2. 四个 Task 按七节演进表推进，收尾 **FAIL = 0、exit 0、通过 167**（167 = 150 + 17 条新增断言；本次无替换类断言）。
3. 只读接口 curl 抽查：`GET /api/conversations-cache?account=<别名>` 返回 `{list, cache_mtime}`；`GET /api/jobs` 每 job 带 `spark`；`GET /api/runs` 每 run 带 `spark`；`GET /api/runs/<id>` 的 meta 带 `spark`。
4. 浏览器人工核验五处橙/灰/`—` + 新建任务跨账号勾选保存（八节清单）。
5. 发送链路零改动：`douyin.py run()`、`runner.py`、`batch_runner.py`、`jobs.py`、`scheduler_daemon.py` 零改动（`scan_conversations()` 只增字段）；`user_data.yaml` 的 `targets` 结构不变。

## 二、任务拆分与提交

| Task | 内容 | 提交（中文 conventional） |
|---|---|---|
| 1 | douyin.py 采集层：2 个类常量 + `_item_spark()` + `scan_conversations()` 返回值加 2 字段（先 RED：5 条新断言全 FAIL） | RED：`test(verify): SPK-001 T1 RED 火花采集断言（期望 150/5）`；GREEN：`feat(douyin): SPK-001 扫描会话时顺带采集火花天数与状态` |
| 2 | panel.py 持久/读取/接口层：`_clean_spark_*` + `_normalize_conversations` 放行 + `_spark_map()` + `list_runs`/`api_run_detail`/`_scheduler_summary` 补全 + `api_conversations` 加 `cache_mtime` + 新只读接口 `GET /api/conversations-cache` | RED：`test(verify): SPK-001 T2 RED 火花持久与补全断言（期望 155/4）`；GREEN：`feat(panel): SPK-001 火花字段落盘放行 + 按名补全 + 只读会话缓存接口` |
| 3 | panel.html 展示层：CSS 令牌与 `.spark` 规则 + `sparkBadge()` + 4 处接入（选会话表 / 定时任务列表 / 执行记录列表 / 执行记录详情） | RED：`test(verify): SPK-001 T3 RED 火花展示断言（期望 159/4）`；GREEN：`feat(panel): SPK-001 火花徽标与四处列表展示（橙/灰/—）` |
| 4 | panel.html 录入改造：`#newJobTargets` textarea → 勾选式（`#newJobPickBtn`/`#newJobSelAllBtn`/`#newJobSelInvBtn`/`#newJobTargetsWrap` + `renderNewJobTargets()`）+ `api()` 支持显式账号 + 保存改用 `newJobTargets`（含第 5 处火花接入） | RED：`test(verify): SPK-001 T4 RED 新建任务目标勾选断言（期望 163/4）`；GREEN：`feat(panel): SPK-001 新建定时任务目标改为按会话勾选（带火花与类型）` |
| 5 | 文档同步：spec 状态更新、`CHANGELOG.md` 条目、`docs/管理面板使用指南.md` 补「火花天数」说明、`docs/superpowers/status/SPK-001.md` | `docs: SPK-001 火花天数说明与状态归档` |

代码与文档分开提交；全程直接提交 main（仓库惯例）；每个 Task 提交前后跑一次 verify 记录 FAIL/PASS（见七节，以实际输出核对为准）。

## 三、Task 1 细则（douyin.py 采集层，零行为改动）

### RED 断言（verify.py 新增节 9，插到 `# --- 8. .vbs 必须是纯 ASCII` 节之后、`# --- 汇总`（verify.py:384）之前）

~~~python
# --- 9. 火花天数采集与展示（SPK-001） ---
# d = read("douyin.py") 已在 verify.py:118 定义
check("★SPK-001 会话项火花文本选择器", ".commonStreaknormalText" in d)
check("★SPK-001 会话项火花图标选择器", ".commonStreakicon" in d)
check("★SPK-001 火花状态按图标灰判定", '"gray" in src' in d)
check("★SPK-001 扫描结果携带火花天数", '"spark_days"' in d)
check("★SPK-001 扫描结果携带火花状态", '"spark_state"' in d)
~~~

RED 期望：5 条全 FAIL（现码实测 0 命中），通过 150 / 失败 5，总数 155。

### GREEN 改动点（字节要求：以下字面量必须原样出现，断言为准绳）

1. 类常量（`douyin.py:414 ZWSP = "\u200b"` 之后、`douyin.py:416 _list_conversation_items` 之前）：

~~~python
    SPARK_TEXT_SEL = ".commonStreaknormalText"
    SPARK_ICON_SEL = ".commonStreakicon"
~~~

2. 新增 `_item_spark()`（`douyin.py:429 _item_kind` 的 return 之后、`douyin.py:431 _find_rendered_item` 之前）：

~~~python
    def _item_spark(self, item) -> tuple:
        """会话项火花徽标 → (天数, 状态)。无火花/读取失败一律 (None, None)。

        状态：图标 src 含 gray → pending（今天还没续）；其余有 src → done（今天已续）；
        图标缺失时兜底看文字色（抖音橙 #ff5e00 的 rgb 形态）。
        SPK-001 D3：虚拟列表回收会抛 detached，异常一律吞掉，绝不拖垮整次扫描。
        """
        days, state = None, None
        try:
            t = item.query_selector(self.SPARK_TEXT_SEL)
            if t:
                raw = (t.text_content() or "").replace(self.ZWSP, "").strip()
                if raw.isdigit():
                    days = int(raw)
            icon = item.query_selector(self.SPARK_ICON_SEL)
            src = (icon.get_attribute("src") or "") if icon else ""
            if "gray" in src:
                state = "pending"
            elif src:
                state = "done"
            else:
                color = (t.evaluate("el => getComputedStyle(el).color") if t else "") or ""
                if "255, 94, 0" in color:
                    state = "done"
        except Exception:  # noqa: BLE001
            return None, None
        if not t:
            return None, None
        return days, state
~~~

3. `scan_conversations()`（`douyin.py:849`）：`found` 旁加 `sparks`，循环内同口径首次为准，返回加 2 字段。

- `douyin.py:856` 的 `found: dict[str, str] = {}` 之后加 `sparks: dict[str, tuple] = {}`；
- `douyin.py:863` 的 `found.setdefault(name, self._item_kind(item))` 之后加 `sparks.setdefault(name, self._item_spark(item))`；
- `douyin.py:878` 的 `return [{"name": n, "type": t} for n, t in found.items()]` 替换为：

~~~python
        return [{"name": n, "type": t,
                 "spark_days": sparks.get(n, (None, None))[0],
                 "spark_state": sparks.get(n, (None, None))[1]} for n, t in found.items()]
~~~

### 验收

RED 150/5 → GREEN 155/0；`git diff` 确认 `run()`/`runner.py`/`batch_runner.py`/`jobs.py`/`scheduler_daemon.py` 零改动；扫描语义（最多 60 屏、连续 3 屏无新 `data-index` 停止，`douyin.py:859-876`）不变。

## 四、Task 2 细则（panel.py 持久/读取/接口层）

### RED 断言

~~~python
check("★SPK-001 会话归一放行火花字段", 'x.get("spark_days")' in p and 'x.get("spark_state")' in p)
check("★SPK-001 按名补全火花映射函数", "def _spark_map(" in p)
check("★SPK-001 会话接口返回缓存时间", '"cache_mtime"' in p)
check("★SPK-001 只读会话缓存接口", '"/api/conversations-cache"' in p)
~~~

RED 期望：4 条全 FAIL（现码 0 命中），通过 155 / 失败 4，总数 159。

### GREEN 改动点

1. 净化函数（`panel.py:129 def _normalize_conversations` 之前）：

~~~python
def _clean_spark_days(v) -> int | None:
    """火花天数净化：非负整数才保留，其余一律 None（旧缓存/手改文件兜底）。"""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    return n if n >= 0 else None


def _clean_spark_state(v) -> str | None:
    """火花状态净化：仅认 done（今天已续）/ pending（今天还没续）。"""
    s = str(v or "").strip()
    return s if s in ("done", "pending") else None
~~~

2. `_normalize_conversations`（`panel.py:137-147`）：分支内取火花、`out.append` 放行两字段（D4：读侧一处收口，防旧格式缓存与手改文件）。

~~~python
    for x in raw or []:
        spark_days = None
        spark_state = None
        if isinstance(x, str):
            name, ctype = x.strip(), "private"
        elif isinstance(x, dict):
            name = str(x.get("name") or "").strip()
            ctype = str(x.get("type") or "private").strip() or "private"
            spark_days = _clean_spark_days(x.get("spark_days"))
            spark_state = _clean_spark_state(x.get("spark_state"))
        else:
            continue
        if name and name not in seen:
            seen.add(name)
            out.append({"name": name, "type": ctype,
                        "spark_days": spark_days, "spark_state": spark_state})
~~~

3. 新增 `_spark_map()`（`panel.py:1568 _enrich_target_types` 的 return 之后、`panel.py:1571 _scheduler_summary` 之前）：

~~~python
def _spark_map(account: str) -> dict:
    """按会话名索引该号最近一次同步的火花快照：name -> {spark_days, spark_state}。

    SPK-001 D8：只读磁盘缓存，不碰内存 _conversations 镜像（跨账号读无副作用）；
    未同步/未命中返回 {}，调用方一律按无火花渲染 —。
    """
    try:
        return {str(c.get("name")): {"spark_days": c.get("spark_days"),
                                     "spark_state": c.get("spark_state")}
                for c in _load_conversations_cache(account) if c.get("name")}
    except Exception:  # noqa: BLE001
        return {}
~~~

4. `list_runs`（`panel.py:407-420`）在 `return runs` 前补 `spark` 映射：

~~~python
    smap = _spark_map(account)
    for m in runs:
        m["spark"] = smap
    return runs
~~~

5. `api_run_detail`（`panel.py:929-953`）在 `return {...}` 前加 `meta["spark"] = _spark_map(acc)`（`acc` 已在 `panel.py:931` 解析）。

6. `_scheduler_summary`（`panel.py:1571-1607`）：`panel.py:1591` 的 `"jobs": jobs.load_jobs(),` 替换为 `"jobs": _jobs_with_spark(),`，并在 `_spark_map()` 之后新增：

~~~python
def _jobs_with_spark() -> list[dict]:
    """任务库逐 job 挂 spark 映射（键=该 job 所属账号的会话缓存）。"""
    out = []
    for j in jobs.load_jobs():
        try:
            j["spark"] = _spark_map(str(j.get("account") or ""))
        except Exception:  # noqa: BLE001
            j["spark"] = {}
        out.append(j)
    return out
~~~

7. `api_conversations`（`panel.py:974-986`）返回值加 `cache_mtime`：

~~~python
    mtime = None
    try:
        cp = account_root(account) / "conversations_cache.json"
        if cp.exists():
            mtime = datetime.fromtimestamp(cp.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        mtime = None
    return {
        "syncing": _sync_running,
        "list": list(_conversations),
        "saved": saved,
        "cache_mtime": mtime,
    }
~~~

8. 新增只读接口（`panel.py:1100` 的 `/api/conversations` 分支之后、`panel.py:1101` 的 `/api/batch-state` 之前）：

~~~python
            if path == "/api/conversations-cache":
                # SPK-001 D8：只读磁盘缓存，供「新建定时任务」跨账号取列表，零内存副作用
                acc = _resolve_account(params)
                if not acc:
                    return self._send_json({"list": [], "cache_mtime": None})
                cp = account_root(acc) / "conversations_cache.json"
                mtime = None
                try:
                    if cp.exists():
                        mtime = datetime.fromtimestamp(
                            cp.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                except Exception:  # noqa: BLE001
                    mtime = None
                return self._send_json({"list": _load_conversations_cache(acc),
                                        "cache_mtime": mtime})
~~~

### 验收

RED 155/4 → GREEN 159/0；curl 抽查四个端点字段齐备；`_ensure_conversations_for`（`panel.py:177-186`）不被新接口触碰（D8 的核心约束）。

## 五、Task 3 细则（panel.html 展示层，4 处接入）

### RED 断言

~~~python
check("★SPK-001 火花徽标渲染函数", "function sparkBadge(" in html_txt)
check("★SPK-001 火花配色令牌", "--spark-hot" in html_txt and "--spark-due" in html_txt)
check("★SPK-001 无火花占位符", '<span class="muted">—</span>' in html_txt)
check("★SPK-001 会话卡展示上次同步时间", 'id="sparkAt"' in html_txt)
~~~

RED 期望：4 条全 FAIL，通过 159 / 失败 4，总数 163。

### GREEN 改动点

1. `:root` 令牌（`panel.html:26 --err` 之后）：

~~~css
    --spark-hot:#ff5e00;     /* 火花：今天已续（抖音橙） */
    --spark-due:#aab4c5;     /* 火花：今天还没续（灰） */
~~~

2. `.spark` 规则（`panel.html:180 .muted` 之后）：

~~~css
  .spark{color:var(--spark-hot);white-space:nowrap;font-variant-numeric:tabular-nums}
  .spark.due{color:var(--spark-due)}
  td.cell-tgt{max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
~~~

3. `sparkBadge()`（`panel.html:898 function escapeHtml` 之前）：

~~~js
// SPK-001：火花徽标。无值 → —（无火花 ≠ 0 天）；橙=今天已续，灰=今天还没续
function sparkBadge(days, state){
  if (days === null || days === undefined || days === "" || !state) return ' <span class="muted">—</span>';  // 状态未知不猜，一律 —
  const cls = state === "pending" ? "spark due" : "spark";
  const tip = state === "pending" ? "今天还没续" : "今天已续";
  return ${` <span class="${cls}" title="${tip}">${Number(days)}天</span>`};
}
~~~

4. 四处接入（列序定稿 D11：**名称 → 火花 → 类型**）：

- ① 选会话表：`panel.html:927` 在「会话名称」th 与「类型」th **之间**插入 `<th style="width:96px">火花</th>`（结果：`<th style="width:46px"></th><th>会话名称</th><th style="width:96px">火花</th><th style="width:130px">类型</th>`）；`panel.html:928` 循环内加 `const sp = (typeof c === "object" && c) ? c : {};`；`panel.html:936`（名称单元格）**之后**、类型单元格 `panel.html:937-944` **之前**插入 `<td>${sparkBadge(sp.spark_days, sp.spark_state)}</td>`。
- ② 定时任务列表 `panel.html:705-708` 替换为（spec Q4 关闭：不再按字符截断，改 CSS 省略号 + `title` 全文）：

~~~js
        const sp = job.spark || {};
        const names = (job.targets || []).map(t => String(t.name || t));
        const tgtHtml = names.map(n => {
          const s = sp[n] || {};
          return esc(n) + sparkBadge(s.spark_days, s.spark_state);
        }).join("、");
~~~

`panel.html:708` 的 `<td title="${esc(tgt)}">${esc(tgt.slice(0, 24))}</td>` 替换为 `<td class="cell-tgt" title="${esc(names.join("、"))}">${tgtHtml}</td>`。

- ③ 执行记录列表 `panel.html:813-815` 替换为：

~~~js
      const sp = r.spark || {};
      const targets = (r.targets || []).map(t => {
        const nm = String(t);
        const s = sp[nm] || {};
        const body = failedSet.has(nm) ? ${`<span style="color:var(--err)">${esc(nm)}</span>`} : esc(nm);
        return body + sparkBadge(s.spark_days, s.spark_state);
      }).join("、") || "—";
~~~

- ④ 执行记录详情 `panel.html:838` 的 `目标：${(m.targets||[]).join("、") || "—"}` 替换为：

~~~js
      `目标：${(m.targets||[]).map(t => { const s = (m.spark||{})[String(t)] || {}; return esc(String(t)) + sparkBadge(s.spark_days, s.spark_state); }).join("、") || "—"}` +
~~~

5. 会话卡说明文案 + 上次同步时间（spec Q1 定稿=**展示**）：`panel.html:339` 的 hint 末尾补

~~~html
<span>火花徽标：橙=今天已续，灰=今天还没续，—=无火花；数据来自最近一次「一键同步」（<span id="sparkAt">—</span>）。</span>
~~~

并在 `loadConversations()`（`panel.html:903-918`）成功回调里回填（该函数已把响应体解构为 `d`，即 `d.cache_mtime`）：

~~~js
    const at = document.getElementById("sparkAt");
    if (at) at.textContent = (d && d.cache_mtime) || "尚未同步";
~~~

### 验收

RED 159/4 → GREEN 163/0；浏览器核对四处橙/灰/`—`、会话卡显示上次同步时间，旧缓存（无火花字段）全 `—` 且不报错。

## 六、Task 4 细则（panel.html 新建定时任务目标录入改造）

### RED 断言

~~~python
check("★SPK-001 新建任务目标选择器替换手打", 'id="newJobTargets"' not in html_txt and 'id="newJobTargetsWrap"' in html_txt)
check("★SPK-001 新建任务目标来源为勾选态", "newJobTargets.length" in html_txt and '"#newJobTargets"' not in html_txt)
check("★SPK-001 接口封装支持显式账号", "opts.account" in html_txt)
check("★SPK-001 火花徽标五处接入", html_txt.count("sparkBadge(") >= 6)
~~~

RED 期望：4 条全 FAIL（前三条现码 0 命中；第四条现码计数 5 = 函数定义 1 + Task 3 的四处调用），通过 163 / 失败 4，总数 167。

### GREEN 改动点

1. HTML（`panel.html:384-385` 两行替换）：

~~~html
      <label style="margin-top:8px">目标（从该账号会话列表勾选；类型随扫描结果）</label>
      <div style="margin-bottom:6px">
        <button id="newJobPickBtn" class="btn ghost sm">加载会话列表</button>
        <button id="newJobSelAllBtn" class="btn ghost sm">全选</button>
        <button id="newJobSelInvBtn" class="btn ghost sm">反选</button>
      </div>
      <div id="newJobTargetsWrap" class="muted">点「加载会话列表」拉取该账号已同步的会话。</div>
~~~

2. JS 状态与渲染（与 `renderConvList` 并列）：

~~~js
// SPK-001：新建定时任务的目标勾选（来源=该账号会话缓存，类型只读，含火花）
let newJobCache = [];      // 该账号最近一次同步的会话
let newJobTargets = [];    // 已勾选 [{name,type}]

function renderNewJobTargets(){
  const wrap = $("#newJobTargetsWrap");
  if (!wrap) return;
  if (!newJobCache.length){
    wrap.innerHTML = '<div class="muted">该账号尚未同步会话，请到「一键触发」页切到该账号点「一键同步」。</div>';
    return;
  }
  const picked = new Set(newJobTargets.map(t => t.name));
  let html = '<div style="max-height:260px;overflow:auto;border:1px solid var(--line);border-radius:8px">';
  html += '<table><thead><tr><th style="width:46px"></th><th>会话名称</th><th style="width:96px">火花</th><th style="width:80px">类型</th></tr></thead><tbody>';
  newJobCache.forEach((c, i) => {
    const name = String(c.name || c);
    const type = c.type || "private";
    html += '<tr>' +
      '<td><input type="checkbox" class="newJobChk" data-idx="' + i + '" ' + (picked.has(name) ? "checked" : "") + '></td>' +
      '<td>' + escapeHtml(name) + '</td>' +
      '<td>' + sparkBadge(c.spark_days, c.spark_state) + '</td>' +
      '<td class="muted">' + (type === "group" ? "群聊" : "私聊") + '</td>' +
    '</tr>';
  });
  html += "</tbody></table></div>";
  html += '<div class="hint" style="margin-top:8px">共 ' + newJobCache.length + ' 个会话，已选 <b>' + newJobTargets.length + '</b> 个。</div>';
  wrap.innerHTML = html;
  wrap.querySelectorAll(".newJobChk").forEach(chk => {
    chk.onchange = () => {
      const c = newJobCache[Number(chk.dataset.idx)];
      const name = String(c.name || c);
      if (chk.checked){
        if (!newJobTargets.some(t => t.name === name))
          newJobTargets.push({name, type: c.type || "private"});
      } else {
        newJobTargets = newJobTargets.filter(t => t.name !== name);
      }
      renderNewJobTargets();
    };
  });
}

function loadNewJobConversations(){
  const account = $("#newJobAccount") ? $("#newJobAccount").value : "";
  if (!account){ toast("请先选择账号", "err"); return; }
  api("/api/conversations-cache", {account}).then(({j: d}) => {
    newJobCache = d.list || [];
    newJobTargets = [];
    renderNewJobTargets();
  }).catch(() => {});
}
~~~

3. 事件绑定（`bindJobsActions` 内，`panel.html:764 save` 之前）：

~~~js
  const pick = $("#newJobPickBtn");
  if (pick) pick.onclick = loadNewJobConversations;
  const sa = $("#newJobSelAllBtn");
  if (sa) sa.onclick = () => { newJobTargets = newJobCache.map(c => ({name: String(c.name || c), type: c.type || "private"})); renderNewJobTargets(); };
  const iv = $("#newJobSelInvBtn");
  if (iv) iv.onclick = () => { const p = new Set(newJobTargets.map(t => t.name)); newJobTargets = newJobCache.filter(c => !p.has(String(c.name || c))).map(c => ({name: String(c.name || c), type: c.type || "private"})); renderNewJobTargets(); };
  const nac = $("#newJobAccount");
  if (nac) nac.onchange = () => { newJobCache = []; newJobTargets = []; renderNewJobTargets(); };
~~~

4. 保存（`panel.html:768` 替换、`panel.html:770` 校验改）：

~~~js
    const targets = newJobTargets.map(t => ({name: t.name, type: t.type}));
    const texts = $("#newJobTexts").value.split("\n").map(x => x.trim()).filter(Boolean);
    if (!account || !time || !newJobTargets.length || !texts.length){ toast("请填完整：账号/时间/目标/文案", "err"); return; }
~~~

5. `api()`（`panel.html:443-451`）支持显式账号覆盖（D8：跨账号读选择器）：

~~~js
async function api(path, opts = {}) {
  opts = opts || {};
  const method = opts.method || "GET";
  const acct = opts.account || activeAccount;
  let url = path;
  const payload = Object.assign({}, opts.body || {});
  if (acct) {
    if (method === "GET") url += (url.includes("?") ? "&" : "?") + qs({account: acct});
    else payload.account = acct;
  }
~~~

### 验收

RED 163/4 → GREEN 167/0；浏览器核对：新建任务可切账号加载列表、勾选/全选/反选、保存后目标类型保真（群聊不落 private）、守护按时触发；`POST /api/jobs`（`panel.py:1392-1412`）与 `jobs.py` 零改动。

## 七、RED/GREEN 演进表与纪律

| Task | 动作 | FAIL | PASS | 总数 |
|---|---|---|---|---|
| 基线 | 2026-10-04 实测 | 0 | 150 | 150 |
| 1 | RED 5 条（现码 0 命中） | 5 | 150 | 155 |
| 1 | GREEN 后 | 0 | 155 | 155 |
| 2 | RED 4 条 | 4 | 155 | 159 |
| 2 | GREEN 后 | 0 | 159 | 159 |
| 3 | RED 4 条 | 4 | 159 | 163 |
| 3 | GREEN 后 | 0 | 163 | 163 |
| 4 | RED 4 条 | 4 | 163 | 167 |
| 4 | GREEN 后 | 0 | 167 | 167 |
| 5 | 文档，verify 不变 | 0 | 167 | 167 |

算术：150 + 5 + 4 + 4 + 4 = 167 ✓（17 条全为新增，无替换类断言）。

纪律：

- **断言为准绳**：GREEN 失败时对照断言逐字修实现措辞/字面形态，不许改断言迁就实现。本 plan 17 条断言全为新增，不涉及既有 check 的修订，无「替换类例外」。
- 节 9 插入点在 `verify.py:238` 节 8 之后、`verify.py:384` 汇总之前；`d`（`verify.py:118`）与 `html_txt`（`verify.py:356`）均在插入点之前定义，作用域成立。
- 同一文件多处修改逐条 patch、逐条看 lint，不并行批量发同文件 patch；改坏用 `git checkout -- <file>` 还原后重做。
- HTML 改动后先开页面点一遍主路径再提交。
- 每 Task 提交信息按二节表；代码与文档分开提交；隐私红线：任何提交文件不得出现真实账号别名/会话名/发送内容（示例一律占位）。

## 八、收尾验收（IMPLEMENT 完成后由 Tester 执行并留证据）

1. verify.py **167/0**、exit 0（真实命令输出入 `docs/superpowers/test-results/SPK-001-IMPL.md`）。
2. 只读接口 curl 抽查（不动真实账号数据）：`/api/conversations-cache?account=<别名>` 返回 `list` + `cache_mtime`；`/api/conversations` 带 `cache_mtime`；`/api/jobs` 每 job 带 `spark`；`/api/runs` 每 run 带 `spark`；`/api/runs/<id>` 的 meta 带 `spark`。
3. 浏览器人工核验清单（面板操作由用户执行并确认）：
   a. 「一键触发」页点「一键同步」→ 扫描完成后选会话表出现「火花」列，橙/灰/`—` 与抖音客户端一致；
   b. 会话卡说明文案可见；
   c. 「定时任务」页任务列表「目标」列每目标带火花徽标、长列表以省略号收尾且悬停见全文；
   d. 「执行记录」列表与详情的目标带火花徽标，未送达仍标红；
   e. 「新建定时任务」：切账号 → 点「加载会话列表」→ 勾选/全选/反选 → 保存；任务目标类型群聊保真；守护按时触发一次；
   f. 旧缓存（无火花字段）账号切过去，全部显示 `—` 且页面不报错。
4. 真实发送**零改动**：本次不新增/修改任何发送路径；核验 e 的守护触发若需真实发送，**需用户逐次授权**，未授权前留收尾待办并如实报告。

## 九、遗留与签字入口

- **Q1（已拍板 2026-10-04：展示）**：Task 3 第 5 点落地 `#sparkAt` + `loadConversations()` 回填，断言「会话卡展示上次同步时间」门禁；Task 2 第 7 点的 `cache_mtime` 不再是无人消费的死字段。
- **Q4（已拍板 2026-10-04：采本 plan 口径）**：定时任务目标列由「截断 24 字」改为「不按字符截断 + CSS 省略号 + `title` 全文」（Task 3 第 4 点 ②）。理由：火花徽标是 HTML，按字符 slice 会截断标签；且用户要求「全部列表一并显示」。需随签字一并确认。
- 本 plan 自审（`docs/superpowers/reviews/SPK-001-plan-review.md`）的 P1/P2/P3 已全部处置（见十、修订记录）；用户 (m00429) 已批准进入 IMPLEMENT，按二节表逐 Task 执行。
- 探针产物 `userdata/probe_spark/` 与脚本 `probe_spark.py` 为临时勘察物，默认不入 git；是否保留由用户决定。

---

## 十、修订记录

### 2026-10-04 自审修订（首轮评审 → 定稿）

`docs/superpowers/reviews/SPK-001-plan-review.md`（结论 CHANGES_REQUIRED）发现的问题及处置：

| 编号 | 级别 | 处置 |
|---|---|---|
| P-P1-1 | P1 | **已修**：Task 3 §五.4① 明确列序（名称 → 火花 → 类型）：表头 th 插在「会话名称」与「类型」之间，行 td 插在 `panel.html:936` 之后、`:937-944` 之前 |
| P-P2-1 | P2 | **已修**：`sparkBadge` 条件补 `|| !state`，状态未知回落 `—` |
| P-P2-2 | P2 | **已修**：`_item_spark` 删除 `elif color: state = "pending"` 兜底，只认橙色 → `done`，否则 `None` |
| P-P2-3 | P2 | **已修**：Task 3 §五.5 落地 `#sparkAt` + `loadConversations()` 回填；新增断言「会话卡展示上次同步时间」；总数 166 → 167 |
| P-P2-4 | P2 | **已定稿**：采本 plan 的 `job["spark"]` 映射形态（spec 4.4 已同步改，决策 D10） |
| P-P3-1 | P3 | **已定稿**：保留 `--spark-due` 令牌（spec R6 已同步改） |
| P-P3-2 | P3 | **已定稿**：以本 plan 的 4.6 元素与文案为准（spec 已删幽灵元素 `#newJobPickHint`、对齐 label/toast） |
| P-P3-3 | P3 | **已修**：`_item_spark` 首分支改为 `if not t: return None, None`，与 spec 4.2 语义一致 |

同轮 spec 自审的 P1（隐私红线）已在 spec 侧修复；plan 侧隐私扫描本就 0 命中。

### 2026-10-04 实施期偏差记录（RED 合并为一次提交）

- **偏差**：原 §七 设计为「每 Task 各自加 RED 断言 → 各自提交」。实施时改为**一次性写入全部 17 条断言**（`verify.py` 新增节 9）并单独提交 RED，四个 Task 只做 GREEN。
- **理由**：断言全部落在 `verify.py` 同一文件，若由四个并行子代理各自追加会互相冲突；且 17 条均为纯新增 token 断言，RED 的「先红后绿」诚实性不受影响。
- **后果**：中间态不再逐 Task 归零——T1 后 155/12、T2 后 159/8、T3 后 163/4、T4 后 167/0（总数均为 167）。**最终验收标准不变：167/0、exit 0。**
- **实测 RED**：`通过 150 / 失败 17`，exit 1（2026-10-04）。

