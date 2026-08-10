# 抖音链路迁移到 /chat 独立页 — 设计文档（spec）

- 日期：2026-08-10
- 状态：待用户签字
- 决策来源：用户拍板「1B、2 手动兜底去掉、3 直接替换」

---

## 一、背景与问题

现有发送/同步链路建立在**首页「消息」浮层**之上：

```
douyin.com 首页 → 点击 text=消息 → 右侧浮层 → 在浮层里找会话 → 发送
```

抖音改版后该链路整条失效。2026-08-10 全流程验证的真实故障链：

```
点击目标不可见（截断匹配） → 手动兜底 30s 超时 → 未找到聊天输入框
```

2/2 目标必现，等于定时任务当前一条都发不出去。

根因不是某个选择器过期，而是**页面形态换了**：IM 已独立成 `https://www.douyin.com/chat` 单页，
首页不再有可点的「消息」浮层入口。现有代码里大量几何推断（输入框正上方同列找标题、
浮层边界排除顶部导航）是为浮层形态设计的补偿逻辑，在独立页上既不必要也不可靠。

---

## 二、实地勘察结论（已验证）

对 `/chat` 做了 5 轮只读探针，抓取真实 DOM 快照与结构 JSON，
并用真实 Chromium 解析快照做了 **39 条断言、GREEN 全过、12 条 RED 变异全部翻红**。

### 2.1 结论表

| 编号 | 结论 | 锚点 |
|---|---|---|
| C1 | 会话项有稳定语义埋点 | `[data-e2e="conversation-item"]` |
| C2 | 会话名 DOM 文本**完整**，不含省略号 | `.conversationConversationItemtitle` |
| C3 | 选中态由 class 明示，全列表恰好 1 项 | `conversationConversationItemcurConversation` |
| C4 | 会话项全部在列表容器内 | `.conversationConversationListwrapper` |
| C5 | 虚拟列表，外层 `data-index` 连续 0..n-1 | `div[data-index]` |
| C6 | 群/私聊可由头像节点判别，互斥 | 群 `img.commonConversationIconnoDrag` / 私 `.commonIMAvataravatarContainer` |
| C7 | 输入框唯一 | `div[data-slate-editor="true"][contenteditable="true"]`，`data-placeholder=发送消息` |
| C8 | 发送按钮唯一 | `svg.e2e-send-msg-btn` |
| C9 | 右侧标题与选中会话一致（群名带 `(人数)` 后缀） | `.RightPanelHeadertitle` |
| C10 | 会话项在主 document；页面 2 个 iframe 均 `display:none` 基础设施帧 | — |
| C10b | **`nocaptcha` 风控帧确实存在** | 风控检测必须保留遍历 frames |
| C11 | 长昵称仅 CSS 溢出截断，`textContent` 完整（`sw=127 > cw=92`） | — |
| C12 | 发送按钮有文本时才加 `publishRedBtn` 变红 | 可作「待发送」信号 |
| C12b | 编辑器空态 `textContent` 是零宽字符 `\u200b` | **判空必须 strip `\u200b`** |
| C13 | 未登录 `/chat` 直接渲染登录面板，无会话项无编辑器 | `#login-panel-new` |
| C14 | 页面上**不存在**可点的「消息」浮层入口 | 旧链路锚点已消失 |
| C15 | 可见输入元素仅 2 个：搜索框 + 聊天编辑器 | — |

### 2.2 三个决定性变化

1. **C2 + C11 推翻了「截断匹配」的全部前提。** 旧代码的 progressively-shorter-prefix
   匹配是为「DOM 文本被截断成 `某某用户名…`」设计的。实测昵称在 DOM 里始终完整，
   截断纯是 CSS `text-overflow`。旧的前缀匹配不仅多余，还是误匹配来源。
   → **改为精确等值匹配**。

2. **C3 给了确定性的会话校验信号。** 旧代码靠几何推断标题（输入框正上方同列、
   浮层边界排除导航），是浮层时代没有稳定锚点时的补偿。现在 `curConversation`
   class + `.RightPanelHeadertitle` 两个明示信号互为印证。
   → **删除 `_PROBE_JS` 全部几何推断**。

3. **C12b 是个隐藏地雷。** 编辑器空态 `textContent` 不是 `""` 而是 `\u200b`。
   任何 `if text:` 或 `== ""` 判空都会误判为「还有残留文字」。

