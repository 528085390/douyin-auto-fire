# 抖音链路迁移到 /chat 独立页 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把发送链路与同步链路从已失效的「首页消息浮层」整体迁移到 `https://www.douyin.com/chat` 独立页，用确定性语义锚点替换几何推断，并让发送成功具备正向证据。

**Architecture:** 直接 `goto /chat` 取代「点消息浮层」；会话用 `[data-e2e="conversation-item"]` 枚举 + 标题精确等值匹配；会话校验用 `curConversation` class 与 `.RightPanelHeadertitle` 双信号；发送后强校验「编辑器清空 + 最后一条 isFromMe 气泡文本匹配」。删除约 350–400 行浮层时代补偿代码，保留风控检测与拟人操作。

**Tech Stack:** Python 3.11 / Playwright (sync API, channel=chrome, headless=False) / 无测试框架，自检靠 `verify.py` + ad-hoc 离线断言。

**Spec:** `docs/superpowers/specs/2026-08-10-migrate-to-chat-page-design.md`（commit d70ab47）

## Global Constraints

- 用户决策 1B：发送成功 = 编辑器清空 **且** 最后一条消息气泡 `isFromMe` 且文本匹配。两条都满足才算成功。
- 用户决策 2：删除 30 秒手动兜底，连带删除 `config.yaml` 的 `browser.manual_select_sec` 与 3 篇文档中的对应描述。
- 用户决策 3：直接替换，不保留新旧双链路。
- 用户签字：群目标名是**纯群名**（不带 `(人数)` 后缀），左侧列表匹配直接等值，无需去后缀归一。
- 用户签字：**所有测试以真实发送为验收标准**，可随意发送、不必担心打扰。
- 编辑器判空必须 `.replace('\u200b','').strip()`——空态 textContent 是零宽字符，不是 `""`。
- 风控检测 `_detect_risk_control` / `_check_risk_stop` **必须保留遍历所有 frame**：`/chat` 确实存在 `nocaptcha` 隐藏帧。
- 不改动：`_open_browser` / `_close_browser` / STEALTH_JS / `_human_move` / `_human_click` / `_human_type` / `_screenshot` / `setup_login` / `runner.py` / `pyenv.py` / 定时任务。
- 不修改 `.workbuddy/memory/` 与 `docs/superpowers/plans/2026-08-09-*.md`（历史存档，改动会让当时决策记录失真）。
- 隐私红线：任何进 git 的文件（含本 plan、verify.py、文档）**不得出现**真实会话名、真实发送内容。示例一律用占位符。
- 提交粒度：每个 Task 结束提交一次，commit message 用中文 conventional commits。

## File Structure

| 文件 | 责任 | 本次动作 |
|---|---|---|
| `douyin.py` | 自动化核心 `DouyinStreak` | 重写导航/匹配/校验/发送/扫描五段；删除 10 处死代码 |
| `verify.py` | 永久自检（无测试框架下的事实标准） | 增补 `/chat` 链路特征断言 + panel 归一化行为断言 |
| `panel.py` | 面板服务 / 会话缓存 | `_conversations` 由 `list[str]` 升级为 `list[dict]`，4 处消费点归一化 |
| `panel.html` | 面板前端 | `renderConvList` 适配 dict，扫描到的 type 作为下拉默认值 |
| `config.yaml` | 公开配置 | 删 `browser.manual_select_sec` |
| `docs/工作原理与架构.md` | 架构文档 | 删「七、人工兜底」整节并调整后续编号；更新链路描述 |
| `docs/配置参考.md` | 配置文档 | 删 `manual_select_sec` 表行与示例行 |
| `docs/故障排查.md` | 排障文档 | 改写会话匹配失败的处置建议 |

**关键接口契约（跨 Task 共享，实现者只看到自己那个 Task，务必照此命名）：**

```python
# douyin.py 模块级常量
DOUYIN_HOME = "https://www.douyin.com"          # 保留
DOUYIN_CHAT = "https://www.douyin.com/chat"     # 新增；DOUYIN_IM 删除

# DouyinStreak 新增/改造方法签名
def _goto_chat(self) -> None: ...
def _is_logged_in(self) -> bool: ...                      # 改造：基于 /chat 双向判定
def _list_conversation_items(self) -> list: ...           # 返回 ElementHandle 列表
def _item_title(self, item) -> str: ...                   # 读 .conversationConversationItemtitle
def _item_kind(self, item) -> str: ...                    # "group" | "private"
def _find_conversation_item(self, name: str): ...         # 精确等值，含滚动；未找到返回 None
def _conversation_is_open(self, name: str) -> bool: ...   # 双信号校验（签名变了：不再收 probe）
def _locate_chat_input(self): ...                         # 改造：单一 slate 锚点
def _editor_text(self) -> str: ...                        # 已 strip \u200b
def _last_bubble(self) -> dict: ...                       # {"from_me": bool, "text": str}
def _send_text(self, text: str, target_name: str = "") -> None: ...
def scan_conversations(self) -> list[dict]: ...           # [{"name": str, "type": str}]
def scan(self) -> list[dict]: ...

# panel.py 新增
def _normalize_conversations(raw: list) -> list[dict]: ...  # str/dict 混合 → [{"name","type"}]
```

