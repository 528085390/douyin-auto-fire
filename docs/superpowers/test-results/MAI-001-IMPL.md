# MAI-001 多账号目录隔离 — 实施验证证据（test-results）

- **任务**: MAI-001-IMPL（多账号目录隔离：账号别名 + 每账号独立环境/数据 + 面板账号切换）
- **验证人**: @tester（Verification Engineer）
- **验证日期**: 2026-09-06
- **结论**: **PASS**
- **关联**: spec `docs/superpowers/specs/2026-09-04-multi-account-isolation-design.md`（版本 2 已批准）；plan `docs/superpowers/plans/2026-09-04-multi-account-isolation.md`（版本 2 用户签字）；状态 `docs/superpowers/status/MAI-001.md`
- **实施提交串**: `5d6dc02`(Task1 RED) → `0f52e09`(Task2 main 账号层+守卫) → `96dde10`(Task3 CLI+runner) → `de701d5`(Task4 panel) → `13eb699`(去重) → `162d12c`(Task5 panel.html) → `956012d`(Task6 文档) → `61221ad`(状态)
- **隐私红线**: 本文件进 git，故不出现真实会话名/真实账号别名；事故证据仅以占位与 gitignored `userdata/` 路径引用。

---

## 一、验证方法（可复现）

1. **逐 Task 隔离验证**：对每个实施 commit 建 detached worktree（`git worktree add --detach <tmp> <commit>`），用项目 venv 解释器跑该 commit 自带的 `verify.py`，避免污染 coder 工作区；验证毕 `git worktree remove --force` + `git worktree prune` 清理（已确认 `git worktree list` 仅剩主仓库）。
2. **验证命令**（仓库事实标准，无测试框架）：
   ```
   cd D:/ai_project/douyin-auto-fire && ./.venv/Scripts/python.exe verify.py
   ```
   期望形态：`通过 N / 失败 0`、`exit 0`；失败时 `exit 1`（README 约定）。
3. **只读纪律**：全程仅跑 verify 与只读检查（git diff/show/grep、AST 扫描、netstat、yaml 只读解析）。**未启动面板、未 POST 任何动作端点、未触碰真实 userdata 写路径**（遵守 lead 纪律与事故教训）。
4. **不凭汇报数字**：所有计数均为本机实测输出，非引用 coder/lead 汇报。

---

## 二、逐 Task verify 计数（RED → GREEN 实测）

| Task | commit | 通过/失败 | exit | traceback 命中 | plan 预期 | 判定 |
|---|---|---|---|---|---|---|
| 1 verify RED | `5d6dc02` | **66 / 35** | 1 | 0 | 大量失败、exit 1、MAI 节红、旧节绿、**禁止 traceback** | ✓ 符合 |
| 2 main 账号层+守卫 | `0f52e09` | **86 / 15** | 1 | 0 | 旧绿、MAI 红减少；仍红=CLI/runner/panel/config 注释 + 「finally 成对」(P2-1 时序) | ✓ 符合 |
| 3 CLI+runner | `96dde10` | **92 / 9** | 1 | 0 | CLI 三条+runner 两条转绿；仍红=panel 相关+config 注释 | ✓ 符合 |
| 4 panel 数据层/API | `de701d5` | **100 / 1** | 1 | 0 | MAI 接近全绿；仍可能红=config 注释；第 4 节 `api_tasks("main")` 无 TypeError | ✓ 符合 |
| 去重（tester 抽检项） | `13eb699` | **100 / 1** | 1 | 0 | 不回退 | ✓ 符合 |
| 5 panel.html | `162d12c` | **100 / 1** | 1 | 0 | 不回退（HTML 未被 verify 锁，计数不变） | ✓ 符合 |
| 6 文档同步 | `956012d` | **101 / 0** | **0** | 0 | **失败 0、exit 0** | ✓ 符合 |
| 状态（代码同 Task6） | `61221ad`(HEAD) | **101 / 0** | **0** | 0 | 全绿不回退 | ✓ 符合 |

> 计数单调收敛 35→15→9→1→0，与 plan 的 RED→GREEN 时序逐 Task 吻合；全程 **0 traceback / 0 AttributeError / 0 TypeError**（grep `Traceback|AttributeError|TypeError|NameError` 各 commit 命中均为 0），满足 plan「禁止 traceback 崩溃」硬约束。

### 各 Task 红项明细（实测 `[FAIL]` 行）

