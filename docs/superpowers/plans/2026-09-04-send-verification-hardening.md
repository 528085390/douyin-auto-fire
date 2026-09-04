# 发送成功判定可信化（编辑器落地正向证据 + verify 修绿）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 堵住发送成功判定的「空真」漏洞——发送前必须拿到正向证据「文字真实进入编辑器」（失败自动重试一次，再失败以新审计 tag `type_fail` 阻断），空/纯空白内容在入口拦截，并把已漂移的 verify.py 自检修回全绿（exit 0）且锁住这些保证。

**Architecture:** `_send_text` 入口先 `text = text.strip()` 并拦截空/纯空白（评审 P1-1：否则 `""==""` 恒真，漏洞残留）；「点击+输入」与「按 Enter」之间用新方法 `_editor_text_equals(text)`（内部剥空白后等值）作无条件前置断言；`publishRedBtn` 红信号降级为纯提示（E1：真发出也可能不红）；「发送后清空」铁证保留但退居第二步。落地比较抽成方法（评审 P1-2）：未来收窄比较规则只改方法体，verify 断言不锁内联字面。verify.py 审计 tag 循环中已删除的 `verify_soft_fail` 换为 `type_fail`，并新增 5 条防回归断言（先 RED 后 GREEN）。文档同步 `docs/工作原理与架构.md` 与 `docs/配置参考.md` 的发送判定/审计 tag 表述。

**Tech Stack:** Python 3.11 / Playwright (sync API, channel=chrome, headless=False) / 无测试框架，自检靠 `verify.py`（`.venv/Scripts/python.exe verify.py`）。

**Spec:** `docs/superpowers/specs/2026-09-04-send-verification-hardening-design.md`（commit 5d96d2a，评审修订见同文件）

## Global Constraints

- 用户决策：文字没进输入框 → **自动重试一次再阻断**（聚焦/弹层瞬态自愈；定时无人值守避免断火花）。
- 用户决策：live 冒烟安排在实现完成后再决定（本次 Task 1–3 不包含）。
- 比较口径（评审 P1-1/P1-2 修订）：入口先 `text = text.strip()` 并**拦截空/纯空白**（否则等值比较在空文本上恒真，漏洞残留）；落地比较统一走新方法 `_editor_text_equals(text)`（内部剥空白后等值）——**方法体是未来收窄比较规则的唯一出口**（spec R1），verify 断言只锁方法存在 + 调用形态 + 非空拦截，不锁内联比较字面。
- 审计 tag 边界：本次只新增 `type_fail`（输入层面）；`type_fail` 与 `send_fail` 互斥（type_fail 时尚未按 Enter）。不得自行发明其他新 tag。
- 软校验降级路径保留：气泡失配仍降级放行、截图命名 `sent_soft_` 前缀、不截审计件（现状不变）。
- 不改动：风控检测（`_detect_risk_control` / `_check_risk_stop`）、拟人操作（`_human_move/click/type`）、会话匹配与切换、`_last_bubble`、扫描、面板 UI、`runner.py`、`pyenv.py`、定时任务、隐私架构。
- 隐私红线：任何进 git 的文件（含本 plan、verify.py、文档）**不得出现**真实会话名、真实发送内容。示例一律用占位符（真实目标只存在于 gitignored 的 `userdata/`）。
- 验证命令一律：`cd D:/ai_project/douyin-auto-fire && ./.venv/Scripts/python.exe verify.py`
- 提交粒度：每个 Task 结束提交一次，commit message 用中文 conventional commits（先例：`test(verify): 增补 /chat 链路特征断言（当前预期 RED）`、`fix(douyin): …`、`docs: …`）。

## File Structure

| 文件 | 责任 | 本次动作 |
|---|---|---|
| `verify.py` | 永久自检（无测试框架下的事实标准） | 审计 tag 循环 `verify_soft_fail`→`type_fail`；新增 5 条防回归断言；同步注释 |
| `douyin.py` | 自动化核心 `DouyinStreak` | `_send_text` 入口加非空拦截 + 新增 `_editor_text_equals` 方法 + 输入阶段落地断言/重试一次/`type_fail` 阻断；红信号措辞降级；`strict_verify` 成员注释同步 |
| `docs/工作原理与架构.md` | 架构文档 | 「六、发送强校验」整节（:85-96）改写；「七、审计机制」tag 表（:102）更新 |
| `docs/配置参考.md` | 配置文档 | `strict_verify` 表行（:20）与 YAML 注释（:60-62）更新 |
| `config.yaml` | 公开配置 | `strict_verify` 注释（:14-15）更新（值不变，仍 `true`） |