---

## 三、目标与非目标

### 目标
1. 发送链路与同步链路整体迁移到 `/chat`，恢复可用。
2. 用确定性锚点替换几何推断，删除因浮层形态而生的补偿代码。
3. 发送成功需有**正向证据**，不再「没报错即成功」。

### 非目标（本次不做）
- 不改风控检测策略（保留遍历 frames，见 C10b）。
- 不改拟人操作（`_human_move` / `_human_click` / `_human_type`）。
- 不改面板 UI、定时任务、`runner.py`、`pyenv.py`。
- 不改 `userdata/` 隐私架构。
- 不处理「同步扫到的会话默认全标 private」（已知问题，独立处理）。
- 不处理「登录窗口不会扫完即关」（已知问题，独立处理）。

---

## 四、方案设计

### 4.1 导航：直达 `/chat`

```
page.goto("https://www.douyin.com/chat")
→ wait_for_selector('[data-e2e="conversation-item"]')
```

- 删除 `_navigate_to_im()`（点「消息」入口）、`_try_switch_to_chat_tab()`（切私信 tab）、
  `_wait_im_frame()`（找 IM iframe）。
- 常量：`DOUYIN_CHAT = "https://www.douyin.com/chat"`，保留 `DOUYIN_HOME`（登录检测用）。

**登录检测改造。** 现有 `_is_logged_in()` 用 `text=登录` 判断，在 `/chat` 上不适用
（登录面板里「登录」字样有多处，且已登录页也可能有别的「登录」文案）。
改为在 `/chat` 上做**双向判定**：

| 信号 | 判定 |
|---|---|
| 出现 `[data-e2e="conversation-item"]` 或 `.conversationConversationListwrapper` | 已登录 |
| 出现 `#login-panel-new` / `#douyin_login_comp_flat_panel` | 未登录 |
| 都没有 | 继续等，直到超时 |

比「找登录二字」更稳，且未登录时能立刻确定，不必空等。

### 4.2 会话匹配：精确等值 + 虚拟列表滚动

```python
def _find_conversation_item(name):        # 返回 handle 或 None
    for 每个 [data-e2e="conversation-item"]:
        title = .conversationConversationItemtitle 的 textContent.strip()
        if title == name: return item
    return None
```

- **精确等值**（C2/C11 支撑）。不再前缀匹配、不再 `text*=` 包含匹配。
- 群名的 `(人数)` 后缀只出现在右侧 header（C9），左侧列表项是纯群名，故列表侧直接等值。
- 找不到 → 在 `.conversationConversationListwrapper` 内滚动，每屏重新枚举；
  连续 3 屏无新 `data-index` 视为到底（C5 给了确定的到底判据）。
- 点击**会话项容器本身**（不是标题 span），沿用 `_human_click`。

### 4.3 会话校验：双信号

点击后等待，两个信号任一命中即通过：

- 该项 class 含 `conversationConversationItemcurConversation`（C3）
- `.RightPanelHeadertitle` 文本去掉 `(\d+)$` 后等于目标名（C9）

两个都读不到 → 判失败。**不再有「探测不到就保守放行」的 C 态**——
旧的 C 态是几何推断不可靠时的妥协，现在锚点确定，读不到就是真没打开，
放行只会发错人。

### 4.4 发送与成功校验（决策 1B）

```
点击编辑器 → _human_type(text) → 确认 publishRedBtn 出现（C12，证明内容进了编辑器）
→ 按 Enter → 等待 → 校验
```

**成功校验（1B，强校验）：**

1. 编辑器已清空 —— `textContent.replace('\u200b','').strip() == ''`（C12b）
2. **且** 消息列表最后一条 `[class*="messageMessageBoxcontentBox"]` 满足：
   - class 含 `isFromMe`
   - 气泡文本 `.TextMessageTextpureText` 与发送内容一致

两条都满足才算成功；否则抛错计入 `failed_count`。

> 为什么要第 2 条：仅凭「编辑器清空」无法区分「发出去了」和「内容被吞了」。
> 上一版正是因为缺正向证据，才出现过「日志说失败、面板显示成功」。