- **`5d6dc02`（35 红）**：全部为 MAI 新断言（账号根目录/account_root/create_account/list_accounts/migrate_legacy_to_account/legacy_pending/validate_alias×3、load_user_data/save_user_data/update_schedule_time/update_message_texts/update_targets 收 alias、load_config 双入口、.running 守卫路径/O_EXCL/pid 探测/acquire/release/finally 成对、runner --account/account=、CLI --account/--migrate/--list-accounts、panel _resolve_account//api/accounts//api/migrate//api/tasks/adopt-legacy/meta account/load_config(account)/worker 守卫/截图反查、config 注释）。旧节（1/2/4/5/6/7/8）全绿。
- **`0f52e09`（15 红）**：「finally 成对」(P2-1 待 Task3) + runner×2 + CLI×3 + panel×8 + config 注释×1。账号原语/守卫定义/load_config 双入口等已转绿。
- **`96dde10`（9 红）**：panel×8（_resolve_account/三端点/meta account/load_config(account)/worker 守卫/截图反查）+ config 注释×1。CLI 三条、runner 两条、「finally 成对」均已转绿（P2-1 时序兑现）。
- **`de701d5`/`13eb699`/`162d12c`（各 1 红）**：仅 `config.yaml real_chrome_profile 注释含多账号互斥警告`——该项 plan 明确归 Task 6，时序正确。
- **`956012d`（0 红）**：config 注释落地，全绿。

---

## 三、verify 断言「零迁就实现」核验

plan Global Constraints 明令：**断言不得迁就实现（只允许 stub 适配）**。核验 `git diff 5d6dc02 HEAD -- verify.py`：

- RED 提交（`5d6dc02`）之后，verify.py 的**唯一**改动是第 4 节三处 `panel.api_tasks()` → `panel.api_tasks("main")`（`de701d5` 引入），并附 P1-2 注释说明用占位账号 + stub 已 mock。**这正是 plan Task 4 Step「P1-2 必做」指定的 stub 适配**（api_tasks 签名收必选 account 后保第 4 节不崩），属 RED 本分，非改断言迁就。
- **所有 MAI 断言字面（账号层/防串号/守卫/panel/config）自 RED 起逐字未动**——GREEN 是靠实现去匹配断言，而非反向。✓ 符合「断言为准绳」。

---

## 四、结构性只读检查（防串号关键形态）

| 检查项 | 命令/方法 | 实测结果 | 判定 |
|---|---|---|---|
| douyin.py 发送核心零改动 | `git diff 68bd66b HEAD --stat -- douyin.py` | 空（自签字基线零改动） | ✓ |
| 守卫五路覆盖 | `grep -n acquire_run_guard/release_run_guard main.py runner.py panel.py` | main.py：CLI 手动运行(408/420)、--migrate(592/598)、--setup-login(634/641)；panel.py：trigger_run worker(507/538)、login(557/567/591,A2)、sync(634/644/674,A2)、adopt-legacy/migrate 端点(1091/1098)。runner 经 trigger_run 合流。 | ✓ 全路覆盖 |
| 守卫释放与 finally 成对 | `grep -c "finally:" main.py panel.py` | main.py 3、panel.py 6；acquire/release 调用点均处 try/finally 结构 | ✓ |
| 切号会话内存自愈 | `grep -n _ensure_conversations_for panel.py` | 定义@175；调用@910(读路径 api_conversations)、1138(save-targets 保存前)、1195(/api/select 切号)、1286——读/存/切号三处自愈齐备(P1-1) | ✓ |
| 截图/明细按 meta.account 反查 | `grep -n _find_run_account panel.py` | 定义@323；调用@862/889/952（明细/截图只读反查，不依赖当前账号,P2-4） | ✓ |
| 顶层重复定义已清 | AST 扫描 HEAD 全部 *.py | douyin/main/panel/pyenv/runner/verify 均 `OK`（0 重复）。tester 中途抽检发现的 main.py `task_name`/`resolve_account` 双定义（301/306 与 389/394）已由 `13eb699` 删除第一组 | ✓ |
| config real_chrome_profile 互斥 | `grep -n real_chrome_profile config.yaml` | 值 `false` + 多账号互斥警告注释（MAI-001） | ✓ |
| run meta 写 account 字段 | `grep -n '"account"' panel.py` | trigger_run worker@521 写 `"account": account`；_save_meta@303 从 meta["account"] 推路径(P2-5) | ✓ |

---

## 五、隐私红线核验