---

### Task 1: verify.py 增补 /chat 链路特征断言（先 RED）

**Files:**
- Modify: `verify.py`（在「--- 5. 真实有头浏览器语义」段之后、「--- 6. 配置未处于会被风控拦截的状态」之前插入新段）

**Interfaces:**
- Consumes: 无（本 Task 只加断言）
- Produces: 一组会在 Task 2–5 完成后转 GREEN 的断言。后续每个 Task 都要跑 `python verify.py`。

> **为什么先写断言：** 项目没有测试框架，`verify.py` 就是事实上的测试命令。
> 先让它 RED，才能证明后面的 GREEN 不是假绿（skill 规则：没见过失败的绿是安慰剂）。

- [ ] **Step 1: 在 verify.py 插入新段（放在第 132 行 `check("extra_args 为拷贝而非别名"...)` 之后）**

```python
# --- 5b. /chat 独立页链路（2026-08-10 迁移） ----------------------------------
# 抖音改版后首页「消息」浮层入口消失，IM 独立成 /chat 单页。
# 这些断言锁住迁移后的形态，防止回退到浮层时代的补偿逻辑。
import ast  # noqa: E402

dtree = ast.parse(d)
dfuncs = {n.name for n in ast.walk(dtree) if isinstance(n, ast.FunctionDef)}

check("douyin.py 定义 DOUYIN_CHAT 常量", "DOUYIN_CHAT" in d)
check("douyin.py 不再保留 DOUYIN_IM（/im/ 旧页）", "DOUYIN_IM" not in d)
check("导航直达 /chat", "douyin.com/chat" in d)

# 浮层时代的补偿代码必须整体消失（AST 级，避免注释里提到就算数）
for dead in ("_navigate_to_im", "_try_switch_to_chat_tab", "_wait_im_frame",
             "_locator_by_name_prefix", "_chat_panel_probe", "_extract_conversation_names"):
    check(f"已删除浮层时代函数 {dead}", dead not in dfuncs)
check("已删除几何推断 _PROBE_JS", "_PROBE_JS" not in d)

# 新链路必须使用确定性语义锚点
check("使用 data-e2e 会话项埋点", 'data-e2e="conversation-item"' in d)
check("使用 slate 编辑器锚点", "data-slate-editor" in d)
check("使用发送按钮 e2e 锚点", "e2e-send-msg-btn" in d)
check("使用选中态 class 校验会话", "curConversation" in d)
check("使用右侧标题锚点校验会话", "RightPanelHeadertitle" in d)

# ★ C12b 地雷：编辑器空态 textContent 是零宽字符，不是 ""
check("★编辑器判空处理零宽字符 \\u200b（原地雷点）", "\\u200b" in d)

# ★ 1B 强校验：必须有正向证据，不能「没报错即成功」
check("★发送后校验最后一条气泡来自本人（isFromMe）", "isFromMe" in d)

# 决策 2：手动兜底整体移除
check("已删除 30 秒手动兜底", "manual_select_sec" not in d)
check("config.yaml 不再含 manual_select_sec",
      "manual_select_sec" not in read("config.yaml"))

# 风控检测必须保留（/chat 确实存在 nocaptcha 隐藏帧，删了就瞎了）
check("★保留风控检测遍历 frames", "_detect_risk_control" in dfuncs
      and "self.page.frames" in d)

# 扫描结果升级为 [{"name","type"}]，群聊能自动识别
check("扫描区分群聊/私聊", "commonConversationIconnoDrag" in d)
```

- [ ] **Step 2: 运行，确认 RED**

Run: `cd /d/ai_project/douyin-auto-fire && .venv/Scripts/python.exe verify.py`

Expected: **FAIL**，退出码 1。失败项应包含 `DOUYIN_CHAT 常量`、`已删除浮层时代函数 _navigate_to_im`、`★编辑器判空处理零宽字符`、`★发送后校验最后一条气泡来自本人` 等约 15 条。

> 若某条意外 PASS，说明该断言写法有问题（例如匹配到了注释），必须先修断言再继续。

- [ ] **Step 3: 提交**

```bash
git add verify.py
git commit -m "test(verify): 增补 /chat 链路特征断言（当前预期 RED）"
```

### Task 2: 导航直达 /chat + 登录检测改造