**关键接口契约（跨 Task 共享，评审 P1-1/P1-2 修订）：** 本次不新增跨模块接口、不改既有方法签名。新增物为：审计 tag 字面量 `"type_fail"`（`_send_text` 内 `_audit_dump("type_fail", target_name)`）；新方法 `def _editor_text_equals(self, text: str) -> bool`（内部 `return self._editor_text() == text.strip()`，收窄比较规则只改方法体）；`_send_text` 入口拦截 `text = text.strip()` 后 `if not text: raise RuntimeError(...含「纯空白」文案)`；输入阶段两处判定 `if not self._editor_text_equals(text):`；重试日志文案「自动重试一次」。verify.py Task 1 断言锁定：方法存在于 AST（`_editor_text_equals in dfuncs`）、调用形态（`"self._editor_text_equals(text)" in d`）、入口拦截（`"text = text.strip()" in d` 且含「纯空白」）、重试文案、旧警告已删。Task 2 必须照此实现，**不得内联比较绕过方法、不得删入口拦截**。

---

### Task 1: verify.py 先 RED（断言新保证 + 清掉陈旧断言）

**Files:**
- Modify: `verify.py:170-177`（审计 tag 齐备注释段 + tag 循环，紧随其后插入新断言）

**Interfaces:**
- Consumes: 无（本 Task 只加断言）
- Produces: 5 条会在 Task 2 后转 GREEN 的断言 + tag 循环新成员 `type_fail`。Task 2 实现者以此为准绳。

> 为什么先 RED：项目没有测试框架，`verify.py` 就是事实上的测试命令。
> 先让它红，才能证明 Task 2 的绿不是假绿（TDD：没见过失败的绿是安慰剂）。

- [ ] **Step 1: 替换 verify.py 的注释段与 tag 循环（:170-177）**

将：

```python
# 审计 tag 齐备：spec 五、错误处理登记的 tag 必须都在代码里发得出来
# （注意：verify_soft_fail 是降级路径的"假成功"标记，绝不能漏——漏了会让
#  verify.py 假绿放过对强校验的误删，正是"verify 没拦住回归"的反面教材）
# 注：verify_fail 硬失败 tag 已在迁移中移除——气泡文本比对不可靠（抖音合并/乱序），
# 真实发送改用「输入框清空+最后 isFromMe 容器」铁证判定，气泡失配只记 verify_soft_fail 不阻断。
for tag in ("no_match", "switch_fail", "wrong_conversation",
            "no_editor", "send_fail", "verify_soft_fail"):
    check(f"审计 tag {tag} 已实现", f'"{tag}"' in d)
```

替换为：

```python
# 审计 tag 齐备：spec 五、错误处理登记的 tag 必须都在代码里发得出来
# 注：verify_fail 硬失败 tag 已在 /chat 迁移中移除；气泡文本失配只降级放行
# （sent_soft 命名截图，不截审计件）。type_fail 为「文字没进输入框」tag
# （2026-09-04 spec 4.1：发送前落地正向证据，重试一次仍失败才发）。
for tag in ("no_match", "switch_fail", "wrong_conversation",
            "no_editor", "send_fail", "type_fail"):
    check(f"审计 tag {tag} 已实现", f'"{tag}"' in d)

# ★ 发送判定空真漏洞（2026-09-04 spec 4.1，评审 P1-1/P1-2 修订）：
# 文字必须真实进入编辑器，否则「发送后输入框清空」铁证在空编辑器上恒真；
# 空/纯空白内容必须在入口被拦截（否则 ""=="" 恒真，漏洞残留）。
check("★文字没进输入框会重试一次再阻断", '"自动重试一次"' in d)
check("★落地比较抽成 _editor_text_equals（收窄只改方法体，不破断言契约）",
      "_editor_text_equals" in dfuncs and "self._editor_text_equals(text)" in d)
check("★空/纯空白内容在 _send_text 入口拦截", "text = text.strip()" in d and "纯空白" in d)
check("★误导性旧警告（可能内容没进编辑器）已删除", "可能内容没进编辑器" not in d)
check("★软校验降级路径保留（sent_soft 命名）", '"sent_soft"' in d)
```

