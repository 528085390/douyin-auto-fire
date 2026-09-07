# 会话项视口外点击落空修复（滚入视口 + 视口外拒点 + 切换重试）— 设计文档（spec）

- 日期：2026-09-07
- Task-ID：SIV-001
- 状态：已批准（2026-09-07 Reviewer APPROVED，`reviews/SIV-001-spec-review.md`；按 `.hermes.md` spec 免签，生效即批准）
- 决策来源：2026-09-07 用户报告执行 `20260907_112242` 中 7 目标有 2 个失败，
  且失败目标在抖音会话列表中真实存在（用户手机截图佐证）；Lead 取证
  （run 日志 + audit JSON + 审计截图 + 读码）定位根因为「虚拟列表缓冲区条目在视口外，
  拟人裸鼠标点击落空」；用户指示按 superpowers 流程出 spec → plan。
- 评审拍板记录：（待评审后补充）

---

## 一、背景与问题

### 1.1 事故链路（2026-09-07 11:22 真实运行取证）

执行 `userdata/accounts/<别名>/runs/20260907_112242`（meta：status=partial，failed=2，2/7 目标；
失败目标为列表底部的两个私聊，下文以 `<目标A>`/`<目标B>` 指代，真实名只存在于 gitignored 的
userdata 证据文件中）：

```
11:22:48 【1/7】<顶部目标>   → sent 截图（成功）
11:23:14 【2/7】<顶部目标>   → sent_soft 截图（成功）
...      【3~5/7】均为列表顶部目标 → 全部成功
11:29:26 【6/7】正在查找私聊「<目标A>」
11:30:00 [审计-switch_fail] 目标=<目标A> | 右侧当前=None | 编辑器=False | 编辑器文本长度=0
11:30:01 [ERROR] 已点击私聊「<目标A>」但右侧未切换到该会话，跳过以免发错人。
11:30:08 【7/7】正在查找私聊「<目标B>」
11:30:39 [审计-switch_fail] 目标=<目标B> | 右侧当前=None | 编辑器=False
11:30:39 [ERROR] 已点击私聊「<目标B>」但右侧未切换到该会话，跳过以免发错人。
```

用户手机抖音截图证实：这两个会话**真实存在**于消息列表中（排底部，07/15 有过往来消息）。
即：不是「列表里没有这个人」（no_match 语义），代码也自认「点到了」，但点击实际没有生效。

### 1.2 根因：虚拟列表缓冲区条目在视口外，裸鼠标点击落空

审计 JSON（`audit_switch_fail_*.json`，本次运行产物）给出决定性证据：

1. **目标条目的 DOM 坐标在视口外**：页面 viewport 为 1280×900（douyin.py:150 固定），
   而两个失败目标的标题元素 `rect.y ≈ 1010`——在可视区底边之下约 110px；
2. **点击后右侧什么都没有打开**：probe 显示 `active=null`、`editor=false`、全部列表项
   `current=false`——不是「切到了别的会话」，而是点击根本没命中任何会话；
3. **审计截图**（`006/007_*_audit_switch_fail.png`）目视证实：左侧可视区最底部是其他会话，
   目标条目未露出；右侧是空占位图（无消息、无输入框）；
4. **对照组**：同轮前 5 个目标全在列表顶部（页面加载后天然在可视区内），全部成功；
   前一天执行 `20260907_111940`（2 个顶部目标）也全部成功。失败与「目标在列表底部」完全相关。

代码层面三个事实叠加成该缺陷：

| # | 事实 | 位置 |
|---|---|---|
| C1 | `_find_conversation_item` 边滚边找，**条目一出现在 DOM 就立即返回**。抖音会话列表是虚拟列表，可视区外还渲染一段缓冲条目——缓冲区条目「DOM 在、屏幕外」，同样算命中 | douyin.py:421-446 |
| C2 | `_human_click` 用 `bounding_box()` 坐标 + 裸 `mouse.move/down/up` 拟人点击。**裸鼠标事件不会自动滚动页面**（与 `ElementHandle.click()` 不同，后者会自动滚入视口）；且 `bounding_box()` 对视口外元素照样返回坐标，连「元素不可见」分支都不会触发 | douyin.py:282-295 |
| C3 | 点击落空后 `_conversation_is_open` 双信号校验失败 → 审计 `switch_fail` → 抛错跳过（保守正确，没有发错人），但**没有任何机制先把条目滚进视口再点** | douyin.py:629-640 |

