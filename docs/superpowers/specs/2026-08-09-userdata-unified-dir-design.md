# 隐私配置统一收归 userdata/ 目录 设计（Spec）

日期：2026-08-09
范围：抖音自动续火花项目（`D:\ai_project\douyin-auto-fire`）
目标：把所有个人隐私数据（会话名、发送内容、发送时间、你的抖音名、会话缓存、登录态、审计记录）统一收进 `userdata/` 文件夹，该文件夹整体 gitignore；程序缺失 `userdata/` 时自动新建骨架（空目录 + 默认模板），不自动填入任何真实隐私。

## 1. 背景与现状问题

当前隐私数据散落 4 处（实地核对结果）：

| 位置 | 内容 | 大小/敏感性 |
|------|------|-----------|
| 根 `user_data.yaml` | targets（对方会话名）、message.texts（发送内容）、schedule（发送时间） | 隐私 |
| 根 `conversations_cache.json` | 会话列表缓存 | 隐私 |
| 根 `runs/` | 审计记录（JSON 元数据 + 截图） | 隐私（含会话名/聊天界面） |
| 根 `browser_data/` | 登录态 cookie（Playwright 持久化） | 最敏感，468M |

代码落点（已 grep 确认）：
- `main.py:32` `USER_DATA_PATH = .../user_data.yaml`；`load_config()` 分层合并；`_load/_save_user_data` 读写该文件。
- `panel.py:91` `RUNS_DIR = BASE/"runs"`；`panel.py:104` `_CONV_CACHE_PATH = BASE/"conversations_cache.json"`；`panel.py:168` `_panel_log = BASE/"panel.log"`。
- `douyin.py:127` `user_data_dir = browser_cfg.get("user_data_dir", "./browser_data")`；`real_chrome_profile: true` 时改为真实 Chrome 目录（panel.py 注释与 douyin.py 逻辑一致）。

问题：隐私目录名不统一、位置分散，`.gitignore` 要逐条列（`user_data.yaml`/`conversations_cache.json`/`panel.log`/`runs/`/`browser_data/`），易漏（历史上就发生过 `config.yaml` 被误写回隐私并险些提交）。统一到单一 `userdata/` 后，gitignore 只需一行，且语义清晰："用户数据全部在此，绝不进 git"。

## 2. 决策（已与用户确认）

1. **统一收归**：所有个人隐私数据进 `userdata/` 文件夹。
2. **浏览器登录态并入**：`browser_data/` 也并进 `userdata/browser_data/`（不留在根目录）。
3. **自动新建=建骨架**：程序检测到 `userdata/` 不存在时，自动创建目录结构 + 默认模板文件（空/占位），**绝不自动填入真实隐私**；真实数据由用户填 `user_data.yaml` 或用面板"一键同步/扫码登录"产生。
4. **git 策略**：`userdata/` 整体 gitignore；用户不提交它。仓库只含公开代码 + `config.yaml` + `user_data.yaml.example` 模板 + 文档。
5. **公开配置保留**：`config.yaml` 仍只含 `browser`/`logging`/`panel` 等非隐私字段（进 git）。`browser.user_data_dir` 改为指向 `userdata/browser_data`。

## 3. 目标目录结构

```
userdata/                        # 整体 gitignore，永不进 git
├── user_data.yaml               # 私有配置：targets(会话名)、message.texts(发送内容)、schedule
├── conversations_cache.json      # 会话列表缓存
├── browser_data/                # 登录态（原根 browser_data/ 迁入）
├── runs/                        # 审计记录（原根 runs/ 迁入）
├── run.log                      # 命令行/定时运行日志（原根 run.log 迁入，含发送内容/目标名）
└── panel.log                    # 面板服务日志（原根 panel.log 迁入，历史含发送内容）
```

根目录**删除**：`user_data.yaml`、`conversations_cache.json`、`runs/`、`browser_data/`（迁移后移除，避免双写/混淆）。

保留根目录：`config.yaml`（公开）、`user_data.yaml.example`（进 git 的模板）、其余代码与文档。

## 4. 代码改造

### 4.1 路径常量集中化

