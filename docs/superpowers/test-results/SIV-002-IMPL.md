# SIV-002 实现测试证据（Tester）

- 任务: 会话查找全量扫描 + 失败目标执行记录审计
- 测试日期: 2026-09-07
- 测试方式: 逐提交点 verify.py 自检 + py_compile 语法检查（仓库无测试框架，以 verify.py 为准）
- **结论: PASS**（RED 真红 8/8 → GREEN 回 2/2 环境态；语法全过）

## 实测证据（命令 + 真实输出）

### 基线（改动前）
```
./.venv/Scripts/python.exe verify.py
EXIT=1
[FAIL] 账号任务 DouyinAutoFire-<别名1> 已注册 :: 未找到 DouyinAutoFire-<别名1>
[FAIL] 账号任务 DouyinAutoFire-<别名2> 已注册 :: 未找到 DouyinAutoFire-<别名2>
```
通过 94 / 失败 2（既有环境态：账号定时任务未在面板注册，与本任务无关）。

### Task 1 RED（提交 594f315，verify.py 新增 6 条断言）
```
EXIT=1
grep -c "[FAIL]" = 8
[FAIL] 账号任务 DouyinAutoFire-<别名1> 已注册
[FAIL] 账号任务 DouyinAutoFire-<别名2> 已注册
[FAIL] ★查找会话前重置列表滚动位置（scrollTop=0）
[FAIL] ★重置后等待虚拟列表重渲染
[FAIL] ★记录失败目标名单 failed_targets
[FAIL] ★run 每次重置 failed_targets
[FAIL] ★panel 写入 meta.failed_targets
[FAIL] ★面板列表页标红失败目标
```
✅ RED 恰为 8 = 既有 2 + 新增 6，新增全部因「保证未实现」失败。

### Task 2+3 GREEN（提交 efed3d5 + 37f2ad7）
```
./.venv/Scripts/python.exe -m py_compile douyin.py panel.py   →  exit 0
./.venv/Scripts/python.exe verify.py
EXIT=1
grep -c "[FAIL]" = 2
[FAIL] 账号任务 DouyinAutoFire-<别名1> 已注册
[FAIL] 账号任务 DouyinAutoFire-<别名2> 已注册
```
✅ 新增 6 条全绿，仅剩既有 2 环境态 FAIL。

### Task 4 收尾（提交 be6d6d8 后复跑）
```
EXIT=1，FAIL=2（同上，文档改动不影响断言）
git status --short → 仅 ?? error.log（历史遗留 untracked，非本次产物）
```

## 数据链路核对（静态走查，非真实发送）

- douyin.py：失败统一进 `run()` 的 `except Exception` → `failed_targets.append(name)`（按名去重）；
  `RiskUnsolved`（风控）分支先于它捕获，整轮中止不记入名单（spec 4.2 语义）；
- panel.py：`getattr(streak, "failed_targets", None) or []` → 有名单写 `meta["failed_targets"]` 且
  错误文案带「失败目标：A、B。」；无名单走原文案（兼容旧版）；
- panel.html：列表页 `failedSet.has(t)` 标红、详情页 `m.failed_targets.length` 渲染「未送达」行；
  旧 run JSON 无该字段时 `|| []` / `&& length` 兜底，不崩。

## 未验证项（如实声明）

- ~~**live 冒烟未执行**~~ → **已授权并执行 PASS（2026-09-07，见下节）**。

## 六、live 冒烟（用户已授权执行，2026-09-07 23:29）

对 <别名2> 账号临时配置 3 目标跑真实发送（临时改 `user_data.yaml`，冒烟后已恢复原 7 目标）：

- `<会话7>`（顶部目标）+ `<会话11>`（上次列表深处目标，对照验证滚动重置）+ `烟测SIV002不存在`（假名字，验证 failed_targets 审计）

```
23:29:24 正在查找私聊「<会话7>」→ 23:29:30 [证据截图] sent_<会话7>.png（成功）
23:30:02 正在查找私聊「<会话11>」  → 23:30:08 [证据截图] sent_2.0.png（成功）
23:30:38 正在查找私聊「烟测SIV002不存在」→ 23:30:44 audit_no_match.png（预期失败）
23:30:45 [ERROR] 未找到私聊「烟测SIV002不存在」→ failed=1
```

观察点（逐项核对）：

- ✅ **滚动重置生效**：目标「<会话11>」上次运行查找耗时 **51s**（从上一目标遗留深处位置向下滚），本次从顶部重置后 **4s 命中**——同一目标、同一列表，查找时间一个数量级的下降，直接证明「重置到顶部再全量扫描」覆盖了漏扫区；
- ✅ **真实目标全部成功**：sent 截图两张（强校验），无 switch_fail、无「重试点击一次」warning；
- ✅ **假目标正确失败为 no_match**（真实不存在，非滚动残留误判），审计截图 + JSON 正常产出；
- ✅ **failed_targets 审计落盘**：`runs/20260907_232912.json` 含
  `"failed_targets": ["烟测SIV002不存在"]` 与错误文案「失败目标：烟测SIV002不存在。」——执行记录可直接看到是哪个失败（用户核心诉求）；
- ✅ **面板渲染路径**：列表页标红逻辑读 `r.failed_targets`、详情页读 `m.failed_targets`（与 JSON 字段同源，静态走查一致）；
- ✅ 运行收尾正常：prune_runs 清理旧记录、守卫释放（RUNNER_EXIT=0）。

配置已恢复原样（7 目标含 <会话12>，备份文件已回滚）。

**结论：SIV-002 修复生效——滚动残留漏扫消除（<会话11> 查找 51s→4s），失败目标名单进执行记录（JSON + 错误文案 + 面板标红），全链路实证 PASS。**

— Tester