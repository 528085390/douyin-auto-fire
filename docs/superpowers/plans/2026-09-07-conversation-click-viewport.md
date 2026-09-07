# 会话项视口外点击落空修复（滚入视口 + 视口外拒点 + 切换重试）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- 日期：2026-09-07
- 状态：待用户签字
- 关联 spec：`docs/superpowers/specs/2026-09-07-conversation-click-viewport-design.md`（待评审）
- 前置：Spec Review APPROVED（reviews/SIV-001-spec-review.md）+ Plan Review APPROVED（reviews/SIV-001-plan-review.md）+ 用户签字后方可 IMPLEMENT（`.hermes.md`：spec 免签、plan 保留用户签字）

**Goal:** 修复「列表底部会话点击落空 → switch_fail」缺陷（SIV-001）：点击会话项前必须保证条目完整落在视口内（滚入 + 按标题重定位新句柄），`_human_click` 对视口外坐标大声拒点，切换校验失败自动重试点击一次，并把这三条保证写进 verify.py 防回归。

**Architecture:** 事故根因是抖音会话列表为虚拟列表——`_find_conversation_item` 边滚边找，条目一进 DOM（含可视区外的缓冲条目）就返回；`_human_click` 用 `bounding_box()` 坐标 + 裸 `mouse.move/down/up`，裸鼠标事件不自动滚动页面，坐标 y≈1010 > 视口高 900 时点击静默落空（2026-09-07 真实运行取证：目标 DOM 在、rect 在视口外、点击后右侧 active=null/editor=false）。修复分三道：① 新方法 `_ensure_item_in_view(item, name)`——边界框不在视口内则 `scroll_into_view_if_needed` → 等待 → `_find_rendered_item(name)` 按标题重定位（虚拟列表滚动会回收/重建节点，旧 handle 可能 detached）→ 复验，至多 3 轮，仍不可见抛错；② `_human_click` 视口守卫——目标框整体出界直接抛「元素在视口外」，把静默落空变成大声失败；③ `_open_conversation` 切换失败重试——warning「重试点击一次」→ 按标题重定位 + 保障可见 + 再点 + 再校验，仍失败才审计 `switch_fail`。verify.py 新增 5 条断言锁方法存在/调用形态/关键 API/文案 token，先 RED 后 GREEN。文档同步架构文档五、七节。

**Tech Stack:** Python 3.11 / Playwright (sync API, channel=chrome, headless=False, viewport 固定 1280×900) / 无测试框架，自检靠 `verify.py`（`.venv/Scripts/python.exe verify.py`）。

**Spec:** `docs/superpowers/specs/2026-09-07-conversation-click-viewport-design.md`（状态：待评审；Reviewer APPROVED 后本 plan 生效前提才成立）

## Global Constraints

- **审批链**：本 plan 头部状态为「待用户签字」；Reviewer APPROVED + 用户签字后才可进入 IMPLEMENT（`.hermes.md` 审批规则）。
- 审计 tag 不新增：`switch_fail` 语义不变（「点了但没切过去」，含「滚不进视口」与「重试后仍未切换」两种子情形）；不得发明新 tag。
- 重试点击发生在任何发送动作之前（切换校验不过不碰输入框），无消息副作用；对同一会话重复点击幂等。
- 重试路径吞掉自身异常，统一走最终 `switch_fail` 审计——只允许一种失败语义。
- 不改动：`_find_conversation_item` 滚动查找算法（stagnant/max_scroll）、风控检测、`_send_text`/type_fail/send_fail 发送链路、扫描、面板 UI、runner.py、panel.py（含 :448 错误文案，P2 另行排期）、定时任务。
- verify.py 断言语义（仓库坑表）：`'"重试点击一次"'` 要求短语**独立成 token**（实现用相邻字面量拆分，如 `"…，" "重试点击一次" "…"`；禁止转义引号）；不得与既有 `"自动重试一次"` token（type_fail 路径）混用。GREEN 失败时**对照断言逐字修实现措辞，不许改断言迁就实现**。
- 基线（spec E9）：verify.py 当前 94 通过 / 2 失败（两个账号任务未在面板注册，既有环境态，与本任务无关）。RED 期望 = 7 FAIL（既有 2 + 新增 5）；GREEN 期望 = 2 FAIL（仅剩既有）。
- 隐私红线：任何进 git 的文件（本 plan、verify.py、douyin.py 注释、文档）**不得出现**真实会话名、真实账号别名、真实发送内容；示例一律占位符（真实目标只存在于 gitignored 的 `userdata/`）。
- 验证命令一律：`cd D:/ai_project/douyin-auto-fire && ./.venv/Scripts/python.exe verify.py`
- 提交粒度：每 Task 一提交，中文 conventional commits，直接提交 main（仓库先例：RED `test(verify): …` → 实现 `fix(douyin): …` → 文档 `docs: …`）。文档与代码分开提交。

