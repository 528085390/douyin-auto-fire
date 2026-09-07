# SIV-001 会话项视口外点击落空修复 — Test 证据

- 日期：2026-09-07
- 测试对象：commit `b98a3e5` → `3e1cbc3` → `f1fff0b`（plan Task 1-3 全量）
- 测试方法：`verify.py` 自检（本仓库事实标准）+ 逐 Task 提交点实测 + 断言零迁就核验 + 隐私终扫
- 测试角色说明：本次 Tester 由 Lead 代行（仓库先例，证据全部为真实命令输出）
- **结论：PASS**（代码层）。live 冒烟未授权，按 plan 以「下次真实运行人工核对」收尾（见「四」）

---

## 一、命令与真实输出（逐 Task 提交点）

验证命令一律：`cd D:/ai_project/douyin-auto-fire && ./.venv/Scripts/python.exe verify.py`

| 提交点 | 命令输出（真实） | 期望 | 判定 |
|---|---|---|---|
| RED：`b98a3e5`（verify.py 新增断言后） | `exit=1`；`通过 94 / 失败 7`（既有 2 + 新增 5） | RED：失败 7、exit 1 | ✅ 与 plan Task 1 期望一致 |
| GREEN：`3e1cbc3`（douyin.py 实现后） | `exit=1`；`通过 99 / 失败 2`（仅剩既有 2 环境态） | 失败 2、新增 5 全过、原 94 不回归 | ✅ 与 plan Task 2 期望一致 |
| 终态：`f1fff0b`（文档同步后） | `exit=1`；`通过 99 / 失败 2` | 与 Task 2 后一致（文档不破坏回归网） | ✅ |

既有 2 失败明细（环境态，非本任务缺陷）：`账号任务 DouyinAutoFire-<别名> ×2 已注册 :: 未找到`——两个账号的定时任务尚未在面板注册（MAI-001 遗留核对项，spec 八-2）。

## 二、断言零迁就核验（Tester 独立核验，非转载评审）

```bash
# RED 提交点的 douyin.py（a58a26c = b98a3e5^）——五条断言目标字面应全部 0 命中
git show b98a3e5^:douyin.py | grep -c "scroll_into_view_if_needed\|viewport_size\|重试点击一次\|_ensure_item_in_view\|元素在视口外"
# → 0（RED 真红，非迁就）

# GREEN 终态 douyin.py——五条断言目标字面应全部 ≥1
grep -c "scroll_into_view_if_needed" douyin.py  # → 1
grep -c "viewport_size" douyin.py               # → 2
grep -c '"重试点击一次"' douyin.py               # → 1（独立 token）
grep -c "_ensure_item_in_view" douyin.py        # → 3（定义 1 + 调用 2）
grep -c '"元素在视口外' douyin.py               # → 1
```

全部通过：GREEN 的实现来源全部真实存在，无装饰性字面。

## 三、结构/行为自查

```bash
python -c "import ast; ast.parse(open('douyin.py',encoding='utf-8').read()); print('syntax ok')"   # → syntax ok
```

新符号定义/调用齐备：`_ensure_item_in_view`（定义 :480，调用 :696/:716）、`_find_rendered_item`（定义 :429，调用 :500/:714）、`_in_viewport`（定义 :467，调用 :290/:493/:508）、`_wait_switch_settled`（定义 :730，调用 :702/:718）。

## 四、live 冒烟（已授权执行，2026-09-07）

计划 Task 4 的 live 冒烟 **已获用户授权并执行**（目标「<会话11>」，列表底部），全链路通过：

```
2026-09-07 20:56:14 [INFO] 检测到已登录，继续。
2026-09-07 20:56:14 [INFO] 【1/1】处理目标: <会话11>
2026-09-07 20:57:02 [INFO] 输入后发送按钮未变红（DOM 类名漂移时常见），以编辑器内容为准
2026-09-07 20:57:05 [INFO] [证据截图] 已保存: 001_205703_sent_2.0.png
2026-09-07 20:57:05 [INFO] 本次续火花完成 ✅（共 1 个目标）
```

观察点：
- ✅ 无 `switch_fail` 审计件（之前失败 2 目标均会产出 audit JSON + 截图，本次未出现）
- ✅ 无「重试点击一次」warning（滚动+点击+切换单次通过）
- ✅ `sent_2.0.png` 前缀 = 强校验通过（非 `sent_soft_` 降级）
- ✅ 截图 206KB 落地 `userdata/accounts/<别名2>/runs/smoke_siv001/001_205703_sent_2.0.png`（用户亲眼看结果）
- ⚠️ 日志「输入后发送按钮未变红」为信息级提示（不是错误；E1 已核实真发出也可能不红），不影响结论

**结论：SIV-001 修复生效——列表底部目标「<会话11>」从必然 switch_fail 变为成功发送。**

离线 verify 只锁代码结构，不能锁运行时 DOM。冒烟提供了「真实抖音虚拟列表 + 底部条目 + 滚入视口 + 点击 + 切换」全链路实证，补上离线验证的最后一环。

（冒烟过程曾遇两个环境插曲：① cookie 过期，用 `--setup-login --account <别名2>` 扫码恢复；② setup-login 进程退出不及时占用 browser_data 目录锁，等待进程退出后重跑。代码层面无问题，属用户设备状态变更。）

## 五、结论

**PASS**（2026-09-07）。RED 7 FAIL → GREEN 2 FAIL 全程符合 plan 期望；断言零迁就；语法/引用/隐私全过。代码层验证闭环，唯一缺口为未授权的 live 冒烟，已按流程转为真实运行后人工核对待办。