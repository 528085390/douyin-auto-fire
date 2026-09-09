# PAN-001 面板前端重构为账号优先工作区（手动任务/定时任务/执行记录一体化 + 目标弹层共用 + 记录固化来源）— 实施计划（plan）

- 日期：2026-09-09
- Task-ID：PAN-001
- 状态：待用户签字（Reviewer APPROVED 后由用户在会话明确「批准」才可进入 IMPLEMENT）
- 依赖的 approved spec：`docs/superpowers/specs/2026-09-09-panel-account-workspace-design.md`
  （2026-09-09 Reviewer APPROVED，`reviews/PAN-001-spec-review.md` 两轮终轮通过；spec 免签生效；
  首轮 P1-1/P2-1~P2-5/P3-1~P3-4 已并入 spec 正文，本 plan 按修订后正文实施）

---

## 一、目标与验收

按 spec 四章实现：面板整体按账号组织（左账号栏 + 账号内三视图：手动任务/定时任务/执行记录）；
手动任务 = 每账号一条任务卡（目标摘要 + 文案 + 立即执行 + 复制为定时）；定时任务与手动共用同一
目标管理弹层（类型小标签点切，不再手打目标文本）；每次执行向 run meta 固化来源与目标类型快照；
批量动作文案统一为「全部账号执行」（BAT-001 语义、串行错峰纪律与后端结构零改动）。

验收标准（全绿条件）：

1. verify.py 基线 2026-09-09 实测 **通过 148 / 失败 0**（spec E16）。
2. Task 演进按五节表推进，收尾 **FAIL = 0、exit 0、通过 167**（167 = 148 + T1 新增 6 + T2 新增
   3 + T3 新增 10；替换类断言 :335/:348-349 随改名意图同步修订，不计入新增数）。
3. 单元级文本断言分层转绿即 Task 验收；面板只读接口 curl 抽查 + 浏览器人工核验清单（七节）由
   Tester/用户在 TEST 阶段执行并留 `test-results/PAN-001-IMPL.md` 证据。
4. 真实运行（manual/scheduled/batch 来源落盘验证）需用户逐次授权（见七节收尾待办），未授权前
   不默认执行。
5. 隐私终扫 0 命中；文档（管理面板使用指南）与代码分开独立 docs 提交。

## 二、任务拆分与提交

| Task | 内容 | 提交（中文 conventional） |
|---|---|---|
| 1 | panel.py run meta 固化 source/source_id/targets_detail + /api/accounts has_login；scheduler_daemon 打 scheduled 标、batch_runner 打 batch 标（先 RED：6 条新断言全 FAIL） | RED：`test(verify): PAN-001 T1 RED 6 条来源固化断言（期望 148/6）`；GREEN：`feat(panel): PAN-001 run meta 固化触发来源与目标类型快照 + accounts has_login` |
| 2 | 「一键出发」用户可触达文案统一为「全部账号执行」：panel.py 7 处（含 1 注释）、scheduler_daemon.py 1 处注释、batch_runner.py 5 处；verify:335 拒绝文案断言随改名替换 + 3 条负断言（p/s/b 不得含旧词） | RED：`test(verify): PAN-001 T2 RED 批量文案收敛断言（期望 153/4，含 :335 替换）`；GREEN：`fix(panel): PAN-001 批量动作文案统一为全部账号执行（p/s/b 用户可触达面）` |
| 3 | panel.html 工作区重构（账号左栏/手动任务卡/定时任务视图/执行记录来源徽标/共用目标弹层/运维收进 header；批量横幅压缩）；verify:348-349 批量入口断言随改名替换 + 10 条新结构断言 | RED：`test(verify): PAN-001 T3 RED 账号工作区结构断言（期望 156/11）`；GREEN：`feat(panel): PAN-001 账号优先工作区重构（左栏+三视图+目标弹层共用+来源徽标）` |
| 4 | 文档同步：管理面板使用指南.md 重写（四页签 → 账号工作区，含新字段说明）+ status 推进 IMPLEMENT 完成 | `docs: PAN-001 管理面板使用指南重写（账号工作区/来源徽标/固化参数）+ status 推进` |

