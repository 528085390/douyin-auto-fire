# SIV-002 Spec Review（会话查找全量扫描 + 失败目标执行记录审计）

- 评审对象: `specs/2026-09-07-conversation-search-reset-audit-design.md`
- 评审日期: 2026-09-07
- 评审方式: Reviewer 读 spec 全篇 + 读真实代码(douyin.py / panel.py / panel.html / verify.py)+ grep 核实断言字面量 + 实测 verify.py 基线
- **结论: APPROVED**(P0/P1 无漏网;P2×2 不阻塞,列入 plan 实施注意)

## 评审发现

| # | 级别 | 位置 | 发现 | 建议 |
|---|---|---|---|---|
| 1 | P2 | spec 4.5 断言 #2 | `"重置后等待虚拟列表重渲染"` 锁 `"time.sleep(random.uniform" in d` 过宽——该子串在 douyin.py 现有 17 处,单独拿出来语义几乎不锁「等待发生在重置之后」 | 可接受(与 #1 `"scrollTop = 0"` AND 后 GREEN 时同真);plan 实现时把 sleep 紧邻重置语句,并加注释 token `# SIV-002` 便于未来断言 |
| 2 | P2 | spec 4.4 | 详情页「未送达」行与 error 文案带名单互为冗余 | 保留(视觉直接,冗余无害);plan 实现时确认二者读同一 `m.failed_targets` 来源,避免文案与列表漂移 |
| 3 | P2 | spec 4.1 | 代码块未体现错误处理表「wrap evaluate 抛错则吞掉走原逻辑」的 try/except | 实现时按 spec 五节补上;风险 R1 已有登记,不阻塞 |

## 已核实安全(逐项核验)

- **V3 RED 诚实性**: `"scrollTop"`、`"failed_targets"` 当前在 douyin.py / panel.py / panel.html 中均 0 命中(grep 实测),spec 4.5 新增 6 条断言 RED 预期 8 FAIL = 既有 2 + 新增 6 成立;
- **基线实测**: `verify.py` 当前 EXIT=1、仅 2 FAIL(账号任务 `DouyinAutoFire-<别名1>`/`DouyinAutoFire-<别名2>` 未注册,环境态),与 spec E10 一致;
- **根因链与代码事实吻合**: `_find_conversation_item`(douyin.py:440-465)仅 `scrollBy` 正向滚动、无起始位置重置,与 spec C1/C2 一致;失败分支统一收敛于 run() 的 except(douyin.py:951-954),单点 append 即可覆盖 no_match/switch_fail/send_fail/type_fail 全部失败路径,spec 4.2 设计成立;
- **审计证据属实**: spec 引用的 `audit_no_match_214723.json`(URL=/chat、可见区为 1-5 月旧会话、nameHits=[])与 run 日志时间戳(目标 6 查找 51s vs 目标 7 仅 8s)与文件内容逐条相符;
- **范围不冲突**: spec 非目标明确不动 SIV-001 交付物(视口保障/switch_fail 语义/审计 tag 集合);run 级错误文案改动属本任务目标 2 的交付(用户要求执行记录可见失败对象),与 SIV-001 非目标「另行排期」不矛盾;
- **文案改动无断言冲突**: panel.py:448 错误文案未被 verify.py 任何断言锁定(grep 全文确认),改动安全;
- **panel.html 前端兜底**: 旧 run JSON 无 failed_targets 时 `|| []` 兜底已写入 spec 五节错误处理表,兼容存量记录。

## P2 处置

以上 3 条 P2 均不阻塞 APPROVED;其中 #3 与风险 R1 合并为 plan 实施注意,#1/#2 由 plan 实现时落实即可。无需第二轮评审。

— Reviewer
