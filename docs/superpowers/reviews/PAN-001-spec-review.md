# PAN-001 spec 评审（两轮归档）

- 评审对象：docs/superpowers/specs/2026-09-09-panel-account-workspace-design.md（PAN-001 面板账号工作区重构）
- 评审日期：2026-09-09（两轮，同日）
- 评审方式：独立 Reviewer 子代理门禁 ×2（逐项对码取证 + 处置回读/新矛盾扫描；全程未读 userdata/）
- 结论：**APPROVED（终轮）**——首轮 CHANGES_REQUIRED（P1×1/P2×4/P3×3）经 Lead 逐条处置（spec 修订提交 7b07ad8）后，二轮聚焦复审 APPROVED（处置 9/9 合理、无新 P0/P1；P3-4 计数笔误见下，随 spec 头部状态更新一并修正）

---

## 第一轮评审（结论：CHANGES_REQUIRED）

# PAN-001 面板前端重构 spec 评审（账号优先工作区）

- 评审对象：docs/superpowers/specs/2026-09-09-panel-account-workspace-design.md（PAN-001，状态：待评审）
- 评审日期：2026-09-09
- 评审方式：独立 Reviewer 单会话门禁，逐项对码取证（只读代码/文档，未触碰 userdata/）
- 代码基线：git main @ 293ebd5（spec 初稿建档提交）
- 结论：**CHANGES_REQUIRED**（P1 一项需修订后复审；P2/P3 建议随修订一并处理）

## 一、评审发现表

| 编号 | 级别 | 位置 | 问题 | 建议处置 |
|---|---|---|---|---|
| PAN-001-P1-1 | P1 | spec 4.1 与错误处理表（零账号/未迁移行） | 单账号且无 legacy 时 aside「整个自动隐藏」，但「＋添加账号」入口只存在于 aside 底部；现码唯一入口是 panel.html:264 按钮（handler :1219 → POST /api/accounts，panel.py:1148-1155），header「⋯」菜单列举项（退出/重置运行/强制重置登录窗口等）不含添加账号，空态整页引导仅在 0 账号时出现 → 默认单号配置下失去「添加第二个账号」的既有能力。且 4.1 所称「沿用 MAI-001 单号收敛」与现码不符：现码单号时只隐藏下拉，账号栏与添加按钮保留（panel.html:1190-1192）。 | 修订 4.1：单账号收敛时保留「＋添加账号」（aside 收缩态或移入 header「⋯」菜单并写明）；错误处理表补对应场景行；可对静态预览补单账号态核验。 |
| PAN-001-P2-1 | P2 | spec 4.4 | 来源徽标「定时 21:30（取 source_id 对应任务时刻）」未定义数据路径：执行记录视图并不加载 jobs，现 /api/jobs 按账号过滤（panel.py:1103/1122），runs 视图如何做 source_id→时刻映射空白；job 已删时兜底「泛称定时」已写，但获取方式留给实现自由发挥，六节验证也没有对应断言。 | 明确数据源：runs 视图按工作区账号拉 /api/jobs 映射（缺行回落泛称定时），或后端随列表附 source 时刻字段并补一条断言。 |
| PAN-001-P2-2 | P2 | spec 4.7 / R5 | 「一键出发」文案退场只盘点了 verify:348-349 单一 token，现码该词散布广：panel.html 8 处（:265 按钮、:1059 toast、:1064 取消确认、:1103 横幅标题、:1107 中断提示等）、panel.py 5 处 409/提示文案（:1216/:1241/:1295/:1342/:1346/:1366）、batch_runner.py docstring/:334/:350/:354/:361、scheduler_daemon.py:6 注释。R5 自述「verify token 替换为唯一词防回潮」锁不住其余散点；verify:335「批量一键出发进行中」（panel.py 409 文案）刻意保留 → 新 UI 下 toast 仍显示旧词，双命名在用户可触达文案中真实并存。 | plan 内置 panel.html/panel.py「一键出发」逐点 grep 清单并定去留：UI 可触达文案（按钮/横幅/确认框/toast）统一「全部账号执行」；后端 409 文案保留属刻意取舍，请在 spec 记录确认（或同步替换 token，含 verify:335）。 |
| PAN-001-P2-3 | P2 | spec 4.6.2 | targets_detail 归一化对 dict 目标缺边界取值：现 meta_targets 对无 name 目标回落 profile_url/「?」（panel.py:582-585），快照若照抄「取 name/type」则 dict 缺 name 或缺 type 时 None 入库，chips 渲染空标签。 | 明确与 582-585 同款兜底：name = t.get(名字键) or t.get(链接键) or 「?」，type = t.get(type 键) or unknown，并把 type 缺省值写进 spec。 |
| PAN-001-P2-4 | P2 | spec 五 错误处理表 | 漏「目标弹层打开期间切换账号/视图刷新」场景：R6 只约束打开时设上下文、保存只写调用方；弹层开着切号（aside 点击触发 setActiveAccount 数据源重载，panel.html:1170-1183）时暂存区归属未定义，存在 A 号勾选误入 B 号配置/表单的串扰面。 | 补场景行：弹层打开期间切号 → 关闭弹层并丢弃暂存（或重绑上下文并按新号会话缓存重载）。 |
| PAN-001-P2-5 | P2 | spec 4.1 | aside 状态点取 /api/state 的 running_account 与 /api/accounts 的 has_login，但 /api/accounts 现仅首启与添加账号后拉取（panel.html:1152/1222），无轮询：running 红点可随 /api/state 5s 刷新（:1257）动起来，has_login 琥珀/绿点会冻结在首屏值（手动登录完成后不刷新仍显未登录）。 | 定义刷新节奏：refreshStatus 周期顺带拉 /api/accounts，或 /api/state 扩充 accounts 状态字段一并返回。 |
| PAN-001-P3-1 | P3 | spec 4.6.4 / 4.1 | has_login = browser_data 目录存在性 ≠ 登录有效（cookie 过期仍绿点/就绪）；仓库现状本无真实登录态探测，属同可靠级，但状态点文案不宜承诺「已登录」。 | UI 措辞弱化（如「就绪/有本地登录痕迹」），已知限制记入风险表。 |
| PAN-001-P3-2 | P3 | spec 4.1 | header 状态胶囊单处化后，现 accountHint 的「另一账号运行中」说明消失；置灰 busy 逻辑保留（错误表已写），但说明功能需落位。 | plan 中给账号行/状态胶囊补 title 提示（running_account 是谁）。 |
| PAN-001-P3-3 | P3 | spec 五 / verify:335 | 「批量一键出发进行中」409 文案保留与新命名并存（同 P2-2 尾），属已文档化取舍。 | 不改亦可；若 P2-2 采纳同步替换则连同 verify:335 token 一并替换。 |