代码与文档分开提交；全程直接提交 main（仓库惯例）；每个 Task 提交前后跑一次 verify 记录
FAIL/PASS（见五节演进表，以实际输出核对为准）。

## 三、Task 1 细则（后端 meta 固化，douyin.py 零改动）

### RED 断言（verify.py，插到「# --- 汇总 ---」之前；描述插入点以实际 grep 定位为准）

```python
# ★ PAN-001 run meta 固化触发来源与目标类型快照 + 账号登录痕迹字段
check("★PAN-001 run meta 记录触发来源 source", '"source": source' in p)
check("★PAN-001 run meta 携带任务 ID source_id", 'meta["source_id"] = source_id' in p)
check("★PAN-001 run meta 固化目标类型快照 targets_detail", 'meta["targets_detail"]' in p)
check("★PAN-001 账号列表含 has_login", '"has_login":' in p)
check("★PAN-001 调度触发打 scheduled 标", 'source="scheduled"' in s and "source_id=job_id" in s)
check("★PAN-001 批量触发打 batch 标", 'source="batch"' in b)
```

RED 期望：6 条全 FAIL（现码 0 命中，已实测）。GREEN 后全部转绿。

### GREEN 改动点（字节要求：以下字面量必须原样出现，断言为准绳）

1. `panel.py` `trigger_run` 签名（现 :549-550 一带）追加关键字参数，保持既有参数顺序与默认语义：
   ```python
   def trigger_run(texts: list[str], headless: bool | None = None,
                   account: str | None = None, *,
                   targets: list | None = None,
                   persist_texts: bool = True,
                   source: str = "manual",
                   source_id: str | None = None) -> str | None:
   ```
2. 建档 meta 处（现 :582-595 `meta = {...}` 前）计算类型快照，并在 meta dict 中/之后写入：
   ```python
   meta_detail = []
   for t in tgt_list:
       if isinstance(t, dict):
           meta_detail.append({"name": t.get("name") or t.get("profile_url") or "?",
                               "type": t.get("type") or "unknown"})
       else:
           meta_detail.append({"name": str(t), "type": "unknown"})
   ```
   meta dict 增一行 `"source": source,`；dict 闭合后（_save_meta 前）增：
   ```python
   if source_id:
       meta["source_id"] = source_id
   meta["targets_detail"] = meta_detail
   ```
   （兜底与 spec 4.6.2/评审 P2-3 一致；保留 `meta["targets"]` 名字串字段与 `meta["account"]` 键不动。）
3. `/api/accounts` 账号项（现 :1067-1068）增字段，字节需含 `"has_login":`：
   ```python
   "accounts": [{"alias": a,
                 "has_task": bool((query_system_task(task_name(a)) or {}).get("exists")),
                 "has_login": bool((account_root(a) / "browser_data").is_dir())},
   ```
   （account_root 已在 panel.py 作用域；字段只增不改。）
4. `scheduler_daemon.py` `_execute_job` 触发调用（现 :429-433）追加两个关键字，字节需含
   `source="scheduled"` 与 `source_id=job_id`（保持 targets/persist_texts=False 原样）：
   ```python
   run_id = panel.trigger_run(
       [str(t) for t in job["texts"]],
       headless=None, account=account,
       targets=[dict(t) for t in job["targets"]],
       persist_texts=False,
       source="scheduled", source_id=job_id)
   ```
5. `batch_runner.py` 触发调用（现 :226 一带）追加 `source="batch"`（不带 targets/persist_texts，
   不触碰 verify:381-382 的 not-in 锁定面）：
   ```python
   run_id = panel.trigger_run(texts, headless=..., account=acc, source="batch")
   ```
   （实际参数形态以现调用为准，仅追加该关键字。）

### 验收

RED 148/6 → GREEN 154/0；`git diff` 确认 douyin.py/jobs.py/main.py/runner.py 零改动。

## 四、Task 2 细则（批量动作文案统一）

### 改名全量 grep 清单（现码落点，2026-09-09 实测）