**Files:**
- Modify: `douyin.py:38-39`（常量）、`douyin.py:205-242`（`_is_logged_in` / `_ensure_login`）
- Delete: `douyin.py:398-434`（`_navigate_to_im`）、`douyin.py:1138-1176`（`_wait_im_frame` / `_try_switch_to_chat_tab`）

**Interfaces:**
- Consumes: 无
- Produces: `DOUYIN_CHAT` 常量、`_goto_chat()`、改造后的 `_is_logged_in()`。Task 3/6 依赖 `_goto_chat()`。

- [ ] **Step 1: 替换常量（第 38–39 行）**

```python
DOUYIN_HOME = "https://www.douyin.com"
# 抖音改版：IM 已独立成单页，首页不再有「消息」浮层入口
DOUYIN_CHAT = "https://www.douyin.com/chat"
```

删掉 `DOUYIN_IM = "https://www.douyin.com/im/"`。

- [ ] **Step 2: 新增 `_goto_chat`（放在原 `_navigate_to_im` 位置）**

```python
    def _goto_chat(self):
        """直达 IM 独立页。取代旧的「首页点消息浮层」链路。"""
        self._progress("正在打开私信页…")
        self.page.goto(DOUYIN_CHAT, wait_until="domcontentloaded", timeout=60000)
        self._check_risk_stop()
        # 会话列表出现即视为 IM 就绪
        self.page.wait_for_selector(
            '[data-e2e="conversation-item"], .conversationConversationListwrapper',
            timeout=30000,
        )
        time.sleep(random.uniform(0.8, 1.6))
```

- [ ] **Step 3: 改造 `_is_logged_in`（原第 205–213 行整体替换）**

```python
    def _is_logged_in(self) -> bool:
        """在 /chat 上双向判定登录态。

        旧实现找「登录」二字，在 /chat 上不可靠：登录面板内有多处该字样，
        已登录页也可能出现。改用两个互斥的结构信号。
        """
        try:
            if self.page.query_selector(
                    '[data-e2e="conversation-item"], .conversationConversationListwrapper'):
                return True
            if self.page.query_selector(
                    "#login-panel-new, #douyin_login_comp_flat_panel"):
                return False
        except Exception:  # noqa: BLE001
            pass
        return False
```

- [ ] **Step 4: 让 `_ensure_login` 走 /chat**

把 `_ensure_login` 里原本 `self.page.goto(DOUYIN_HOME...)` 改为 `self._goto_chat()` 之前的裸导航形式——注意此处**不能**直接调 `_goto_chat()`（它会 `wait_for_selector` 会话列表，未登录时必然超时）：

```python
        self.page.goto(DOUYIN_CHAT, wait_until="domcontentloaded", timeout=60000)
```

其余等待扫码的循环逻辑（300s）保持不变。

- [ ] **Step 5: 删除三个死函数**

整体删除 `_navigate_to_im`、`_wait_im_frame`、`_try_switch_to_chat_tab`，以及 `run()` / `scan()` 里对它们的调用（改为调 `_goto_chat()`）。

- [ ] **Step 6: 语法检查**

Run: `cd /d/ai_project/douyin-auto-fire && .venv/Scripts/python.exe -c "import ast,sys; ast.parse(open('douyin.py',encoding='utf-8').read()); print('AST OK')"`
Expected: `AST OK`

- [ ] **Step 7: 提交**

```bash
git add douyin.py
git commit -m "refactor(douyin): 导航直达 /chat，登录检测改用结构双向判定"
```

---

### Task 3: 会话匹配（精确等值 + 虚拟列表滚动）

**Files:**
- Modify: `douyin.py`（替换 `_conversation_list_locator:380`、`_click_conversation:690-819`、`_wait_im_list_ready:820-843`）
- Delete: `douyin.py:435-457`（`_locator_by_name_prefix`）、`douyin.py:551-568`（`_chat_panel_probe`）、`_PROBE_JS` 常量块

**Interfaces:**
- Consumes: `_goto_chat()`（Task 2）
- Produces: `_list_conversation_items()`、`_item_title(item)`、`_item_kind(item)`、`_find_conversation_item(name)`。Task 4 用 `_find_conversation_item`，Task 6 用前三个。

> **关键背景（实现者必读）：** 会话名在 DOM 里**始终完整**，左侧看到的 `xxx…` 是
> CSS `text-overflow` 造成的视觉截断（实测 `scrollWidth=127 > clientWidth=92`）。
> 旧代码的「逐步缩短前缀匹配」建立在错误前提上，是误匹配来源。**必须精确等值。**

- [ ] **Step 1: 新增三个基础方法**

