# MAI-001 多账号目录隔离 — Code Review（代码评审）

- 日期：2026-09-06
- 评审对象：提交串 `5d6dc02`→`956012d`（HEAD `61221ad`，状态文件提交），diff 基线 = 已签 plan commit `68bd66b`
- 评审方法：逐文件读实现代码（main.py 651 行 / panel.py 1314 行 / runner.py 115 行 / verify.py 353 行 / panel.html 1020 行 / config.yaml）；独立复跑 `verify.py`；AST 扫描顶层重复定义；`node --check` 复验 JS 语法；`git grep` 隐私扫描；核对事故根因是否暴露新代码缺陷
- 结论：**APPROVED**（P0 无漏网；P1 无；P2 × 3 不阻塞建议项）

---

## 一、已签 plan 关键形态落地核验

| plan 锁定项 | 代码落点（实测行号） | 判定 |
|---|---|---|
| 账户数据函数显式 alias、无隐式默认 | main.py:180 `load_user_data(alias)`、:191 `save_user_data(alias,data)`、:199 `update_schedule_time(alias,time_str)`、:206 `update_message_texts(alias,texts)`、:214 `update_targets(alias,targets)`——alias 均为第一位置参数、无默认值 | ✓ |
| `load_config(alias=None)` 双入口 | main.py:70-86：None 只合并 config.yaml 公开键、不碰私有；alias 给定才合并私有 + 覆盖 `browser.user_data_dir` | ✓ |
| panel 包装 `load_config(account=None)` | panel.py:234-239 → `_main_load_config(account)`；panel main() 启动读 port 用无参（:1270） | ✓ |
| 入口解析层「恰 1 账号」兜底唯一化 | main.py:364-386 `resolve_account`：显式→用之；恰 1→沿用；>1→exit 2；legacy→exit 2；零账号→exit 2。数据函数内部无兜底 | ✓ |
| runner 账号透传 | runner.py:71-90：`--account` 解析→缺省走 `resolve_account(None)`（SystemExit→`_crash` 留痕 exit 2）→`panel.api_state(account)`→`trigger_run(...,account=account)`→`_load_meta(run_id,account)` | ✓ |
| `.running` 守卫 O_EXCL+pid 自愈 | main.py:304-356：`_pid_alive`（tasklist /FI）、`acquire_run_guard`（`os.O_CREAT|os.O_EXCL|os.O_WRONLY`、陈旧 pid 探测删除重试一次）、`release_run_guard`（unlink） | ✓ |
| 守卫覆盖六路 + 「锁→守卫→线程」顺序 + 早退释放 | ① runner/面板触发：panel.py:486-543（进程内锁检查 :504-506 → acquire :507 → 起线程 :533；线程启动异常 try/except release+re-raise :536-542）；② login：panel.py:546-571 acquire、:574-591 worker finally release；③ sync：panel.py:624-648 acquire、:651-674 worker finally release；④ CLI 手动：main.py:406-420 acquire+finally release；⑤ CLI 登录：main.py:631-642 acquire+finally release；⑥ 迁移：main.py:591-598 CLI + panel.py:1085-1098 API，均 acquire+finally release | ✓ |
| run meta 携带 account；`_save_meta` 从 meta 推路径 | panel.py:301-309（缺 account 抛 ValueError 防串号）、:519-521 meta 初始化含 account | ✓ |
| 截图/明细按 meta.account 反查 + 穿越防护不放宽 | panel.py:323-332 `_find_run_account`（遍历账号目录找 meta）、:860-884 `api_run_detail`、:887-902 `api_run_screenshots`、:945-975 `_send_screenshot`（resolve + `startswith(base)` 前缀校验原样保留，base 换为账号 run_dir） | ✓ |
| `_ensure_conversations_for` 读/存/切号三处自愈 | panel.py:175-184 定义；读：:905-910 `api_conversations` 开头；存：:1192-1205 save-targets 先 ensure 再以磁盘缓存为基合并（不直接信内存）；切号：:1132-1139 `/api/select` 生效时 ensure；sync 后置归属 :666；启动初始化归属 :1280-1297 | ✓ |
| 账号解析统一入口 `_resolve_account` | panel.py:259-275：显式→校验在列表；动作路径无 account→None（端点 400）；只读缺省→last→唯一→None | ✓ |
| 动作端点强制显式 account | panel.py:1140-1259：setup-login/sync/trigger/save-targets/save-message/tasks POST/disable/enable/delete 全部 `_resolve_account(merged, action=True)`，None→400「缺少 account」 | ✓ |
| adopt-legacy 无 schedule.time 不静默删旧任务 | panel.py:1106-1131：tm 缺失→400 明确提示，不删旧任务 | ✓ |
| migrate 补全账号骨架 | main.py:278-294：迁移后补 browser_data/runs/user_data.yaml/conversations_cache 四类标准件 | ✓ |
| `ensure_userdata` 收窄 | main.py:59-67：只建 userdata/ 与 accounts/，不再建顶层私有骨架 | ✓ |
| `legacy_pending` A1 锚定 | main.py:223-245：targets 非空 或 browser_data 非空目录 或 runs 非空目录；默认骨架（'在吗'/21:30）不算 | ✓ |
| 别名校验含 Windows 保留设备名 | main.py:135-149：`VALID_ALIAS_RE` + `WINDOWS_RESERVED_NAMES`（CON/PRN/AUX/NUL/COM1-9/LPT1-9，大小写不敏感） | ✓ |
| `task_name(alias)` 前缀语义 | main.py:359-361；panel.py:113 `TASK_NAME_PREFIX`；create_task/change_task/query_system_task 按账号任务名（panel.py:760-804、687-722） | ✓ |
| verify 第 4 节调用点适配（P1-2） | verify.py:143/149/155 三处 `panel.api_tasks("main")`；stub `lambda *a, **k`（:141/148） | ✓ |
| verify 第 3 节按账号探测 + RED 退回 | verify.py:79-134：`_account_layer` 探测→aliases 非空逐号 `_probe_task(task_name(a))`；空→旧单任务名分支 | ✓ |
| verify MAI 断言与 plan v2 字面一致 | verify.py:277-344：P1-4 修订后 `"ACCOUNTS_ROOT" in m and '"accounts"' in m`（:283）；finally 成对断言 `"release_run_guard()" in m and "finally:" in m`（:313-314）；守卫/CLI/runner/panel/config 断言与 plan Task 1 一致 | ✓ |
| douyin.py 发送核心零改动 | `git diff 68bd66b HEAD --name-only` 不含 douyin.py | ✓ |
| config.yaml real_chrome_profile 互斥警告 | config.yaml:29-31 注释含「多账号目录隔离（MAI-001）…必须保持 false…串号」 | ✓ |
| 重复定义已清（tester 抽检项） | AST 顶层扫描 main/panel/runner/verify/douyin 五文件：重复定义 = 0（`task_name`/`resolve_account` 各仅 1 处，main.py:359/364） | ✓ |
| panel.html JS 语法 | `node --check` 提取 script 块：通过 | ✓ |
| `renderEmptyState` display 清理修复 | panel.html:960-968：`sections.forEach(s => { s.style.display = empty ? "none" : ""; })`——有账号后清除内联 none，交回 CSS 控制 | ✓ |
| 跨账号运行置灰 + 徽标 | panel.html:524-544：`otherRunning = s.running_account && s.running_account !== activeAccount`→触发/保存/登录/同步按钮 disabled；runBadge「运行中: X」；accountHint 文案 | ✓ |
| fetch 封装自动附 account | panel.html:413-427 `api()`：GET 拼 query、POST 入 body；全文件仅 3 处裸 fetch（封装内部 :427、/api/shutdown :608、/api/select :939——后两者无需 account 或已带 alias body） | ✓ |

