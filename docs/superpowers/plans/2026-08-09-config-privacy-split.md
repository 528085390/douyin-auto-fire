# 配置隐私拆分 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把私人数据（会话名、发送内容、发送时间、会话缓存）从会进 git 的文件拆到 `user_data.yaml`（gitignore），让项目可被公开 clone 而不泄露用户隐私，同时保留面板"自动带出"体验。

**Architecture:** `main.load_config()` 改为分层合并：先读公开 `config.yaml`，再若存在私有 `user_data.yaml` 则覆盖 `targets`/`message`/`schedule` 私有键。`main` 的三个 `update_*` 写回函数改写 `user_data.yaml`。`.gitignore` 挡掉隐私文件，`panel.log` 清理历史。最后 `git init` + 首次安全提交 + 推送到远端。

**Tech Stack:** Python 3.11（项目 `.venv`）、PyYAML（已装）、标准库 `re`/`json`、git。无新增第三方依赖。`.venv/Scripts/python.exe` 为项目解释器。

## Global Constraints

- 私有边界（已确认）：`targets` + `message.texts` + `schedule` + `conversations_cache.json` 归私有（不进 git）。
- 公开边界（已确认）：`browser` + `logging` + `panel` + 注释/结构说明留 `config.yaml`（进 git）。
- 写回目标（已确认）：私有字段只写回 `user_data.yaml`，不再写 `config.yaml`。
- 加载机制（已确认）：方案 1 分层合并——下游 `douyin.py` / `verify.py` 通过 `load_config()` 取合并后配置，调用点零改动。
- 终结动作（已确认）：拆分完成后 `git init` + 首次安全提交 + 推送到 `https://github.com/528085390/douyin-auto-fire`。
- 项目无单元测试框架；验证用 `.venv/Scripts/python.exe -c "import ..."` 内联断言与 `verify.py` 自检（README 第五节）。
- 解释器固定用 `.venv/Scripts/python.exe`；勿用别的 venv。
- YAGNI：不加密、不多用户、不改 Playwright/登录逻辑、不改面板 UI 文案（提示"保存到配置文件"可保持，因 user_data.yaml 也是配置文件）。

---

### Task 1: 新建 user_data.yaml 并迁移私有字段

**Files:**
- Create: `user_data.yaml`（项目根）
- Modify: 无

**Interfaces:**
- Produces: `user_data.yaml` 内容为 `{targets, message, schedule, random}`，供 Task 3 的 `load_config` 合并读取。

- [ ] **Step 1: 创建 user_data.yaml，填入从当前 config.yaml 搬出的私有值**

内容（保留注释，便于 clone 用户理解）：
```yaml
# 私有用户数据 —— 含会话名、发送内容、发送时间，请勿提交到 git（已被 .gitignore 屏蔽）
# 模板见 user_data.yaml.example

targets:
  - name: "示例学习群"
    type: group
  - name: "示例用户A"
    type: private

message:
  # 发送内容，可写多条，开启 random 后每天随机抽一条，更自然
  texts:
    - "示例内容一"
  random: true

schedule:
  time: "01:56"            # 每天发送时间，24 小时制
```

- [ ] **Step 2: 校验文件能被 yaml 解析**

Run: `.venv/Scripts/python.exe -c "import yaml,pathlib; d=yaml.safe_load(pathlib.Path('user_data.yaml').read_text(encoding='utf-8')); print('targets',len(d.get('targets',[]))); print('texts',d['message']['texts']); print('time',d['schedule']['time'])"`
Expected: 打印 `targets 2`、`texts ['示例内容一']`、`time 01:56`，无异常。

---

### Task 2: 改造 load_config 做分层合并

**Files:**
- Modify: `main.py:31`（新增 `USER_DATA_PATH`）、`main.py:36-40`（`load_config` 合并逻辑）

**Interfaces:**
- Consumes: 无（基础层）
- Produces: 新函数 `load_config()` 返回合并后 dict；`USER_DATA_PATH` 常量供 Task 4 的 `update_*` 复用。

- [ ] **Step 1: 在 CONFIG_PATH 后新增 USER_DATA_PATH 常量**

把 `main.py:31` 的 `CONFIG_PATH = ...` 之后加一行：
```python
CONFIG_PATH = Path(__file__).parent / "config.yaml"
USER_DATA_PATH = Path(__file__).parent / "user_data.yaml"
```
并把 `TIME_RE` 之前的空行保持。

