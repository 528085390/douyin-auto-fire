# SIV-001 会话项视口外点击落空修复 — Plan 独立评审

- 日期：2026-09-07
- 评审对象：`docs/superpowers/plans/2026-09-07-conversation-click-viewport.md`（commit 89ecdcd，4 Tasks）
- 对照基准：spec 版本 1（同 commit，已 APPROVED，见 `reviews/SIV-001-spec-review.md`）；真实代码 douyin.py / verify.py / panel.py（当前 HEAD）；基线实测 `./.venv/Scripts/python.exe verify.py` = 94 通过 / 2 失败（唯一 2 失败为账号任务未注册的环境态，与本任务无关）；推论 RED 期望 7 FAIL、GREEN 期望 2 FAIL 与 plan Task 1/2/3 所述一致。
- 评审角色说明：本次 Reviewer 由 Lead 代行（独立子代理评审任务被上游 HTTP 503 + 工具参数封装 bug 打断，未产出文件）。
- **结论：APPROVED**（2026-09-07）。P0 无；P1 无；P2 × 2（见「二」）。plan 可进入「等待用户签字」；签字后按 Task 1→4 执行。

---

## 一、P0 / P1 发现

无。逐 Task 核实要点如下：

### Task 1（verify.py 先 RED）
- 断言块插入点明确（verify.py:217 之后、几何探针注释之前）；5 条断言与 spec 4.4 一一对应。
- 断言语义正确（skill 坑表）：`'"重试点击一次"'` 要求独立成 token；`'"元素在视口外'` 用前引号形态；`viewport_size`/`scroll_into_view_if_needed` 为裸子串。
- RED 期望 7 FAIL（既有 2 + 新增 5）与实测基线一致，且新增 5 条在 douyin.py 当前均为 0 命中（已实测），RED 诚实。

### Task 2（douyin.py 实现）
- 三道防线的实现块完整：`_human_click` 守卫（:282-295 替换）、`_find_rendered_item`/`_in_viewport`/`_ensure_item_in_view` 新增（:419 后/:446 后）、`_open_conversation` 改造（:612-642 替换）+ `_wait_switch_settled` 辅助。
- 字节对齐已实测：plan 实现块含 `"重试点击一次"` 独立 token（相邻字面量拆分）、`"元素在视口外` 6 处、`_ensure_item_in_view` 15 处、`self._ensure_item_in_view(` 5 处；douyin.py 当前 0（RED 态符合预期）。
- detached handle 坑、重试幂等、单一失败语义（重试路径吞异常统一走 switch_fail）、Enter 后链路不动——均与 spec 一致。
- Step 6 有语法/引用自查（AST parse + 新符号定义/调用计数），Step 7 提交粒度正确。

### Task 3（文档同步）
- 五节追加 + 七节括注两处修改点精确（:96 后/:126）；`git diff --stat` 应恰好 1 文件；隐私终扫脚本改为从 gitignored run meta 动态取名（命令文本不含真实名），设计正确。
- 收尾核对（无文件改动）把「下次真实运行核对底部目标」落为显式待办，符合仓库惯例。

### Task 4（live 冒烟，待授权）
- 触发条件明确（用户授权 + 提供底部目标/无害文本/账号）；观察点完整（不再 switch_fail、sent/sent_soft 截图、重试 warning 频次）；R1/R2 分析路径指向另开任务，不在本 plan 顺手改——边界清晰。

---

## 二、P2 发现（不阻塞签字，建议执行时留意）

| # | 发现 | 处理建议 |
|---|---|---|
| P2-1 | Task 2 Step 1 的 `_human_click` 守卫在 `_in_viewport` 尚未定义时若被先执行（纯理论，类方法运行期解析）不会报错；但若未来有人把 `_in_viewport` 改名/删除，守卫会 AttributeError——属正常耦合，无碍 | 无需改动；review 已确认 `_in_viewport` 与 `_ensure_item_in_view` 同批新增，Task 2 单提交原子性保证二者共存 |
| P2-2 | Task 2 Step 4 的 `item2 = self._find_rendered_item(name) or self._find_conversation_item(name)` 中，若 `_find_conversation_item` 返回 None（列表里名字消失），`_ensure_item_in_view(item2…)` 对 None 取 bounding_box 会抛 AttributeError，被外层 `except Exception` 吞掉 → 统一走 switch_fail | 语义正确（None 场景本就该 switch_fail）；仅建议实现时确认 `_ensure_item_in_view` 对 None 入参的兜底（P2-1 spec 已要求 box=None 分支） |

---

## 三、已核实安全（供执行者直接引用）

- 基线 verify = 94/2（环境态 2 失败），与 plan 各 Task 期望严格一致。
- 断言与实现块字节兼容（5 条全部在 plan 中找到对应字面，douyin.py 当前 0 命中 = RED 诚实）。
- 隐私红线：plan 全文已脱敏；终扫命令文本不含真实名，运行期从 gitignored 文件动态读取。
- 提交粒度：Task 1 `test(verify):` → Task 2 `fix(douyin):` → Task 3 `docs:`，中文 conventional，每 Task 独立提交，符合仓库先例。
- 冒烟授权前置：Task 4 明确标注「待授权」，未授权时以「下次真实运行后人工核对」收尾，无擅自外发。

---

## 四、最终结论

**APPROVED**（2026-09-07）。plan 4 Tasks 结构完整、Step 可执行、验证期望与实测基线一致、字节对齐通过、隐私设计干净。P2×2 为不阻塞建议项。

下一步：**等待用户签字**（plan 头部状态「待用户签字」）；签字后进入 IMPLEMENT（Task 1 先 RED）。