结论：**校验链路工作正常（宁可跳过不发错人），缺的是点击前的「可见性保障」**。
凡是排在列表底部（需要滚动才能看到）的会话，当前实现必然点击落空、必然 switch_fail。
随着目标数增多/会话列表变长，该缺陷命中率只会上升。

### 1.3 次生问题：报错文案误导排查方向

panel.py:448 的 run 级错误文案「多为未匹配到会话。请检查会话名是否与抖音列表完全一致」
把用户引向「改名」方向，而本次真因是视口外点击落空——用户第一反应正是
「列表有这两个人啊？？」。文案属 P2（不阻塞本修复，见非目标）。

---

## 二、勘察结论（证据表）

| 编号 | 结论 | 证据 |
|---|---|---|
| E1 | 失败目标标题元素 rect.y≈1010 > viewport 高 900，点击坐标在屏幕外 | audit_switch_fail_113001/113039.json `page.nameHits[].rect` + douyin.py:150 |
| E2 | 点击后右侧未打开任何会话（非切错、非风控弹层） | 同上 JSON `probe.active=null, editor=false, 全部 current=false` |
| E3 | 审计截图目视：目标条目未露出可视区，右侧空占位 | 006_113000 / 007_113039 audit_switch_fail.png |
| E4 | 同轮顶部 5 目标全部成功；失败与「列表底部」完全相关 | run 日志 + 截图 001~005 |
| E5 | `_find_conversation_item` DOM 命中即返回，不管条目是否在视口内 | douyin.py:430-432 |
| E6 | `_human_click` 裸鼠标事件 + bounding_box 视口外仍返回坐标 → 静默落空 | douyin.py:282-295 |
| E7 | Playwright 语义：`ElementHandle.click()` 自动滚动到元素，`page.mouse.*` 不会（本机实测 `scroll_into_view_if_needed` / `viewport_size` API 均可用） | Playwright 官方行为 + 本机 .venv 实测 hasattr 通过 |
| E8 | 会话名可能同时出现在其他条目的消息预览文本里（如群聊预览「<目标B>：@…」），但匹配只读 `.conversationConversationItemtitle` 标题节点，不会误配——预览命中不是本次根因 | audit JSON nameHits 多条命中 + douyin.py:410-413 |
| E9 | verify.py 基线：94 通过 / 2 失败（既有环境态：两个账号任务未在面板注册，与本任务无关） | 2026-09-07 实测 `./.venv/Scripts/python.exe verify.py` exit 1 |

---

## 三、目标与非目标

### 目标

1. **点击会话项前保证条目完整落在视口内**：新增 `_ensure_item_in_view`——边界框不在视口内
   则 `scroll_into_view_if_needed` → 等待渲染 → **按标题重定位新句柄**（虚拟列表滚动会回收/
   重建节点，旧 ElementHandle 可能 detached）→ 复验，循环至多 3 次；仍不可见则抛错，
   由调用方审计 `switch_fail` 并跳过（保持「宁可跳过不发错人」）。
2. **`_human_click` 增加视口守卫（第二道防线，修类不修点）**：目标坐标整体在视口外时
   直接抛错拒点，把「静默落空」变成「大声失败」——保护所有裸鼠标点击路径（会话项/编辑器/
   发送按钮），不止本次事故点。
3. **点击后未切换自动重试点击一次**（与 type_fail「自动重试一次」同风格的用户既有决策延伸）：
   重定位条目 → 再保障可见 → 再点 → 再校验；仍失败才审计 `switch_fail` + 抛错。
   重试无任何发送副作用（切换校验通过前不碰输入框）。
4. `verify.py` 新增 5 条防回归断言（先 RED 后 GREEN），锁方法存在/调用形态/关键 API/重试文案。
5. 同步 `docs/工作原理与架构.md` 第五节（会话匹配）与第七节（审计说明）。

### 非目标（本次不做）