## File Structure

| 文件 | 责任 | 本次动作 |
|---|---|---|
| `verify.py` | 永久自检（无测试框架下的事实标准） | 5b 节 `sent_soft` 检查后新增 SIV-001 断言块（5 条） |
| `douyin.py` | 自动化核心 `DouyinStreak` | `_human_click` 视口守卫；新增 `_find_rendered_item` / `_in_viewport` / `_ensure_item_in_view`；`_open_conversation` 点击前保障可见 + 切换失败重试一次 |
| `docs/工作原理与架构.md` | 架构文档 | 五节「会话项枚举与匹配」追加可见性保障条目；七节 `switch_fail` 括注两种子情形 |

**关键接口契约（跨 Task 共享）：** 新增物为——方法 `def _find_rendered_item(self, name: str)`（当前已渲染 DOM 内按标题精确等值查找，不滚动）；方法 `def _in_viewport(self, box) -> bool`（边界框完整落在 `self.page.viewport_size` 内）；方法 `def _ensure_item_in_view(self, item, name: str, max_tries: int = 3)`（滚入视口 + 重定位 + 复验，返回可点击句柄，失败抛 RuntimeError）；`_human_click` 内视口守卫（抛错文案以「元素在视口外」开头）；`_open_conversation` 内 `self._ensure_item_in_view(` 调用点与 `"重试点击一次"` 独立 token。既有方法签名一律不变。Task 1 断言锁定这些形态，Task 2 必须照此实现，**不得绕过方法内联滚动、不得省略重定位（旧 handle 滚动后可能 detached）**。

---

### Task 1: verify.py 先 RED（SIV-001 断言块）

**Files:**
- Modify: `verify.py:217` 之后（5b 节 `check("★软校验降级路径保留（sent_soft 命名）", …)` 与 `# ★ _audit_dump 不能再引用已删的几何探针` 之间插入）

**Interfaces:**
- Consumes: 既有变量 `d`（douyin.py 原始源码文本，含注释）、`dfuncs`（douyin.py AST 函数名集合）
- Produces: 5 条会在 Task 2 后转 GREEN 的断言。Task 2 实现者以此为准绳。

> 为什么先 RED：项目没有测试框架，verify.py 就是事实上的测试命令。先让它红，才能证明 Task 2 的绿不是假绿。

- [ ] **Step 1: 插入断言块**

在 `check("★软校验降级路径保留（sent_soft 命名）", '"sent_soft"' in d)` 之后插入：

```python
# ★ SIV-001 会话项可见性（2026-09-07 spec）：虚拟列表在可视区外渲染缓冲条目——
# DOM 在、bounding_box 有坐标，但裸鼠标事件不自动滚动，点在视口外=静默落空
# （2026-09-07 真实运行：列表底部 2 目标全部 switch_fail）。三道保证：
# 点击前滚入视口并重定位句柄；_human_click 视口外拒点；未切换自动重试点击一次。
check("★_ensure_item_in_view 存在且被调用（点击前滚入视口）",
      "_ensure_item_in_view" in dfuncs and "self._ensure_item_in_view(" in d)
check("★滚动使用 scroll_into_view_if_needed", "scroll_into_view_if_needed" in d)
check("★视口判定使用 viewport_size", "viewport_size" in d)
check("★会话未切换会自动重试点击一次", '"重试点击一次"' in d)
check("★_human_click 拒绝视口外点击", '"元素在视口外' in d)
```

- [ ] **Step 2: 跑 verify.py 确认 RED**

Run: `cd D:/ai_project/douyin-auto-fire && ./.venv/Scripts/python.exe verify.py`
Expected: **失败 7 项、exit 1** = 既有 2（`账号任务 DouyinAutoFire-* 已注册` ×2，spec E9 环境态）+ 新增 5：
1. `★_ensure_item_in_view 存在且被调用（点击前滚入视口）`（无该方法与调用）
2. `★滚动使用 scroll_into_view_if_needed`（douyin.py 现无该 API）
3. `★视口判定使用 viewport_size`（现仅 :483 审计 JS 里的 `innerWidth`，无 `viewport_size` 字样）
4. `★会话未切换会自动重试点击一次`（无该 token）
5. `★_human_click 拒绝视口外点击`（无该文案）

