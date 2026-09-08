# SCH-001 IMPL 测试证据（单元级打桩冒烟 + verify 全绿）

- 日期：2026-09-08
- Task：SCH-001（定时任务条目库 + 常驻调度器）
- 执行：Tester 代行（单会话无独立 Tester bot，证据为真实命令输出；冒烟假账号用 ASCII 假别名）
- 结论：**PASS**

## 1. verify.py 全量自检

命令：`./.venv/Scripts/python.exe verify.py`

真实输出（节选）：

```
通过 148 / 失败 0
```

exit 0。基线（2026-09-08 spec 期）为通过 121 / 失败 2（2 失败 = 旧按号 schtasks 注册探测，
第 3 节机制替换后消失）；GREEN 口径 148/0 与 plan 一致。

## 2. 守护状态机打桩冒烟（8 场景）

命令：`./.venv/Scripts/python.exe userdata/_smoke_sch001.py`
（gitignored 冒烟脚本；打桩点 = jobs.JOBS_PATH / STATE/HEARTBEAT/守卫路径 → tempfile、
假 ASCII 账号 accA/accB、FakePanel 写假 run meta、假时钟 sleep 拨钟、错峰常数不缩短仅时钟模拟）

真实输出：

```
通过 17 / 失败 0

  [ok]   S1 两号同刻均触发 :: fired=['jA', 'jB']
  [ok]   S1 第二条错峰 ≥15min(end→start) :: endA=2026-09-08 21:30:00 atB=2026-09-08 21:45:00 gap=900s
  [ok]   S1 两号 run_id 不同
  [ok]   S2 同号同刻两条并存执行 :: fired=['jC', 'jD']
  [ok]   S3 终态 running→success 且带 run_id
  [ok]   S4 running 残留复核收尾
  [ok]   S4 复核不重新触发
  [ok]   S4 dispatching 陈旧残留视为未触发 :: fired=['jF']
  [ok]   S5 cancel 后剩余 skipped :: {"status":"skipped","reason":"用户取消"}
  [ok]   S5 cancel 标志消费后清除
  [ok]   S5 stop 优雅退出 :: rc=0 hb=stopped
  [ok]   S6 跨天未触发条目不静默丢 :: {"status":"skipped","reason":"跨天未及触发"}
  [ok]   S6 date/fired/queue 重置
  [ok]   S7 删后不发送 :: {"status":"skipped","reason":"任务已删除/停用"}
  [ok]   S8 死 pid 守卫被自清且任务照常触发
  [ok]   S9 新鲜 dispatching 滞留留痕不重发 :: {"status":"skipped","reason":"守护中断未确认（不重发，请人工检查执行记录）"}
  [ok]   S10 心跳字段 last_err 齐备 :: keys=['boot_at','current','last_err','next_due','pid','ts']
```

exit 0。断言以 scheduler_state.json 等终态 JSON 为准（非日志）。

## 3. 冒烟抓出并已修复的守护缺陷

1. 终态回写被覆盖：轮询收尾 `_record` 后重读磁盘再写 prev/current，把 success 终态回写成
   running → 修复为「以磁盘最新为基合并终态后一次性原子落盘」（scheduler_daemon.py ⑤）。
2. 跨天重置未即时落盘：`_reset_if_new_day` 只改内存不写盘，崩溃会丢「跨天未及触发」记录 →
   修复为函数内 `_write_state(st)`。
3. `_load_state`/`_write_state` 调用存在但缺定义 → 补别名（复用 load_state/_write_json）。

修复后 verify 复跑仍 148/0（无回归）。

## 4.5 Code Review 两轮处置（2026-09-08，终轮 APPROVED）

首轮 CHANGES_REQUIRED（P0 无；P1×3/P2×3/P3×1）→ 处置提交 f05ced6 → 第二轮聚焦复审
**APPROVED**（P0/P1/P2 全 0）。处置与回归锁定：

- F1 任务「上次运行」数据流闭环：GET /api/jobs 载荷补 `last_results`（面板列不再是死代码）；
- F2 长等待期（守卫/错峰/轮询）心跳不停更（每 ≤5s）+ 心跳新增 `last_err` 字段；
- F3 两处 loadTasks 残留 → loadJobs（全仓 0 命中）；
- F4 新建任务目标按会话缓存回填 type（群聊保真）；行内编辑 UI 裁剪留痕（spec/plan 已记录）；
- F5 idle 心跳写盘异常不自杀 + 队列补货写盘兜底（N4）；
- F6 dispatching 滞留分支留痕（不重发优先）——冒烟新增 S9 锁定；
- F7 error.log 入 .gitignore。
- 冒烟新增 S9/S10（N1 回归锁定）；verify 148/0、冒烟 17/0 复跑通过。

## 5. 未覆盖项（待授权/人工）

- 真实发送冒烟（对真实目标）需用户逐次授权——未执行。
- 面板 API 功能冒烟与守护真跑演示（curl + pythonw + 注册表开关往返）按 plan 9.4 待用户环境确认；
- 一键迁移与旧系统任务清理为真实账号数据/系统动作，由用户在面板点击执行。