**Enter 兜底：** Enter 后若 `publishRedBtn` 仍在（说明没发出去），点击一次
`svg.e2e-send-msg-btn`，再走同一套校验。旧代码用「输入框仍含原文」判断，
在 `\u200b` 语义下不可靠。

### 4.5 手动兜底：删除（决策 2）

删除 `_open_conversation` 里的 30 秒 `time.sleep(manual)` 与 `manual_timeout` 审计分支。
匹配不到 → 留审计证据 → 直接抛错，计 `failed_count`，继续下一个目标。

连锁改动（不能只删代码）：
- `config.yaml`：删 `browser.manual_select_sec` 及其注释
- `docs/工作原理与架构.md`：删「七、人工兜底」整节，并调整后续小节编号
- `docs/配置参考.md`：删配置表行 + 示例 YAML 中的该行
- `docs/故障排查.md`：删「调大 manual_select_sec」建议，改为「核对会话名是否与抖音显示完全一致」

> 注：`manual_select_sec` 还出现在 `.workbuddy/memory/` 与
> `docs/superpowers/plans/2026-08-09-*.md`。前者非项目代码，后者是**历史 plan 存档**，
> 都不修改——改历史存档会让当时的决策记录失真。

### 4.6 同步扫描：复用同一套锚点

`scan_conversations()` 重写为枚举 `[data-e2e="conversation-item"]` 取
`.conversationConversationItemtitle`，滚动同 4.2。

- 删除 `_extract_conversation_names()` 里那套多策略 JS（title/aria-label、
  容器首行、头像祖先 + 十几条正则过滤）。那些启发式是为「没有语义埋点」写的，
  C1/C2 之后全部多余，且正是「群聊不自动识别、会话名混入消息预览」的来源。
- **顺带修一个已知问题**：C6 让群/私聊可判别，扫描结果从 `list[str]` 升级为
  `list[dict]`：`{"name": str, "type": "group"|"private"}`。

**兼容性处理（必须做）：** `panel.py` 的 `_conversations`、
`conversations_cache.json`、`/api/conversations`、`panel.html` 渲染
目前都假定 `list[str]`。方案：
- `scan()` 返回 `list[dict]`
- `panel.py` 侧做归一化：读缓存时若元素是 str 则升级为 `{"name": s, "type": "private"}`
- 前端 `convSavedMap` 逻辑保持不变，仅在渲染时用扫描到的 `type` 作为下拉框默认值

这样旧缓存文件不会炸，且群聊能自动预选「群聊」。

### 4.7 删除清单

| 删除 | 行数约 | 理由 |
|---|---|---|
| `_PROBE_JS` + `_chat_panel_probe` | ~110 | 几何推断，被 C3/C9 取代 |
| `_navigate_to_im` | ~36 | 浮层入口已不存在（C14） |
| `_try_switch_to_chat_tab` | ~18 | `/chat` 无 tab 切换 |
| `_wait_im_frame` | ~19 | IM 不在 iframe（C10） |
| `_locator_by_name_prefix` | ~23 | 截断匹配前提不成立（C2/C11） |
| `_active_conversation_name` 的 14 条选择器兜底 | ~30 | 被 C9 单一锚点取代 |
| `_extract_conversation_names` 的多策略 JS | ~80 | 被 C1/C2 取代 |
| `_conversation_list_locator` 的 4 候选 | ~16 | 收敛为 C4 单一锚点 |
| 手动兜底 | ~10 | 决策 2 |
| `_send_text` 的三态 C 分支 | ~12 | 锚点确定后不再需要 |

合计约 **350–400 行**。`_audit_dump` **保留**但简化（改用新锚点采证）。

### 4.8 保留清单（明确不动）

- `_detect_risk_control` / `_check_risk_stop` —— C10b 证明 nocaptcha 帧真实存在
- `_open_browser` / `_close_browser` / STEALTH_JS / channel=chrome
- `_human_move` / `_human_click` / `_human_type` / `_screenshot`
- `run()` 的 needs_verify / failed_count / total_count / progress_callback 语义
- `setup_login()`

---

## 五、错误处理