> 若失败数 ≠ 7：停下来核对——既有 2 项是否变化（环境问题）、新增断言是否笔误；修回再继续。

- [ ] **Step 3: 提交（红测试独立提交，仓库先例）**

```bash
git add verify.py && git commit -m "test(verify): SIV-001 会话项可见性断言先 RED（滚入视口/视口外拒点/重试点击）"
```

---

### Task 2: douyin.py 实现三道保证（转 GREEN）

**Files:**
- Modify: `douyin.py:282-295`（`_human_click`：加视口守卫）
- Modify: `douyin.py:419` 之后（`_item_kind` 与 `_find_conversation_item` 之间：新增 `_find_rendered_item`）
- Modify: `douyin.py:446` 之后（`_find_conversation_item` 与 `_audit_dump` 之间：新增 `_in_viewport` / `_ensure_item_in_view`）
- Modify: `douyin.py:612-642`（`_open_conversation`：点击前保障可见 + 切换失败重试一次）

**Interfaces:**
- Consumes: 既有 `_find_conversation_item(name)` / `_item_title(item)` / `_conversation_is_open(name)` / `_audit_dump(tag, name)` / `ITEM_SEL` 常量——均不改签名。Playwright `ElementHandle.scroll_into_view_if_needed(timeout=)`、`Page.viewport_size`（本机 .venv 实测可用，spec E7）。
- Produces: `_find_rendered_item` / `_in_viewport` / `_ensure_item_in_view` 方法、`_human_click` 守卫文案「元素在视口外」、`_open_conversation` 的 `self._ensure_item_in_view(` 调用与 `"重试点击一次"` 独立 token。字面形态必须与 Task 1 断言逐字一致。

- [ ] **Step 1: `_human_click` 视口守卫（douyin.py:282-295）**

将：

```python
    def _human_click(self, handle, label: str = ""):
        """移动到元素内随机一点，按下-松开之间留人类时差。"""
        assert self.page is not None
        box = handle.bounding_box()
        if not box:
            raise RuntimeError(f"元素不可见，无法点击: {label}")
        cx = box["x"] + box["width"] * random.uniform(0.35, 0.65)
```

替换为：

```python
    def _human_click(self, handle, label: str = ""):
        """移动到元素内随机一点，按下-松开之间留人类时差。"""
        assert self.page is not None
        box = handle.bounding_box()
        if not box:
            raise RuntimeError(f"元素不可见，无法点击: {label}")
        # SIV-001 守卫：裸鼠标事件不会自动滚动页面，bounding_box 对视口外元素
        # 照样返回坐标——不拦住就是静默点空（2026-09-07 底部会话事故根因）。
        if not self._in_viewport(box):
            vp = self.page.viewport_size or {}
            raise RuntimeError(
                f"元素在视口外，无法点击: {label}"
                f"（box y={box['y']:.0f}~{box['y'] + box['height']:.0f},"
                f" viewport={vp.get('width')}x{vp.get('height')}）")
        cx = box["x"] + box["width"] * random.uniform(0.35, 0.65)
```

- [ ] **Step 2: 新增 `_find_rendered_item`（douyin.py:419 之后，`_item_kind` 与 `_find_conversation_item` 之间）**

```python
    def _find_rendered_item(self, name: str):
        """在当前已渲染 DOM 里按标题精确等值查找会话项（不滚动）。

        与 _find_conversation_item（边滚边找）分工：虚拟列表滚动会回收/重建节点，
        滚动后旧 ElementHandle 可能 detached，必须用它拿新句柄再操作。
        """
        for item in self._list_conversation_items():
            if self._item_title(item) == name:
                return item
        return None
```

- [ ] **Step 3: 新增 `_in_viewport` / `_ensure_item_in_view`（douyin.py:446 之后，`_find_conversation_item` 与 `_audit_dump` 之间）**