新增统一基础常量（建议放 `main.py` 或新建 `paths.py`，本 spec 用 `main.py` 内常量 + 导出供 panel.py 复用，保持最小改动）：

```python
BASE = Path(__file__).parent
USERDATA_DIR = BASE / "userdata"
USER_DATA_PATH = USERDATA_DIR / "user_data.yaml"
CONV_CACHE_PATH = USERDATA_DIR / "conversations_cache.json"
RUNS_DIR = USERDATA_DIR / "runs"
BROWSER_DATA_DIR = USERDATA_DIR / "browser_data"
```

`panel.py` 当前用 `BASE / "config.yaml"`、`BASE / "runs"`、`BASE / "conversations_cache.json"`、`BASE / "panel.log"`。其中 `panel.log` 是面板服务日志（非隐私内容，只是运行日志）——**保留在根目录或移入 userdata 均可**；本 spec 将 `panel.log` 也移入 `userdata/`（因为它是本地运行产物，且历史上含发送内容，统一更省心）。最终 `panel.log` 路径：`USERDATA_DIR / "panel.log"`。

### 4.2 自动新建骨架

新增函数（放 `main.py`，供 panel.py 启动时调用）：

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

- 调用时机：`load_config()` 开头、panel.py 启动初始化时、`_save_user_data` 写回前——任一路径入口都先 `ensure_userdata()`，保证"检测不到就新建骨架"。
- 面板 HTTP 服务启动（`panel.py` 模块顶层或 `main()`）最先调用 `ensure_userdata()`。
- `load_config()` 合并逻辑不变（读 `config.yaml` + 覆盖 `userdata/user_data.yaml` 私有键），仅路径从根改为 `userdata/`。

### 4.3 各模块写盘路径替换

- `main.py`：`USER_DATA_PATH` 指向 `userdata/user_data.yaml`（§4.1）；`_save_user_data` 写前**必须**调 `ensure_userdata()`（spec 要求，plan 原 Step 1 跳过，已修正）。
- `panel.py`：
  - `RUNS_DIR = USERDATA_DIR / "runs"`（原 `BASE/"runs"`）。
  - `_CONV_CACHE_PATH = USERDATA_DIR / "conversations_cache.json"`（原 `BASE/...`）。
  - `_panel_log = USERDATA_DIR / "panel.log"`（原 `BASE/"panel.log"`）。
  - 模块顶层 `RUNS_DIR.mkdir` 改为 `ensure_userdata()` 调用（或保留 mkdir 但路径更新）。
- `runner.py`（定时任务入口，**原 plan 漏纳入，已补**）：
  - `CRASH_LOG = USERDATA_DIR / "run.log"`（原 `BASE/"run.log"`，从 main 导入 `USERDATA_DIR`），且导入后调用 `ensure_userdata()` 再写 log，避免 userdata 未建时 `FileNotFoundError`。
- `config.yaml`：`logging.file` 由 `"./run.log"` 改为 `"./userdata/run.log"`（run.log 一并收进 userdata/，否则 gitignore 收敛后会泄露）。
  - 启动时调用 `ensure_userdata()`。
- `douyin.py:127`：`user_data_dir = browser_cfg.get("user_data_dir", "./userdata/browser_data")`，且 `config.yaml` 的 `browser.user_data_dir` 改为 `"./userdata/browser_data"`。
- `real_chrome_profile: true` 分支：仍指向真实 Chrome 目录（不受 userdata/ 影响，保持原逻辑）。

### 4.4 数据迁移（一次性）

执行阶段把现有根目录隐私数据迁入 `userdata/`（保留用户真实数据，仅移动位置）：
- `user_data.yaml` → `userdata/user_data.yaml`（含真实 targets/texts/schedule）。
- `conversations_cache.json` → `userdata/conversations_cache.json`。
- `runs/` → `userdata/runs/`（含历史审计，9.4M）。
- `browser_data/` → `userdata/browser_data/`（468M 登录态，必须迁移否则要重新扫码）。
- `run.log` → `userdata/run.log`（CLI/定时运行日志，含发送内容/目标名，P0-1 修复一并收进）。
- `panel.log` → `userdata/panel.log`（面板服务日志，历史含发送内容，P1-6 补）。