- [ ] **Step 2: 跑 verify.py 确认 RED**

Run: `./.venv/Scripts/python.exe verify.py`
Expected: **失败 5 项、exit 1**：
1. `审计 tag type_fail 已实现`（douyin.py 尚无该字面量）
2. `★文字没进输入框会重试一次再阻断`（无「自动重试一次」文案）
3. `★落地比较抽成 _editor_text_equals…`（无该方法与调用）
4. `★空/纯空白内容在 _send_text 入口拦截`（无 `text = text.strip()` 与非空判断）
5. `★误导性旧警告（可能内容没进编辑器）已删除`（旧代码 :653 仍有该文案）

> 若失败数 ≠ 5：停下来核对是否误改了其他断言，先修回再继续。

- [ ] **Step 3: 提交（红测试独立提交，仓库先例 `849fab6`）**

```bash
git add verify.py && git commit -m "test(verify): 发送落地断言先 RED（tag 循环 verify_soft_fail→type_fail）"
```

---

### Task 2: douyin.py 实现入口拦截 + 落地正向证据 + type_fail（转 GREEN）

**Files:**
- Modify: `douyin.py:106-108`（`strict_verify` 成员注释）
- Modify: `douyin.py:636-641`（`_send_text` 头部：入口非空拦截，置于 wrong_conversation 复检之前）
- Modify: `douyin.py:565` 之后（`_editor_text` 与 `_last_bubble` 之间新增 `_editor_text_equals` 方法）
- Modify: `douyin.py:647-656`（`_send_text` 输入阶段：等值断言 + 重试 + type_fail + 红信号降级）

**Interfaces:**
- Consumes: 既有 `_human_click(el, label)` / `_human_type(text)` / `_editor_text()` / `_locate_chat_input()` / `_audit_dump(tag, name)` —— 均不改签名。
- Produces: `_editor_text_equals` 方法、入口拦截（`text = text.strip()` + `if not text:`）、输入阶段两处 `if not self._editor_text_equals(text):`、重试日志「自动重试一次」、`type_fail` 审计。字面形态必须与 Task 1 断言逐字一致（评审 P1-2：**不得**内联 `_editor_text() != text.strip()` 绕过方法）。

- [ ] **Step 1: 更新 `strict_verify` 成员注释（douyin.py:106-108）**

将：

```python
        # 发送成功强校验。默认严格（编辑器清空 + 气泡回读双条件）；
        # 若某账号下气泡 class 与锚点不匹配导致误判，可置 false 退化为仅查编辑器清空。
        self.strict_verify = bool(self.browser_cfg.get("strict_verify", True))
```

替换为：

```python
        # 发送成功强校验（2026-09-04 spec 4.1）：文字进入编辑器 + 发送后清空为无条件双证据；
        # 气泡文本比对仅在 strict=True 时附加（false 时跳过比对，读不到本人容器只告警）。
        self.strict_verify = bool(self.browser_cfg.get("strict_verify", True))
```

- [ ] **Step 2: 入口非空拦截（douyin.py:636-641，评审 P1-1）**

将：

```python
    def _send_text(self, text: str, target_name: str = ""):
        """发送并强校验。决策 1B：必须有正向证据，不能「没报错即成功」。"""
        if target_name and not self._conversation_is_open(target_name):
```

替换为：

```python
    def _send_text(self, text: str, target_name: str = ""):
        """发送并强校验。决策 1B：必须有正向证据，不能「没报错即成功」。"""
        # 入口口径（评审 P1-1）：空/纯空白是配置错误，直接拦截——否则
        # text.strip()=="" 与空编辑器等值恒真，走通旧空真路径被记 success。
        text = text.strip()
        if not text:
            raise RuntimeError(
                "发送内容为空或纯空白（配置问题），已跳过该目标以免空真误报成功。")
        if target_name and not self._conversation_is_open(target_name):
```