```python
    def _in_viewport(self, box) -> bool:
        """边界框是否完整落在视口内（SIV-001）。部分可见也算在内——
        与既有行为一致，只拦「整体出界」（那种点击必然落空）。"""
        if not box:
            return False
        vp = self.page.viewport_size or {}
        vw, vh = vp.get("width", 0), vp.get("height", 0)
        if vw <= 0 or vh <= 0:
            return True  # 读不到视口尺寸时不拦（守卫只针对可判定的落空场景）
        return (box["x"] >= 0 and box["y"] >= 0
                and box["x"] + box["width"] <= vw
                and box["y"] + box["height"] <= vh)

    def _ensure_item_in_view(self, item, name: str, max_tries: int = 3):
        """滚动会话项进入视口，返回可点击的（可能已重定位的）句柄。

        SIV-001：虚拟列表在可视区外还渲染缓冲条目——DOM 在、坐标在视口外，
        裸鼠标点击等于点空。滚动后节点可能被回收重建，旧句柄会 detached，
        每轮都要按标题重定位新句柄再复验。仍不可见则抛错（大声失败，
        由调用方审计 switch_fail），绝不带病点击。
        """
        for _ in range(max_tries):
            try:
                box = item.bounding_box()
            except Exception:  # noqa: BLE001  节点已被虚拟列表回收
                box = None
            if self._in_viewport(box):
                return item
            try:
                item.scroll_into_view_if_needed(timeout=3000)
            except Exception:  # noqa: BLE001  detached/不可滚动：走重定位
                pass
            time.sleep(random.uniform(0.4, 0.8))
            fresh = self._find_rendered_item(name)
            if fresh is None:
                break
            item = fresh
        try:
            box = item.bounding_box()
        except Exception:  # noqa: BLE001
            box = None
        if self._in_viewport(box):
            return item
        raise RuntimeError(f"会话项「{name}」无法滚动进可视区，无法可靠点击。")
```

- [ ] **Step 4: 改造 `_open_conversation`（douyin.py:612-642）**

将：

```python
        item = self._find_conversation_item(name)
        if item is None:
            # 点不到：列表里根本没有这个名字
            self._audit_dump("no_match", name)
            raise RuntimeError(
                f"未找到{label}「{name}」，请核对名称是否与抖音中显示的完全一致。")

        self._human_click(item, f"{label}「{name}」")
        try:
            self.page.wait_for_selector(
                'div[data-slate-editor="true"][contenteditable="true"]', timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(random.uniform(0.6, 1.2))

        if not self._conversation_is_open(name):
            # 点到了但校验不过：切换失败（与 no_match 语义区分开）
            self._audit_dump("switch_fail", name)
            raise RuntimeError(f"已点击{label}「{name}」但右侧未切换到该会话，跳过以免发错人。")

        self._check_risk_stop()
```

替换为：

```python
        item = self._find_conversation_item(name)
        if item is None:
            # 点不到：列表里根本没有这个名字
            self._audit_dump("no_match", name)
            raise RuntimeError(
                f"未找到{label}「{name}」，请核对名称是否与抖音中显示的完全一致。")

        # SIV-001：DOM 命中 ≠ 可见——缓冲条目坐标在视口外，点击前必须滚入视口
        # 并重定位新句柄（虚拟列表滚动会回收节点）。滚不进去同样审计 switch_fail。
        try:
            item = self._ensure_item_in_view(item, name)
        except Exception:  # noqa: BLE001
            self._audit_dump("switch_fail", name)
            raise

        self._human_click(item, f"{label}「{name}」")
        self._wait_switch_settled()

        if not self._conversation_is_open(name):
            # 点击未生效可能是瞬态（渲染慢/列表重排）：自动重试点击一次再判死刑。
            # 重试无发送副作用——切换校验通过前不碰输入框；重复点击同一会话幂等。
            # 「重试点击一次」独立成 token：verify.py 锁定该文案，改措辞须同步断言。
            logger.warning(
                f"点击{label}「{name}」后右侧未切换，"
                "重试点击一次"
                "…")
            time.sleep(random.uniform(0.5, 1.0))
            try:
                item2 = self._find_rendered_item(name) or self._find_conversation_item(name)
                if item2 is not None:
                    item2 = self._ensure_item_in_view(item2, name)
                    self._human_click(item2, f"{label}「{name}」")
                    self._wait_switch_settled()
            except Exception as e:  # noqa: BLE001
                # 重试路径自身异常不另立语义，统一走下方 switch_fail 审计
                logger.warning("重试点击未成功: %s", e)
            if not self._conversation_is_open(name):
                # 点到了但校验不过：切换失败（与 no_match 语义区分开）
                self._audit_dump("switch_fail", name)
                raise RuntimeError(
                    f"已点击{label}「{name}」但右侧未切换到该会话，跳过以免发错人。")

        self._check_risk_stop()
```