```python
    ITEM_SEL = '[data-e2e="conversation-item"]'
    LIST_SEL = ".conversationConversationListwrapper"

    def _list_conversation_items(self) -> list:
        """枚举当前已渲染的会话项（虚拟列表，只有可视区附近有 DOM）。"""
        return self.page.query_selector_all(self.ITEM_SEL)

    def _item_title(self, item) -> str:
        """会话名。DOM 文本完整，无需处理省略号。"""
        t = item.query_selector(".conversationConversationItemtitle")
        return (t.text_content() or "").strip() if t else ""

    def _item_kind(self, item) -> str:
        """群聊 / 私聊。两种头像节点互斥。"""
        if item.query_selector("img.commonConversationIconnoDrag"):
            return "group"
        return "private"
```

- [ ] **Step 2: 新增 `_find_conversation_item`（精确等值 + 滚动到底）**

```python
    def _find_conversation_item(self, name: str, max_scroll: int = 40):
        """在虚拟列表里精确等值查找会话项；找不到返回 None。

        虚拟列表只渲染可视区，必须边滚边找。用外层 data-index 判断是否到底：
        连续 3 屏没有出现新的 index，视为已到列表末尾。
        """
        seen_idx: set[str] = set()
        stagnant = 0
        for _ in range(max_scroll):
            for item in self._list_conversation_items():
                if self._item_title(item) == name:
                    return item
            idx = {
                (d.get_attribute("data-index") or "")
                for d in self.page.query_selector_all(f"{self.LIST_SEL} div[data-index]")
            }
            stagnant = stagnant + 1 if idx <= seen_idx else 0
            seen_idx |= idx
            if stagnant >= 3:
                break
            wrap = self.page.query_selector(self.LIST_SEL)
            if not wrap:
                break
            wrap.evaluate("el => el.scrollBy(0, el.clientHeight * 0.8)")
            time.sleep(random.uniform(0.4, 0.8))
        return None
```

- [ ] **Step 3: 重写 `_click_conversation`（原 690–819 行整段替换）**

```python
    def _click_conversation(self, name: str, timeout: int = 15000) -> bool:
        """找到并点开目标会话。点击会话项容器本身，不点标题 span。"""
        item = self._find_conversation_item(name)
        if item is None:
            return False
        self._human_click(item, f"会话「{name}」")
        try:
            self.page.wait_for_selector(
                'div[data-slate-editor="true"][contenteditable="true"]', timeout=timeout)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(random.uniform(0.6, 1.2))
        return self._conversation_is_open(name)
```

- [ ] **Step 4: 删除死代码**

删除 `_locator_by_name_prefix`、`_chat_panel_probe`、`_PROBE_JS` 常量块、`_conversation_list_locator` 的 4 候选实现（由 `LIST_SEL` 取代）、`_wait_im_list_ready` 的旧实现（改为等 `ITEM_SEL`）。

- [ ] **Step 5: 语法检查 + 死符号复查**

```bash
cd /d/ai_project/douyin-auto-fire
.venv/Scripts/python.exe -c "import ast; ast.parse(open('douyin.py',encoding='utf-8').read()); print('AST OK')"
grep -n "_locator_by_name_prefix\|_chat_panel_probe\|_PROBE_JS" douyin.py
```
Expected: `AST OK`，且 grep **无输出**（有输出说明还有调用点没清）。

- [ ] **Step 6: 提交**

```bash
git add douyin.py
git commit -m "refactor(douyin): 会话匹配改为精确等值+虚拟列表滚动，删除截断前缀匹配"
```

### Task 4: 会话校验双信号 + 发送强校验（决策 1B）

**Files:**
- Modify: `douyin.py`（`_conversation_is_open:643-654`、`_active_conversation_name:655-689`、`_locate_chat_input:844-887`、`_open_conversation:888-949`、`_send_text:950-1043`）

**Interfaces:**
- Consumes: `_find_conversation_item`（Task 3）、`_click_conversation`（Task 3）
- Produces: `_conversation_is_open(name)`（**签名变更**：不再接收 `probe` 参数）、`_editor_text()`、`_last_bubble()`、强校验版 `_send_text`

> **两个必须记住的陷阱：**
> 1. 编辑器空态 `textContent` 是零宽字符 `\u200b`，不是 `""`。`if text:` 会永远为真。
> 2. 右侧标题里群名带 `(人数)` 后缀，左侧列表是纯群名。校验时对右侧标题去后缀。

- [ ] **Step 1: 重写 `_active_conversation_name` 与 `_conversation_is_open`**

```python
    def _active_conversation_name(self) -> str | None:
        """右侧面板当前打开的会话名（群名会带 (人数) 后缀，此处去掉）。"""
        el = self.page.query_selector(".RightPanelHeadertitle")
        if not el:
            return None
        raw = (el.text_content() or "").strip()
        return re.sub(r"\(\d+\)$", "", raw).strip() or None

    def _conversation_is_open(self, name: str) -> bool:
        """双信号校验，任一命中即通过。

        信号 A：左侧该会话项带选中态 class（全列表恰好 1 项有）
        信号 B：右侧标题去后缀后等于目标名

        旧代码有第三态「什么都读不到就保守放行」，那是几何推断不可靠时的妥协。
        现在锚点确定，读不到就是真没打开——放行只会发错人。
        """
        for item in self._list_conversation_items():
            cls = item.get_attribute("class") or ""
            if "curConversation" in cls and self._item_title(item) == name:
                return True
        return self._active_conversation_name() == name
```

