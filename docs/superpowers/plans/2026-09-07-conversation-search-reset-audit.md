# 会话查找全量扫描 + 失败目标执行记录审计 — 实施计划（plan）

- 日期：2026-09-07
- Task-ID：SIV-002
- 状态：**已批准（用户）**（2026-09-07 用户签字生效；签字后进入 IMPLEMENT）
- 依赖的 approved spec：`docs/superpowers/specs/2026-09-07-conversation-search-reset-audit-design.md`
  （2026-09-07 Reviewer APPROVED，`reviews/SIV-002-spec-review.md`）

---

## 一、目标回顾（spec 摘要）

1. 修复「部分失败」根因：`_find_conversation_item` 每次查找前把会话列表滚动位置
   重置到顶部，再做既有全量向下扫描，杜绝跨目标滚动残留导致的目标漏扫（误判 no_match）。
2. 失败目标写入执行记录审计：douyin.py 记录 `failed_targets` 名单 → panel.py 写入
   run meta JSON（`failed_targets` 字段 + 错误文案带名单）→ panel.html 列表页标红、
   详情页显示「未送达」名单。
3. verify.py 新增 6 条防回归断言（先 RED 后 GREEN）；同步架构文档。

## 二、验收标准

1. `verify.py` 基线 2 FAIL（账号任务未注册，环境态，非本任务）；RED 阶段恰为 8 FAIL
   （既有 2 + 新增 6，且新增失败原因均为「保证未实现」，非笔误）；GREEN 阶段回到 2 FAIL。
2. douyin.py `_find_conversation_item` 每次查找前执行 `scrollTop = 0` 重置并等待
   虚拟列表重渲染；原有向下滚动/stagnant 判定逻辑不变。
3. douyin.py 运行级失败统一记入 `self.failed_targets`（按名去重、每次运行重置）；
   风控中止（RiskUnsolved/needs_verify）不记入。
4. run meta JSON 在失败时含 `failed_targets` 名单；错误文案带「失败目标：…」。
5. panel.html 执行记录列表页目标列失败项标红；详情页显示未送达名单（旧记录无该字段时兜底不崩）。
6. 文档同步：`docs/工作原理与架构.md` 会话匹配节 + 执行记录字段说明。

## 三、任务分解（逐 Task 独立提交）

### Task 1：verify.py 先 RED（test:/chore: 提交）

文件：`verify.py`（5b 节 SIV-001 断言块后新增 4.5 断言块）

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

验证：`./.venv/Scripts/python.exe verify.py` → 期望 FAIL 恰为 8（既有 2 + 新增 6），
逐条确认新增 6 条失败原因。退出码捕获用重定向文件再 `echo EXIT=$?`（勿用管道取码）。

### Task 2：douyin.py 实现（fix:/feat: 提交）

文件：`douyin.py`

1. **4.1 滚动重置**（`_find_conversation_item`，:440 起）：
   - 方法开头、`seen_idx` 初始化前插入：

     ```python
     # ★ SIV-002：抖音会保留上一次会话查找遗留的滚动位置，而虚拟列表排序随
     # 消息刷新（发过的会话浮到顶部）。不重置就从深处向下滚，目标在当前位置
     # 上方时永远扫不到 → 误判 no_match。每次查找先滚回顶部再做全量向下扫描。
     wrap = self.page.query_selector(self.LIST_SEL)
     if wrap:
         try:
             wrap.evaluate("el => { el.scrollTop = 0; }")
         except Exception:  # noqa: BLE001  重置失败走原逻辑（不更糟）
             pass
         time.sleep(random.uniform(0.5, 0.9))  # 等虚拟列表重新渲染顶部条目
     ```

   - 注意：sleep 与 evaluate 用 try 包裹（spec 风险 R1 / 评审 P2#3）；注释含 `SIV-002`
     便于未来断言（评审 P2#1）。