并在 `_open_conversation` 之后新增等待辅助方法（抽取既有等待形态，行为不变）：

```python
    def _wait_switch_settled(self):
        """点击会话后等待右侧切换就绪（编辑器出现或超时兜底 + 随机停顿）。"""
        try:
            self.page.wait_for_selector(
                'div[data-slate-editor="true"][contenteditable="true"]', timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(random.uniform(0.6, 1.2))
```

> 提醒：`_open_conversation` 之外的一切（`_send_text` 链路、审计、run() 失败分支）**保持原样不动**。
> 字节对齐自查（skill 坑表）：断言 `'"重试点击一次"'` 要求该短语独立成 token——上方实现用
> 相邻字面量拆分（`f"…，" "重试点击一次" "…"`）满足；`"元素在视口外` 为 f-string 开头短语，
> 前引号紧贴。提交前跑 `grep -c '"重试点击一次"' douyin.py` 应 ≥1（verify 同源匹配）。

- [ ] **Step 5: 跑 verify.py 确认 GREEN**

Run: `cd D:/ai_project/douyin-auto-fire && ./.venv/Scripts/python.exe verify.py`
Expected: **失败 2、exit 1**——仅剩既有 2 项（账号任务未注册，spec E9 环境态）；SIV-001 新增 5 条全过、原 94 条不回归。

> 若新增断言仍红：失败原因应为「字面形态不一致」，对照断言逐字修正实现措辞——不许改断言迁就实现。若既有 94 条出现新 FAIL：实现破坏了原保证，回退检查。

- [ ] **Step 6: 语法/引用自查**

Run: `./.venv/Scripts/python.exe -c "import ast; ast.parse(open('douyin.py',encoding='utf-8').read()); print('syntax ok')"`
Run: `grep -n "_ensure_item_in_view\|_find_rendered_item\|_in_viewport\|_wait_switch_settled" douyin.py` → 每个新符号应有定义 1 处 + 调用 ≥1 处。

- [ ] **Step 7: 提交**

```bash
git add douyin.py && git commit -m "fix(douyin): 会话项点击前滚入视口+视口外拒点+切换失败重试点击一次（SIV-001）"
```

---

### Task 3: 文档同步（架构文档五、七节）

**Files:**
- Modify: `docs/工作原理与架构.md:96` 之后（五节「会话项枚举与匹配」列表末尾追加）
- Modify: `docs/工作原理与架构.md:126`（七节审计 tag 行 `switch_fail` 括注）

**Interfaces:**
- Consumes: Task 2 后的真实行为（点击前 `_ensure_item_in_view`；`_human_click` 视口外拒点；未切换重试点击一次；`switch_fail` 含两种子情形）
- Produces: 与代码一致的文档（verify.py 不锁文档文案，防漂移靠体检）

- [ ] **Step 1: 五节追加可见性保障条目（:96 之后）**

在「匹配采用**精确等值**……连续 3 屏无新 `data-index` 视为到底。」一行之后追加：

```markdown
- **点击前可见性保障（SIV-001）**：虚拟列表在可视区外还渲染缓冲条目——DOM 命中 ≠ 可见，裸鼠标点击视口外坐标会静默落空（2026-09-07 真实事故：列表底部目标全部 `switch_fail`）。故点击前 `_ensure_item_in_view` 把条目滚入视口（`scroll_into_view_if_needed`）并**按标题重定位新句柄**（滚动会回收/重建节点，旧句柄可能 detached），至多 3 轮；`_human_click` 对整体出界的坐标直接拒点（大声失败）。点击后未切换会自动**重试点击一次**（重定位 + 保障可见 + 再点 + 再校验），仍失败才审计 `switch_fail` 并跳过。
```

- [ ] **Step 2: 七节 `switch_fail` 括注（:126）**

将：

```markdown
所有失败/异常路径（未匹配 `no_match`、切错会话 `wrong_conversation`、点到了但没切过去 `switch_fail`、找不到编辑器 `no_editor`、文字没进输入框 `type_fail`、发送后输入框仍有残留 `send_fail`）都会调用 `_audit_dump(tag, name)`，产出两份证据：
```

替换为：

```markdown
所有失败/异常路径（未匹配 `no_match`、切错会话 `wrong_conversation`、点到了但没切过去 `switch_fail`——含「条目无法滚入可视区」与「重试点击后仍未切换」两种子情形（SIV-001）、找不到编辑器 `no_editor`、文字没进输入框 `type_fail`、发送后输入框仍有残留 `send_fail`）都会调用 `_audit_dump(tag, name)`，产出两份证据：
```