- [ ] **Step 2: 简化 `_locate_chat_input`（原 844–887 行整段替换）**

```python
    def _locate_chat_input(self):
        """聊天输入框。/chat 上唯一，无需再排除搜索框。"""
        return self.page.query_selector(
            'div[data-slate-editor="true"][contenteditable="true"]')
```

- [ ] **Step 3: 新增 `_editor_text` 与 `_last_bubble`**

```python
    ZWSP = "\u200b"

    def _editor_text(self) -> str:
        """编辑器当前文本。空态是零宽字符，必须剥掉再判空。"""
        el = self._locate_chat_input()
        if not el:
            return ""
        return (el.text_content() or "").replace(self.ZWSP, "").strip()

    def _last_bubble(self) -> dict:
        """消息列表最后一条气泡：是否本人发出 + 文本内容。"""
        return self.page.evaluate(
            """() => {
                const box = Array.from(
                    document.querySelectorAll('[class*="messageMessageBoxcontentBox"]'));
                if (!box.length) return {from_me: false, text: ""};
                const last = box[box.length - 1];
                const t = last.querySelector('[class*="TextMessageTextpureText"]');
                return {
                    from_me: (last.getAttribute("class") || "").includes("isFromMe"),
                    text: t ? (t.textContent || "").trim() : "",
                };
            }"""
        )
```

- [ ] **Step 4: 重写 `_send_text`（原 950–1043 行整段替换）**

```python
    def _send_text(self, text: str, target_name: str = ""):
        """发送并强校验。决策 1B：必须有正向证据，不能「没报错即成功」。"""
        if target_name and not self._conversation_is_open(target_name):
            self._audit_dump("wrong_conversation", target_name)
            raise RuntimeError(f"当前打开的不是目标会话「{target_name}」，已跳过以免发错人。")

        el = self._locate_chat_input()
        if not el:
            self._audit_dump("no_editor", target_name)
            raise RuntimeError("未找到聊天输入框。")

        self._human_click(el, "聊天输入框")
        self._human_type(text)
        time.sleep(random.uniform(0.3, 0.7))

        # 内容确实进了编辑器：发送按钮此时应变红
        if not self.page.query_selector("svg.e2e-send-msg-btn.publishRedBtn"):
            logger.warning("输入后发送按钮未变红，可能内容没进编辑器")

        self.page.keyboard.press("Enter")
        time.sleep(random.uniform(0.8, 1.5))

        # Enter 没生效则补点发送按钮
        if self._editor_text():
            btn = self.page.query_selector("svg.e2e-send-msg-btn")
            if btn:
                self._human_click(btn, "发送按钮")
                time.sleep(random.uniform(0.8, 1.5))

        # --- 强校验：两条都满足才算成功 ---
        if self._editor_text():
            self._audit_dump("send_fail", target_name)
            raise RuntimeError("发送后输入框仍有残留文字，判定未发出。")

        bubble = self._last_bubble()
        if not bubble.get("from_me") or bubble.get("text") != text:
            self._audit_dump("verify_fail", target_name)
            raise RuntimeError(
                f"发送校验失败：最后一条气泡 from_me={bubble.get('from_me')} "
                f"文本不匹配（收到 {len(bubble.get('text') or '')} 字）。"
            )

        self._screenshot(f"sent_{target_name}" if target_name else "sent")
        self._check_risk_stop()
```

> 注意：错误信息里**不要**打印气泡原文（会把发送内容写进日志）。只打字数。

- [ ] **Step 5: 删除手动兜底（`_open_conversation` 内，原第 933 行附近）**

删掉这三样：读 `manual_select_sec` 的那行、`time.sleep(manual)` 暂停、`manual_timeout` 审计分支。匹配不到直接：

```python
        if not self._click_conversation(name):
            self._audit_dump("no_match", name)
            raise RuntimeError(f"未找到会话「{name}」，请核对名称是否与抖音中显示的完全一致。")
```

- [ ] **Step 6: 语法检查 + 残留检查**

```bash
cd /d/ai_project/douyin-auto-fire
.venv/Scripts/python.exe -c "import ast; ast.parse(open('douyin.py',encoding='utf-8').read()); print('AST OK')"
grep -n "manual_select_sec\|manual_timeout" douyin.py
```
Expected: `AST OK`，grep **无输出**。

- [ ] **Step 7: 提交**

```bash
git add douyin.py
git commit -m "feat(douyin): 会话校验双信号+发送强校验(气泡回读)，删除手动兜底"
```