## 二、已核实安全项（逐项取证）

1. 证据表行号比对（E1-E17 全部成立，实测核实）：
   - E1 nav.tabs 三页签 = panel.html:306-310 ✓；E2 折叠卡 = :330-349、CSS 折叠上限 1200px = :102 ✓
   - E3 renderConvList 行内 dselect 私聊/群聊 + 隐藏类型输入 = :920-951（行控件实于 :934-945，锚 927-946 在函数体内，成立）✓
   - E4 手打 textarea :384-385；JS 保存硬编码 type private = :768 ✓
   - E5 三层全局条 = :248-278（header :248-257 / account-bar :260-267 / batchBanner :269 / migrateBanner :271-278）✓
   - E6 refreshStatus 双处运行态 = :526-581（statusPill :527-541、runBadge :564-573、accountHint :574-575；锚 527-575 覆盖主体）✓
   - E7 meta 建档 = panel.py:586-595（含 account/texts/targets 名字串，无来源字段）；终态 = :491-512（failed/total/failed_targets/needs_verify/partial/error/success）；_save_meta 由 meta[account] 推路径 = :351-359 ✓
   - E8 run meta 无来源标记：建档 dict 无 source/source_id；守护两段式落盘 fired+run_id 反查 = scheduler_daemon.py:410-463（fired run_id :447、_record :453-460）✓
   - E9 列表/详情读 meta.targets 名字串 = panel.html:838、panel.py api_run_detail :929-956；meta 类型仅名字 = panel.py:582-585 ✓
   - E10 /api/accounts 仅 {alias, has_task} = panel.py:1064-1072（无 has_login）✓
   - E11 verify.py:325（failed_targets in panel.html）、:348-349（一键出发 + loadBatchState）、:376（新建定时任务 + loadJobs）、:377（开机自启 + 下次触发）、:378（一键迁移 + 清理旧系统任务）逐条核实 ✓；且全文件对 panel.html 的字面断言仅此 5 处（:325/:349/:376/:377/:378），E11 盘点完整 ✓
   - E12 runner/batch 未接新参数锁定 = verify.py:379-382（仅 rsrc 与 b，scheduler 不在锁定面）✓
   - E13 调度触发形态 = scheduler_daemon.py:429-433（texts/headless=None/account/targets 逐参 dict/persist_texts=False）；批量 = batch_runner.py:226-228（无 targets/persist_texts）✓
   - E14 list_runs/prune_runs = panel.py:407-454（每号 keep=3 一致）；startPoll liveLog = panel.html:646-672；详情弹窗/灯箱 = :829-893 ✓
   - E15 指南文档旧 4 页签（含独立「选会话」页与 schtasks 语义）= docs/管理面板使用指南.md:80-129（章标题 :80/:93/:105/:129）✓ 文档确已滞后，重写必要
   - E16 基线复核：2026-09-09 实测 ./.venv/Scripts/python.exe verify.py → 「通过 148 / 失败 0」，exit 0 ✓
   - E17 douyin.py:78-85 config targets 读取确认；jobs.py/守护状态机零改动目标与代码一致 ✓