- [ ] **Step 3: 新增 `_editor_text_equals` 方法（douyin.py:565 之后，评审 P1-2）**

在 `_editor_text` 方法结束（`return (el.text_content() or "").replace(self.ZWSP, "").strip()`）与 `_last_bubble` 定义之间插入：

```python
    def _editor_text_equals(self, text: str) -> bool:
        """编辑器当前文本是否与发送文本一致（双方剥空白后比较）。

        收窄比较规则（如 slate 对 emoji/连续空格的归一差异）只改这里——
        spec R1 应急出口：verify.py 只锁方法存在与调用形态，不锁方法体。
        """
        return self._editor_text() == text.strip()
```

- [ ] **Step 4: 改造 `_send_text` 输入阶段（douyin.py:647-656）**

将：

```python
        self._human_click(el, "聊天输入框")
        self._human_type(text)
        time.sleep(random.uniform(0.3, 0.7))

        # 内容确实进了编辑器：发送按钮此时应变红
        if not self.page.query_selector("svg.e2e-send-msg-btn.publishRedBtn"):
            logger.warning("输入后发送按钮未变红，可能内容没进编辑器")

        self.page.keyboard.press("Enter")
```

替换为：

```python
        # --- 输入阶段：文字必须真实进入编辑器（2026-09-04 spec 4.1）---
        # 否则「发送后输入框清空」铁证在空编辑器上恒真（空真），漏发也会被记 success。
        # 聚焦/弹层多为瞬态问题：自动重试一次（用户决策），仍失败则审计 type_fail 阻断。
        self._human_click(el, "聊天输入框")
        self._human_type(text)
        time.sleep(random.uniform(0.3, 0.7))
        if not self._editor_text_equals(text):
            logger.warning(
                "文字未进入输入框（编辑器=%r），自动重试一次…", self._editor_text())
            time.sleep(random.uniform(0.5, 1.0))
            el = self._locate_chat_input()  # 重新定位，避免 handle 失效
            if el:
                # 重试安全：_human_type 开头 Ctrl+A+Backspace 预清空（:300-302），
                # 部分落地也会被清掉重打，不会叠加成重复文本——勿在别处自行清理
                self._human_click(el, "聊天输入框")
                self._human_type(text)
                time.sleep(random.uniform(0.3, 0.7))
        if not self._editor_text_equals(text):
            self._audit_dump("type_fail", target_name)
            raise RuntimeError(
                "文字未能进入输入框（可能被弹层遮挡或焦点丢失），已跳过以免误判成功。")

        # 内容确实进了编辑器（上方已断言）。按钮变红仅作提示：实测真发出也可能不红
        # （2026-09-04 运行日志 E1），不作判定依据
        if not self.page.query_selector("svg.e2e-send-msg-btn.publishRedBtn"):
            logger.info("输入后发送按钮未变红（DOM 类名漂移时常见），以编辑器内容为准")

        self.page.keyboard.press("Enter")
```

> 提醒：`Enter` 之后的一切（补点按钮、清空铁证、气泡软校验、sent/sent_soft 截图、风控复检）**保持原样不动**。

- [ ] **Step 5: 跑 verify.py 确认 GREEN**

Run: `./.venv/Scripts/python.exe verify.py`
Expected: **失败 0、exit 0**（通过项预计 61，以实际打印为准）。

> 若仍红：失败原因应为「字面形态不一致」（如措辞/方法名与 Task 1 断言有出入），对照断言逐字修正——不许改断言迁就实现。

- [ ] **Step 6: 扫代码确认没有残留旧文案（文档层留到 Task 3 一并扫）**

Run: `grep -n "可能内容没进编辑器" douyin.py verify.py` → 预期无输出。
Run: `grep -n "verify_soft_fail" douyin.py verify.py` → 预期无输出（该字面量已从代码与自检中整体移除）。

- [ ] **Step 7: 提交**

```bash
git add douyin.py verify.py && git commit -m "fix(douyin): 发送前文字落地正向证据+空内容入口拦截（type_fail/非空双重堵空真）"
```

---

### Task 3: 文档同步（架构文档 / 配置参考 / config 注释）