---

### Task 5: 扫描链路重写 + 群聊自动识别

**Files:**
- Modify: `douyin.py`（`scan_conversations:1177-1241`、`scan:1265-1286`、`_dump_scan_debug:1242-1264`）
- Delete: `douyin.py:1044-1137`（`_extract_conversation_names` 多策略 JS）

**Interfaces:**
- Consumes: `_goto_chat()`（T2）、`_list_conversation_items` / `_item_title` / `_item_kind`（T3）
- Produces: `scan_conversations() -> list[dict]`、`scan() -> list[dict]`，元素形如 `{"name": str, "type": "group"|"private"}`。**Task 6 依赖这个返回类型。**

- [ ] **Step 1: 重写 `scan_conversations`**

```python
    def scan_conversations(self) -> list[dict]:
        """扫描全部会话。返回 [{"name","type"}]，type 为 group/private。

        旧实现用十几条正则从 title/aria-label/头像祖先里猜名字，是「没有语义埋点」
        时代的产物，也是「会话名混入消息预览、群聊识别不出」的根因。
        现在有 data-e2e 埋点，直接枚举即可。
        """
        found: dict[str, str] = {}
        seen_idx: set[str] = set()
        stagnant = 0
        for _ in range(60):
            for item in self._list_conversation_items():
                name = self._item_title(item)
                if name:
                    found.setdefault(name, self._item_kind(item))
            idx = {
                (d.get_attribute("data-index") or "")
                for d in self.page.query_selector_all(f"{self.LIST_SEL} div[data-index]")
            }
            stagnant = stagnant + 1 if idx <= seen_idx else 0
            seen_idx |= idx
            if stagnant >= 3:
                break
            wrap = self.page.query_selector(self.LIST_SEL)
            if not wrap:
                break
            wrap.evaluate("el => el.scrollBy(0, el.clientHeight * 0.8)")
            time.sleep(random.uniform(0.4, 0.8))
        self._progress(f"扫描完成，共 {len(found)} 个会话")
        return [{"name": n, "type": t} for n, t in found.items()]
```

- [ ] **Step 2: 让 `scan()` 走 /chat 并返回 dict 列表**

`scan()` 内把 `_navigate_to_im()` 等调用换成 `self._goto_chat()`，返回值直接透传 `scan_conversations()`。类型标注改为 `-> list[dict]`。

- [ ] **Step 3: 删除 `_extract_conversation_names` 与 `_dump_scan_debug` 的 frame 遍历**

`_extract_conversation_names` 整体删除。`_dump_scan_debug` 保留但简化为 dump 主 document 的列表项标题（IM 不在 iframe 里）。

- [ ] **Step 4: 语法 + 残留检查**

```bash
cd /d/ai_project/douyin-auto-fire
.venv/Scripts/python.exe -c "import ast; ast.parse(open('douyin.py',encoding='utf-8').read()); print('AST OK')"
grep -n "_extract_conversation_names" douyin.py
```
Expected: `AST OK`，grep **无输出**。

- [ ] **Step 5: 提交**

```bash
git add douyin.py
git commit -m "refactor(douyin): 扫描改用 data-e2e 枚举，顺带自动识别群聊"
```

### Task 6: 面板兼容 list[str] → list[dict]

**Files:**
- Modify: `panel.py:112`（`_conversations` 声明）、`:117-137`（缓存读写）、`:716-724`（`api_conversations`）、`:869-873`（save-targets 并入缓存）、`:925-938`（启动种子）、扫描 worker 里写 `_conversations` 处
- Modify: `panel.html:735-780`（`loadConversations` / `renderConvList`）

**Interfaces:**
- Consumes: `scan()` 返回 `list[dict]`（Task 5）
- Produces: `_normalize_conversations(raw) -> list[dict]`

> **为什么必须做归一化：** 用户磁盘上现有的 `conversations_cache.json` 是
> `["名字A","名字B"]` 格式。直接改成 dict 会让面板启动即崩。归一化读取是唯一安全路径。

- [ ] **Step 1: 在 `panel.py` 的 `_CONV_CACHE_PATH` 定义后新增归一化函数**

```python
def _normalize_conversations(raw: list) -> list[dict]:
    """把 str/dict 混合的会话列表统一成 [{"name","type"}]。

    历史缓存是 list[str]（旧版本无群聊识别），迁移到 /chat 后升级为 dict。
    读取侧统一归一，避免旧缓存文件导致面板启动崩溃。
    """
    out: list[dict] = []
    seen: set[str] = set()
    for x in raw or []:
        if isinstance(x, str):
            name, ctype = x.strip(), "private"
        elif isinstance(x, dict):
            name = str(x.get("name") or "").strip()
            ctype = str(x.get("type") or "private").strip() or "private"
        else:
            continue
        if name and name not in seen:
            seen.add(name)
            out.append({"name": name, "type": ctype})
    return out
```