| 场景 | 行为 |
|---|---|
| 未登录 | `_ensure_login` 等待扫码（沿用 300s），超时抛错 |
| 会话名匹配不到（列表里没这个名字） | 审计 `no_match` → 抛错 → `failed_count+1` → 下一个目标 |
| 点击后校验不通过（点了但右侧没切过去） | 审计 `switch_fail` → 抛错 → 计失败 |
| 发送前复检发现打开的不是目标会话 | 审计 `wrong_conversation` → 抛错 → 计失败（不发错人） |
| 编辑器找不到 | 审计 `no_editor` → 抛错 → 计失败 |
| Enter + 按钮都没发出去 | 审计 `send_fail` → 抛错 → 计失败 |
| 气泡校验不匹配（`strict_verify=true`，默认） | 审计 `verify_fail` → 抛错 → 计失败（**不谎报成功**） |
| 气泡校验不匹配（`strict_verify=false`，降级） | 审计 `verify_soft_fail` → 告警 → 按成功处理 |
| 风控 | 维持现状：`RiskUnsolved` → `needs_verify=True` → 停止整轮 |

**tag 边界（实现时不得自行发明新 tag）：** 找不到名字=`no_match`；
点到了但没切过去=`switch_fail`；发送前复检不符=`wrong_conversation`。
三者语义互斥，用于区分「名字错了」「点击没生效」「切到别人了」三类根因。

---

## 六、验证方案

项目无测试套件，沿用 `verify.py` + ad-hoc 双轨。

### 6.1 `verify.py` 增补（永久自检）

- AST 断言：`douyin.py` 不再引用已删符号（`_navigate_to_im` / `_PROBE_JS` /
  `_locator_by_name_prefix` / `_wait_im_frame` / `_try_switch_to_chat_tab`）
- 断言 `DOUYIN_CHAT` 存在且 `_ensure_login` 不再依赖 `text=登录`
- 断言 `config.yaml` 无 `manual_select_sec`，且 `douyin.py` 不再读它
- 断言判空逻辑含 `\u200b`（C12b 地雷防回归）
- 行为断言：`panel` 侧 `list[str]` 旧缓存能被归一化为 `list[dict]`（喂真实临时缓存文件）

### 6.2 ad-hoc 离线断言（对已抓快照）

新链路的选择器逻辑抽成纯函数后，用本次抓取的 `page_opened.html` 快照驱动，
断言能正确选出 2 个会话、判出群/私、读出右侧标题。RED：注入变异确认翻红。

### 6.3 live 冒烟（需用户在场）

用**真实发送**验证端到端，但先约定：
- 目标临时改成用户自己的小号或收藏夹会话，避免打扰真人
- 或用户明确授权对现有目标发一条

> ⚠️ 无论哪种，live 发送必须用户明确点头才执行。

---

## 七、风险

| 风险 | 缓解 |
|---|---|
| 抖音再次改版 | 优先用 `data-e2e` / `e2e-*` 埋点（C1/C8），比 hash class 稳 |
| hash class 变动（`conversationConversationItem*`） | 这类语义前缀 class 相对稳定；`_audit_dump` 保留以便快速定位 |
| 精确等值匹配对名字更敏感 | 匹配失败时审计 JSON 里 dump 全部列表项标题，让用户一眼看出差异 |
| 强校验可能误判失败 | 校验失败留截图+JSON；已实现 `browser.strict_verify` 开关，置 `false` 即退化为「仅编辑器清空」（气泡不符只告警并记 `verify_soft_fail`），无需改代码 |
| `list[str]`→`list[dict]` 破坏旧缓存 | 归一化读取 + verify.py 行为断言覆盖 |

---

## 八、待确认

1. **6.3 live 冒烟**：是否授权真实发送？发给谁？
2. **群名 `(人数)` 后缀**：用户在面板里配置群目标时，填的是纯群名还是带后缀？
   本设计假定**纯群名**（左侧列表就是纯名）。若用户当前配置里存了带后缀的名字，
   需要在匹配时对目标名也做一次去后缀归一。

---

## 九、实施顺序（供 plan 参考）

1. `verify.py` 先补特征断言（此时应 RED —— 旧代码还在）
2. 改 `douyin.py`：导航 → 匹配 → 校验 → 发送 → 扫描
3. 改 `panel.py` 归一化 + `panel.html` 默认 type
4. 删 `config.yaml` 的 `manual_select_sec`
5. 同步 3 篇文档
6. `verify.py` 转 GREEN + ad-hoc 离线断言
7. live 冒烟（待授权）
