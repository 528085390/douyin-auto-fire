# 隐私配置统一收归 userdata/ 目录 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把所有个人隐私数据（会话名、发送内容、发送时间、会话缓存、登录态、审计记录）统一收进 `userdata/` 文件夹并整体 gitignore；程序缺失 `userdata/` 时自动建骨架（空占位，不填真实隐私）；一次性迁移现有根目录隐私数据。

**Architecture:** 在 `main.py` 集中定义 `userdata/` 下的统一路径常量 + `ensure_userdata()` 骨架函数；`load_config()`/`_save_user_data`/`panel.py`/`douyin.py` 全部改用这些常量。`config.yaml` 的 `browser.user_data_dir` 改指 `./userdata/browser_data`。`.gitignore` 收敛为一行 `userdata/`。执行阶段用 move 把根目录 4 处隐私数据迁入 `userdata/`。

**Tech Stack:** Python 3.11（项目 `.venv`）、PyYAML、标准库 `pathlib`/`json`/`shutil`、git。解释器固定用 `.venv/Scripts/python.exe`。

> **执行定位约定（修复 P1-3 行号漂移）：** 本文所有 `文件:行号` 仅为阅读锚点；实际落地请用**内容片段**在文件中定位（patch 工具按内容匹配，不依赖行号）。若文件内容与本文片段不一致，先读最新文件再定位，不要盲填行号。

> **防嵌套铁律（贯穿 Task 5/7，修复 P0-2/P1-4/P1-5）：** 任何 `mv src destdir` 前，必须确认 `destdir` 不存在（先 rmdir 空骨架）；恢复数据时用 `mv _ud_tmp/* userdata/` 而非 `mv _ud_tmp userdata`。违反会嵌套出 `userdata/runs/runs` 之类，丢失登录态/审计。

## Global Constraints

- 统一收归（已确认）：所有个人隐私进 `userdata/`，整体 gitignore，用户不提交。
- 浏览器登录态并入（已确认）：`browser_data/` 并进 `userdata/browser_data/`。
- 自动新建=建骨架（已确认）：`ensure_userdata()` 只建目录 + 默认空模板，**不填真实隐私**。
- 无 `douyin_name` 字段（用户口误，已删除）：私有 `user_data.yaml` 仅含 `targets`/`message`/`schedule`。
- 分层合并保持：`config.yaml` 公开（browser/logging/panel），`userdata/user_data.yaml` 私有，`load_config()` 合并后下游零改动。
- `update_*` 只写 `userdata/user_data.yaml`，绝不复写 `config.yaml`（防历史隐私泄露）。
- YAGNI：不加加密/多用户；不改 Playwright 逻辑、拟人操作、风控、审计机制；不改面板 UI 文案。
- 迁移安全：`browser_data/` 468M 用同盘 move（非 copy），失败保留原目录不删。

---

### Task 1: main.py 集中路径常量 + ensure_userdata()

**Files:**
- Modify: `main.py:31-52`（在 CONFIG_PATH 后加统一常量与 ensure_userdata；load_config 开头调用）

**Interfaces:**
- Produces: `USERDATA_DIR`、`USER_DATA_PATH`、`CONV_CACHE_PATH`、`RUNS_DIR`、`BROWSER_DATA_DIR` 常量；`ensure_userdata()` 供 panel.py 导入。

- [ ] **Step 1: 在 CONFIG_PATH 后新增 userdata 路径常量**

把 `main.py:31-32`：
```python
CONFIG_PATH = Path(__file__).parent / "config.yaml"
USER_DATA_PATH = Path(__file__).parent / "user_data.yaml"
```
改为：
```python
CONFIG_PATH = Path(__file__).parent / "config.yaml"
# 统一用户私有数据目录（整体 gitignore，不进 git）
USERDATA_DIR = Path(__file__).parent / "userdata"
USER_DATA_PATH = USERDATA_DIR / "user_data.yaml"
CONV_CACHE_PATH = USERDATA_DIR / "conversations_cache.json"
RUNS_DIR = USERDATA_DIR / "runs"
BROWSER_DATA_DIR = USERDATA_DIR / "browser_data"
```