- 不新增审计 tag：`switch_fail` 语义不变（「点了但没切过去」），「无法滚入可视区」是它的
  子情形，审计件里 probe/nameHits 足以区分；不发明 `offscreen` 之类新 tag。
- 不改 panel.py:448 run 级错误文案（「多为未匹配到会话」误导，P2 文案优化另行排期）。
- 不改 `_find_conversation_item` 的滚动查找算法本身（stagnant 判定、max_scroll）。
- 不改风控检测、发送链路（_send_text/type_fail/send_fail）、扫描、面板 UI、runner、定时任务。
- 不处理既有基线 2 FAIL（账号任务注册是面板操作，属 MAI-001 遗留核对项，非代码缺陷）。

---

## 四、方案设计

### 4.1 新方法 `_ensure_item_in_view(item, name)`（核心修复）

```python
def _ensure_item_in_view(self, item, name: str, max_tries: int = 3):
    """滚动会话项进入视口并返回可点击的新句柄。

    虚拟列表在可视区外还渲染缓冲条目：DOM 在、bounding_box 有坐标，
    但裸鼠标事件不会自动滚动页面，点在视口外等于点空（SIV-001 事故根因）。
    """
    for _ in range(max_tries):
        box = 安全取 item.bounding_box()          # handle 可能已被回收 → 视为 None
        if self._in_viewport(box):
            return item
        item.scroll_into_view_if_needed(timeout=3000)   # 失败/节点脱离则吞掉，走重定位
        随机等待 0.4~0.8s
        fresh = self._find_rendered_item(name)     # 按标题重定位（不滚动）
        if fresh is None: break
        item = fresh
    最终复验一次 _in_viewport → 通过则返回 item
    raise RuntimeError(f"会话项「{name}」无法滚动进可视区，无法可靠点击。")
```

配套两个小方法：

- `_find_rendered_item(name)`：在**当前已渲染** DOM 里按标题精确等值找条目（不滚动）——
  与 `_find_conversation_item`（边滚边找）分工：滚动后旧句柄可能 detached，用它拿新句柄。
- `_in_viewport(box)`：边界框完整落在 `page.viewport_size` 内（x/y ≥ 0 且右/下边 ≤ 视口宽/高）。

`_open_conversation` 中调用点：`_find_conversation_item` 命中后、`_human_click` 前：

```python
try:
    item = self._ensure_item_in_view(item, name)
except Exception:
    self._audit_dump("switch_fail", name)   # 滚不进去也留审计证据
    raise
```

### 4.2 `_human_click` 视口守卫（第二道防线）

```python
box = handle.bounding_box()
if not box:
    raise RuntimeError(f"元素不可见，无法点击: {label}")
vp = self.page.viewport_size or {"width": 0, "height": 0}
if 目标框整体在视口外（上/下/左/右任一方向完全出界）:
    raise RuntimeError(f"元素在视口外，无法点击: {label}（box=…, viewport=…）")
```

理由：`bounding_box()` 对视口外元素照常返回坐标（E6），现状下「坐标在屏幕外」与
「坐标在屏幕内」走完全相同的点击路径，落空是静默的。守卫把它变成显式失败；
编辑器/发送按钮天然在视口内，不受影响（误拒也只发生在本就会点空的场景）。

### 4.3 切换失败自动重试点击一次（`_open_conversation`）

现状：点击 → 等编辑器（15s 超时兜底）→ `_conversation_is_open` 失败 → 立即审计抛错。
改为：

```
点击 → 等待 → 校验
  ├─ 通过 → 继续（现状不变）
  └─ 不通过 → logger.warning(…「重试点击一次」…) → 短暂等待
        → item2 = _find_rendered_item(name) or _find_conversation_item(name)
        → _ensure_item_in_view(item2) → 再点击 → 再等待 → 再校验
        ├─ 通过 → 继续
        └─ 仍不通过 → _audit_dump("switch_fail") → raise（现状文案不变）
```

要点：

- 重试发生在**任何发送动作之前**（切换校验不过就不会碰输入框），无消息副作用；
  对同一会话重复点击幂等。