**Files:**
- Modify: `docs/工作原理与架构.md:85-96`（「六、发送强校验」整节）与 `:102`（审计 tag 表）
- Modify: `docs/配置参考.md:20`（`strict_verify` 表行）与 `:60-62`（YAML 注释）
- Modify: `config.yaml:14-15`（`strict_verify` 注释，值不动）

**Interfaces:**
- Consumes: Task 2 后的真实语义（入口非空拦截 + 落地/清空双证据无条件；气泡比对仅 strict=true 附加；tag 表含 type_fail、不含 verify_fail/verify_soft_fail）
- Produces: 与代码一致的文档（verify.py 不锁文档文案，但文档错误会让下次体检再次报漂移）

- [ ] **Step 1: 改写「六、发送强校验」节（架构.md:85-96）**

将 :89、:91、:93-94、:96 四段替换为：

```markdown
发送动作：点击聊天输入框 → 按字输入 → **确认文字进入编辑器（经 `_editor_text_equals` 与发送内容等值比对；失败自动重试一次，再失败审计 `type_fail` 并跳过该目标）** → 回车（`Enter` 即发送）→ 若输入框仍有残留再补点「发送」按钮 → **铁证：输入框已清空** → 气泡回读仅作附加信心 → 截图 → 复检风控。发送内容为空/纯空白属配置错误，在入口直接拦截，不进入发送流程。

发送成功判定（2026-09-04 spec 4.1）由两级证据构成，缺一不可：

- **前置（无条件）**：文字真实进入编辑器——经 `_editor_text_equals(text)` 与发送文本等值（比较规则收窄只改该方法体）。空真防护：若打字从未落地，编辑器全程为空，则「清空」判定恒真、会漏发误报成功，故必须先断言落地；
- **铁证（无条件）**：发送动作后编辑器已清空——`textContent` 剥掉零宽字符 `\u200b` 后为空。

`browser.strict_verify=true` 时在上述双证据之外再附加气泡文本比对（最后一条 `isFromMe` 容器文本包含发送内容），失配只告警并按成功降级处理，截图命名 `sent_soft_` 前缀（不截审计件，不谎报失败）；`false` 时跳过该气泡比对（文字落地 + 清空仍强制）。
```

> 注：整段替换后「强校验必须两条都满足」的旧列表（:91-94 原三行）随上合并入，注意不残留孤儿行。

- [ ] **Step 2: 更新审计 tag 表（架构.md:102）**

将：

```markdown
所有失败/异常路径（未匹配 `no_match`、切错会话 `wrong_conversation`、点到了但没切过去 `switch_fail`、找不到编辑器 `no_editor`、发送后输入框仍有残留 `send_fail`、气泡校验不匹配 `verify_fail` / 降级放行 `verify_soft_fail`）都会调用 `_audit_dump(tag, name)`，产出两份证据：
```

替换为：

```markdown
所有失败/异常路径（未匹配 `no_match`、切错会话 `wrong_conversation`、点到了但没切过去 `switch_fail`、找不到编辑器 `no_editor`、文字没进输入框 `type_fail`、发送后输入框仍有残留 `send_fail`）都会调用 `_audit_dump(tag, name)`，产出两份证据：
```

- [ ] **Step 3: 更新 `strict_verify` 表行（配置参考.md:20）**

将：

```markdown
| `browser.strict_verify` | 布尔 | `true` | 发送成功校验强度。`true`=输入框清空 + 最后一条气泡回读双重校验（推荐）；`false`=仅校验输入框清空，气泡不符只告警并留审计证据。仅在气泡锚点因抖音改版失配、导致真实发送被误判为失败时才降级。 |
```

替换为：

```markdown
| `browser.strict_verify` | 布尔 | `true` | 发送成功校验强度。无条件双证据：文字进入编辑器 + 发送后输入框清空（空/纯空白内容入口拦截）。`true`=再附加最后气泡文本比对（推荐）；`false`=跳过气泡比对（气泡锚点失配时的应急退化）。 |
```

- [ ] **Step 4: 更新 YAML 注释（配置参考.md:60-62 与 config.yaml:14-15）**

配置参考.md：

```yaml
  # 发送成功校验强度：true=文字落地+输入框清空+气泡文本比对（推荐）；
  # false=跳过气泡比对（文字落地+清空仍强制；空内容入口拦截）
  strict_verify: true
```