- [ ] **Step 2: 新增 ensure_userdata()（建骨架，不填隐私）**

在 `load_config()` 之前插入：
```python
def ensure_userdata() -> None:
    """缺失 userdata/ 时自动建骨架（空目录 + 默认模板），不填真实隐私。"""
    USERDATA_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(exist_ok=True)
    BROWSER_DATA_DIR.mkdir(exist_ok=True)
    if not USER_DATA_PATH.exists():
        USER_DATA_PATH.write_text(
            "# 私有用户数据 —— 会话名/发送内容/发送时间，请勿提交（已被 .gitignore 屏蔽）\n"
            "# 复制 user_data.yaml.example 的内容或在此填写你自己的数据。\n\n"
            "targets: []\n"
            "message:\n  texts: [\"在吗\"]\n  random: false\n"
            "schedule:\n  time: \"21:30\"\n",
            encoding="utf-8",
        )
    if not CONV_CACHE_PATH.exists():
        CONV_CACHE_PATH.write_text("[]", encoding="utf-8")
```

- [ ] **Step 3: load_config 开头调用 ensure_userdata()**

把 `main.py` 现有 `load_config()`（约 38-52 行）：
```python
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"找不到配置文件: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        merged = yaml.safe_load(f) or {}
    # 分层合并：私有数据在 user_data.yaml（gitignore），公开结构在 config.yaml
    if USER_DATA_PATH.exists():
        with USER_DATA_PATH.open("r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        for key in _PRIVATE_KEYS:
            if key in user:
                merged[key] = user[key]
    return merged
```
改为在合并前先 `ensure_userdata()`：
```python
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"找不到配置文件: {CONFIG_PATH}")
    ensure_userdata()  # 确保 userdata/ 与私有配置文件存在（骨架）
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        merged = yaml.safe_load(f) or {}
    # 分层合并：私有数据在 userdata/user_data.yaml（gitignore），公开结构在 config.yaml
    if USER_DATA_PATH.exists():
        with USER_DATA_PATH.open("r", encoding="utf-8") as f:
            user = yaml.safe_load(f) or {}
        for key in _PRIVATE_KEYS:
            if key in user:
                merged[key] = user[key]
    return merged
```

- [ ] **Step 4: 内联验证 ensure_userdata 建骨架且不填隐私**

Run:
```bash
rm -rf userdata
.venv/Scripts/python.exe -c "import main; main.ensure_userdata(); import os; print('dir', os.path.isdir('userdata')); print('ud', open('userdata/user_data.yaml',encoding='utf-8').read()); print('conv', open('userdata/conversations_cache.json',encoding='utf-8').read()); print('runs', os.path.isdir('userdata/runs')); print('bd', os.path.isdir('userdata/browser_data'))"
```
Expected: 打印 `dir True`、`ud` 内容为默认空模板（targets: []、texts: ["在吗"]、无真实隐私）、`conv []`、`runs True`、`bd True`。

- [ ] **Step 5: 确认 load_config 仍从 userdata 读到私有值（用迁移前的真实 user_data.yaml 暂不 rename）**

Run: `.venv/Scripts/python.exe -c "import main; c=main.load_config(); print('targets', c['targets'][0]['name']); print('texts', c['message']['texts'])"`
Expected: 打印真实 targets 名与 texts（因当前根 `user_data.yaml` 仍在，load_config 走旧路径——此步仅为 sanity，Task 4 迁移后才全走 userdata/；迁移前此处可能仍读根 user_data.yaml，属正常，重点看 Task 4 后）。

---

### Task 2: _save_user_data 写回路径改为 userdata/

**Files:**
- Modify: `main.py:85-96`（`_load_user_data`/`_save_user_data`）