- [ ] **Step 2: 重写 load_config 做分层合并**

替换 `main.py:36-40` 的 `load_config` 为：
```python
# 私有键（优先从 user_data.yaml 覆盖，不进 git）
_PRIVATE_KEYS = ("targets", "message", "schedule")


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

- [ ] **Step 3: 内联验证合并正确（user_data.yaml 存在时）**

Run: `.venv/Scripts/python.exe -c "import main; c=main.load_config(); print('targets',c['targets']); print('texts',c['message']['texts']); print('time',c['schedule']['time']); print('browser',c.get('browser') is not None)"`
Expected: targets 含两条、texts 含"示例内容一"、time 01:56、browser 存在（来自 config.yaml），即私有值取自 user_data.yaml，公开值取自 config.yaml。

- [ ] **Step 4: 内联验证回退（临时改名 user_data.yaml，load_config 不崩）**

Run:
```bash
mv user_data.yaml _ud_tmp.yaml
.venv/Scripts/python.exe -c "import main; c=main.load_config(); print('no crash; targets=', c.get('targets')); print('browser ok=', c.get('browser') is not None)"
mv _ud_tmp.yaml user_data.yaml
```
Expected: 打印 `no crash; targets= None`（或默认），`browser ok= True`，且 `user_data.yaml` 已恢复（第二条 mv 成功）。

---

### Task 3: 把三个 update_* 写回函数改指 user_data.yaml

**Files:**
- Modify: `main.py:73-133`（`update_schedule_time`、`update_message_texts`、`update_targets`）

**Interfaces:**
- Consumes: `USER_DATA_PATH`（Task 2 定义）
- Produces: 三个函数更名为统一写 `user_data.yaml`；maintain `verify.py` 仍通过（它 mock `load_config`，不依赖 update_* 落盘位置）。

> 说明：原三个函数用正则在 config.yaml 上就地替换。改为写 `user_data.yaml`——因为 user_data.yaml 是"纯私有"文件，可以直接整体重写对应块，无需保留 config.yaml 的注释协作。实现采用"读现有 user_data.yaml（无则用模板）→ 改内存 dict → 整体 dump 写回"，比正则更稳。保留 `time_str` 合法性由调用方保证。

- [ ] **Step 1: 重写三个函数为写 user_data.yaml**

替换 `main.py:73-133` 三函数为：
```python
def _load_user_data() -> dict:
    """读取私有数据；文件不存在则返回空 dict。"""
    if USER_DATA_PATH.exists():
        with USER_DATA_PATH.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def _save_user_data(data: dict) -> None:
    """整体写回私有数据（保留可读结构）。"""
    USER_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with USER_DATA_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def update_schedule_time(time_str: str):
    """把 schedule.time 写回 user_data.yaml。"""
    data = _load_user_data()
    data.setdefault("schedule", {})["time"] = time_str
    _save_user_data(data)


def update_message_texts(texts: list[str]):
    """把 message.texts 写回 user_data.yaml（自动维护 random）。"""
    data = _load_user_data()
    data.setdefault("message", {})["texts"] = list(texts)
    data["message"]["random"] = len(texts) > 1
    _save_user_data(data)


def update_targets(targets: list[dict]):
    """把 targets 写回 user_data.yaml。targets 为 [{name, type}, ...]。"""
    data = _load_user_data()
    data["targets"] = [{"name": str(t.get("name", "")).strip(),
                        "type": str(t.get("type", "private")).strip() or "private"}
                       for t in targets]
    _save_user_data(data)