2. RED 诚实性（panel.py/panel.html/scheduler_daemon.py/batch_runner.py/jobs.py/runner.py/main.py/verify.py 全量 grep）：管理目标、复制为定时任务、targets_detail、has_login、全部账号执行、「source」: source、source=scheduled、source=batch、从手动任务带入、source_id → 全部 0 命中 ✓；旧 token「一键出发」现命中（panel.html 8 处等）→ 替换类 RED 成立 ✓
3. 替换必要性/唯一性：verify:348-349 必须随按钮改名替换（否则 RED 态即绿的锁定面撕裂）；「全部账号执行」现 0 命中、无更宽/更窄 token 冲突，替换唯一 ✓
4. scheduler/batch 打标不违反 not-in 锁定：verify:379-382 只锁 runner.py 与 batch_runner.py 的 persist_texts 与边界形态 targets=；给 scheduler_daemon.py:429-433 与 batch_runner.py:226 仅加 source/source_id 关键字不引入上述两词（实测两文件现无该形态）✓
5. meta 新字段对老记录/既有断言兼容：source/source_id/targets_detail 仅在建档 dict（:586-595）增量写入，_worker 从磁盘重载 meta（:469）再合并终态，字段不丢；既有断言（verify:324-325/357-359）不锁 meta 键集合；老记录缺字段由前端兜底（spec 4.4 已写回落名字串/泛称手动/弱化展示，不迁移）✓；/api/accounts 只增 has_login 字段，老前端读取零影响 ✓
6. 方案覆盖完整性：spec 无 TBD/TODO 占位残留（aside 结构标记与来源徽标函数名标注 plan 定字节，属仓库 spec→plan 交接惯例，非违规占位）；错误处理表覆盖充分，缺口见 P1-1/P2-1/P2-4/P2-5；六节验证方案分层可执行（RED 断言 → verify 全绿 → 面板服务启动 + curl 只读接口抽查新字段 → 浏览器人工清单 → 真实运行需逐次授权列为收尾待办），实施顺序与 TDD 提交纪律一致 ✓
7. 隐私红线：本评审全程未读取 userdata/；本评审文本与 spec 全文均无真实账号别名/会话名（仅占位符）✓

## 三、处置建议

1. P1-1 修订（可连同 P2 各项小改）后独立 docs 提交，spec 逐处标注「评审 Px-Fy 修订」；
2. 复审聚焦发现表各编号回读与处置，不重开新议题；
3. 复审 APPROVED 后由 Lead 归档本评审文件、更新 spec 头部状态行与 status 文件（SPEC APPROVED），再进入 plan 起草（plan 落实 P2-2 全量 grep 清单、P2-1 数据路径与断言字节预对齐）。

