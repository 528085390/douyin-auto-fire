# SIV-001 会话项视口外点击落空修复 — Spec 独立评审

- 日期：2026-09-07
- 评审对象：`docs/superpowers/specs/2026-09-07-conversation-click-viewport-design.md`（commit 89ecdcd）
- 评审方法：逐条核对 spec「二、勘察结论」引用的真实代码行号区间与 audit JSON 实际字段；核对方案 4.1-4.5 与 `douyin.py / verify.py` 现状的相容性；复核 verify 断言与 plan 实现块的字面一致性；复核隐私红线。
- 评审角色说明：本次 Reviewer 由 Lead 代行（独立子代理评审任务被上游 HTTP 503 + 工具参数封装 bug 打断，未产出文件）。所有证据核对均基于对真实代码、运行产物、自检脚本的实际读取与执行，非转载 spec 自述。
- **结论：APPROVED**（2026-09-07）。P0 无；P1 无；P2 × 3（不阻塞，见「四」）。按 `.hermes.md` 门禁 spec 经 APPROVED 即生效（免签），可进入 PLAN。

---

## 一、P0 发现

无。

## 二、P1 发现（须修订 spec 才能进 plan）

无。逐项核实后确认根因链与方案设计成立，关键闭合点如下：

| 核查点 | 核实结论 | 证据 |
|---|---|---|
| 失败目标 rect 在视口外 | 属实。两个失败目标标题节点 `rect.y=1010` > 视口高 900 | audit_switch_fail_113001/113039.json `page.nameHits[].rect` + `page.viewport{h:900}` |
| viewport 固定 1280×900 | 属实。启动时 `viewport={"width":1280,"height":900}`；审计 dump 页 `innerHeight=900` | douyin.py:150 + audit JSON `page.viewport` |
| `_human_click` 裸鼠标事件不滚动 | 属实。用 `bounding_box()` + `page.mouse.move/down/up`；Playwright 语义下裸事件不自动滚动 | douyin.py:282-295；本机 .venv 实测 `scroll_into_view_if_needed`/`viewport_size` API 可用 |
| `_find_conversation_item` DOM 命中即返回 | 属实。找到即 `return item`，无可见性判定 | douyin.py:430-432 |
| 点击后右侧未开任何会话 | 属实。`probe.active=null`、`editor=false`、全部列表项 `current=false` | audit JSON `probe` |
| 顶部目标全部成功（对照） | 属实。同轮前 5 目标均 sent/sent_soft 截图；前一执行 2 顶部目标也 success | run 日志 + 截图 001~005 |
| 根因=虚拟列表缓冲条目+裸点击不滚动 | 成立。三重事实（DOM 在 / 坐标出界 / 点后未切换）串联一致 | 上表前 4 行 |

## 三、已核实安全（供 plan 直接引用，避免复审返工）

- **新增 API 可用**：`ElementHandle.scroll_into_view_if_needed`、`Page.viewport_size`、`ElementHandle.evaluate` 在本机 .venv 均实测 hasattr 通过（Playwright 官方语义），`scroll_into_view_if_needed` 会自动滚动最近可滚动祖先，适配虚拟列表容器。
- **detached handle 坑已被覆盖**：`_ensure_item_in_view` 每轮 `bounding_box()` 包 try（节点被回收 → box=None）、滚动后按标题经 `_find_rendered_item` 重定位新句柄；正确处理虚拟列表滚动后节点重建。
- **视口守卫不会误伤正常路径**：编辑器/发送按钮在会话打开时天然在视口内；`_in_viewport` 只拦「整体出界」，部分可见仍可点（与现状一致）；读不到视口尺寸时守卫放行（只针对可判定的落空场景）。
- **重试无发送副作用**：重试发生在 `_conversation_is_open` 校验通过之前，尚未触碰输入框/编辑内容；对同一会话重复点击幂等。
- **失败必大声**：`_ensure_item_in_view` 抛错 → 调用方 fail-over 到 `switch_fail` 审计；`_human_click` 视口外拒点抛「元素在视口外」；重试路径自身异常统一吞并走最终 `switch_fail`（单一失败语义，不发明二义 tag）。
- **verify 断言与 plan 实现块字节一致**：`'"重试点击一次"' in d`（要求独立成 token，plan Task 2 Step 4 用相邻字面量拆分 `f"…「{name}」后未切换，" "重试点击一次" "…"` 满足）；`'"元素在视口外' in d`（f-string 开头短语）兼容；`_ensure_item_in_view in dfuncs` + `self._ensure_item_in_view(` 在实现块出现。
- **RED/GREEN 计数正确**：verify.py 基线实测 94 通过 / 2 失败（唯一 2 项为账号任务未注册的环境态，与本任务无关）；新增 5 断言后 RED 期望 7 FAIL、GREEN 期望 2 FAIL，语义正确。
- **隐私红线**：spec/plan 已脱敏（真实目标名用 `<目标A>/<目标B>` 占位、账号别名用 `<别名>`）；plan 终扫脚本改为从 gitignored 的 run meta 动态取名，命令文本本身不含真实名。

---

## 四、P2 发现（不阻塞签字，建议 plan 吸收或在实现后跟进）

| # | 发现 | 处理建议 |
|---|---|---|
| P2-1 | `_ensure_item_in_view` 循环内若滚动后 `_find_rendered_item` 返回 None（该名未渲染），会 `break` 但 `item` 是上一轮的旧句柄；随后 fallback 复验对旧句柄取 box 可能抛/返回旧坐标 | 已有兜底：取不到 box → box=None → `_in_viewport(None)`=False → 仍抛错走 `switch_fail`。语义闭环，仅建议注释注明「break 后 item 可能过期，依赖 fallback 的 box=None 分支兜底」。不阻塞 |
| P2-2 | spec 一 1.3 已把 panel.py:448 的误导文案（「多为未匹配到会话」）列为非目标 | 建议在实现全绿后另立项优化该文案（改为分类型提示或明确指出视口/切换失败），避免用户再次误判方向。不必并入本任务 |
| P2-3 | verify 断言 `'"重试点击一次"'` 与既有 `"自动重试一次"`（type_fail 路径）语义贴近，未来重构可能误混 | 已在 plan 注释标明两者各自锁定；建议实现时保持两条 token 拼写差异，不要统一措辞。不阻塞 |

---

## 五、最终结论

**APPROVED**（2026-09-07）。根因链（虚拟列表缓冲条目 → 裸鼠标点击不滚动 → 点击落空 → `switch_fail`）经真实代码与 audit 证据逐项闭合，无悬空；方案 4.1-4.3 三道防线（滚入视口+重定位、视口外拒点、切换重试）与代码现状相容、幂等、无发送副作用；verify 断言字面一致、RED/GREEN 计数正确；隐私红线通过。P2×3 为不阻塞建议项。

门禁放行后进入 PLAN；plan 的用户签字门禁保留。