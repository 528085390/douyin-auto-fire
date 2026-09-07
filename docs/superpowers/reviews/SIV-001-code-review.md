# SIV-001 会话项视口外点击落空修复 — Code Review

- 日期：2026-09-07
- 评审对象：commit `b98a3e5`（verify.py RED）→ `3e1cbc3`（douyin.py 实现）→ `f1fff0b`（文档同步）
- 对照基准：plan `docs/superpowers/plans/2026-09-07-conversation-click-viewport.md`（用户签字 2026-09-07）；spec（已批准）；verify.py 断言（Task 1）
- 评审角色说明：本次 Reviewer 由 Lead 代行（仓库先例：独立子代理评审不稳定时 Lead 代行并附独立核验证据）
- **结论：APPROVED**（2026-09-07）。P0 无；P1 无；P2 × 2（不阻塞，见「四」）

---

## 一、P0 发现

无。

## 二、P1 发现（须修订后才能 TEST）

无。逐项核验如下：

### 2.1 断言零迁就（防「为过测试焊死代码」）

| 断言（Task 1） | douyin.py 实现来源 | 核验 |
|---|---|---|
| `"_ensure_item_in_view" in dfuncs and "self._ensure_item_in_view(" in d` | `def _ensure_item_in_view`（douyin.py:480）+ 调用 2 处（:696 首点、:716 重试点） | 属实 |
| `"scroll_into_view_if_needed" in d` | `item.scroll_into_view_if_needed(timeout=3000)`（douyin.py:497） | 属实 |
| `"viewport_size" in d` | `self.page.viewport_size or {}`（:290 守卫 + :469 判定） | 属实 |
| `'"重试点击一次"' in d` | 相邻字面量拆分独立 token（:710-711），`grep -c = 1` | 属实 |
| `'"元素在视口外' in d` | f-string 开头短语（:292） | 属实 |

**零迁就证据**：RED 提交 `b98a3e5^`（即 a58a26c）时 douyin.py 五条断言目标字面全部 0 命中（实测 `git show b98a3e5^:douyin.py | grep -c` = 0）——RED 是真红，GREEN 的实现全部来自 plan Task 2 正文，无装饰性字面。

### 2.2 实现正确性（对照 plan Task 2 四步）

- **`_human_click` 守卫**（:286-294）：`bounding_box` 为 None 保持原「元素不可见」报错；`_in_viewport` 不通过才拒点；三处既有调用点（会话项 :698/:717、编辑器 :664/:678 区、发送按钮后端）均为正常可视元素，行为不回归。
- **`_in_viewport`**（:467-475）：box=None → False（拒）；viewport 读不到（w/h ≤ 0）→ True 放行（守卫只针对可判定落空场景）；部分可见（边界只拦整体出界）→ 可点，与既有行为一致。
- **`_ensure_item_in_view`**（:480-512）：3 轮循环内 bounding_box 包 try（detached 回收 → box=None）→ `_in_viewport` 通过即返回；否则 `scroll_into_view_if_needed` 包 try（detached/不可滚走重定位）→ 随机等待 → `_find_rendered_item(name)` 按标题重定位（不滚动）。循环后 fallback 复验一次，仍不可见抛「无法滚动进可视区」。**plan P2-1/P2-2 的两个防坑点均已落地**（break 后 fallback box=None 分支兜底；None 入参时 bounding_box 抛错被上层 except 捕获统一走 switch_fail）。
- **`_open_conversation` 改造**（:686-728）：`_ensure_item_in_view` 调用点 try/except → 失败审计 `switch_fail` 再抛（单一失败语义）；未切换 → warning「重试点击一次」（独立 token）→ 重定位（`_find_rendered_item or _find_conversation_item`）→ 保障可见 → 再点 → `_wait_switch_settled` → 重试路径自身异常统一吞并走最终 switch_fail。重试发生在 `_conversation_is_open` 通过之前，**不碰输入框，无发送副作用**；重复点击同一会话幂等。
- **`_wait_switch_settled`**（:730-737）：抽取原 `_open_conversation` 的等待形态（editor 15s 超时兜底 + 0.6~1.2s 随机停顿），行为不变。

### 2.3 回归风险

- 唯一公共路径改动 = `_human_click` 守卫：全部既有调用目标均天然在视口内（会话项/编辑器/发送按钮），唯一可能触发拒点的场景是「元素整体出界」——而该场景下旧代码必然静默落空（正是本缺陷），故新行为只删除「静默失败」不引入新失败。
- verify 全绿回归：Task 2 后 99 通过 / 2 失败（既有 2 环境态），Task 3 文档同步后仍 99/2，无回归。
- 隐私：douyin.py 注释与文档无真实会话名/账号别名（终扫通过）。

---

## 三、已核实安全（供 TEST 直接引用）

- 结构断言全部由真实实现满足，无迁就（2.1）。
- 语义锚点/既有保证未被触碰：`_send_text` 链路、审计 tag 全集（no_match/switch_fail/wrong_conversation/no_editor/type_fail/send_fail 仍各 1 处）、`_find_conversation_item` 算法、风控、多账号层。
- 提交粒度符合 plan：`test(verify):` → `fix(douyin):` → `docs:`，每 Task 独立，中文 conventional。

---

## 四、P2 发现（不阻塞）

| # | 发现 | 建议 |
|---|---|---|
| P2-1 | `_ensure_item_in_view` 与 `_human_click` 均含 bounding_box 调用（重复取框），极端慢速渲染下重试点击的保障链多一次几何读取 | 无碍；如需微优化可后续让 `_ensure_item_in_view` 返回框缓存；本任务不阻塞 |
| P2-2 | `_wait_switch_settled` 的 15s 编辑器等待在重试路径同样生效，重试最坏耗时被拉长 | 可接受（重试本就是低频异常路径）；如需可在 plan 后续任务缩短重试路径等待 |

---

## 五、最终结论

**APPROVED**（2026-09-07）。三道防线实现与 plan Task 2 逐字对齐、断言零迁就（RED 真红、GREEN 真绿）、公共路径无回归风险、隐私干净。P2×2 为不阻塞建议项。放行进入 TEST。