```

- [ ] **Step 2: 验证 update_message_texts 改写 user_data.yaml 后 load_config 能读到**

Run:
```bash
cp user_data.yaml /tmp/ud_backup.yaml
.venv/Scripts/python.exe -c "import main; main.update_message_texts(['测试A','测试B']); c=main.load_config(); print(c['message']['texts'], c['message']['random'])"
cp /tmp/ud_backup.yaml user_data.yaml
```
Expected: 打印 `['测试A', '测试B'] True`，且最后 `cp` 把 user_data.yaml 恢复原值（"示例内容一"）。

- [ ] **Step 3: 验证 update_targets 改写后结构正确**

Run:
```bash
cp user_data.yaml /tmp/ud_backup.yaml
.venv/Scripts/python.exe -c "import main; main.update_targets([{'name':'张三','type':'private'}]); print(main.load_config()['targets'])"
cp /tmp/ud_backup.yaml user_data.yaml
```
Expected: 打印 `[{'name': '张三', 'type': 'private'}]`，且 user_data.yaml 已恢复。

---

### Task 4: 精简 config.yaml 为公开部分

**Files:**
- Modify: `config.yaml`（删除 targets/message/schedule 实际键）
- Create: `user_data.yaml.example`（进 git 的占位模板）

**Interfaces:**
- Consumes: 无（data 层收尾）
- Produces: 公开 `config.yaml` 仅含 browser/logging/panel；`user_data.yaml.example` 供 clone 用户复制。

- [ ] **Step 1: 重写 config.yaml 只留公开字段**

将 `config.yaml` 改为（保留原有 browser/logging/panel 注释，去掉 targets/message/schedule 实际内容，改为注释指引）：
```yaml
# 抖音自动续火花 - 公开配置（可提交到 git）
# 私人数据（会话名、发送内容、发送时间）在 user_data.yaml（已被 .gitignore 屏蔽）。
# 首次使用请复制 user_data.yaml.example 为 user_data.yaml 并填写你自己的内容。

browser:
  # 是否无头（后台）运行。
  # ⚠️ 实测：headless: true 时抖音 100% 弹出拼图滑块验证，任务会立刻停手无法发送。
  #    因此必须保持 headless: false（真实有头浏览器），窗口正常显示在屏幕内。
  headless: false
  # 浏览器数据目录：登录态（cookie）会持久化到这里，请勿删除
  user_data_dir: "./browser_data"
  timeout: 60
  manual_select_sec: 30
  extra_args:
    - "--disable-blink-features=AutomationControlled"
    - "--no-sandbox"
  channel: "chrome"
  real_chrome_profile: false

logging:
  file: "./run.log"

panel:
  port: 8765
```
（注意：若原 config.yaml 的 browser/logging/panel 有注释需要保留，以原文件为准照搬到上述结构；本 step 以"只留公开字段"为目标。）

- [ ] **Step 2: 创建 user_data.yaml.example 模板**

内容（空占位，含注释）：
```yaml
# 私有用户数据模板 —— 复制本文件为 user_data.yaml 并填写你自己的内容（user_data.yaml 已被 .gitignore 屏蔽，不会提交）
# 请勿直接修改本模板文件名。

targets:
  - name: "这里填抖音会话昵称或群名"
    type: group   # private（私聊）或 group（群聊）
  # - name: "另一个会话"
  #   type: private

message:
  # 发送内容，可写多条，开启 random 后每天随机抽一条，更自然
  texts:
    - "在吗"
  random: false

schedule:
  time: "21:30"            # 每天发送时间，24 小时制 HH:MM