## 二、独立实测（不凭汇报数字）

- `verify.py` 实测：**通过 101 / 失败 0，exit 0**（与 Coder/Lead 汇报一致）。
- 顶层重复定义 AST 扫描：五文件均无重复（`13eb699` 去重有效）。
- `node --check` panel.html script 块：通过。
- 隐私扫描：`git grep` 真实会话名（<会话3>/<会话4>）在本次 MAI-001 diff（13 文件）中**无命中**；唯一命中在历史提交 `a5a494a` 的旧 spec 文件（非本次范围）；状态文件已清洁（Lead 已清）。
- 环境核查：8765 端口无监听、`userdata/accounts/` 为空、顶层旧数据仍在（真实迁移属 Task 7 用户操作，符合预期）、无 `.running`/`panel_state.json` 残留。

## 三、事故根因独立判断（Lead 要求）

**结论：事故根因是环境（旧面板进程 + Windows 允许双进程 bind 同端口），非新代码缺陷。**

独立验证：新代码 `/api/trigger`（panel.py:1215-1225）先 `_resolve_account(merged, action=True)`，缺 account → 400「缺少 account」拒绝——该拒绝路径存在且形态正确。事故中执行发送的是 8765 端口上**改造前的旧面板进程**（旧代码 `trigger_run(texts, headless=False)` 无 account 校验、无守卫），测试请求被旧进程按旧逻辑执行。新代码的 400 拒绝路径未被证明失效（请求根本没到达新进程）。Coder 的失误在于冒烟前未查端口占用 + 对动作端点发了未授权 POST——教训已写入其 skill，处置到位（进程全停、配置恢复、无残留）。**无需代码改动**；建议 Task 7 用户真实迁移前再确认 8765 无旧进程。

## 四、P2 建议项（不阻塞，可自愿采纳）

- **C1**：main.py:39-42 `USER_DATA_PATH/CONV_CACHE_PATH/RUNS_DIR/BROWSER_DATA_DIR` 四个模块级常量已无任何引用（全库 grep 仅定义处），属收窄后死常量，建议顺手删除（不影响行为）。
- **C2**：panel.html:976 `setActiveAccount(e.target.value, null)` 的 `accs`/`keepCurrentTab` 参数在函数体内未使用（:936-949），属死参数，建议清理签名。
- **C3**：panel.py `/api/migrate`（:1085-1098）先 `acquire_run_guard(alias)` 后由 `migrate_legacy_to_account` 内部做 `validate_alias`——非法别名会先创建 `.running`（内容含非法 alias 字符串，无害）再失败释放。建议把 alias 校验提到守卫获取前，更干净（当前行为无危害）。

---

## 五、结论

**APPROVED**。提交串忠实落地已签 plan（版本 2）锁定的全部关键接口契约与防串号/守卫/自愈形态；verify 实测 101/0 exit 0；重复定义已清；douyin.py 零改动；事故根因确认为环境问题、新代码拒绝路径完好；本次 diff 隐私干净。P2×3 为可选清理项。代码评审关卡通过，可进入 Tester 验证留证。