- **MAI-001 新增/改动文件零隐私命中**：`git diff 68bd66b HEAD --name-only` 列出的全部文件中，对真实会话名/账号别名 grep 无命中。✓
- **userdata/ 未被 git 跟踪**：`git ls-files userdata/` 为空。✓ 真实数据只在 gitignored `userdata/`。
- **既有历史 spec 命中（非本次回归）**：真实会话名出现于 `docs/superpowers/specs/2026-09-04-send-verification-hardening-design.md`，经 `git grep -c 68bd66b` 确认该命中在**签字基线即已存在**（属上一特性的历史存档）。按仓库规则历史 spec 不改（改历史存档会让决策记录失真）。**此非 MAI-001 引入，不计入本次失败项**，但记录在案供 lead 知悉。

---

## 六、事故证据记录（2026-09-06 真实发送，Coder 自报，tester 独立核验）

> 按 lead 要求记入证据。tester 仅做只读取证，不评判处置（处置由 lead 已核实）。

- **事故**：Task 5 冒烟时 8765 端口挂着改造前启动的旧面板进程（Windows 允许双进程 bind 同端口），测试 `POST /api/trigger` 被旧进程按旧代码（无 account 校验）执行，12:58 向两个真实会话各发出一条文本 "x"，不可撤回。
- **物证（gitignored userdata/，只读核验）**：
  - `userdata/runs/20260906_125754/` 存在，含 2 张发送截图（`001_..._sent_<会话A>.png`、`002_..._sent_soft_<会话B>.png`，文件名含真实会话名故此处占位）。
  - `userdata/runs/20260906_125754.json`：`status=success, total=2, failed=0, error=False`。
  - **关键法证**：该 meta **无 `account` 字段**——而新代码 trigger_run worker（panel.py:521）必写 `"account": account`。meta 缺 account 字段客观印证此 run 由**改造前旧进程**执行，与新代码缺陷无关（支持 lead/reviewer 的根因初判：环境问题=旧进程+双 bind，非新代码 400 拒绝路径失效）。
- **处置核验（只读）**：
  - 8765 端口当前无监听（`netstat -ano | grep 8765` 空）——新旧面板确已停止。✓
  - 无 `userdata/.running`、无 `userdata/panel_state.json` 残留。✓
  - 顶层 `userdata/user_data.yaml` 只读解析：keys=`message/schedule/targets`，targets 2 条，**无残留 "x" 值**（被覆写内容已恢复）。✓
  - `userdata/accounts/` 为空（真实迁移属 Task 7 用户操作，符合预期）。✓
- **对验证结论的影响**：事故发生在 Task 5 冒烟环节（coder 侧），**不影响 verify.py 的 RED→GREEN 客观计数**（verify 不发送消息、不触发动作端点）。最终 HEAD verify 101/0 exit 0 为干净实测。事故根因为环境（旧进程双 bind），未暴露新代码防串号缺陷。

---

## 七、环境残留核验

- `git status --short`：仅 `error.log`（2026-08-22 历史遗留，非 MAI 相关，plan Task 6 已注明不提交）+ `docs/superpowers/reviews/MAI-001-code-review.md`（reviewer 评审进行中，未跟踪）。无其他未跟踪/未提交改动。✓
- `git worktree list`：仅剩主仓库（验证用临时 worktree 已全部清理）。✓

---

## 八、结论

**PASS** — MAI-001 实施串（Task 1-6 + 去重）通过逐 Task 客观验证：

1. verify 计数单调收敛 **35→15→9→1→0**，最终 **101 / 0、exit 0**，全程 0 traceback，与已签 plan 的 RED→GREEN 时序逐 Task 吻合。
2. verify 断言**零迁就实现**（RED 后唯一改动为 plan 指定的 api_tasks stub 适配）。
3. 防串号关键形态全部落地：douyin.py 零改动、守卫五路覆盖（runner/面板触发/login/sync/CLI 手动+登录+迁移）且 finally 成对、`_ensure_conversations_for` 读/存/切号三处自愈、截图/明细按 meta.account 反查、重复定义已清、config real_chrome_profile 互斥警告。
4. 隐私红线：MAI-001 改动文件零命中、userdata 未跟踪、user_data.yaml 无事故残留。
5. 事故已独立取证并记录（§六），根因为环境（旧进程双 bind），未暴露新代码缺陷；不影响 verify 客观结论。

**移交**：
- @reviewer 代码评审可并行/接续进行（本证据供引用，尤其 §六 事故法证 meta 无 account 字段）。
- @lead 两关过后终审，向 @user 交付 Task 7 人工核对清单（真实迁移/扫码/错峰定时由用户执行——tester 不代跑真实发送）。
- 既有历史 spec 隐私命中（§五）非本次回归，建议 lead 知悉即可，不在本任务处置。
