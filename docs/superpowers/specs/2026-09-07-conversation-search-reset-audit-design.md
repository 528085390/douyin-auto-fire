# 会话查找全量扫描 + 失败目标执行记录审计 — 设计文档（spec）

- 日期：2026-09-07
- Task-ID：SIV-002
- 状态：已批准（2026-09-07 Reviewer APPROVED，`reviews/SIV-002-spec-review.md`；按 `.hermes.md` spec 免签，生效即批准）
- 决策来源：2026-09-07 用户报告执行 `20260907_213940`（<别名2> 账号）7 目标中 1 个失败、
  且执行记录看不到具体是哪个失败；要求排查原因并将失败私聊对象写入执行记录审计。
  Lead 取证（run 日志 + audit no_match JSON + 对比前一轮 `20260907_112242` + 读码）
  定位根因；用户纠正「先出 spec 文档」后本文件成文。
- 评审拍板记录：2026-09-07 Reviewer APPROVED（P0/P1 无漏网，P2×3 不阻塞，见 `reviews/SIV-002-spec-review.md`）

---

## 一、背景与问题

### 1.1 事故链路（2026-09-07 21:39 真实运行取证）

执行 `userdata/accounts/<别名2>/runs/20260907_213940`（meta：status=partial，failed=1，7 目标）：

```
21:39:46 【1/7】<会话7>         → 查找 5s → sent 截图（成功）
21:40:38 【2/7】<会话4>   → 查找 ~7s → sent_soft 截图（成功）
21:41:24 【3/7】<会话8>   → 查找 ~18s → sent 截图（成功）
21:42:57 【4/7】<会话9>          → 查找 ~5s → sent_soft 截图（成功）
21:44:02 【5/7】<会话10>           → 查找 ~6s → sent_soft 截图（成功）
21:45:36 【6/7】<会话11>            → 查找 ~51s → sent 截图（成功）
21:47:08 【7/7】<会话12>        → 查找 8s → [审计-no_match] 未找到私聊「<会话12>」
21:47:23 本次有 1 个目标未成功发送
```

run JSON 只记录 `failed: 1, total: 7` 与一段笼统错误文案，
**没有记录具体哪个目标失败**——用户无法在执行记录里直接看到失败对象。

### 1.2 根因：单向向下滚动 + 跨目标滚动位置残留 → 目标在上方时永远扫不到

审计 JSON（`audit_no_match_214723.json`，本次运行产物）给出决定性证据：

1. **URL 正确**：`https://www.douyin.com/chat`，页面就绪，不是导航失败；
2. **查找结束时可见区是列表底部（旧会话区）**：probe.items 全是 1~5 月的旧会话
   （珍哥物理、小羊羔、涂只、薇拉摄影新疆店、太和（粉丝解析）…共 15 项），
   本轮的 7 个目标**一个都不在可见区**；`listItems` 时间戳从 05/10 一路排到 01/29——
   这是列表最旧的会话区，说明滚动位置在列表深处；
3. **整页无目标名文本**：`page.nameHits = []`，`<会话12>` 不在页面任何可见节点上
   （不是「渲染了但没匹配上」，是查找过程根本没扫到它）；
4. **时间对比指向滚动残留**：目标 6（<会话11>）查找耗时约 51 秒（向下滚到深处才命中），
   目标 7 仅 8 秒就触发「连续 3 屏无新 index」判定到底——从目标 6 遗留的深处位置
   继续向下滚，很快到底，上方的 `<会话12>` 从未被扫到。

代码层面三个事实叠加成该缺陷：

| # | 事实 | 位置 |
|---|---|---|
| C1 | `_find_conversation_item` **只单向向下滚动**（`scrollBy(0, clientHeight*0.8)`），从不向上滚 | douyin.py:440-465 |
| C2 | 跨目标**滚动位置不重置**：同一 page 的列表 DOM 跨目标复用，上一目标查找遗留的 scrollTop 被下一个目标继承（抖音前端会恢复/保留列表滚动状态，1.2 证据 2） | douyin.py:440-465 + `_open_conversation` 调用链 |
| C3 | 虚拟列表**排序随消息刷新**：每个目标发送成功后该会话时间戳更新、浮到列表顶部；后续目标查找从残留的深处位置向下滚，够不到上方的目标 | douyin.py:931-961 发送循环 + 抖音列表排序行为 |

结论：**「部分失败」不是目标不存在，是查找算法漏扫**。`<会话12>` 真实存在
（上午 `20260907_112242` 同一列表曾把它滚到并点击——虽然当时因 SIV-001 的
视口问题变成 switch_fail，但证明它在列表中）。SIV-001 修复后，底部条目
可正常点击；本次暴露的是**查找阶段的同类缺陷的另一面：漏扫上半区**。