config.yaml（值 `strict_verify: true` 不动）：

```yaml
  # 发送成功校验强度。无条件双证据：文字进入编辑器 + 发送后输入框清空（空内容入口拦截）；
  # true=再附加最后气泡文本比对（推荐）；false=跳过气泡比对（锚点失配时应急退化）
  strict_verify: true
```

- [ ] **Step 5: 回归自检 + 全库残留扫**

Run: `./.venv/Scripts/python.exe verify.py` → Expected: 失败 0、exit 0。
Run: `git diff --stat` → 应恰好 3 个文件：`docs/工作原理与架构.md`、`docs/配置参考.md`、`config.yaml`（douyin.py/verify.py 已在 Task 2 提交）。
Run: `grep -rn "verify_soft_fail\|可能内容没进编辑器" douyin.py verify.py docs/ config.yaml` → 预期仅剩 `docs/superpowers/` 历史档案（08-10 及更早 spec/plan，**不修改**——改历史存档会让当时的决策记录失真）。

- [ ] **Step 6: 提交**

```bash
git add docs/工作原理与架构.md docs/配置参考.md config.yaml
git commit -m "docs: 同步发送判定/审计 tag 语义（架构文档+配置参考+config 注释）"
```

> **收尾核对（评审 P1-3，流程兜底，无文件改动）：** 若未授权 Task 4 冒烟，下一次真实运行
> （手动前台触发或 21:30 定时首跑）后，人工核对一次执行记录日志：是否有**非预期**的
> `type_fail`（重试后仍失败 = R1 类误报信号）。失败是大声的（audit + failed_count），
> 不会静默谎报——此核对只用于尽早发现比较规则需按 spec R1 收窄的情况。

---

### Task 4: live 冒烟（待授权，实现全绿后单独决定）

**触发条件：** Task 3 完成后用户授权（spec 八-1）。用户提供：
- 目标会话名 `<SMOKE_TARGET>`（建议小号或收藏夹会话，避免打扰真人）
- 测试内容 `<SMOKE_TEXT>`（用一条无害短句，如「冒烟测试」+ 时间戳）

- [ ] **Step 1: 一次性注入运行（只发该目标，不改 userdata 配置）**

```bash
cd D:/ai_project/douyin-auto-fire && ./.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); from main import load_config, setup_logging; from douyin import DouyinStreak; cfg=load_config(); cfg['targets']=[{'name':'<SMOKE_TARGET>','type':'private'}]; cfg.setdefault('message',{})['texts']=['<SMOKE_TEXT>']; cfg['message']['random']=False; cfg['screenshot_dir']='userdata/runs/smoke_test'; setup_logging(cfg); DouyinStreak(cfg).run()"
```

（用户在场观察可见浏览器；`screenshot_dir` 自动 mkdir。）

- [ ] **Step 2: 核对证据**
- 日志出现「文字未进入输入框…自动重试一次」→ 仅当触发瞬态，属预期兜底；
- 产生 `sent_<SMOKE_TARGET>.png`（强校验通过）或 `type_fail` 审计件（重试后仍失败）；
- **R1 校准点**：若强校验因「内容确实进了但比较不等」（emoji/换行等 slate 归一差异）误报 type_fail → 记录真实 editor 文本与原文差异，另开小任务**只改 `_editor_text_equals` 方法体**收窄比较（如折叠空白，不放松非空主口径）——verify 断言不锁方法体，收窄不破坏断言契约（评审 P1-2）。不得顺手改本 plan 已提交代码之外的东西。

- [ ] **Step 3: 收尾**
冒烟产物在 gitignored 的 `userdata/runs/smoke_test` 内，可留档或删除；无代码改动则无需提交。

---

## 验证总览

| Task | 命令 | 期望 |
|---|---|---|
| 1 | `verify.py` | RED：失败 5 项、exit 1 |
| 2 | `verify.py` | GREEN：失败 0、exit 0 |
| 3 | `verify.py` + `git diff --stat` | 失败 0、exit 0；恰好 2 个文档文件 + config.yaml |
| 4（可选） | 一次性注入命令 | 见 Task 4 Step 2 观察点 |