**Interfaces:**
- Consumes: `USER_DATA_PATH`（Task 1 定义，已在 userdata/ 下）
- Produces: 三个 `update_*` 写回 userdata/user_data.yaml（路径已由常量决定，逻辑不变，仅确认 _save_user_data 用 USER_DATA_PATH）。

- [ ] **Step 1: _save_user_data 写前调用 ensure_userdata()（修复 P1-2：spec 要求，原 plan 跳过）**

把 `main.py` 现有 `_save_user_data`：
```python
def _save_user_data(data: dict) -> None:
    """整体写回私有数据（保留可读结构）。"""
    USER_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with USER_DATA_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
```
改为（写前确保骨架存在，不依赖 parent.mkdir 兜底，符合 spec §4.3）：
```python
def _save_user_data(data: dict) -> None:
    """整体写回私有数据（保留可读结构）。"""
    ensure_userdata()  # 确保 userdata/ 与 user_data.yaml 存在（缺失自动建骨架）
    with USER_DATA_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
```
（注：原 `USER_DATA_PATH.parent.mkdir` 不再需要，ensure_userdata 已建好目录。）

- [ ] **Step 2: 验证 update_message_texts 写回 userdata/user_data.yaml**

Run:
```bash
cp user_data.yaml _ud_bak.yaml
.venv/Scripts/python.exe -c "import main; main.ensure_user_data if False else None; main.update_message_texts(['X1','X2']); import os; p='userdata/user_data.yaml'; print('wrote to', p, os.path.exists(p)); print(main.load_config()['message']['texts'])"
cp _ud_bak.yaml user_data.yaml; rm -f _ud_bak.yaml
```
Expected: 打印 `wrote to userdata/user_data.yaml True` 与 `['X1', 'X2']`；根 `user_data.yaml` 已恢复。

- [ ] **Step 3: 验证根目录旧 user_data.yaml 未被写入（防双写/隐私泄露）**

Run: `.venv/Scripts/python.exe -c "print('root ud has X1?', 'X1' in open('user_data.yaml',encoding='utf-8').read())"`
Expected: 打印 `root ud has X1? False`（根 user_data.yaml 仍是原真实数据，未受 update 影响；Task 4 会迁移它）。

---

### Task 3: panel.py 写盘路径改指 userdata/

**Files:**
- Modify: `panel.py:91-92`（RUNS_DIR）、`panel.py:104`（_CONV_CACHE_PATH）、`panel.py:168`（_panel_log）、模块加载早期调 ensure_userdata

**Interfaces:**
- Consumes: `ensure_userdata`、`USERDATA_DIR`、`RUNS_DIR`、`CONV_CACHE_PATH`（从 main 导入）
- Produces: panel.py 全部私有落盘进 userdata/；启动时自动建骨架。

- [ ] **Step 1: panel.py 导入 ensure_userdata 并早期调用**

在 `panel.py:41`（`from main import update_schedule_time, update_message_texts, update_targets`）改为：
```python
from main import (
    update_schedule_time, update_message_texts, update_targets, ensure_userdata,
)
# 模块加载即确保 userdata/ 骨架存在（缺失自动新建）
ensure_userdata()
```
（注：`main` 模块 import 时会执行其顶层代码；`ensure_userdata` 已定义于 main 顶层，导入即可用。）