- 重试路径吞掉自身异常（重定位失败/滚不进去/拒点），统一走最终 `switch_fail` 审计，
  避免出现第二种失败语义。
- 日志文案用相邻字面量拆分让 `"重试点击一次"` 独立成 token（verify.py 断言语义，
  仓库既有技巧；不得与 type_fail 的 `"自动重试一次"` token 混用，两条断言各自锁定）。

### 4.4 `verify.py` 防回归断言（先 RED 后 GREEN）

在 5b 节（/chat 链路断言）`sent_soft` 检查之后新增块：

```python
# ★ SIV-001 会话项可见性（2026-09-07 spec）：虚拟列表缓冲区条目 DOM 在但坐标在视口外，
# 裸鼠标点击落空 → switch_fail。点击前必须滚入视口并重定位句柄；视口外坐标拒点；
# 切换失败自动重试点击一次。
check("★_ensure_item_in_view 存在且被调用（点击前滚入视口）",
      "_ensure_item_in_view" in dfuncs and "self._ensure_item_in_view(" in d)
check("★滚动使用 scroll_into_view_if_needed", "scroll_into_view_if_needed" in d)
check("★视口判定使用 viewport_size", "viewport_size" in d)
check("★会话未切换会自动重试点击一次", '"重试点击一次"' in d)
check("★_human_click 拒绝视口外点击", '"元素在视口外' in d)
```

断言语义自查（skill 坑表）：`'"重试点击一次"'` 要求该短语**独立成 token**（相邻字面量拆分
实现）；`'"元素在视口外'` 用前引号形态（f-string 消息以该短语开头，尾随 `，无法点击…`
不相邻后引号）；`viewport_size` / `scroll_into_view_if_needed` 为裸子串（API 名唯一，无歧义）。
基线注意（E9）：当前 verify 已有 2 个既有 FAIL（账号任务未注册，环境态），
RED 期望 = 既有 2 + 新增 5 = 7 FAIL；GREEN 期望 = 仅剩既有 2 FAIL、新增 5 全过。

### 4.5 文档同步清单

| 文件:位置 | 现状 | 改为 |
|---|---|---|
| `docs/工作原理与架构.md` 五节「会话项枚举与匹配」（:96 后） | 只写「边滚边找，3 屏无新 index 到底」 | 追加一条：点击前 `_ensure_item_in_view` 滚入视口 + 重定位句柄；`_human_click` 视口外拒点；未切换自动重试点击一次，仍失败才 `switch_fail`（SIV-001） |
| `docs/工作原理与架构.md` 七节审计 tag 说明（:126） | `switch_fail`=点到了但没切过去 | 括注补充：含「条目无法滚入可视区」与「重试点击后仍未切换」两种子情形 |

---

## 五、错误处理

| 场景 | 行为 |
|---|---|
| 条目在 DOM 但边界框在视口外（本次事故） | `_ensure_item_in_view` 滚入视口 + 重定位句柄 → 正常点击（预期直接修复） |
| 滚动后句柄 detached / 条目被回收 | `_find_rendered_item` 按标题重定位新句柄，循环至多 3 次 |
| 3 次后仍无法滚入视口 | 抛错 → `_open_conversation` 捕获 → 审计 `switch_fail` → failed_count+1 → 下一目标 |
| 点击后未切换（第一次） | warning「重试点击一次」→ 重定位 + 保障可见 + 再点 + 再校验 |
| 重试后仍未切换 | 审计 `switch_fail` + 抛错（现状文案不变）→ failed_count+1 → 下一目标 |
| 重试路径自身异常（找不到/滚不进/拒点） | 吞掉，统一走最终 `switch_fail` 审计（单一失败语义） |
| 任何裸鼠标点击目标坐标整体在视口外 | `_human_click` 直接抛「元素在视口外，无法点击」（大声失败，不静默落空） |
| 列表里确实没有该名字 | `no_match`（现状不变，与本修复无关） |
| 风控 | 现状不变：`_check_risk_stop` / `needs_verify`，整轮停止 |

---

## 六、验证方案

项目无测试框架，沿用「verify.py 自检 + 可选 live 冒烟」双轨（仓库先例）。