- [ ] **Step 2: 缓存读取走归一化**

`_load_conversations_cache` 的 `return [str(x) for x in data if x]` 改为
`return _normalize_conversations(data)`；无缓存时 `return []` 不变。

- [ ] **Step 3: 修正 4 个消费点**

| 位置 | 原代码 | 改为 |
|---|---|---|
| `save-targets` 并入缓存（约 870 行） | `if t["name"] not in _conversations` | `if t["name"] not in {c["name"] for c in _conversations}` 并 append `{"name": t["name"], "type": t.get("type","private")}` |
| 启动种子（约 931 行） | `_conversations.append(name)` | `_conversations.append({"name": name, "type": t.get("type","private")})` |
| 扫描 worker 写回 | `_conversations = names` | `_conversations = _normalize_conversations(names)` |
| `api_conversations`（716 行） | `"list": list(_conversations)` | 不变（现在元素已是 dict） |

- [ ] **Step 4: 前端 `renderConvList` 适配（panel.html:760-775）**

```javascript
  convCache.forEach((c, i) => {
    const name = typeof c === "string" ? c : c.name;
    const scanned = (typeof c === "object" && c.type) ? c.type : "private";
    const checked = convSavedMap[name] ? "checked" : "";
    // 已保存的类型优先；否则用扫描识别出的类型作默认值
    const type = convSavedMap[name] || scanned;
```

后续模板里的 `${escapeAttr(name)}` / `${escapeHtml(name)}` 保持不变（变量名已对齐）。
`pollConv` 里的 `d.list.length` 无需改动。

- [ ] **Step 5: 行为验证（喂真实旧格式缓存，不启动浏览器）**

```bash
cd /d/ai_project/douyin-auto-fire && .venv/Scripts/python.exe -c "
import panel
old = ['会话甲','会话乙']
n = panel._normalize_conversations(old)
assert n == [{'name':'会话甲','type':'private'},{'name':'会话乙','type':'private'}], n
mixed = ['会话甲', {'name':'某群','type':'group'}, {'name':'会话甲'}, '', None]
m = panel._normalize_conversations(mixed)
assert m == [{'name':'会话甲','type':'private'},{'name':'某群','type':'group'}], m
print('归一化 OK:', m)
"
```
Expected: 打印 `归一化 OK: [...]`，无 AssertionError。

- [ ] **Step 6: 提交**

```bash
git add panel.py panel.html
git commit -m "feat(panel): 会话列表升级为 name+type，兼容旧 list[str] 缓存"
```

---

### Task 7: 清理 config.yaml 与 3 篇文档

**Files:**
- Modify: `config.yaml:15`、`docs/工作原理与架构.md`、`docs/配置参考.md:20,61`、`docs/故障排查.md:38`

**Interfaces:**
- Consumes: 无
- Produces: 无（文档一致性）

> **不要动** `.workbuddy/memory/2026-08-05.md` 和
> `docs/superpowers/plans/2026-08-09-config-privacy-split.md`——历史存档，改了会让当时的决策记录失真。

- [ ] **Step 1: `config.yaml` 删除 `manual_select_sec: 30` 及其上方注释行**

- [ ] **Step 2: `docs/配置参考.md`**
  - 删表格行 `| browser.manual_select_sec | 整数 | 30 | ... |`（第 20 行）
  - 删示例 YAML 里的 `manual_select_sec: 30`（第 61 行）

- [ ] **Step 3: `docs/故障排查.md` 第 38 行改写**

```markdown
4. 微调建议：确认 `targets[].name` 与抖音会话列表里显示的名称**完全一致**（现已改为精确匹配，不再做前缀匹配）。群目标填**纯群名**，不要带 `(人数)` 后缀。若仍匹配不到，查看审计 JSON 里 dump 的实际列表项标题做比对。
```

- [ ] **Step 4: `docs/工作原理与架构.md`**
  - 删除「## 七、人工兜底（manual fallback）」整节（第 103–110 行）
  - 后续小节重编号：八→七、九→八、十→九
  - 第 99 行发送动作描述改为：
    ```markdown
    发送动作：点击聊天输入框 → 按字输入 → 确认发送按钮变红 → 回车 → 若输入框仍有残留再点「发送」按钮 → **强校验（输入框已清空 且 最后一条气泡为本人发出且文本匹配）** → 截图 → 复检风控。
    ```
  - 第 85–87 行会话判定描述改为双信号（选中态 class / 右侧标题）
  - 第 115 行审计 tag 列表：删 `manual_timeout`，加 `no_editor`、`send_fail`、`verify_fail`、`switch_fail`

- [ ] **Step 5: 一致性检查**