2. **4.2 失败名单**：
   - `__init__`（:102 failed_count 旁）新增 `self.failed_targets: list[str] = []`；
   - `run()`（:930 附近）`self.failed_count = 0` 旁新增 `self.failed_targets = []`；
   - 失败分支（:951-954 except）append：`if name not in self.failed_targets: self.failed_targets.append(name)`；
   - `RiskUnsolved` 分支（:946-950）不动。

验证：`./.venv/Scripts/python.exe verify.py` → 新增 6 条中 douyin.py 相关 4 条转绿。

### Task 3：panel.py + panel.html 实现（feat: 提交）

文件：`panel.py`、`panel.html`

1. **panel.py `_worker`**（:434-450）：
   - `meta["failed"] = failed_n` 后：`failed_names = list(getattr(streak, "failed_targets", None) or []); if failed_names: meta["failed_targets"] = failed_names`；
   - 错误文案改造（:447-450）：有名单时 `（失败目标：A、B。）`，无名单走原文案兜底
     （评审 P2#2：与前端同一 `m.failed_targets` 来源）。
2. **panel.html**：
   - `loadRuns`（:700）：目标列渲染时 `(r.failed_targets || []).includes(t)` 的项包
     `<span style="color:var(--err)">…</span>`；
   - `showDetail`（:723-724）：`m.failed_targets` 存在时追加
     `<br><span style="color:var(--err)">未送达：${m.failed_targets.join("、")}</span>`。

验证：`./.venv/Scripts/python.exe verify.py` → 新增 6 条全绿，仅剩既有 2 FAIL（GREEN）。

### Task 4：文档同步（docs: 提交）

- `docs/工作原理与架构.md`：会话匹配节追加「查找前重置列表滚动位置（SIV-002）」；
  执行记录节补充 `failed_targets` 字段与面板展示说明。
- 更新 `status/SIV-002.md` 关卡推进记录。

验证：`verify.py` 仍为 2 FAIL（文档不锁断言）；`git status` 干净（仅既有 error.log untracked）。

## 四、验证方案（Tester 口径）

| 阶段 | 动作 | 期望 |
|---|---|---|
| RED | Task 1 后跑 verify | FAIL=8（既有 2 + 新增 6），新增全为「保证未实现」 |
| GREEN | Task 2+3 后跑 verify | FAIL=2（仅账号任务未注册环境态） |
| 语法 | `python -m py_compile douyin.py panel.py` | exit 0 |
| 数据 | 构造含 failed_targets 的 run meta 走 loadRuns/showDetail 渲染 | 列表页标红、详情页名单 |
| live 冒烟（待授权） | 对含列表底部目标的真实目标组发一次 | 无 no_match；run JSON 含 failed_targets |
| 收尾核对（未授权冒烟时） | 下一次真实运行后看执行记录 | 失败目标名单可见、无新增 no_match |

**如实声明**：verify.py 锁结构不锁运行时「重置后真的扫到上半区」；该局限由
live 冒烟（需用户授权）或下次真实运行核对弥补。

## 五、风险与回退

| 风险 | 缓解 |
|---|---|
| scrollTop=0 抛错/异常 | try/except 吞掉走原逻辑（最坏与现状一致） |
| 等待不足首轮读旧条目 | 0.5~0.9s 等待；向下滚动覆盖全列表兜底 |
| 文案改动破坏既有断言 | 已 grep 确认 verify.py 无锁定 panel.py:448 文案；新 token 随断言锁定 |
| 实现中偏离 spec | 本 plan 即 spec 4.1-4.6 的落地映射，逐条对应；diff 只触及列明位置 |

## 六、提交纪律

- 文档与代码分开独立提交；commit message 中文 conventional：
  Task1 `test: SIV-002 RED…`、Task2 `fix: SIV-002 会话查找滚动重置 + failed_targets 记录`、
  Task3 `feat: SIV-002 执行记录失败目标审计（meta+面板）`、Task4 `docs: SIV-002 架构文档同步`。
- 每个 Task 验证通过后再提交；GREEN 达成后向用户报告并请示 live 冒烟授权。