迁移用 `shutil.move` / 命令行 `move`；迁移后删除根目录原文件/目录（避免双写）。**迁移必须在代码改造（Task 1-4）完成后执行**，否则运行时找不到旧数据。

> **⚠️ 防嵌套（P0-2）：** 迁移前 `ensure_userdata()` 可能已创建空的 `userdata/runs/`、`userdata/browser_data/`。Windows/git-bash 的 `mv src destdir`（destdir 已存在）会把 src 移进 destdir 内部形成 `userdata/runs/runs` 嵌套，导致真实数据被套空目录、登录态/审计丢失。因此迁移前**先 rmdir 这些空骨架**（`rmdir userdata/runs userdata/browser_data 2>/dev/null`），使目标不存在，再 move 真实数据。`browser_data/` 468M 用同盘 move（非 copy），失败保留原目录不删。

### 4.5 .gitignore 收敛

`.gitignore` 改为只忽略 `userdata/`（及其他非本项目项如 `.venv/`/`.skills/`/`.hermes/`/`.workbuddy/`），移除原先逐条列的 `user_data.yaml`/`conversations_cache.json`/`panel.log`/`runs/`/`browser_data/`：

```gitignore
# 用户私有数据（会话名/发送内容/登录态/审计），整体不进 git
userdata/
# 本地/外部工具目录
.venv/
.skills/
.hermes/
.workbuddy/
```

> 注意：`user_data.yaml.example` 是模板、要进 git，**不能**被 `userdata/` 匹配（它在根目录，不在 userdata/ 内），不受影响。

## 5. 验证

- **骨架自动新建**：临时重命名 `userdata/` 后启动 `panel.py`（或 import main 调 `ensure_userdata`），确认自动生成 `userdata/` + `user_data.yaml`（空占位）+ `conversations_cache.json`（`[]`）+ 空 `runs/` + 空 `browser_data/`，且均不含真实隐私。
- **路径正确**：`load_config()` 从 `userdata/user_data.yaml` 读到私有值；`douyin.py` 实际用 `userdata/browser_data` 作为登录态目录（可在不登录情况下检查目录创建位置）。
- **迁移完整性**：迁移后 `userdata/user_data.yaml` 含原真实 targets/texts；`userdata/browser_data` 与原 `browser_data` 内容一致（登录态不丢）。
- **git 隔离**：`git status --porcelain` 不列 `userdata/`；`git ls-files | grep userdata` 为空；`user_data.yaml.example` 仍被追踪。
- **端到端**：`python main.py --run-once`（有登录态时）按 `userdata/` 的数据正常发送；`verify.py` 退出码 0。
- **文档**：README 目录结构改为 `userdata/（私有，gitignore）` 一项概括；`docs/配置参考.md` 说明私有数据位置变更。

## 6. 范围外（YAGNI）

- 不加配置加密、多用户、云同步。
- 不改 Playwright 启动逻辑、拟人操作、风控、审计截图机制。
- 不改面板 UI 文案（仅底层路径变化；提示"保存到配置文件"仍成立，因 user_data.yaml 仍是配置文件，只是进了 userdata/）。
- 不处理 `real_chrome_profile: true` 的真实 Chrome 目录（保持原逻辑，它本来就绕过 userdata/）。

## 7. 风险与缓解

- **迁移遗漏**：`browser_data` 468M 迁移耗时长，用移动（同盘 rename）而非复制，避免磁盘翻倍；迁移失败则保留原目录、不删。
- **双写**：代码改造后必须确保根目录旧路径不再被任何模块引用（grep 复查 `BASE/"runs"`、`BASE/"conversations_cache.json"`、`BASE/"panel.log"`、`"./browser_data"` 全部消失）。
- **config.yaml 误写隐私**（历史教训）：`ensure_userdata` 只写 `userdata/`，`update_*` 只写 `user_data_path`（在 userdata 内），`config.yaml` 永远不会被写入私有键——保持现状的分层合并约束。