### 1.3 次生问题：执行记录不可审计失败对象

run JSON（meta）只写 `failed` 计数和通用文案，面板执行记录列表/详情页
都看不到「到底是哪个目标没发出去」。排查要靠翻日志 grep 目标名，
用户原话「执行记录里看不到是哪个私聊失败」。

---

## 二、勘察结论（证据表）

| 编号 | 结论 | 证据 |
|---|---|---|
| E1 | 失败目标为第 7 个目标 `<会话12>`，查找仅 8 秒即判 no_match | run 日志 21:47:15→21:47:23 |
| E2 | 失败时页面 URL 正确（/chat 就绪），不是导航/登录问题 | audit_no_match_214723.json `page.url` |
| E3 | 查找结束时可见区为列表底部旧会话（时间戳 01/29~05/10），本轮 7 目标均不在可见区 | 同上 `probe.items` / `page.listItems` |
| E4 | 整页无目标名文本（nameHits=[]），是漏扫而非渲染/匹配失败 | 同上 `page.nameHits` |
| E5 | 对照上午轮 `20260907_112242`：`<会话12>` 曾在列表可见区（最后一项）被找到并点击 → switch_fail（SIV-001 修复前的视口问题），证明目标真实存在于列表 | 该轮 audit_switch_fail 日志列表项 |
| E6 | `_find_conversation_item` 仅 `scrollBy` 正向滚动，无向上扫描、无起始位置重置 | douyin.py:440-465 |
| E7 | 目标 6 查找约 51s（深处命中）vs 目标 7 仅 8s（快速到底）→ 滚动位置被继承 | run 日志时间戳对比 |
| E8 | run meta 只含 failed/total 计数与通用错误文案，无失败目标名单 | runs/20260907_213940.json |
| E9 | 面板执行记录列表页只渲染 targets 全名、详情页只渲染 error 文案，无失败项标记 | panel.html:698-724 |
| E10 | verify.py 基线：94 通过 / 2 失败（既有环境态：账号任务未在面板注册，与本任务无关） | 2026-09-07 实测 verify.py exit 1 |

---

## 三、目标与非目标

### 目标

1. **查找前重置列表滚动位置**：`_find_conversation_item` 每次查找先把会话列表
   滚回顶部（`scrollTop = 0` + 等待虚拟列表重渲染），再做既有的全量向下扫描。
   保证每次查找覆盖整份列表，杜绝「目标在残留位置上方 → 漏扫 → 误判 no_match」。
2. **失败目标写入执行记录审计（数据层）**：douyin.py 记录 `failed_targets` 名单
   （每次运行重置；no_match / switch_fail / send_fail / type_fail 等所有失败路径统一记录，
   按目标名去重）；panel.py worker 写入 run meta JSON 新增 `failed_targets` 字段，
   run 级错误文案带出失败名单（执行记录详情页直接可见）。
3. **面板展示失败目标（UI 层）**：执行记录列表页目标列中失败目标标红；
   详情页错误行显示失败名单（或单独渲染「未送达」行），不再只有笼统计数。
4. `verify.py` 新增防回归断言（先 RED 后 GREEN），锁：滚动位置重置实现、
   failed_targets 记录/写入/展示链路。
5. 同步 `docs/工作原理与架构.md`（会话匹配节 + 执行记录字段说明）。

### 非目标（本次不做）

- 不做「双向滚动 / 智能定位 / 搜索框辅助」等增强：本次最小修复 = 每次查找重置到顶部
  再全量向下扫（单列表规模下足够；40 屏上限不变）。
- 不改 SIV-001 已交付的视口保障（`_ensure_item_in_view`、`_human_click` 视口守卫、
  重试点击一次）与 `switch_fail` 语义。
- 不改发送链路（_send_text / type_fail / send_fail）、风控检测、扫描、runner、定时任务。
- 不新增审计 tag：`no_match` 语义不变（只是触发频次下降）。
- 不处理 `error.log`（gitignored 外残留文件，与本次无关）与既有基线 2 FAIL（账号任务注册属面板操作）。

---

## 四、方案设计

### 4.1 滚动位置重置（核心修复，douyin.py `_find_conversation_item`）

