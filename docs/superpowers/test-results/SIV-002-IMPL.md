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

- **live 冒烟未执行**（需用户授权）：verify.py 只能锁代码结构，不能锁「滚动重置后
  真实扫到上半区目标」这一运行时行为。待用户授权后对含列表底部目标的真实目标组
  发一次无害文本验证；未授权则靠下一次真实运行收尾核对（执行记录中失败目标名单应可见、
  不应再出现因滚动残留引发的 no_match）。

— Tester