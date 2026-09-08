# BAT-001-IMPL 验证证据（Tester）

- 任务：BAT-001 一键出发：全账号串行批量执行（号间强制错峰 15 分钟）
- 日期：2026-09-08
- 方式：由 Lead 代行 Tester（独立子代理 reviewer 负责 CODE_REVIEW；本文件证据全部为
  真实命令输出，未转载 spec/plan 自述）。验证命令：
  `./.venv/Scripts/python.exe verify.py` 与 `userdata/_smoke_bat001.py`（打桩冒烟，
  不改动真实浏览器/网络/守卫/发送）。
- **结论：PASS**（RED/GREEN 全链路数字符合 plan 预期；单元冒烟两场景全过 exit 0；
  功能级冒烟**未授权**，见「遗留」）

## 1. RED（Task 1 后）—— 实测与 plan 预期一致

```
$ ./.venv/Scripts/python.exe verify.py | grep -cE '^\\s*\\[ok\\]'   → 105
$ ./.venv/Scripts/python.exe verify.py | grep -cE '^\\s*\\[FAIL\\]' → 18
$ ./.venv/Scripts/python.exe verify.py | grep -E '^通过'            → 通过 105 / 失败 18
```

- FAIL 组成 = 既有 2（账号任务 `DouyinAutoFire-<别名1>`/`DouyinAutoFire-<别名2>` 未注册，
  环境态，与 BAT-001 无关）+ 新增 16（★BAT-001 ×16，原因均为保证未实现）。
- plan 预期「18 FAIL = 既有 2 + 新增 16」：**一致**。提交 f9295a6。

## 2. 中间态（Task 2 / Task 3 后）

| 阶段 | 实测 | 说明 |
|---|---|---|
| Task 2 后（batch_runner.py 落地） | 通过 114 / 失败 9 | 新增 9 条 b 断言全过；剩 2+6(panel)+1(html) |
| Task 3 后（panel.py 三端点+拒绝） | 通过 120 / 失败 3 | 剩 2(既有)+1(html) |
| Task 4 后（panel.html） | 通过 121 / 失败 2 | 仅剩既有环境态 2 FAIL |

## 3. GREEN（最终）—— 121 通过 / 2 失败（仅剩环境态）

```
$ ./.venv/Scripts/python.exe verify.py | grep -E '^通过'
通过 121 / 失败 2
[FAIL] 账号任务 DouyinAutoFire-<别名1> 已注册 :: 未找到（请在面板为对应账号注册）
[FAIL] 账号任务 DouyinAutoFire-<别名2> 已注册 :: 未找到（请在面板为对应账号注册）
```

新增 16 条断言全部 [ok]，无「改断言迁就实现」（断言文本与 Task 1 RED 提交逐字一致）。

## 4. 单元级冒烟（打桩，不动真实浏览器/网络/守卫/发送）

脚本：`userdata/_smoke_bat001.py`（gitignored；临时账号目录 accA/accB/accC + 
`trigger_run` 打桩写假 run meta + `time.sleep` 加速）。实测输出（exit 0）：

```
== S1 顺序/成功/预检跳过 ==
  [ok]   S1 退出码 0
  [ok]   S1 phase=finished
  [ok]   S1 accA success   {status: success, run_id: smoke_…, end: …, failed_targets: []}
  [ok]   S1 accB success   {status: success, run_id: smoke_…, end: …, failed_targets: []}
  [ok]   S1 accC skipped(未保存内容)
  [ok]   S1 A/B 都拿到 run_id
  [ok]   S1 accB end 落盘
  [ok]   S1 _prev_run_end = accB end（末号也落盘）
  [ok]   S1 顺序：accB 结束不早于 accA 开始
== S2 错峰等待中取消 ==
  [ok]   S2 有账号进入 waiting_stagger
  [ok]   S2 phase=cancelled
  [ok]   S2 等待账号最终 skipped(用户取消)
单元冒烟：通过 FAILS=[]
SMOKE_EXIT=0
```

覆盖语义：① 串行顺序（A→B→C 预检跳过不阻塞）② 单号收尾显式落盘 + `_prev_run_end`
（末号也落盘 → 号间错峰基准不丢，评审 P2-F4）③ 错峰等待状态机（`waiting_stagger` +
`next_start_at`）④ 取消以磁盘为准（最小写集置 `cancel_requested` → 等待立即退出 →
`phase=cancelled`、等待账号 skipped「用户取消」，评审 P2-F3/F7）⑤ 原子写两写方。

冒烟还实测并暴露了一个 Windows 真实竞态：执行器高频 os.replace 期间并发读
`batch_state.json` 会瞬时 `PermissionError(13)`（共享冲突）——已修复（读/写双方小重试，
提交 fbb153e，修复后冒烟稳定全过）。

## 5. 无法自动化的部分（如实声明）

- 15 分钟真实错峰等待、面板关闭后执行器继续跑完、双账号真实浏览器全链路 → 需功能级
  冒烟（`--stagger-minutes 1`，约 8-10 分钟）或日常真实使用核对。verify 只锁结构
  （token/路由/调用形态），锁不到时序行为。

## 遗留

1. **功能级冒烟未授权**：用户在 plan 签字时选择「不预授权，实现全绿后再逐次确认再跑」。
   待用户点头后执行：面板点「一键出发」或 CLI `pythonw batch_runner.py --batch-all
   --stagger-minutes 1`，两真实账号各发一条无害占位文本，核对横幅推进 + 各号 run meta
   落盘 + 取消按钮路径。
2. 两个账号任务（`DouyinAutoFire-<别名1>`/`<别名2>`）未在面板注册 = verify 既有 2 FAIL
   来源（MAI-001 遗留核对项，用户在面板操作），不阻塞 BAT-001。
3. `userdata/_smoke_bat001.py` 保留在 gitignored userdata/ 便于复跑；不入库。