```python
def _find_conversation_item(self, name: str, max_scroll: int = 40):
    """（原 docstring 保留）"""
    # ★ SIV-002：抖音会保留上一次会话查找遗留的滚动位置，而虚拟列表排序随
    # 消息刷新（发过的会话浮到顶部）。不重置就从深处向下滚，目标在当前位置
    # 上方时永远扫不到 → 误判 no_match。每次查找先滚回顶部再做全量向下扫描。
    wrap = self.page.query_selector(self.LIST_SEL)
    if wrap:
        wrap.evaluate("el => { el.scrollTop = 0; }")
        time.sleep(random.uniform(0.5, 0.9))  # 等虚拟列表重新渲染顶部条目
    # …（原有 seen_idx / stagnant / 向下滚动循环原样保留）
```

要点：

- 用 `scrollTop = 0` 直接重置（`scrollBy` 相对偏移无法回顶部；滚动容器就是
  `LIST_SEL`，原代码已在用它 scrollBy，语义一致）；
- 重置后等待 0.5~0.9s 让虚拟列表重渲染顶部条目（否则首轮检查的还是旧条目，
  又会继续向下滚回深处）；
- 原有「先检查当前渲染项 → 记 data-index → 判断 stagnant → 向下滚」循环不改；
- 幂等：目标在顶部时首轮即命中，开销只多一次重置+等待（每目标约 1s）。

### 4.2 失败目标名单（douyin.py 数据层）

- `__init__` 新增：`self.failed_targets: list[str] = []`（与 failed_count 并列）；
- `run()` 每次运行开始重置：`self.failed_targets = []`；
- 失败分支（`except Exception` 处）追加：`name not in self.failed_targets` 时
  append（按目标名去重；同一目标循环内只会失败一次，去重是防御）；
- `RiskUnsolved`（风控中止）分支不记入 failed_targets——整轮停止、未逐个失败，
  保持现状语义（needs_verify）。

### 4.3 写入执行记录（panel.py `_worker`）

在 `meta["failed"] = failed_n` 附近新增：

```python
failed_names = list(getattr(streak, "failed_targets", None) or [])
if failed_names:
    meta["failed_targets"] = failed_names
```

run 级错误文案改为带名单（仅当有名单时附加，无名单走原文案兜底）：

```python
suffix = f"失败目标：{'、'.join(failed_names)}。" if failed_names else "多为未匹配到会话。"
meta["error"] = meta.get("error") or (
    f"共 {total_n} 个目标，其中 {failed_n} 个未成功发送（{suffix}"
    "请检查会话名是否与抖音列表完全一致，或在弹出的浏览器中手动点击该会话。"
)
```

（文案措辞在 plan/实现时按仓库「token 锁定」惯例落成 verify.py 可锁定的形态。）

### 4.4 面板展示（panel.html）

- 执行记录**列表页**（loadRuns）：目标列渲染时，`failed_targets` 中的名字包
  `<span style="color:var(--err)">…</span>` 标红；
- **详情页**（showDetail）：错误行已有 `m.error`（此时含失败名单）；
  若 `m.failed_targets` 存在再单列一行「未送达：…」标红（与 error 文案互为冗余，
  视觉更直接）。

### 4.5 `verify.py` 防回归断言（先 RED 后 GREEN）

在 5b 节 SIV-001 断言块后新增：

```python
# ★ SIV-002 会话查找全量扫描 + 失败目标审计（2026-09-07 spec）：
# 单向向下滚动 + 跨目标滚动位置残留 → 目标在上方时漏扫误判 no_match；
# 每次查找先重置列表到顶部。失败目标名单写入 run meta，面板标红展示。
check("★查找会话前重置列表滚动位置（scrollTop=0）", "scrollTop = 0" in d)
check("★重置后等待虚拟列表重渲染", "scrollTop = 0" in d and "time.sleep(random.uniform" in d)
check("★记录失败目标名单 failed_targets", "self.failed_targets" in d
      and "failed_targets.append(name)" in d)
check("★run 每次重置 failed_targets", "self.failed_targets = []" in d)
check("★panel 写入 meta.failed_targets", "meta[\"failed_targets\"]" in p)
check("★面板列表页标红失败目标", "failed_targets" in read("panel.html"))
```

断言语义自查：`"scrollTop = 0"` 为唯一实现 token；`meta["failed_targets"]` 锁
panel.py 写入；panel.html 锁前端消费。基线（E10）：RED 期望 = 既有 2 + 新增 6 = 8 FAIL；
GREEN 期望 = 仅剩既有 2 FAIL。

### 4.6 文档同步清单

| 文件:位置 | 现状 | 改为 |
|---|---|---|
| `docs/工作原理与架构.md` 会话匹配节 | 写「边滚边找，3 屏无新 index 到底」 | 追加：查找前先重置列表滚动位置到顶部，再全量向下扫（SIV-002）；原因=滚动位置跨目标残留 + 排序随消息刷新 |
| `docs/工作原理与架构.md` 执行记录节 | 未提 failed_targets | 补充 run meta 新增 `failed_targets` 字段，面板列表页标红、详情页显示名单 |