| 文件 | 行（现码） | 现文案 | 替换为 |
|---|---|---|---|
| panel.py | 234（注释） | `# BAT-001 一键出发（全账号串行批量）：…` | 去掉旧词改写，如 `# 批量全部账号执行（串行）：状态文件读写与激活判定` |
| panel.py | 1216/1241/1295 | `批量一键出发进行中，请先取消或等待结束。` | `批量（全部账号执行）进行中，请先取消或等待结束。` |
| panel.py | 1342 | `批量一键出发已在运行。` | `批量（全部账号执行）已在运行。` |
| panel.py | 1346 | `面板当前有任务/登录/同步在运行，结束后再一键出发。` | `面板当前有任务/登录/同步在运行，结束后再发起全部账号执行。` |
| panel.py | 1366 | `一键出发已启动：全部账号将顺次执行（号间错峰 15 分钟）。` | `全部账号执行已启动：全部账号将顺次执行（号间错峰 15 分钟）。` |
| scheduler_daemon.py | 6（注释） | `与手动/一键出发共用全局守卫…` | `与手动/全部账号执行共用全局守卫…` |
| batch_runner.py | 1（docstring） | `一键出发批量执行器（BAT-001 spec 4.2…）` | `全部账号执行批量执行器（串行错峰 15 分钟，独立进程）` |
| batch_runner.py | 334 | argparse description `一键出发批量执行器（BAT-001）` | `全部账号执行批量执行器` |
| batch_runner.py | 350 | `批量一键出发开始：…` | `批量全部账号执行开始：…` |
| batch_runner.py | 354 | crash 提示 `…可重按面板「一键出发」或对剩余账号单号补跑…` | `…可回到面板重按「全部账号执行」或对剩余账号单号补跑…` |
| batch_runner.py | 361 | `批量一键出发结束。` | `批量全部账号执行结束。` |

规则：**用户可触达文案（端点返回 error/message、落盘/日志 reason、横幅文案）与源码注释全清**
（本 Task 负断言要求 p/s/b 三文件 0 残留，故注释也一并不留旧词，比 spec 4.7「注释豁免」更严格，
目的为使负断言可执行且彻底防回潮）；历史 docs/superpowers/ 存档不改。

### RED 断言（verify.py）

```python
# ★ PAN-001 批量动作文案统一为「全部账号执行」（BAT-001 语义不变）
# 正断言由下方 verify:335 替换承担（替换为同一 token 的 in p 检查），此处只补负断言：
check("★PAN-001 面板源码旧批量词退场", "一键出发" not in p)
check("★PAN-001 调度器源码旧批量词退场", "一键出发" not in s)
check("★PAN-001 批量执行器源码旧批量词退场", "一键出发" not in b)
```

并把既有 `verify.py:335` 的检查从
`check("★BAT-001 批量激活期拒绝单号动作", "批量一键出发进行中" in p)`
替换为 `check("★BAT-001 批量激活期拒绝单号动作", "（全部账号执行）进行中" in p)`。

RED 期望：335 替换后 1 失败 + 3 条负断言失败 = **4 FAIL**（153/4）。
GREEN：按清单逐点替换后 335 与 3 条负断言全绿 → **157/0**。

### 验收

`grep -c 一键出发 panel.py scheduler_daemon.py batch_runner.py` = 0；verify 157/0；跑一遍既有
BAT/SCH 断言零破坏（batch_state.json/waiting_stagger 等 token 未触碰）。

## 五、Task 3 细则（panel.html 工作区重构）

### RED 断言（verify.py）

```python
# ★ PAN-001 账号优先工作区（左栏 + 三视图 + 共用目标弹层 + 来源徽标）
check("★PAN-001 账号左栏结构标记", 'id="accountRail"' in html_txt)
check("★PAN-001 工作区三视图页签",
      'data-ws="manual"' in html_txt and 'data-ws="sched"' in html_txt and 'data-ws="runs"' in html_txt)
check("★PAN-001 手动任务卡管理目标入口", "管理目标" in html_txt)
check("★PAN-001 复制为定时任务入口", "复制为定时任务" in html_txt)
check("★PAN-001 新建定时带入手动配置", "从手动任务带入" in html_txt)
check("★PAN-001 全部账号执行入口（替换一键出发）", "全部账号执行" in html_txt)
check("★PAN-001 来源徽标渲染函数", "function srcZh" in html_txt)
check("★PAN-001 定时时刻映射函数", "srcTimeMap" in html_txt)
check("★PAN-001 旧批量词从 HTML 退场", "一键出发" not in html_txt)
check("★PAN-001 旧单号触发词从 HTML 退场", "前台触发" not in html_txt and "一键触发" not in html_txt)
```

