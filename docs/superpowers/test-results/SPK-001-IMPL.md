# SPK-001 实现测试证据（Tester）

- 任务: 火花天数展示：逐好友采集与全列表呈现
- 测试日期: 2026-10-04
- 测试方式: `verify.py` 自检（仓库无测试框架，以 `verify.py` 为准）+ AST 语法检查 + 真实浏览器 live 冒烟
- **结论: PASS**（RED 真红 17/17 → GREEN 167/0；语法全过；live 冒烟实采成功）

## 一、基线（改动前，提交 `26ddce0`）

```
$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python.exe verify.py
→ 通过 150 / 失败 0，exit 0
```

## 二、RED（提交 `9802278`，verify.py 新增节 9 共 17 条断言）

```
$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python.exe verify.py
→ 通过 150 / 失败 17，exit 1
[FAIL] ★SPK-001 douyin 采集火花天数节点
[FAIL] ★SPK-001 douyin 采集火花图标节点
[FAIL] ★SPK-001 火花状态灰色判定
[FAIL] ★SPK-001 扫描结果携带 spark_days
[FAIL] ★SPK-001 扫描结果携带 spark_state
[FAIL] ★SPK-001 面板归一放行火花字段
[FAIL] ★SPK-001 面板按名补全火花映射
[FAIL] ★SPK-001 会话接口带缓存时间
[FAIL] ★SPK-001 会话缓存只读接口（不切内存镜像）
[FAIL] ★SPK-001 火花徽标渲染函数
[FAIL] ★SPK-001 火花配色令牌
[FAIL] ★SPK-001 无火花占位符
[FAIL] ★SPK-001 会话卡展示上次同步时间
[FAIL] ★SPK-001 新建任务目标选择器替换手打
[FAIL] ★SPK-001 新建任务目标来源为勾选态
[FAIL] ★SPK-001 接口封装支持显式账号
[FAIL] ★SPK-001 火花徽标五处接入
```

✅ RED 恰为 **17 = 本次全部新增**（16 条正断言 + 1 条负断言对），原有 150 条无一被破坏；新增全部因「保证未实现」而红。

## 三、GREEN（提交 `5e8e6b3` + `587c18c` + `d3aec90` 后）

```
$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python.exe verify.py
→ 通过 167 / 失败 0，exit 0
```

✅ 167 = 150 + 17，与 plan §七 演进表算术一致（150 + 5 + 4 + 4 + 4）。

## 四、语法与静态检查

```
.venv\Scripts\python.exe -c "import ast;ast.parse(open('douyin.py',encoding='utf-8').read());print('AST OK')"  → AST OK
.venv\Scripts\python.exe -c "import ast;ast.parse(open('panel.py',encoding='utf-8').read());print('AST OK')"   → AST OK
```

- `panel.html`：提取 `<script>` 块用 `new Function()` 解析 **OK**；花括号 / 圆括号 / 方括号配平各为 0；`<script>` 开闭各 1；`<div>` 开 77 / 闭 77。
- token 复核：`function sparkBadge(` ×1、`sparkBadge(` ×6（1 定义 + 5 调用）、`id="newJobTargets"` 不存在、`id="newJobTargetsWrap"` 存在、`"#newJobTargets"` 引用不存在、`newJobTargets.length` 存在、`opts.account` 存在、`id="sparkAt"` 存在。

## 五、live 冒烟（真实浏览器，2026-10-04）

面板以 `.venv\Scripts\pythonw.exe panel.py` 起在 `http://127.0.0.1:8765`（pid 存活、端口 LISTENING），对一个账号点「一键同步」：

```
POST /api/sync-conversations {account:<别名1>}   → 24s 完成
GET  /api/conversations?account=<别名1>
→ count=45   cache_mtime=2026-10-04 16:49
   [group]   days=410 state=done      <群聊A>
   [group]   days=195 state=done      <群聊B>
   [private] days=22  state=done      <会话A>
   [private] days=22  state=done      <会话B>
   [private] days=21  state=done      <会话C>
   [private] days=21  state=pending   <会话D>
   [private] days=18  state=pending   <会话E>
   [private] days=18  state=pending   <会话F>
   （其余 37 项 days/state 均为空 → 前端渲染 `—`）
```

观察点（逐项核对）：

- ✅ **采集真的生效**：45 个会话里 8 个带火花，橙 5（410/195/22/22/21 天）+ 灰 3（21/18/18 天），与探针阶段「群聊同样有火花」「灰=今天还没续」的结论一致。
- ✅ **无火花 ≠ 0 天**：其余 37 项 `spark_days/spark_state` 为 `null`，前端渲染 `—`（决策 D6）。
- ✅ **零额外开销**：采集内联在既有扫描循环里（同一 ElementHandle 上再查两个子节点），扫描总耗时 24s，与改动前同量级。
- ✅ **不发任何消息**：全程只读 DOM，无 `_send_text` 调用；无风控触发。
- ✅ **落盘与读取链路通**：`userdata/accounts/<别名1>/conversations_cache.json` 已写入火花字段，`GET /api/conversations` 返回 `cache_mtime`，面板卡片显示上次同步时间。

## 六、未验证项（如实声明）

- **另一账号**：未实测（缓存每账号一份，需各自同步一次）。
- **新建定时任务勾选录入的端到端保存**：已静态核对（`newJobTargets.map(t => ({name, type}))` → `POST /api/jobs`，后端 `_enrich_target_types` 与 `jobs.py` 零改动），但**未真实点保存**，属人工确认项。
- **抖音改版导致选择器失效**：无法预演，仅由 verify 断言锁字面量 + 前端 `—` 兜底。

## 七、代码评审后修复复测（2026-10-04）

独立代码评审（`docs/superpowers/reviews/SPK-001-code-review.md`）判 CHANGES_REQUIRED：P0×1（已提交文档隐私泄露）+ P1×1（`panel.html` 的 `api()` 让 `activeAccount` 覆盖 body 里显式带的账号 → 新建任务跨账号串号）。修复与复测：

**RED（先加门禁断言）**
```
$env:PYTHONIOENCODING='utf-8'; .venv\Scripts\python.exe verify.py
→ 通过 167 / 失败 1，exit 1
  [FAIL] ★SPK-001 接口封装账号优先级(不覆盖显式账号)
```

**GREEN（修 `panel.html:456-460` 账号优先级）**
```
  const method = opts.method || "GET";
  let url = path;
  const payload = Object.assign({}, opts.body || {});
  const acct = opts.account || payload.account || activeAccount;   // 原为 opts.account || activeAccount
→ 通过 168 / 失败 0，exit 0
```

**隐私复扫（P0-1）**
```
git grep -n -I -E '<真实别名>|<真实会话名...>' -- docs/ CHANGELOG.md README.md
→ worktree: NO HITS（HEAD 仍为修复前版本，随本轮提交更新）
```

- ✅ 第 18 条断言 RED 诚实（新增断言在旧实现下必 FAIL）。
- ✅ 原有 167 条零回归。
- ⚠️ **未做浏览器端到端复测**：`api()` 的账号优先级修正在真实面板上「选 B 账号建任务」的路径**未实际点过**，仅由断言锁定表达式 + 静态核对（body 已带 `account`，故 `acct` 必等于所选账号）。