- [ ] **Step 3: 回归自检 + 改动面核对**

Run: `./.venv/Scripts/python.exe verify.py` → Expected: 失败 2（仅既有环境态）、与 Task 2 后一致。
Run: `git diff --stat` → 应恰好 1 个文件：`docs/工作原理与架构.md`（douyin.py/verify.py 已在前两个 Task 提交）。
Run: 隐私红线终扫——**命令文本本身不含真实名**，真实目标名/别名只从 gitignored 的 run meta 动态读取（执行前把 `<别名>` 替换为真实账号别名，该别名不进 git）：

```bash
./.venv/Scripts/python.exe - <<'PY'
import json, pathlib
meta = json.loads(pathlib.Path(
    "userdata/accounts/<别名>/runs/20260907_112242.json").read_text(encoding="utf-8"))
secrets = [t for t in meta.get("targets", []) if t] + ["<别名>"]
files = [
    "docs/superpowers/specs/2026-09-07-conversation-click-viewport-design.md",
    "docs/superpowers/plans/2026-09-07-conversation-click-viewport.md",
    "docs/superpowers/status/SIV-001.md",
    "docs/工作原理与架构.md", "verify.py", "douyin.py",
]
bad = [(f, s) for f in files for s in secrets
       if s in pathlib.Path(f).read_text(encoding="utf-8")]
print("隐私命中:", bad or "无（通过）")
PY
```

→ 预期输出 `隐私命中: 无（通过）`。任何命中都意味着真实会话名/别名漏进了 git 跟踪文件，必须脱敏后再提交。

- [ ] **Step 4: 提交**

```bash
git add docs/工作原理与架构.md && git commit -m "docs: 同步会话项可见性保障与 switch_fail 子情形（SIV-001）"
```

> **收尾核对（无文件改动）：** 若未授权 Task 4 冒烟，下一次真实运行（面板手动触发或定时任务）后，人工核对执行记录：**列表底部目标**是否成功（sent/sent_soft 截图）、有无非预期 `switch_fail`、有无「重试点击一次」warning（有 = 兜底生效，记录频次即可）。

---

### Task 4: live 冒烟（待授权，实现全绿后单独决定）

**触发条件：** Task 3 完成后用户授权（spec 八-1）。用户提供：
- 目标会话名 `<SMOKE_TARGET>`（**必须是列表底部、需要滚动才能看到的会话**——顶部目标证明不了本修复；建议用本次失败的目标之一）
- 测试内容 `<SMOKE_TEXT>`（无害短句，如「冒烟测试」+ 时间戳）
- 账号别名 `<ACCOUNT>`

- [ ] **Step 1: 面板触发（用户在面板操作，或经用户同意后 CLI 一次性注入）**

面板路径（推荐，用户偏好看板操作）：切到对应账号 → 目标只勾 `<SMOKE_TARGET>` → 文案临时改为 `<SMOKE_TEXT>` → 一键触发 → 观察可见浏览器。

- [ ] **Step 2: 核对证据**
- 日志出现「正在查找私聊「<SMOKE_TARGET>」」后**不再**出现该目标的 switch_fail；
- 出现 `sent_<SMOKE_TARGET>.png`（或 sent_soft）截图，右侧会话确已切换；
- 若出现「重试点击一次」warning 属兜底生效（瞬态），记录频次；若重试后仍 switch_fail → 保留 audit JSON，回到 spec R1/R2 分析（滚动拉锯/列表重排），另开任务，不在本 plan 内顺手改。

- [ ] **Step 3: 收尾**
冒烟产物在 gitignored 的 `userdata/accounts/<ACCOUNT>/runs/` 内，留档即可；无代码改动则无需提交。恢复用户原目标勾选与文案。

---

## 验证总览

| Task | 命令 | 期望 |
|---|---|---|
| 1 | `verify.py` | RED：失败 7（既有 2 + 新增 5）、exit 1 |
| 2 | `verify.py` + 语法/引用自查 | 失败 2（仅既有环境态）、新增 5 全过、94 条不回归 |
| 3 | `verify.py` + `git diff --stat` + 隐私终扫 | 失败 2；恰好 1 个文档文件；隐私扫描无输出 |
| 4（可选，待授权） | 面板触发底部目标 | 见 Task 4 Step 2 观察点 |