并把既有 `verify.py:348-349` 检查从
`check("★BAT-001 前端一键出发按钮与横幅", "一键出发" in read("panel.html") and "loadBatchState" in read("panel.html"))`
替换为
`check("★BAT-001 前端批量入口与横幅", "全部账号执行" in read("panel.html") and "loadBatchState" in read("panel.html"))`。

RED 期望：348 替换 1 失败 + 上 10 条新断言失败（其中 3 条为负断言：旧词现码均在）= **11 FAIL**
（156/11）。GREEN 后 → **167/0**。

### GREEN 改动点（panel.html 整页重写，行为语义要求）

1. **保留（断言锁定，必须继续存在）**：`loadBatchState`、`loadJobs`、`failed_targets`、
   「新建定时任务」「开机自启」「下次触发」「一键迁移」「清理旧系统任务」字面量；
   既有 JS 主链路（refreshStatus 5s 轮询、startPoll/liveLog、loadConversations、renderConvList、
   loadRuns/showDetail、pollConv、renderBatch、setActiveAccount 数据源切换、busy 置灰）按新 DOM
   移植保留语义。
2. **壳层**：左栏 `aside` 元素 id=`accountRail`（含账号行与状态点、底部「⚡ 全部账号执行」按钮
   与「＋ 添加账号」）；header 只留 logo/标题/单处运行状态胶囊（title 携带 running_account）/
   运维「⋯」菜单（退出面板/重置运行/强制重置登录窗口收进菜单）；批量横幅压缩为 header 下细条。
   **单账号且无 legacy**：aside 隐藏，header 显示「＋ 添加账号」ghost 按钮（id 如 `addAccountTop`，
   复用现 addAccountBtn 的别名输入+扫码引导逻辑）；多账号时 header 按钮隐藏、入口在 aside。
   `renderAccountBarState`/`renderEmptyState` 相应改写（零账号空态与迁移横幅保留）。
   状态点数据：has_login 等随 refreshStatus 顺带拉 /api/accounts 更新；运行红点读 /api/state 的
   running_account。切号回调先关目标弹层（若开）并清暂存。
3. **手动任务视图（data-ws=manual）**：任务卡含目标摘要 chips 区 +「管理目标」按钮（开弹层）+
   文案 textarea +「保存」+「立即执行」+「打开浏览器」+「复制为定时任务」（切到定时页签并预填）。
   移除内嵌扫描表格与每行类型下拉；类型以 chips 小标签展示。
4. **定时任务视图（data-ws=sched）**：守护状态卡（保留「开机自启」「下次触发」字样与启停/取消
   按钮）、任务列表（去掉账号列）、新建表单（目标区 = 摘要 chips +「管理目标」按钮，复用同一
   弹层；文案区；每天时间；保存走 /api/jobs，目标传 {name,type} 不再 JS 硬编码 private；
   「从手动任务带入」按钮预填）。「旧版迁移与清理」内容仅在 legacy 存在时展示（token 保留）。
5. **执行记录视图（data-ws=runs）**：行含来源徽标（`srcZh(src)` 渲染：manual→手动、
   scheduled→定时[HH:MM 经 `srcTimeMap` 由 /api/jobs 懒加载映射 source_id→time，失败回落泛称
   定时]、batch→批量；老记录无 source 兜底手动弱化展示）；固化摘要（目标 N + 文案截断）；
   failed_targets 红字「未送达」保留；详情弹窗增「固化参数」区（targets_detail 名称+类型标签、
   文案原文、来源与触发时刻），日志/截图/needs_verify 引导保留。