```bash
cd /d/ai_project/douyin-auto-fire
grep -rn "manual_select_sec" --include=*.py --include=*.yaml --include=*.md . | grep -v '^./userdata/' | grep -v '^./.workbuddy/' | grep -v 'plans/2026-08-09'
```
Expected: **无输出**。

- [ ] **Step 6: 提交**

```bash
git add config.yaml docs/
git commit -m "docs+config: 移除手动兜底，文档同步 /chat 新链路"
```

---

### Task 8: verify.py 转 GREEN + 真实发送验收

**Files:**
- Run: `verify.py`
- Run: 面板一键触发（真实发送）

**Interfaces:**
- Consumes: Task 1–7 全部产出

> **用户已明确授权：随便发、随便测、不怕打扰，所有测试以真实发送为验收标准。**

- [ ] **Step 1: 跑 verify.py，确认 Task 1 的断言全部转 GREEN**

Run: `cd /d/ai_project/douyin-auto-fire && .venv/Scripts/python.exe verify.py`
Expected: 退出码 0，`失败 0`。Task 1 里那批 `★` 断言全部 `[ok]`。

- [ ] **Step 2: 离线断言——用已抓快照驱动选择器逻辑**

写临时脚本 `C:\Users\huang\AppData\Local\Temp\hermes-verify-chat-logic.py`，
用 `userdata/probe/page_opened.html` 快照 + 真实 Chromium（`channel="chrome"`，
全网络 abort）断言：能选出 2 个会话项、标题读取完整、群/私判别正确、
编辑器与发送按钮各唯一。RED 侧注入变异确认翻红。跑完**删除脚本**。

- [ ] **Step 3: 真实同步验收**

启动面板 → 点「一键同步」→ 确认：
- 扫描出的会话数量与抖音实际一致
- **群聊自动标记为「群聊」**（旧版全标 private，这是本次顺带修的已知问题）

- [ ] **Step 4: ★真实发送验收（核心验收项）**

面板选中目标（含至少 1 个群）→ 填测试内容 → 一键触发。逐项确认：

| 验收点 | 期望 |
|---|---|
| 浏览器直接打开 `/chat` | 不再经过首页点「消息」 |
| 会话被正确点开 | 右侧标题 = 目标名 |
| **消息真的出现在对话里** | 抖音界面肉眼可见 |
| 面板执行记录 | 成功数与实际发送数**一致** |
| 无 30 秒卡顿 | 手动兜底已删 |
| 截图审计 | `runs/<id>/` 下有 `sent_*.png` |

- [ ] **Step 5: 反向验收（证明强校验不是摆设）**

把一个目标名改成不存在的名字（如 `不存在的会话XYZ`）再触发，确认：
- 快速失败，不卡 30 秒
- 面板记为**失败**（不是成功）
- `runs/<id>/` 有 `audit_no_match_*.json`，里面 dump 了实际列表项标题

> 这一步很重要：上一版就出过「日志说失败、面板显示成功」。必须证明失败路径真的记失败。

- [ ] **Step 6: 提交**

```bash
git add -A
git commit -m "test: /chat 链路真实发送验收通过"
```

---

## Self-Review

**1. Spec 覆盖检查**

| Spec 章节 | 对应 Task |
|---|---|
| 4.1 导航直达 /chat + 登录检测 | Task 2 |
| 4.2 精确等值 + 虚拟列表滚动 | Task 3 |
| 4.3 双信号校验（删 C 态放行） | Task 4 Step 1 |
| 4.4 发送 1B 强校验 | Task 4 Step 3–4 |
| 4.5 删手动兜底 + 连锁改动 | Task 4 Step 5、Task 7 |
| 4.6 扫描重写 + 群聊识别 + 兼容 | Task 5、Task 6 |
| 4.7 删除清单（10 项） | Task 2/3/4/5 分别覆盖 |
| 4.8 保留清单 | Global Constraints 明确 + Task 1 断言锁定风控 |
| 五、错误处理 7 种场景 | Task 4（审计 tag）+ Task 8 Step 5 反向验收 |
| 6.1 verify.py 增补 | Task 1 + Task 8 Step 1 |
| 6.2 ad-hoc 离线断言 | Task 8 Step 2 |
| 6.3 live 冒烟 | Task 8 Step 3–5 |

无遗漏。

**2. 占位符扫描**：无 TBD/TODO；每个代码步骤都给了完整可粘贴代码。

**3. 类型一致性**：
- `_conversation_is_open(name)` 签名变更已在 Task 4 Interfaces 显式标注（旧版收 `probe` 参数）
- `scan_conversations() -> list[dict]` 在 Task 5 Produces 声明，Task 6 Consumes 对齐
- `_item_kind` 返回值 `"group"|"private"` 与 panel/前端 type 字段取值一致
- `ITEM_SEL` / `LIST_SEL` / `ZWSP` 类属性在 Task 3/4 定义，后续 Task 引用名称一致