```

- [ ] **Step 3: 确认合并后仍能取到私有值（config.yaml 已精简）**

Run: `.venv/Scripts/python.exe -c "import main; c=main.load_config(); print('targets',len(c['targets'])); print('texts',c['message']['texts']); print('time',c['schedule']['time']); print('browser',c['browser']['channel'])"`
Expected: targets 2 条、texts 含原内容、time 01:56、browser.channel chrome——即私有值仍来自 user_data.yaml，公开 browser 来自新 config.yaml。

- [ ] **Step 4: 确认 config.yaml 不再含私人会话名/内容**

Run: `grep -nE "$(python -c 'import yaml,re;d=yaml.safe_load(open(\"userdata/user_data.yaml\",encoding=\"utf-8\"));print(\"|\".join(re.escape(x) for x in [t[\"name\"] for t in d.get(\"targets\",[])]+list((d.get(\"message\") or {}).get(\"texts\",[]))))')" config.yaml || echo "OK: 无私人数据"`  <!-- 关键词从私有文件动态取，不在文档里写死真实值 -->
Expected: 输出 `OK: 无私人数据`。

---

### Task 5: conversations_cache.json 纳入 gitignore + 清理 panel.log

**Files:**
- Modify: `.gitignore`
- Modify: `panel.log`（清空历史私人记录）

**Interfaces:**
- Consumes: 无
- Produces: git 将忽略 `user_data.yaml`、`conversations_cache.json`、`panel.log`；`panel.log` 不再含历史私人数据。

- [ ] **Step 1: 更新 .gitignore**

将 `.gitignore` 改为：
```gitignore
# 忽略本地浏览器数据、日志、虚拟环境、私有用户数据
browser_data/
__pycache__/
*.pyc
venv/
run.log
.venv/
# 私有用户数据（会话名/发送内容/发送时间/会话缓存），请勿提交
user_data.yaml
conversations_cache.json
panel.log
```

- [ ] **Step 2: 确认 conversations_cache.json 与 panel.log 已被忽略**

Run: `git check-ignore user_data.yaml conversations_cache.json panel.log config.yaml 2>/dev/null; echo "---"; git check-ignore config.yaml || echo "config.yaml NOT ignored (期望：不忽略)"`
Expected: 前三行分别打印 `user_data.yaml`、`conversations_cache.json`、`panel.log`；最后一行 `config.yaml NOT ignored`（即 config.yaml 不被忽略，可进 git）。

- [ ] **Step 3: 清空 panel.log 历史私人记录**

Run: `.venv/Scripts/python.exe -c "open('panel.log','w',encoding='utf-8').close(); print('panel.log 已清空')"`
（或写一行占位说明）。无需保留 45 条私人记录。

- [ ] **Step 4: 确认 panel.log 私人数据已清除**

Run: `grep -cE "$(python -c 'import yaml,re;d=yaml.safe_load(open(\"userdata/user_data.yaml\",encoding=\"utf-8\"));print(\"|\".join(re.escape(x) for x in [t[\"name\"] for t in d.get(\"targets\",[])]+list((d.get(\"message\") or {}).get(\"texts\",[]))))')" userdata/panel.log; echo "上面应为 0 或文件为空"`  <!-- 同上，动态取词 -->
Expected: 计数为 0（或文件为空时 grep 报错但无匹配行）。

---

### Task 6: 更新文档（README + 配置参考）

**Files:**
- Modify: `README.md`（目录结构注释、`config.yaml` 描述）
- Modify: `docs/配置参考.md`（说明 config.yaml 公开、user_data.yaml 私有）

**Interfaces:**
- Consumes: 无
- Produces: 文档与实现一致，clone 用户知道复制 `user_data.yaml.example`。

- [ ] **Step 1: 更新 README 目录结构注释**

在 `README.md` 目录结构块中，把：
```
├── config.yaml              # 主配置（时间、目标、消息、浏览器、面板端口）
```
改为：
```
├── config.yaml              # 公开配置（浏览器、日志、面板端口）；时间/目标/消息已拆到 user_data.yaml
├── user_data.yaml           # 私有用户数据（会话名、发送内容、发送时间）—— 已被 .gitignore 屏蔽，请勿提交
├── user_data.yaml.example   # 私有数据模板，复制为 user_data.yaml 后填写
```
并在同一块中 `conversations_cache.json` 行尾补 `# 已被 .gitignore 屏蔽`。

- [ ] **Step 2: 更新 README 核心特性第一项措辞**

把 `README.md:11` 的 `多目标：config.yaml 里可配多个会话...` 改为 `多目标：user_data.yaml 里可配多个会话（私聊 private / 群聊 group），逐个发送。`（如措辞需更顺，以"私有数据在 user_data.yaml"为准。）

- [ ] **Step 3: 更新 docs/配置参考.md 头部说明**

把 `docs/配置参考.md:3` 的 `配置文件 config.yaml 位于项目根目录...面板在...操作时也会自动回写该文件。` 改为 `公开配置 config.yaml 位于项目根目录（浏览器/日志/面板端口）。私有数据（会话名、发送内容、发送时间）在 user_data.yaml（已被 .gitignore 屏蔽），面板会自动回写 user_data.yaml。`

- [ ] **Step 4: 更新 docs/配置参考.md 回写说明段**

把 `docs/配置参考.md:88-92` 的"面板在以下操作时会修改 config.yaml"三条，改为"面板在以下操作时会修改 user_data.yaml"并把文件名由 config.yaml 改为 user_data.yaml（三处）。

- [ ] **Step 5: 文档自检——确认 README/配置参考 不再称 config.yaml 存私人字段**