- [ ] **Step 2: RUNS_DIR 改指 userdata/**

把 `panel.py:91-92`：
```python
RUNS_DIR = BASE / "runs"
RUNS_DIR.mkdir(exist_ok=True)
```
改为：
```python
RUNS_DIR = USERDATA_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)
```
需先让 `USERDATA_DIR` 在 panel.py 可见：在 `panel.py:45`（`CONFIG_PATH = BASE / "config.yaml"`）后加：
```python
from main import USERDATA_DIR
```
（或直接从 main 导入；与 Step 1 的 import 合并。）

- [ ] **Step 3: _CONV_CACHE_PATH 改指 userdata/**

把 `panel.py:104`：
```python
_CONV_CACHE_PATH = BASE / "conversations_cache.json"
```
改为：
```python
_CONV_CACHE_PATH = USERDATA_DIR / "conversations_cache.json"
```

- [ ] **Step 4: _panel_log 改指 userdata/**

把 `panel.py:168`：
```python
_panel_log = BASE / "panel.log"
```
改为：
```python
_panel_log = USERDATA_DIR / "panel.log"
```

- [ ] **Step 5: 内联验证 panel.py 路径全部在 userdata/ 下**

Run: `.venv/Scripts/python.exe -c "import panel; print('runs', panel.RUNS_DIR); print('conv', panel._CONV_CACHE_PATH); print('log', panel._panel_log); print('all under userdata:', str(panel.RUNS_DIR).replace(chr(92),'/').count('userdata/')==1 and 'userdata/' in str(panel._CONV_CACHE_PATH) and 'userdata/' in str(panel._panel_log))"`
Expected: 三个路径均含 `userdata/`，最后打印 `all under userdata: True`。

- [ ] **Step 6: 确认 panel.py 不再引用根旧路径**

Run: `grep -n 'BASE / "runs"\|BASE / "conversations_cache.json"\|BASE / "panel.log"\|"./browser_data"\|BASE/"runs"' panel.py || echo "OK: 无根旧路径引用"`
Expected: 打印 `OK: 无根旧路径引用`。

---

### Task 4: douyin.py / config.yaml / runner.py 的私有路径改指 userdata/

**Files:**
- Modify: `douyin.py:127`（默认 user_data_dir）
- Modify: `config.yaml`（`browser.user_data_dir` 值 + `logging.file` 值）
- Modify: `runner.py:31`（`CRASH_LOG`）+ 导入 `ensure_userdata`/`USERDATA_DIR` 并在写 log 前调用

**Interfaces:**
- Consumes: `USERDATA_DIR`（Task 1 定义）
- Produces: 浏览器登录态目录、CLI/定时运行日志均落在 userdata/。

- [ ] **Step 1: douyin.py 默认 user_data_dir 改指 userdata/browser_data**

把 `douyin.py:127`：
```python
user_data_dir = self.browser_cfg.get("user_data_dir", "./browser_data")
```
改为：
```python
user_data_dir = self.browser_cfg.get("user_data_dir", "./userdata/browser_data")
```

- [ ] **Step 2: config.yaml 的 user_data_dir 与 logging.file 改值**

把 `config.yaml` 中：
```yaml
  user_data_dir: "./browser_data"
```
改为：
```yaml
  user_data_dir: "./userdata/browser_data"
```
并把 `logging.file`：
```yaml
  file: "./run.log"
```
改为：
```yaml
  file: "./userdata/run.log"
```

- [ ] **Step 3: runner.py 的 CRASH_LOG 改指 userdata/run.log 并先建骨架**

把 `runner.py:31`：
```python
CRASH_LOG = BASE / "run.log"
```
改为（在 runner.py 顶部 import 区加入，且**先** `ensure_userdata()` **再** 定义 `CRASH_LOG`）：
> ```python
> from main import ensure_userdata, USERDATA_DIR
> ensure_userdata()  # 确保 userdata/ 与 run.log 父目录存在（缺失自动建骨架）
> CRASH_LOG = USERDATA_DIR / "run.log"
> ```
> 注意：必须**先** `ensure_userdata()` **再** 定义 `CRASH_LOG`，否则 userdata 未建时 `CRASH_LOG.open("a")` 会 `FileNotFoundError`。原 `runner.py:31` 的 `CRASH_LOG = BASE / "run.log"` 整行删除，改到 `ensure_userdata()` 调用之后。

- [ ] **Step 4: 验证 run.log 路径在 userdata/ 下**

Run: `.venv/Scripts/python.exe -c "import runner; print('CRASH_LOG =', runner.CRASH_LOG); assert 'userdata/run.log' in str(runner.CRASH_LOG).replace(chr(92),'/'); print('OK')"`
Expected: 打印 `CRASH_LOG = .../userdata/run.log` 与 `OK`。

- [ ] **Step 5: 验证 config.yaml logging.file 在 userdata/ 下**

Run: `.venv/Scripts/python.exe -c "import yaml; c=yaml.safe_load(open('config.yaml',encoding='utf-8')); print('logging.file =', c['logging']['file']); assert c['logging']['file']==\"./userdata/run.log\"; print('OK')"`
Expected: 打印 `logging.file = ./userdata/run.log` 与 `OK`。

---

### Task 5: 一次性迁移现有根目录隐私数据到 userdata/

**Files:**
- Move: 根 `user_data.yaml` → `userdata/user_data.yaml`
- Move: 根 `conversations_cache.json` → `userdata/conversations_cache.json`
- Move: 根 `runs/` → `userdata/runs/`
- Move: 根 `browser_data/` → `userdata/browser_data/`

**Interfaces:**
- Consumes: Task 1-4 已完成（userdata/ 骨架已可由 ensure_userdata 创建，但此处用真实数据覆盖）
- Produces: 根目录不再有隐私文件；真实数据完整保留于 userdata/。

> **⚠️ 防嵌套（修复 P0-2 / P1-4）：** 开发自测时 ensure_userdata() 已创建空的 `userdata/runs/`、`userdata/browser_data/`、`userdata/user_data.yaml`、`userdata/conversations_cache.json`。Windows/git-bash 的 `mv src destdir`（destdir 已存在）会把 src **移进** destdir 内部，形成 `userdata/runs/runs`、`userdata/browser_data/browser_data` 嵌套，导致真实数据被套空目录、登录态/审计丢失。**因此迁移前必须先 rmdir 这些空骨架**，使 `userdata/runs`、`userdata/browser_data` 不存在，再 move 真实数据，才能在正确位置落位。`browser_data/` 468M 用同盘 move（快、不翻倍），失败保留原目录不删。

- [ ] **Step 1: 确认当前根隐私数据存在**

Run: `ls -d user_data.yaml conversations_cache.json runs browser_data run.log panel.log 2>&1`

- [ ] **Step 2: 先清空骨架，再执行迁移（move，防嵌套）**

Run:
```bash
# 清掉 ensure_userdata 可能已建的空骨架：先删子目录，再删空了的 userdata 本身
rmdir userdata/runs 2>/dev/null; rmdir userdata/browser_data 2>/dev/null
rmdir userdata 2>/dev/null
mkdir -p userdata
# 迁移真实数据（userdata/ 下对应目标此时不存在，不会嵌套）
mv user_data.yaml userdata/user_data.yaml
mv conversations_cache.json userdata/conversations_cache.json
mv runs userdata/runs
mv browser_data userdata/browser_data
mv run.log userdata/run.log 2>/dev/null
mv panel.log userdata/panel.log 2>/dev/null
echo "=== 迁移后根目录应只剩公开文件 ==="
ls -1 | grep -E "user_data.yaml|conversations_cache.json|^runs$|^browser_data$|run.log|panel.log" && echo "FAIL: 根仍有隐私" || echo "OK: 根目录隐私已迁走"
echo "=== 确认无嵌套（userdata/runs/runs 不应存在）==="
ls -d userdata/runs/runs userdata/browser_data/browser_data 2>/dev/null && echo "FAIL: 嵌套" || echo "OK: 无嵌套"
```
Expected: 打印 `OK: 根目录隐私已迁走` 与 `OK: 无嵌套`。

- [ ] **Step 3: 验证 userdata/ 含真实数据**

Run: `.venv/Scripts/python.exe -c "import yaml; d=yaml.safe_load(open('userdata/user_data.yaml',encoding='utf-8')); print('targets', d['targets'][0]['name']); print('texts', d['message']['texts']); import os; print('browser_data exists', os.path.isdir('userdata/browser_data')); print('runs exists', os.path.isdir('userdata/runs'))"`
Expected: 打印真实 targets 名、texts、browser_data exists True、runs exists True（迁移完整）。

- [ ] **Step 4: 端到端调用 load_config 从 userdata 读到真实数据**

Run: `.venv/Scripts/python.exe -c "import main; c=main.load_config(); print('targets', c['targets'][0]['name']); print('texts', c['message']['texts']); print('schedule', c['schedule']['time'])"`
Expected: 打印真实值（证明合并链路已全走 userdata/）。

---

### Task 6: .gitignore 收敛为 userdata/ + 更新文档

**Files:**
- Modify: `.gitignore`（收敛为一行 userdata/）
- Modify: `README.md`（目录结构概括 userdata/）
- Modify: `docs/配置参考.md`（私有数据位置说明）

**Interfaces:**
- Consumes: Task 5 已完成
- Produces: git 仅忽略 userdata/；文档与实现一致。

- [ ] **Step 1: .gitignore 收敛**

把 `.gitignore` 改为：
```gitignore
# 用户私有数据（会话名/发送内容/登录态/审计），整体不进 git
userdata/
# 本地/外部工具目录（非本项目代码）
.venv/
.skills/
.hermes/
.workbuddy/
```

- [ ] **Step 2: 确认 userdata/ 被忽略、user_data.yaml.example 仍追踪**

Run: `git check-ignore userdata/ userdata/user_data.yaml config.yaml 2>/dev/null; echo "---"; git check-ignore userdata/ >/dev/null 2>&1 && echo "OK: userdata/ 被忽略" || echo "FAIL"; git check-ignore config.yaml >/dev/null 2>&1 && echo "FAIL: config.yaml 被忽略" || echo "OK: config.yaml 不忽略（可进 git）"`

- [ ] **Step 3: README 目录结构用 userdata/ 概括**

把 README 目录结构块中分散的：
```
├── user_data.yaml           # 私有用户数据（会话名、发送内容、发送时间）—— 已被 .gitignore 屏蔽，请勿提交
├── user_data.yaml.example   # 私有数据模板，复制为 user_data.yaml 后填写
...
├── runs/                    # 每次执行记录（本地生成，已被 .gitignore 屏蔽：...）
├── panel.log                # 面板服务日志（本地生成，已被 .gitignore 屏蔽）
├── run.log                  # 命令行模式运行日志（本地生成，已被 .gitignore 屏蔽）
├── browser_data/            # 浏览器登录态（自动生成，请勿删除）
├── conversations_cache.json # 最近一次「选会话」扫描到的会话列表缓存（本地生成，已被 .gitignore 屏蔽）
```
合并替换为：
```
├── userdata/                # 用户私有数据（会话名/发送内容/登录态/审计/面板日志）—— 整体 .gitignore，永不进 git
│   ├── user_data.yaml        #   私有配置（targets/message/schedule），缺失自动建骨架
│   ├── conversations_cache.json # 会话列表缓存
│   ├── browser_data/        #   登录态（自动生成，请勿删）
│   └── runs/                #   审计记录（自动生成）
├── user_data.yaml.example   # 私有数据模板（进 git），复制为 userdata/user_data.yaml 后填写
```
（保留 `user_data.yaml.example` 在根目录、进 git 的说明；移除根目录原有的 `runs/`、`panel.log`、`run.log`、`browser_data/`、`conversations_cache.json`、`user_data.yaml` 独立条目，避免与 userdata/ 重复。）

- [ ] **Step 4: docs/配置参考.md 更新私有数据位置**

把 `docs/配置参考.md:3` 中"私有数据（会话名、发送内容、发送时间）在 `user_data.yaml`"改为"私有数据（会话名、发送内容、发送时间、会话缓存、登录态、审计）统一在 `userdata/` 目录（`userdata/user_data.yaml` 等），该目录已被 `.gitignore` 屏蔽，缺失时程序自动新建骨架"。

- [ ] **Step 5: 文档自检——确认无残留旧路径描述**

Run: `grep -rn "根目录.*user_data.yaml\|config.yaml 存.*私人\|已被 .gitignore 屏蔽.*user_data.yaml" README.md docs/配置参考.md || echo "OK: 文档已对齐 userdata/ 方案"`
Expected: 打印 `OK: 文档已对齐 userdata/ 方案`（或仅有"user_data.yaml.example 进 git"类正确描述）。

---

### Task 7: 验证 + 提交 + 推送

**Files:**
- 仓库已 init（前序任务），本次新提交 + 推送

**Interfaces:**
- Consumes: Task 1-6 全部产物
- Produces: 远端 main 含统一 userdata/ 方案，且 userdata/ 不在版本库；根目录无残留私密文件。

- [ ] **Step 1: 骨架自动新建（模拟全新 clone 场景，修复 P1-5 恢复命令）**

Run:
```bash
mv userdata _ud_tmp
.venv/Scripts/python.exe -c "import panel; print('panel imported, userdata auto-created:', __import__('os').path.isdir('userdata'))"
ls userdata 2>&1
# 修复 P0-A / P0-5：import panel 已触发 ensure_userdata 重建空骨架 userdata/runs、userdata/browser_data，
# 必须先 rmdir 这些空骨架，再移回真实数据，否则会嵌套成 userdata/runs/runs（登录态/审计丢失）。
# 用 dotglob 含点文件，rm -rf 兜底清临时目录。
rmdir userdata/runs 2>/dev/null
rmdir userdata/browser_data 2>/dev/null
shopt -s dotglob
mv _ud_tmp/* userdata/ 2>/dev/null
shopt -u dotglob
rm -rf _ud_tmp 2>/dev/null
ls -a userdata 2>&1
```
Expected: import panel 时自动创建 userdata/（含空骨架）；`rmdir` 清掉空骨架后 `mv _ud_tmp/* userdata/`（dotglob）把**全部**内容（含点文件、含 runs/browser_data）正确并入 userdata/（**不**嵌套成 `userdata/runs/runs`）；`rm -rf _ud_tmp` 确保临时目录清掉；`ls -a userdata` 显示真实数据含隐藏项。

- [ ] **Step 2: verify.py 自检**

Run: `.venv/Scripts/python.exe verify.py; echo "exit=$?"`
Expected: 退出码 0。

- [ ] **Step 3: 根目录残留私密文件断言（修复 P0-3①）**

Run:
```bash
echo "=== 根目录不应残留任何私密文件 ==="
ls -1 | grep -xE "user_data.yaml|conversations_cache.json|run.log|panel.log|browser_data|runs" && echo "FAIL: 根残留私密文件" || echo "OK: 根目录无私密文件残留"
```
Expected: 打印 `OK: 根目录无私密文件残留`。

- [ ] **Step 4: git 状态确认 userdata/ 不进版本库**

Run: `git status --porcelain | grep -E "userdata" && echo "FAIL: userdata 在暂存" || echo "OK: userdata 被忽略"; git ls-files | grep -E "^userdata/" && echo "FAIL: userdata 已追踪" || echo "OK: userdata 未追踪"`

- [ ] **Step 5: 隐私门禁（修复 P1-A：必须早于 git push）+ 全量提交 + 推送**

先跑隐私校验门禁（扫描已追踪集私密文件名 + 动态读 userdata 真实密文 + conversations_cache/run.log/panel.log 内容密文），**确认无泄露才允许 git add / commit / push**：

```bash
.venv/Scripts/python.exe -c "
import subprocess, yaml, json, os
tracked = subprocess.run(['git','ls-files'],capture_output=True,text=True).stdout
secret_names = ['user_data.yaml','conversations_cache.json','run.log','panel.log','browser_data','runs']
leak_name = [n for n in secret_names if n in tracked.splitlines()]
# 动态密文：从 userdata/ 真实隐私文件读值，确认绝不出现在已追踪集
secrets = []
ud = yaml.safe_load(open('userdata/user_data.yaml',encoding='utf-8')) or {}
for t in ud.get('targets',[]): secrets.append(str(t.get('name','')))
for x in ud.get('message',{}).get('texts',[]): secrets.append(str(x))
secrets.append(ud.get('schedule',{}).get('time',''))
try:
    cc = json.load(open('userdata/conversations_cache.json',encoding='utf-8'))
    for c in (cc if isinstance(cc,list) else []): secrets.append(str(c))
except Exception: pass
for fn in ['userdata/run.log','userdata/panel.log']:
    if os.path.exists(fn):
        secrets.append(open(fn,encoding='utf-8',errors='ignore').read())
leak_secret = [s for s in secrets if s and s in tracked]
print('tracked secret file names:', leak_name)
print('tracked real secrets:', leak_secret)
assert not leak_name, '私密文件名泄露'
assert not leak_secret, '真实隐私内容泄露'
print('OK: 无隐私泄露')
"
# 门禁通过后才提交推送
git add .
git commit -q -m "refactor: 统一隐私数据到 userdata/ 目录并整体 gitignore

- main.py 集中 userdata/ 路径常量 + ensure_userdata() 自动建骨架（不填隐私）
- load_config/_save_user_data 改走 userdata/user_data.yaml
- panel.py 的 runs/conversations_cache/panel.log 改指 userdata/
- douyin.py / config.yaml 的 user_data_dir 改指 ./userdata/browser_data
- runner.py 的 run.log 改指 userdata/run.log（修复 run.log 隐私回归）
- 一次性迁移根目录隐私数据（含 468M 登录态）到 userdata/（防嵌套）
- .gitignore 收敛为单行 userdata/
- 更新 README 与配置参考文档"
git push origin main
```
Expected: 门禁打印 `OK: 无隐私泄露`；推送成功；`git ls-files | grep '^userdata/'` 为空。若门禁 assert 失败，则**停止、不提交、不推送**，排查泄露源。

- [ ] **Step 6: 推送后复核（最终隐私校验，double-check）**

Run:
```bash
.venv/Scripts/python.exe -c "
import subprocess
tracked = subprocess.run(['git','ls-files'],capture_output=True,text=True).stdout
print('userdata tracked count:', tracked.count('userdata/'))
assert tracked.count('userdata/')==0
print('OK: userdata 未进版本库')
"
```
Expected: 打印 `userdata tracked count: 0` 与 `OK: userdata 未进版本库`。

---

## 自审（写作时完成）

1. **Spec 覆盖**：§3 目录结构→Task1/5；§4.1 常量→Task1；§4.2 ensure_userdata→Task1；§4.3 写盘替换→Task2/3/4；§4.4 迁移→Task5；§4.5 gitignore→Task6；§5 验证→各 Task Step；§6 文档→Task6。无遗漏。
2. **Placeholder 扫描**：无 TBD；每步有命令+期望。verify.py 为真实收尾验收。
3. **类型一致性**：`USERDATA_DIR`/`USER_DATA_PATH`/`CONV_CACHE_PATH`/`RUNS_DIR`/`BROWSER_DATA_DIR` 在 Task1 定义、Task2/3/4 复用；`ensure_userdata` 在 Task1 定义、Task3 Step1 导入、Task7 Step1 验收。命名全程一致。
4. **风险点**：`browser_data` 468M 用 move（Task5 Step2）非 copy，符合 Global Constraints。迁移前 Task1-4 已完成、路径已切，迁移后 load_config 全走 userdata（Task5 Step4 验证）。panel.py import main 时 ensure_userdata 触发（Task3 Step1），但根 browser_data 仍在迁移前存在——douyin 取 `./userdata/browser_data`（Task4），故迁移前若运行会找不到登录态；**执行顺序：Task1-4 改代码 → Task5 迁移 → 之后才端到端运行**，避免中途运行。已在 Task7 Step1 用"模拟全新 clone"验证骨架，但真实运行需在 Task5 后。
5. **双写防护**：Task3 Step6 显式 grep 确认 panel.py 无根旧路径；Task2 Step3 确认根 user_data.yaml 未被 update 写入。