---

## 第二轮聚焦复审（结论：APPROVED，终轮）

# PAN-001 spec 第二轮聚焦复审（处置复核 + 新矛盾扫描）

- 评审对象：docs/superpowers/specs/2026-09-09-panel-account-workspace-design.md（含首轮处置修订版，最新提交 7b07ad8；初稿 293ebd5）
- 评审日期：2026-09-09
- 评审方式：逐条回读首轮发现表各编号处置（grep 定位段落+真实代码行号比对）+ 修订后全篇新矛盾扫描；代码事实抽查 panel.html/panel.py/scheduler_daemon.py/batch_runner.py/verify.py 锚点；未重跑 verify.py 全量（首轮已核 148/0，代码零改动）
- 复审范围：只核首轮发现表处置与新引入矛盾，不重开已决议题
- 结论：APPROVED（首轮 9 个编号处置全部合理、标注齐备；修订未引入新 P0/P1 矛盾；仅 1 处 P3 级事实笔误建议顺手修正，不阻塞批准）

## 一、首轮发现表编号处置逐条复核（9/9 合理）

| 编号 | 处置落点（grep 核实） | 复核结论 |
|---|---|---|
| P1-1 | 4.1 L96-99：单账号且无 legacy 时 aside 整体隐藏，但「＋添加账号」入口移入 header（ghost 按钮），多账号时入口回 aside；五错误表第 7 行新增同款行为 | 合理。与建议一致；header 入口仅单号默认态出现、不与其他行冲突。代码事实：panel.html:1190-1192 现码即「单号仅隐藏下拉、保留添加按钮」（sel 隐藏判定 accs.length>1||(accs.length===1&&hasLegacy)，addAccountBtn 不在判定内），修订明确「不得回归该能力」，且本次修改点（aside/header）与现码（account-bar）不重叠 |
| P2-1 | 4.4 L135-137：执行记录视图进入时按工作区账号懒拉一次 /api/jobs 建 source_id→time 映射（视图内缓存），拉取失败/任务已删/映射缺行回落泛称「定时」；L137 明确映射函数名与是否随 runs 响应附带时刻由 plan 定字节并补断言；六节新增类断言列示映射函数名（srcTimeMap 等） | 合理。数据路径已闭合（触发侧 4.6.3 由 scheduler 打 source_id=job_id，展示侧此处定义反查），缺行回落语义与五错误表行 4（老记录兜底）不冲突 |
| P2-2 | 4.7 L176-184：「一键出发」从用户可触达文案整体退场（HTML 按钮/横幅/确认框/toast、端点返回、落盘 reason 必须统一；源码注释/docstring 不强制）；plan 内置全仓 grep 清单逐点替换；标识符 loadBatchState/batch_state.json/batch_runner.py//api/trigger-all 不改名；verify.py:335 与 :348-349 同步替换 | 合理。与建议一致并收窄到可执行口径（用户可触达面强制+注释豁免）。代码事实：verify.py:335 确为批量一键出发进行中 in p（panel.py:1216/1241/1295 三处 409 文案）、:348-349 确锁 panel.html「一键出发」+loadBatchState；replace 类断言意图一致 |
| P2-3 | 4.6.2 L160-164：meta 增 targets_detail 逐目标 {name,type} 规范化快照，name 兜底 t.get(name) or t.get(profile_url) or ?（与 panel.py:582-585 现 meta_targets 同款），type：dict 缺省 unknown、str 亦 unknown，缺值不得入 None | 合理。与建议完全一致；代码事实：panel.py:582-585 实测逐字同款，spec 引用锚正确；前端 chips 空标签风险已堵 |
| P2-4 | 4.1 L101-102：切号回调先关闭目标弹层并丢弃暂存，防止 A 号勾选串入 B 号；五错误表第 9 行同款 + 标注「重开按新号会话缓存重载」 | 合理。与 4.5（弹层上下文）及七表 R6（手动/定时上下文隔离、保存只写调用上下文）互补无冲突：弹层只服务打开它的上下文，暂存未保存即丢弃、已保存走上下文隔离，两机制并存成立 |
| P2-5 | 4.1 L93-94：has_login 与账号行副信息随 refreshStatus 周期（5s，现 panel.html:1257）顺带重拉 /api/accounts 更新；运行红点随 /api/state 5s 刷新已覆盖 | 合理。节奏定义清楚，两个数据源刷新各自闭合；代码事实：panel.html:1257 确为 setInterval(refreshStatus, 5000)。红点(has 状态源)与琥珀点(/api/accounts)可能瞬时不同步，但状态点语义红优先（4.1 明示红脉冲=运行中命中），且 has_login 仅目录存在性、运行不改变它，误差至多一周期且 UI 以红为准，不构成矛盾 |
| P3-1 | 4.1 L91-92：has_login 措辞改为「有本地登录痕迹」非「登录已生效」；七表 R8 缓解同口径 | 合理。R8 措辞「有本地登录痕迹/就绪」与 4.1 一致，UI 不承诺登录态，cookie 过期兜底语义（以实际运行为准）自洽 |
| P3-2 | 4.1 L104-106：accountHint「另一账号运行中」信息落位到状态胶囊 title 与对应账号行状态点悬停提示（running_account 是谁） | 合理。accountHint 现于 panel.html:266 账号栏内，账号栏弃用后该信息去向已定义 |
| P3-3 | 与 P2-2 合并处置：4.7 L182-183「verify.py:335 的 panel.py 批量拒绝文案 token 随改名意图同步替换」；五错误表行 3（L196）、六节替换类（L213-215）均带「评审 P2-2/P3-3」双标注 | 合理。合并处置一致；「verify:335 随改名替换」的说法在 4.7 / 五 / 六 / R2 四处口径统一（均为 panel.py 批量拒绝文案 token 换为含「全部账号执行」新句、字面量 plan 定稿并与实现字节预对齐），无漂移 |

