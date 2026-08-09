# 配置隐私拆分设计（Spec）

日期：2026-08-09
范围：抖音自动续火花项目（`D:\ai_project\douyin-auto-fire`）
目标：把私人数据（会话名、发送内容、发送时间、会话缓存）从会进 git 的文件里拆出去，让别人 clone 时拿不到用户隐私，同时保留"下次打开面板自动带出"的便利。

## 1. 背景与问题

现状（`git status` 报错，说明仓库尚未 init，处于"随时会误提交"状态）：

| 文件 | 含私人数据 | 是否被 gitignore |
|------|-----------|------------------|
| `config.yaml` | 是：targets（会话名）、message.texts（发送内容）、schedule（发送时间） | 否，会进 git |
| `conversations_cache.json` | 是：会话名列表 | 否，会进 git |
| `panel.log` | 是：45 处发送内容/会话名历史 | 否，会进 git |
| `run.log` | 是：51 处发送内容 | 是，已忽略 |
| `browser_data/` | 是：登录态 cookie（最敏感） | 是，已忽略 |

引用链路：
- `main.py::load_config()` 读 `config.yaml`。
- `main.py::update_schedule_time / update_message_texts / update_targets` 用正则把值写回 `config.yaml`（保留注释结构）。
- `panel.py` 触发/保存时调用上述 `update_*`，把发送内容和会话名写回 `config.yaml`。
- `douyin.py` 从合并后 config 取 `message` / `targets`（`config.get("message", {})`、`config.get("targets")`）。
- `verify.py` 只 mock `panel.load_config`，不直接碰私有键。

## 2. 决策（已与用户确认）

1. **私有边界（保守版）** = `targets` + `message.texts` + `schedule` + `conversations_cache.json`
   - 额外把 `schedule` 也归私有，避免暴露活跃时段。
2. **公开边界** = `browser` + `logging` + `panel`（端口）+ 注释/结构说明。
3. **写回目标** = 私有字段只写回 `user_data.yaml`（不再写 config.yaml）。
4. **git** = 拆分完成后执行 `git init` + 首次提交（仅含安全文件）。

## 3. 文件职责

- `config.yaml`（公开，进 git）：只留 `browser` / `logging` / `panel` 及顶部说明注释；删除实际 `targets`、`message`、`schedule` 键（或保留为注释示例）。
- `user_data.yaml`（新增，**gitignore**）：`targets`、`message.texts`、`random`、`schedule`。首次由当前 config.yaml 私有字段搬入；带注释。
- `user_data.yaml.example`（新增，进 git）：私有键的占位/空模板 + 注释，供 clone 用户复制为 `user_data.yaml` 后填写。
- `conversations_cache.json`：继续单独存在，**加进 gitignore**。

## 4. 加载 / 合并机制（方案 1：分层合并）

- `main.py` 新增 `USER_DATA_PATH = BASE / "user_data.yaml"`。
- `load_config()` 改为：
  1. `base = yaml.safe_load(config.yaml)`（公开底配置）。
  2. 若 `user_data.yaml` 存在：`user = yaml.safe_load(user_data.yaml)`，对私有键（`targets`、`message`、`schedule`）做**浅覆盖合并到 base**（message/schedule 是嵌套 dict，覆盖整个 dict 即可，因为 user_data.yaml 存的是完整 message/schedule）。
  3. 返回合并结果。
- 这样 `douyin.py` / `verify.py` 下游调用 `config["message"]` / `config["targets"]` 不变，blast radius 仅限 `load_config` 与三个 `update_*`。
- `user_data.yaml` 缺失时：私有字段为空/默认值，程序不崩（`douyin.py` 已有 `if not self.targets` 跳过逻辑）。

## 5. 写回改造（main.py 的 update_*）

- `update_schedule_time(time_str)`：改为写 `user_data.yaml` 的 `schedule.time`（保留自身结构/注释；若文件不存在则生成带注释模板）。
- `update_message_texts(texts)`：写 `user_data.yaml` 的 `message.texts`（同时维护 `message.random = len(texts) > 1`）。
- `update_targets(targets)`：写 `user_data.yaml` 的 `targets`。
- 保持"保留注释/结构"的既有风格，但 `user_data.yaml` 注释可独立于 config.yaml。

## 6. 面板（panel.py）

- 已通过调用 `main.update_*` 间接写回，无需改动触发/保存逻辑。
- 读状态时 `cfg.get("targets")` / `cfg.get("message")` 仍从合并后 config 取值，无需改。
- 状态接口（`/state`、`/load` 等返回 message_texts/targets 处）来源不变。

## 7. 隔离隐私 + git 准备

- `.gitignore` 增加：`user_data.yaml`、`user_data.yaml.example` 不忽略（它要进 git）、`conversations_cache.json`、`panel.log`。
- 清理 `panel.log` 中已有的 ~45 条私人记录（清空或截断为占位）。
- `git init`；首次提交前用 `git add` 明确挑选安全文件；`.gitignore` 已挡掉隐私文件。提交内容：源码、`config.yaml`、`user_data.yaml.example`、`.gitignore`、`README.md`、`docs/`、`.bat` 等——**不含** `user_data.yaml` / `conversations_cache.json` / `panel.log` / `run.log` / `browser_data/` / `.venv/` / `__pycache__`。

## 8. 验证

- 合并正确性：`main.py -c`（或临时脚本）加载后断言 `config["targets"]` / `config["message"]["texts"]` / `config["schedule"]["time"]` 取自已搬入的 user_data.yaml 值。
- 回退正确性：临时重命名 `user_data.yaml`，`load_config()` 不抛异常，私有字段为空/默认。
- 端到端：运行 `python main.py --run-once`（在真实有登录态时）确认仍按 user_data.yaml 的目标与内容发送。
- 隐私校验：`git status --porcelain` 不应列出 `user_data.yaml`、`conversations_cache.json`、`panel.log`；`git ls-files` 不含上述文件。
- 文档：更新 README 与 `docs/配置参考.md`，说明 `config.yaml` 公开、`user_data.yaml` 私有、`user_data.yaml.example` 模板。

## 9. 范围外（YAGNI）

- 不做配置加密、不做多用户隔离、不改 Playwright/登录逻辑、不动 `browser_data/` 处理。
- 不改面板 UI 文案（仅底层文件变化，提示文字"保存到配置文件"可后续微调，本 spec 不强制）。