1. **RED**：按 4.4 新增 verify.py 断言 → 跑 verify → 确认 FAIL 恰为 既有 2 + 新增 5 = 7，
   且新增失败原因是「保证未实现」而非笔误。
2. **GREEN**：按 4.1-4.3 实现 douyin.py → 跑 verify → 新增 5 条全过、仅剩既有 2 FAIL（E9）。
3. **文档**：按 4.5 同步后再跑 verify（文档不锁断言，防漂移靠体检）。
4. **live 冒烟（待授权，见八-1）**：对**列表底部**的真实会话发送一次——这是唯一能证明
   「滚入视口→点击→切换成功」全链路的手段（离线无法复现抖音虚拟列表 DOM）。
   观察点：日志不再出现底部目标的 switch_fail；出现 sent/sent_soft 截图；
   若出现「重试点击一次」warning 属兜底生效，需记录频次。
5. **未授权冒烟时的收尾核对**：下一次真实运行（面板手动触发或定时任务）后，人工核对
   执行记录：底部目标是否成功、有无非预期 switch_fail。

**无法自动化的部分（如实声明）**：verify.py 只能锁代码结构（方法/调用/API/文案 token），
不能锁「滚动后真的点中了」这一运行时行为；该局限由 live 冒烟或下次真实运行核对弥补。

---

## 七、风险

| # | 风险 | 缓解 |
|---|---|---|
| R1 | `scroll_into_view_if_needed` 触发虚拟列表再渲染/回收，重定位又拿到视口外新句柄（循环拉锯） | max_tries=3 上限 + 每轮复验边界框；拉锯失败走大声审计，不会静默漏发/发错 |
| R2 | 点击会话后列表按最近会话重排，重试路径按「位置」找条目会错位 | 重试一律**按标题**重定位（`_find_rendered_item`/`_find_conversation_item`），不依赖位置；找不到再回退滚动查找 |
| R3 | `_human_click` 视口守卫误拒正常元素（如窗口异常、元素部分出界） | 守卫只拒「整体出界」（部分可见仍可点，与现状一致）；viewport 由代码固定 1280×900（douyin.py:150），编辑器/按钮布局稳定；误拒=大声失败，劣化不超过现状的静默落空 |
| R4 | 重试点击把「本会成功的慢切换」变成双击 | 双击同一会话幂等（打开动作无副作用）；重试前有 0.5~1s 等待 + 首次点击后已有最长 15s 编辑器等待，慢切换大概率已被首轮校验捕获 |
| R5 | verify 断言绑字面形态，未来重构误伤 | 遵循仓库惯例：锁方法存在/调用形态/API 名/独立 token，不锁行号与方法体；文案改动须同步断言（token 注释标明） |
| R6 | 滚动动作增加被风控识别为机器行为的概率 | 滚动本就是 `_find_conversation_item` 既有动作（每次查找都在滚），本次只多「滚入视口」一次短滚动 + 失败路径一次重试；目标间 15~45s 随机间隔不变 |

---

## 八、待确认

1. **live 冒烟授权**：实现全绿后，是否对一个**列表底部**的真实会话发一条无害文本验证？
   （建议就用本次失败的其中一个目标 + 「冒烟测试」类短句；按仓库纪律必须用户明确点头才执行。）
2. **既有基线 2 FAIL**：两个账号任务（`DouyinAutoFire-<别名>` ×2）尚未在面板注册（MAI-001 遗留核对项）。
   与本任务无关，但它是 verify 全绿（0 FAIL）的前提——是否由用户顺手在面板完成注册？

---

## 九、实施顺序（供 plan 参考）

1. `verify.py` 先 RED：新增 4.4 断言块 → 跑红确认（7 FAIL = 既有 2 + 新增 5）
2. `douyin.py` 实现：`_human_click` 守卫（4.2）→ 新方法 `_find_rendered_item` /
   `_in_viewport` / `_ensure_item_in_view`（4.1）→ `_open_conversation` 改造（4.1 调用点 + 4.3 重试）
3. `verify.py` 转 GREEN（仅剩既有 2 FAIL）
4. 文档同步（4.5）
5. （可选，待授权）live 冒烟；未授权则按验证方案第 5 条收尾核对