Run: `grep -rn "config.yaml.*发送内容\|config.yaml.*会话名\|config.yaml.*定时" README.md docs/配置参考.md || echo "OK: 文档已对齐"`
Expected: 输出 `OK: 文档已对齐`（或仅有合理的"config.yaml 公开配置"类描述，无"config.yaml 存私人字段"说法）。

---

### Task 7: git init + 首次安全提交 + 推送

**Files:**
- Create: `.git`（仓库）、首次 commit
- 远端: `https://github.com/528085390/douyin-auto-fire`

**Interfaces:**
- Consumes: Task 1-6 全部产物
- Produces: 远端仓库含公开文件、不含任何私人数据。

- [ ] **Step 1: 初始化仓库并加 .gitignore 后确认隐私文件被忽略**

Run:
```bash
git init -q
git add .gitignore
echo "=== 应被忽略（不出现在 untracked 里） ==="
git status --porcelain | grep -E "user_data.yaml|conversations_cache.json|panel.log|run.log|browser_data|\.venv" || echo "GOOD: 隐私文件均未出现在待提交列表"
```
Expected: 打印 `GOOD: 隐私文件均未出现在待提交列表`（即 grep 无匹配）。

- [ ] **Step 2: 全量 add 并提交（.gitignore 已挡隐私）**

Run:
```bash
git add .
git commit -q -m "chore: 拆分私有配置到 user_data.yaml，公开配置可安全进 git

- load_config 分层合并 config.yaml(user_data 私有覆盖)
- 三个 update_* 写回 user_data.yaml
- config.yaml 仅留 browser/logging/panel
- 新增 user_data.yaml.example 模板
- .gitignore 屏蔽 user_data.yaml/conversations_cache.json/panel.log
- 清理 panel.log 历史私人记录
- 更新 README 与配置参考"
echo "=== 提交后确认隐私文件不在版本库 ==="
git ls-files | grep -E "user_data.yaml|conversations_cache.json|panel.log" || echo "GOOD: 版本库不含隐私文件"
```
Expected: 打印 `GOOD: 版本库不含隐私文件`。

- [ ] **Step 3: 添加远端并推送（main 分支）**

Run:
```bash
git branch -M main
git remote add origin https://github.com/528085390/douyin-auto-fire
git push -u origin main
```
Expected: 推送成功，无报错。若远端已存在 README（GitHub 自动创建），`push` 会被拒绝——此时先 `git pull --rebase origin main`（若有冲突以本地为准，因为本地是权威拆分版）再 `git push -u origin main`。

- [ ] **Step 4: 隐私最终校验（远端克隆模拟）**

Run: `.venv/Scripts/python.exe -c "import subprocess,os; print('tracked private check:'); print(subprocess.run(['git','ls-files'],capture_output=True,text=True).stdout.count('user_data.yaml'))"`
Expected: 计数为 0（版本库未追踪 user_data.yaml）。

- [ ] **Step 5: 跑一次 verify.py 确认拆分未破坏定时链路**

Run: `.venv/Scripts/python.exe verify.py; echo "exit=$?"`
Expected: 退出码 0（或打印全部通过）。若因环境缺浏览器内核报错，属允许的非阻断项，但配置相关检查须通过。

---

## 自审（写作时完成）

1. **Spec 覆盖**：§2 私有边界→Task1/3/4；§3 文件职责→Task1/4；§4 合并→Task2；§5 写回→Task3；§6 gitignore+log清理→Task5；§7 git init+提交+推送→Task7；§8 验证→各 Task 的 Step 验证；§9 文档→Task6。无遗漏。
2. **Placeholder 扫描**：无 TBD/TODO；每步均有可运行命令与期望输出。verify.py 在 Task7 作为真实验收，非占位。
3. **类型一致性**：`USER_DATA_PATH`（Task2 定义）被 Task3 `update_*` 复用；`_load_user_data/_save_user_data`（Task3 内部）仅在 Task3 使用；`load_config` 返回 dict 贯穿 Task2/3/4 验证。命名一致。
4. **风险点**：Task7 Step3 若远端已有内容需 rebase——已在步骤内给出降级路径。panel.py 未改动（通过 update_* 间接落盘 user_data.yaml），符合 spec §6。