---

## 五、错误处理

| 场景 | 行为 |
|---|---|
| 列表容器选择器找不到（wrap=None） | 跳过重置，走原逻辑（现状兜底；正常页面不会发生） |
| scrollTop=0 后虚拟列表未即时重渲染 | 0.5~0.9s 等待；首轮检查仍可能扫到旧条目，但后续向下滚动会覆盖全列表（与现状一致） |
| 目标真实不在列表 | `no_match`（语义不变，触发频次随漏扫修复下降） |
| 目标在列表底部（需滚动） | 重置到顶部 → 全量向下扫 → 命中 → SIV-001 视口保障点击（已交付） |
| 同一目标因故多次失败 | failed_targets 按名去重，只记一次 |
| 风控中止（RiskUnsolved / needs_verify） | 不记入 failed_targets（整轮停止语义，保持现状） |
| 旧版 run JSON 无 failed_targets 字段 | 前端 `|| []` 兜底；error 文案无名单时走原文案 |

---

## 六、验证方案

项目无测试框架，沿用「verify.py 自检 + 可选 live 冒烟」双轨（仓库先例）。

1. **RED**：按 4.5 新增 verify.py 断言 → 跑 verify → 确认 FAIL 恰为 既有 2 + 新增 6 = 8，
   且新增失败原因均为「保证未实现」。
2. **GREEN**：按 4.1-4.4 实现 → 跑 verify → 新增 6 条全过、仅剩既有 2 FAIL（E10）。
3. **文档**：按 4.6 同步后再跑 verify（文档不锁断言）。
4. **live 冒烟（待授权，见八-1）**：对含列表底部目标的真实会话组发送一次——验证
   「重置滚动 → 全量扫描 → 底部目标命中」全链路；同时核对执行记录 JSON 出现
   `failed_targets`、面板列表页失败项标红、详情页显示名单。
5. **未授权冒烟时的收尾核对**：下一次真实运行后人工核对执行记录：
   是否还有 no_match；若有，失败目标是否在执行记录中可见。

**无法自动化的部分（如实声明）**：verify.py 只能锁代码结构（token/字段/调用形态），
不能锁「滚动重置后真的扫到上半区目标」这一运行时行为；由 live 冒烟或下次真实运行核对弥补。

---

## 七、风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | scrollTop=0 触发虚拟列表重渲染异常/抛错 | evaluate 抛错会让整个查找失败 → 包 try/except 吞掉走原逻辑（现状兜底，见五） |
| R2 | 重置后等待不足，首轮仍读旧条目并向下滚 | 0.5~0.9s 等待 + 向下滚动覆盖全列表，最坏情况与现状一致（不会更差） |
| R3 | 列表项多时 40 屏上限不够（目标极深） | 现状语义：扫不到即 no_match；SIV-001 后底部命中已修复，深列表属既有边界 |
| R4 | failed_targets 与 failed_count 不一致（漏记/多记） | 单一失败分支统一 append；panel 以 failed_targets 名单渲染、failed 计数兜底，两者同源 |
| R5 | 错误文案带名单后文案变化触发既有/新增断言冲突 | 文案在实现时落成独立 token，verify 断言同步锁（仓库惯例） |
| R6 | 滚动重置增加被风控识别的概率 | 每目标多一次 scrollTop 置零（JS 直接设属性，比 scrollBy 更轻）；目标间 15~45s 随机间隔不变 |

---

## 八、待确认

1. **live 冒烟授权**：实现全绿后，是否对一个含列表底部目标的真实目标组发一条无害文本
   验证全链路？（按仓库纪律必须用户明确点头才执行。）
2. **既有基线 2 FAIL**：两个账号任务（`DouyinAutoFire-<别名>` ×2）尚未在面板注册
   （MAI-001 遗留核对项），是 verify 全绿的前提；是否由用户顺手在面板完成注册？

---

## 九、实施顺序（供 plan 参考）

1. `verify.py` 先 RED：新增 4.5 断言块 → 跑红确认（8 FAIL = 既有 2 + 新增 6）
2. `douyin.py` 实现：4.1 滚动重置 → 4.2 failed_targets 记录
3. `panel.py` 实现：4.3 meta.failed_targets + 错误文案带名单
4. `panel.html` 实现：4.4 列表页标红 + 详情页未送达行
5. `verify.py` 转 GREEN（仅剩既有 2 FAIL）
6. 文档同步（4.6）
7. （可选，待授权）live 冒烟；未授权则按验证方案第 5 条收尾核对