修订标注齐全性：grep -c 评审 P 命中 12 行，覆盖全部 9 个编号（P3-3 按合并处置随 P2-2 标注于 4.7/五/六），无遗漏编号、无标注错位。

## 二、新矛盾扫描（修订后全篇）

1. 五错误表 ↔ 六验证：替换类（一键出发→全部账号执行）两侧口径一致（五表行 3「批量拒绝提示文案同步改名…verify:335 随改名替换」；六节「verify.py:335…同步替换…三者 RED 态一旧一新增，演进表按替换对计」），无互相矛盾；五表新增行 7/9 与四节 4.1 行为一一对应。
2. 4.7 ↔ R5/R9：4.7（用户可触达文案强制统一、注释豁免、标识符不改）与 R5/R9（双命名残留风险、plan 内置 grep 清单）缓解措施完全同源同口径，无新增冲突。
3. 4.1 ↔ 4.5 弹层规则：4.1 的「切号先关弹层丢暂存」与 4.5 的「手动入口写账号配置 / 定时入口写表单暂存」为不同生命周期阶段（打开中 vs 保存时），加上 R6 上下文隔离，三层防护自洽，未发现修订引入的规则打架。
4. 4.6.3 与既有锁定面字节兼容：scheduler 打标点在 scheduler_daemon.py:429-433（不在 verify.py:379-382 锁定面内）；batch_runner.py:226 现调用形态为 trigger_run(texts, headless=None, account=acc) 不带 targets/persist_texts，加 source=batch 后文中不产生 , targets= 边界形态、不触发 persist_texts/targets 锁定断言（:381-382 用 not in 锁整个文件文本），「batch 调用只加 source」自洽成立。
5. 4.1 切号引用「refreshStatus otherRunning 语义」（五表行 8）：refreshStatus 现码确含 otherRunning 判定（panel.html:554），切号不改执行中 run 的语义沿用成立。
6. 4.6.2 保留 meta.targets 名字串与 E9 兼容声明一致；老记录不迁移回填（非目标 7）与 R3/前端兜底互相印证。

扫描结论：未发现修订引入的新 P0/P1 级矛盾。

## 三、代码事实抽查（行号锚未漂移）