6. **目标管理弹层（共用）**：同一 DOM 弹层，手动任务与新建定时两入口设置上下文并各自暂存；
   一键同步/全选/反选/保存所选沿用现有端点；会话行类型 = 可点切换小标签（私聊⇄群聊），
   移除 dselect 展开下拉形态。
7. **文案收敛**：html 内不得残留「一键出发」「一键触发」「前台触发」「目标会话」旧页卡用语
   （「目标会话」改称「目标」或随 chips 语境），header 副标题同步。

### 验收

RED 156/11 → GREEN 167/0；重写后人工抽查 DOM（浏览器打开页面）：三视图可切换、切号联动、
目标弹层增删保存、复制/带入预填、来源徽标与老记录兜底、批量入口与横幅。

## 六、RED/GREEN 演进表与纪律

| Task | 动作 | FAIL | PASS |
|---|---|---|---|
| 基线 | 2026-09-09 实测 | 0 | 148 |
| 1 | RED 6 条（全部新断言，现码 0 命中） | 6 | 148 |
| 1 | GREEN 后 | 0 | 154 |
| 2 | RED（:335 替换 1 失败 + 新断言 3 失败） | 4 | 153 |
| 2 | GREEN 后 | 0 | 157 |
| 3 | RED（:348 替换 1 失败 + 新断言 10 失败） | 11 | 156 |
| 3 | GREEN 后 | 0 | 167 |
| 4 | 文档，verify 不变 | 0 | 167 |

纪律：
- **断言为准绳**：GREEN 失败时对照断言逐字修实现措辞/字面形态，不许改断言迁就实现；例外仅为
  T2/T3 中 :335/:348-349 的「替换类」断言——该替换属 spec 4.7/六 拍板的改名意图，本 plan 已
  预对齐字节，属正式修订而非迁就。
- 同一文件的多处修改逐条 patch、逐条看 lint，不并行批量发同文件 patch；改坏用
  `git checkout -- <file>` 还原后重做。
- 新增模块落地先做静态自引用核对再冒烟；HTML 重构后先开页面点一遍主路径再提交。
- 每 Task 提交信息按二节表；代码与文档分开提交；隐私红线：任何提交文件不得出现真实账号别名/
  会话名/发送内容（示例一律占位）。

## 七、收尾验收（IMPLEMENT 完成后由 Tester 执行并留证据）

1. verify.py **167/0**、exit 0（真实命令输出入 test-results）。
2. 只读接口 curl 抽查（不动真实账号数据）：/api/accounts 返回含 has_login；/api/state 正常；
   /api/jobs、/api/runs 正常返回（老记录无 source/targets_detail，前端兜底以浏览器核验为准）。
3. 浏览器人工核验清单（面板操作由用户执行并确认）：
   a. 左栏切号 → 三视图数据联动切换；单账号形态下 header「＋添加账号」可用；
   b. 手动任务「管理目标」弹层：同步/勾选/类型点切/保存所选 → 摘要 chips 更新；
   c. 「复制为定时任务」与「从手动任务带入」预填正确；
   d. 定时任务保存后列表可见、目标为独有副本、类型保留；
   e. 执行记录：手动/定时/批量来源徽标、老记录兜底展示、详情含固化参数区与截图；
   f. 「全部账号执行」入口、压缩横幅与取消；运维「⋯」菜单内退出/重置可用。
4. 真实运行（manual/scheduled/batch 三种来源 run meta 落盘验证）**需用户逐次授权**：授权后跑
   一次无害文案冒烟 + 一条定时补跑 + 一次全部账号执行，核对 run meta source/source_id/
   targets_detail 落盘与徽标展示；未授权前留收尾待办，如实报告。

## 八、遗留与签字入口

- examples/example-D-account-workspace.html（布局预览，未跟踪）由用户决定删除或保留，默认不入 git。
- 本 plan 经 Reviewer APPROVED 后仍需用户签字（头部状态改「已批准（用户签字 YYYY-MM-DD）」）方可
  进入 IMPLEMENT；签字后按二节表逐 Task 执行。