| spec 锚 | 实测 | 一致 |
|---|---|---|
| panel.html:1190-1192 单号隐藏下拉保留添加按钮 | bar.style.display 与 sel.style.display 判定如 P1-1 所述，addAccountBtn 独立 | ✅ |
| panel.py:582-585 meta_targets name 兜底 | (t.get(name) or t.get(profile_url) or ?) 逐字同款 | ✅ |
| panel.html:1257 refreshStatus 5s 轮询 | setInterval(refreshStatus, 5000) | ✅ |
| panel.py:547-550 trigger_run 签名区 / 586-595 建档 | 签名现为 texts/headless/account/targets/persist_texts，source 为新增点，无现码冲突 | ✅ |
| panel.py:1067-1068 /api/accounts 无 has_login | 现码仅 alias/has_task/legacy/last_account；grep panel.py+panel.html「has_login/已登录」0 命中，新字段为纯增量 | ✅ |
| scheduler_daemon.py:429-433 调用形态 | trigger_run([...], headless=None, account=..., targets=[dict(t)...], persist_texts=False) | ✅ |
| batch_runner.py:226 调用形态 | 与 E13 一致（上方已述） | ✅ |
| verify.py:335/348-349/325/376-378 | 335=批量一键出发进行中 in p；348-349=一键出发+loadBatchState in html；325=failed_targets in html；376-378=新建定时任务+loadJobs/开机自启+下次触发/一键迁移+清理旧系统任务 | ✅ |

工作树状态：panel.py/panel.html/batch_runner.py/scheduler_daemon.py/verify.py 相对 7b07ad8 零改动（git diff 空），唯一未跟踪项 examples/example-D-account-workspace.html（预览临时产物，spec 八节已声明不入 git）——代码事实锚点无漂移风险。

## 四、新发现（P3，建议顺手修正、不阻塞）

- **P3-4（事实笔误）**：4.7 L177 称「一键出发」在 panel.html 散布「8 处」，实测 panel.html 共 10 处（行 265 按钮/268 注释/511 注释/555 注释/1033 注释/1059 toast/1064 确认框/1103 横幅标题/1107 中断提示/1193 注释）。其中 6 处为真实用户可触达文案（265/1059/1064/1103/1107/1193 按钮 title 亦含），4 处为注释（按 4.7 口径不强制替换）。处置建议：4.7 括号内计数改为「10 处」或删去具体数字改述「散布广（按钮/title/toast/取消确认/横幅标题/中断提示等，共 10 处命中、含注释）」——该处本是佐证「散布面广」的修辞性盘点，plan 的全仓 grep 清单才是指令性依据，数字误差不影响实施正确性；因 spec 已把可执行语义收敛为「用户可触达文案整体退场+plan grep 清单」，若按现状放行，Lead 修订时改一处计数即可。

另注（非问题）：4.1 L96「panel.html:1190-1192」行号引用的是重构前现码形态（aside 尚未存在），语义为「现码单号能力不得回归」，表述无误读风险；六节新增类断言允许「aside 结构标记 data-ws 或等价唯一 class/id，plan 定字节」，与 4.2 的「复制为定时任务」按钮词等一致。

## 五、已核实安全（隐私红线）

1. 复审全程未读 userdata/ 任何文件；代码读取仅限 panel.html/panel.py/batch_runner.py/scheduler_daemon.py/verify.py 及 spec 本身。
2. spec 与本文档均以占位表述（「某账号/A 号/B 号」）指代账号，未出现真实账号别名、会话名或发送内容；examples/ 预览文件未入库（git untracked），spec 八节已声明不依赖其提交。
3. 本复审输出不含任何真实运行/账号数据引用。

## 六、处置建议

- spec 状态行可更新为「已批准（2026-09-09 Reviewer APPROVED）」；本复审 markdown 归档为 docs/superpowers/reviews/PAN-001-spec-review.md（保留两轮全文，头部结论=终轮 APPROVED）。
- 可选跟进（不阻塞批准）：4.7 的「8 处」计数改「10 处」或删数字；进入 plan 阶段时全仓 grep 清单与 verify 替换断言按「断言为准绳」预对齐字节。
- 首轮全部 9 个编号处置合理、标注齐备，无新 P0/P1 矛盾，裁决 APPROVED。
