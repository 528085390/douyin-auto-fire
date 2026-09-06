"""
抖音自动续火花 - 入口

交互模式（直接运行 python main.py）：
  1. 选择 手动触发 / 定时触发
  2. 输入要发送的信息（可多行，用于随机轮换）
  · 手动触发 -> 用本次输入的内容立即给所有目标发一次（不改配置文件）
  · 定时触发 -> 输入时间(HH:MM)，把时间与内容写入配置并注册 Windows 定时任务

非交互用法（多账号，MAI-001）：
  python main.py --run-once --account main   # 立即给账号 main 的目标发一次
  python main.py 21:30 --account main        # 账号 main 每日 21:30 定时
  python main.py --setup-login --account main  # 打开浏览器供账号 main 登录
  python main.py --migrate main              # 迁移旧版单账号数据到账号 main
  python main.py --list-accounts             # 列出所有账号别名
  python main.py --test                      # 仅验证依赖与浏览器能否启动（免账号）
  单账号时 --account 可省略（自动沿用）；多账号时必须显式指定。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

from douyin import DouyinStreak

CONFIG_PATH = Path(__file__).parent / "config.yaml"
# 统一用户私有数据目录（整体 gitignore，不进 git）
USERDATA_DIR = Path(__file__).parent / "userdata"
USER_DATA_PATH = USERDATA_DIR / "user_data.yaml"
CONV_CACHE_PATH = USERDATA_DIR / "conversations_cache.json"
RUNS_DIR = USERDATA_DIR / "runs"
BROWSER_DATA_DIR = USERDATA_DIR / "browser_data"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TASK_NAME = "DouyinAutoFire"  # 旧任务名（兼容/迁移收尾用）；账号任务名 = task_name(alias)

# 私有键（优先从 user_data.yaml 覆盖，不进 git）
_PRIVATE_KEYS = ("targets", "message", "schedule")

# 多账号（MAI-001）：每账号一个目录；私有骨架只在 create_account 时于账号目录内创建
ACCOUNTS_ROOT = USERDATA_DIR / "accounts"
RUN_GUARD_PATH = USERDATA_DIR / ".running"          # 跨进程运行守卫（独占文件）
PANEL_STATE_PATH = USERDATA_DIR / "panel_state.json"  # {last_account: alias}（由 panel.py 读写）
VALID_ALIAS_RE = re.compile(r"^[A-Za-z0-9_]{1,24}$")
# Windows 保留设备名（大小写不敏感），作为目录名会失败，校验函数直接挡下
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} \
    | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


def ensure_userdata() -> None:
    """缺失 userdata/ 时建目录（多账号语义，spec 4.1/P1-3）。

    只保证 userdata/ 与 accounts/ 存在；不再自动创建顶层 user_data.yaml /
    browser_data / runs / conversations_cache.json —— 那些私有骨架改由
    create_account 在 accounts/<别名>/ 内创建，避免「空骨架被误判为旧数据」。
    """
    USERDATA_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_ROOT.mkdir(exist_ok=True)


def load_config(alias: str | None = None) -> dict:
    """加载配置。alias=None：只合并 config.yaml 公开键（基础设施读，零账号安全，
    不碰任何账号私有文件）；alias 给定：再合并该账号 user_data.yaml 私有键并覆盖
    browser.user_data_dir 指向账号 browser_data（防串号关键覆盖）。"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"找不到配置文件: {CONFIG_PATH}")
    ensure_userdata()
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        merged = yaml.safe_load(f) or {}
    if alias is not None:
        user = load_user_data(alias)
        for key in _PRIVATE_KEYS:
            if key in user:
                merged[key] = user[key]
        merged.setdefault("browser", {})["user_data_dir"] = \
            str(account_root(alias) / "browser_data")
    return merged


def setup_logging(config: dict):
    log_file = (config.get("logging") or {}).get("file")
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def run_test(config: dict):
    """仅验证 Playwright 能否启动浏览器，不登录、不发送。"""
    logging.info("执行依赖/浏览器启动测试...")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://example.com")
        title = page.title()
        browser.close()
    logging.info("浏览器启动成功，测试页标题: %s", title)
    logging.info("测试通过 ✅ 依赖与浏览器均正常。")


# ---------------------------------------------------------------------- #
# 自动模式：设为每日定时
# ---------------------------------------------------------------------- #
def account_root(alias: str) -> Path:
    """账号目录（调用方保证别名已校验）。"""
    return ACCOUNTS_ROOT / alias


def list_accounts() -> list[str]:
    """扫描 accounts/ 下含 user_data.yaml 或 browser_data 的子目录名，排序返回。"""
    if not ACCOUNTS_ROOT.is_dir():
        return []
    out = []
    for d in sorted(ACCOUNTS_ROOT.iterdir()):
        if d.is_dir() and ((d / "user_data.yaml").exists() or (d / "browser_data").is_dir()):
            out.append(d.name)
    return out


def validate_alias(alias: str) -> str | None:
    """别名合法性检查：合法返回 None；非法返回给用户看的中文错误文案（完整规则）。

    panel/CLI 共用同一入口（spec 4.1）。规则：1~24 个字符，仅英文/数字/下划线，
    拒绝中文、空格、-、Windows 文件名字符 \\ / : * ? " < > |、首尾点、
    Windows 保留设备名（CON/NUL/PRN/AUX/COM1-9/LPT1-9，大小写不敏感）。
    """
    if not isinstance(alias, str) or not alias:
        return "别名不能为空（1~24 个字符，仅限英文/数字/下划线）。"
    if not VALID_ALIAS_RE.match(alias):
        return ("别名不合法：仅限 1~24 个英文/数字/下划线字符，"
                "不能含中文、空格、连字符及 \\ / : * ? \" < > | 等符号，首尾不能是点。")
    if alias.upper() in WINDOWS_RESERVED_NAMES:
        return f"别名 {alias!r} 是 Windows 保留设备名，无法作为目录名，请换一个。"
    return None


def create_account(alias: str) -> Path:
    """校验别名 → mkdir → 写账号骨架（user_data.yaml + browser_data/ + runs/ +
    conversations_cache.json []），返回账号目录。别名非法抛 ValueError（含文案）。"""
    err = validate_alias(alias)
    if err:
        raise ValueError(err)
    root = account_root(alias)
    if root.exists():
        raise ValueError(f"账号 {alias!r} 已存在。")
    root.mkdir(parents=True, exist_ok=True)
    (root / "browser_data").mkdir(exist_ok=True)
    (root / "runs").mkdir(exist_ok=True)
    ud = root / "user_data.yaml"
    if not ud.exists():
        ud.write_text(
            "# 私有用户数据（账号: " + alias + "）—— 会话名/发送内容/发送时间，请勿提交\n"
            "# 多账号下每个账号一份，位于 userdata/accounts/<别名>/user_data.yaml\n\n"
            "targets: []\n"
            "message:\n  texts: [\"在吗\"]\n  random: false\n"
            "schedule:\n  time: \"21:30\"\n",
            encoding="utf-8",
        )
    cc = root / "conversations_cache.json"
    if not cc.exists():
        cc.write_text("[]", encoding="utf-8")
    return root


def load_user_data(alias: str) -> dict:
    """读取账号私有数据；文件不存在返回空 dict。只收 alias（防串号）。"""
    if validate_alias(alias) is not None:
        return {}  # 非法别名不抛——调用方先用 validate_alias 给完整文案
    p = account_root(alias) / "user_data.yaml"
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_user_data(alias: str, data: dict) -> None:
    """整体写回账号私有数据（保留可读结构）。"""
    root = account_root(alias)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "user_data.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def update_schedule_time(alias: str, time_str: str) -> None:
    """把 schedule.time 写回账号 user_data.yaml。"""
    data = load_user_data(alias)
    data.setdefault("schedule", {})["time"] = time_str
    save_user_data(alias, data)


def update_message_texts(alias: str, texts: list[str]) -> None:
    """把 message.texts 写回账号 user_data.yaml（自动维护 random）。"""
    data = load_user_data(alias)
    data.setdefault("message", {})["texts"] = list(texts)
    data["message"]["random"] = len(texts) > 1
    save_user_data(alias, data)


def update_targets(alias: str, targets: list[dict]) -> None:
    """把 targets 写回账号 user_data.yaml。"""
    data = load_user_data(alias)
    data["targets"] = [{"name": str(t.get("name", "")).strip(),
                        "type": str(t.get("type", "private")).strip() or "private"}
                       for t in targets]
    save_user_data(alias, data)


def legacy_pending() -> bool:
    """顶层是否存在「真实旧数据」（评审 A1 锚点，与旧骨架默认值彻底解耦）：
    user_data.yaml 的 targets 非空，或 browser_data/ 非空目录，或 runs/ 非空目录。
    旧版 ensure_userdata 生成的默认骨架（message.texts/schedule.time 非空但 targets 空）
    不算——避免「只设过时间没配过目标」的空壳被误判为 legacy 走无谓迁移。
    （spec 4.1 宽口径在本 plan 收窄为 A1 锚点，保证「迁移后不复发、新装机不误判」不变。）
    """
    ud = USERDATA_DIR / "user_data.yaml"
    if ud.exists():
        try:
            with ud.open("r", encoding="utf-8") as f:
                user = yaml.safe_load(f) or {}
            if user.get("targets"):
                return True
        except Exception:  # noqa: BLE001
            return True  # 读不了按未迁移保守处理，交给用户
    bd = USERDATA_DIR / "browser_data"
    if bd.is_dir() and any(bd.iterdir()):
        return True
    rd = USERDATA_DIR / "runs"
    if rd.is_dir() and any(rd.iterdir()):
        return True
    return False


def migrate_legacy_to_account(alias: str) -> dict:
    """把旧顶层单账号数据迁入 accounts/<别名>/。幂等可重跑。

    返回 {"ok": bool, "moved": [已迁移项], "failed": [失败项], "error": str|None}。
    已存在同名账号 → error 拒绝；逐项 shutil.move（源存在才移）；失败不中断整体。
    """
    err = validate_alias(alias)
    if err:
        return {"ok": False, "moved": [], "failed": [], "error": err}
    root = account_root(alias)
    if root.exists():
        return {"ok": False, "moved": [], "failed": [],
                "error": f"账号 {alias!r} 已存在，请换名或先手动处理。"}
    root.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    failed: list[str] = []
    pairs = [
        (USERDATA_DIR / "user_data.yaml", root / "user_data.yaml"),
        (USERDATA_DIR / "conversations_cache.json", root / "conversations_cache.json"),
        (USERDATA_DIR / "browser_data", root / "browser_data"),
        (USERDATA_DIR / "runs", root / "runs"),
    ]
    for src, dst in pairs:
        if not src.exists():
            continue
        try:
            shutil.move(str(src), str(dst))
            moved.append(src.name)
        except Exception as e:  # noqa: BLE001
            failed.append(f"{src.name}（{e}）")
    # P2-3：迁移后补全账号骨架——旧数据可能只有 browser_data/runs（无顶层 user_data.yaml /
    # conversations_cache.json），账号目录也必须具备四类标准件，adopt-legacy/面板读取才自洽。
    (root / "browser_data").mkdir(exist_ok=True)
    (root / "runs").mkdir(exist_ok=True)
    ud = root / "user_data.yaml"
    if not ud.exists():
        ud.write_text(
            "# 私有用户数据（账号: " + alias + "）—— 会话名/发送内容/发送时间，请勿提交\n"
            "# 由旧数据迁移生成；请在面板「定时任务」页设置发送时间与内容后注册任务。\n\n"
            "targets: []\n"
            "message:\n  texts: [\"在吗\"]\n  random: false\n"
            "schedule:\n  time: \"21:30\"\n",
            encoding="utf-8",
        )
    cc = root / "conversations_cache.json"
    if not cc.exists():
        cc.write_text("[]", encoding="utf-8")
    ok = not failed
    return {"ok": ok, "moved": moved, "failed": failed,
            "error": None if ok else ("部分迁移失败，可重跑续迁："
                                      + "; ".join(failed))}


def task_name(alias: str) -> str:
    """账号的任务名 = 前缀 + 别名（纯 ASCII）。"""
    return "DouyinAutoFire-" + alias


def resolve_account(flag_alias: str | None) -> str:
    """CLI/runner 非交互入口账号解析（spec 4.3/评审拍板④）：

    1) --account 显式 → 用之（不存在则报错列别名 exit 2）；
    2) 未给且恰 1 账号 → 自动沿用（单账号零打扰）；
    3) 未给且多账号 → 报错列别名 exit 2（不默认跑第一个，防串号）；
    4) 未给且 legacy_pending() → 提示先 --migrate，exit 2；
    5) 零账号且无 legacy → 报「请先在面板添加账号或迁移旧数据」，exit 2。
    """
    aliases = list_accounts()
    if flag_alias is not None:
        err = validate_alias(flag_alias)
        if err or flag_alias not in aliases:
            sys.exit(f"账号 {flag_alias!r} 不存在或别名不合法。可用账号：{aliases or '(无)'}")
        return flag_alias
    if len(aliases) == 1:
        return aliases[0]
    if len(aliases) > 1:
        sys.exit(f"存在多个账号（{'、'.join(aliases)}），请用 --account 显式指定要运行的账号。")
    if legacy_pending():
        sys.exit("检测到旧版单账号数据，请先执行：python main.py --migrate <别名> "
                 "或打开面板按迁移引导操作。")
    sys.exit("尚未创建任何账号。请在面板添加账号，或执行 python main.py --migrate <别名> 迁移旧数据。")


# ---------------------------------------------------------------------- #
# 跨进程运行守卫（spec 4.3/P1-1）：userdata/.running 独占文件
# ---------------------------------------------------------------------- #
def _pid_alive(pid: int) -> bool:
    """Windows 上探测 pid 是否存活（tasklist /FI）。"""
    try:
        res = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        return str(pid) in res.stdout
    except Exception:  # noqa: BLE001
        return True  # 探测失败保守视为存活，宁可拦下让用户手动处理


def acquire_run_guard(account: str) -> str | None:
    """独占创建 userdata/.running（O_EXCL）。成功返回 None；已被占用返回占用描述
    （含账号+pid），调用方据此报「账号 X（pid Y）正在运行中」并跳过本次。

    陈旧残留自愈：文件已存在且记录的 pid 不存在 → 删除后重试一次（正常路径跑不到
    重试）。调用方保证 finally 中 release_run_guard()。
    """
    data = {"account": account, "pid": os.getpid(), "start_ts": time.time()}
    for attempt in (1, 2):
        try:
            fd = os.open(RUN_GUARD_PATH,
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return None
        except FileExistsError:
            try:
                cur = json.loads(RUN_GUARD_PATH.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                cur = {}
            pid = int(cur.get("pid") or 0)
            if pid and _pid_alive(pid):
                return f"账号 {cur.get('account', '?')}（pid {pid}）正在运行中"
            # 陈旧残留（pid 已不存在）：删除重试
            try:
                RUN_GUARD_PATH.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                return "运行守卫文件无法清理，请手动删除 userdata/.running 后重试"
            continue
        except OSError as e:
            return f"创建运行守卫失败：{e}"
    return "运行守卫被占用且未能清理，请手动检查 userdata/.running"


def release_run_guard() -> None:
    """释放跨进程守卫（finally 中调用）。"""
    try:
        RUN_GUARD_PATH.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass


def task_name(alias: str) -> str:
    """账号的任务名 = 前缀 + 别名（纯 ASCII）。"""
    return "DouyinAutoFire-" + alias


def resolve_account(flag_alias: str | None) -> str:
    """CLI/runner 非交互入口账号解析（spec 4.3/评审拍板④）：

    1) --account 显式 → 用之（不存在则报错列别名 exit 2）；
    2) 未给且恰 1 账号 → 自动沿用（单账号零打扰）；
    3) 未给且多账号 → 报错列别名 exit 2（不默认跑第一个，防串号）；
    4) 未给且 legacy_pending() → 提示先 --migrate，exit 2；
    5) 零账号且无 legacy → 报「请先在面板添加账号或迁移旧数据」，exit 2。
    """
    aliases = list_accounts()
    if flag_alias is not None:
        err = validate_alias(flag_alias)
        if err or flag_alias not in aliases:
            sys.exit(f"账号 {flag_alias!r} 不存在或别名不合法。可用账号：{aliases or '(无)'}")
        return flag_alias
    if len(aliases) == 1:
        return aliases[0]
    if len(aliases) > 1:
        sys.exit(f"存在多个账号（{'、'.join(aliases)}），请用 --account 显式指定要运行的账号。")
    if legacy_pending():
        sys.exit("检测到旧版单账号数据，请先执行：python main.py --migrate <别名> "
                 "或打开面板按迁移引导操作。")
    sys.exit("尚未创建任何账号。请在面板添加账号，或执行 python main.py --migrate <别名> 迁移旧数据。")


def prompt_messages() -> list[str]:
    """交互式输入要发送的信息；可输入多行（空行结束），用于随机轮换。"""
    print("请输入要发送的信息（每行一条，可输入多条用于随机轮换；输入空行结束）：")
    lines: list[str] = []
    while True:
        try:
            line = input("  > ").strip()
        except EOFError:
            break
        if line == "":
            if lines:
                break
            continue  # 至少输入一条
        lines.append(line)
    return lines or ["在吗"]


def run_once_with_messages(texts: list[str], alias: str):
    """用指定内容立即发送一次（仅本次，不改动配置文件）。走跨进程守卫。"""
    guard_err = acquire_run_guard(alias)
    if guard_err:
        logging.error("无法发送：%s", guard_err)
        return
    try:
        cfg = load_config(alias)
        cfg.setdefault("message", {})["texts"] = texts
        cfg["message"]["random"] = len(texts) > 1
        DouyinStreak(cfg).run()
    except Exception as e:  # noqa: BLE001
        logging.getLogger("douyin-streak").exception("本次运行失败: %s", e)
    finally:
        release_run_guard()


def setup_auto_with_messages(time_str: str, texts: list[str], alias: str):
    """设定时：写回时间+发送内容到账号配置，并注册 Windows 定时任务。"""
    if not TIME_RE.match(time_str):
        logging.error("时间格式不正确，应为 HH:MM（24 小时制），例如 21:30")
        return
    update_schedule_time(alias, time_str)
    update_message_texts(alias, texts)
    logging.info("已将账号 %s 每日时间设为 %s，发送内容已更新（共 %d 条）。",
                 alias, time_str, len(texts))
    if try_register_task(time_str, alias):
        logging.info(
            "✅ 已注册 Windows 定时任务，每天 %s 自动运行，可关闭本窗口。", time_str
        )
        return
    logging.error(
        "未能注册系统定时任务（schtasks 调用失败，多半需要管理员权限或被组策略禁用）。"
        "请检查后重试，或在任务计划程序里手动创建（命令见 docs/命令行与定时任务.md）。"
    )


def try_register_task(time_str: str, alias: str | None = None) -> bool:
    """尝试用 Windows 任务计划程序注册每日定时任务。成功返回 True。

    与面板共用同一套逻辑：schtasks + pythonw runner.py，
    不再依赖 setup_windows_task.ps1（其 COM 调用在后台子进程里会失败）。
    alias 给定 → 任务名 DouyinAutoFire-<别名>，触发命令带 --account；
    alias=None → 旧单任务名 DouyinAutoFire（迁移收尾/兼容旧调用）。
    """
    from pyenv import resolve_python

    python_exe = resolve_python(windowless=True)
    if python_exe is None:
        logging.warning(
            "找不到已安装 playwright 的 Python 解释器。请先执行："
            "uv venv .venv && uv pip install -r requirements.txt"
        )
        return False
    runner = Path(__file__).parent / "runner.py"
    tn = task_name(alias) if alias is not None else TASK_NAME
    trigger = f'"{python_exe}" "{runner}" --run-once' \
        + (f' --account "{alias}"' if alias is not None else "")
    cmd = [
        "schtasks", "/Create", "/TN", tn,
        "/TR", trigger, "/SC", "DAILY", "/ST", time_str, "/F",
    ]
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        logging.warning("调用任务计划程序失败: %s", e)
        return False
    if res.returncode == 0:
        logging.info("定时任务命令: %s", trigger)
        return True
    logging.warning("任务计划程序返回错误:\n%s", (res.stderr or res.stdout).strip())
    return False


def setup_auto(time_str: str, alias: str):
    if not TIME_RE.match(time_str):
        logging.error("时间格式不正确，应为 HH:MM（24 小时制），例如 21:30")
        return
    update_schedule_time(alias, time_str)
    logging.info("已将账号 %s 每日发送时间设置为 %s", alias, time_str)

    if try_register_task(time_str, alias):
        logging.info(
            "✅ 已注册 Windows 定时任务，每天 %s 自动运行，可关闭本窗口。", time_str
        )
        return
    logging.error(
        "未能注册系统定时任务（schtasks 调用失败，多半需要管理员权限或被组策略禁用）。"
        "请检查后重试，或在任务计划程序里手动创建（命令见 docs/命令行与定时任务.md）。"
    )


# ---------------------------------------------------------------------- #
# 交互模式
# ---------------------------------------------------------------------- #
def pick_account_interactive() -> str | None:
    """交互模式账号选择：列表选号；恰 1 个账号直接沿用；
    零账号/未迁移给提示并返回 None（交互模式不 exit，只引导）。"""
    aliases = list_accounts()
    if len(aliases) == 1:
        return aliases[0]
    if aliases:
        print("可用账号：")
        for i, a in enumerate(aliases, 1):
            print(f"  [{i}] {a}")
        try:
            choice = input("请选择账号（输入序号或别名，回车默认第一个）：").strip()
        except EOFError:
            choice = ""
        if not choice:
            return aliases[0]
        if choice.isdigit() and 1 <= int(choice) <= len(aliases):
            return aliases[int(choice) - 1]
        if choice in aliases:
            return choice
        print(f"未识别的账号 {choice!r}，退出。")
        return None
    if legacy_pending():
        print("检测到旧版单账号数据，请先执行：python main.py --migrate <别名>")
        print("（或打开面板按顶部迁移引导操作），完成后再进入交互模式。")
        return None
    print("尚未创建任何账号。请打开面板点「＋ 添加账号」，")
    print("或执行：python main.py --migrate <别名> 迁移旧数据。")
    return None


def interactive(alias: str | None = None):
    if alias is None:
        alias = pick_account_interactive()
        if alias is None:
            return
    print("=" * 42)
    print(f"       抖音自动续火花（账号: {alias}）")
    print("  [1] 手动触发   = 立即给所有目标发一次")
    print("  [2] 定时触发   = 设为每天定时自动发")
    print("=" * 42)
    try:
        choice = input("请选择 (1=手动 / 2=定时)：").strip()
    except EOFError:
        choice = ""
    if choice not in ("1", "2"):
        print("未选择有效模式，退出。")
        return

    msgs = prompt_messages()

    if choice == "1":
        logging.info("手动模式：用本次输入的内容立即发送一次（账号 %s）。", alias)
        run_once_with_messages(msgs, alias)
        return

    # 定时模式：再问时间
    try:
        t = input("请输入每天发送时间（HH:MM，如 21:30）：").strip()
    except EOFError:
        t = ""
    setup_auto_with_messages(t, msgs, alias)


def main():
    parser = argparse.ArgumentParser(description="抖音自动续火花")
    parser.add_argument("time", nargs="?", help="可选：传入 HH:MM 直接设为每日定时（非交互）")
    parser.add_argument("--run-once", action="store_true", help="立即发送一次后退出")
    parser.add_argument("--setup-login", action="store_true", help="仅打开浏览器登录/解验证码，不发送")
    parser.add_argument("--test", action="store_true", help="仅测试依赖与浏览器")
    parser.add_argument("--account", help="指定账号别名（不传且多账号时报错；单账号自动沿用）")
    parser.add_argument("--migrate", metavar="ALIAS", help="迁移旧版单账号数据到新账号目录")
    parser.add_argument("--list-accounts", action="store_true", help="列出所有账号别名")
    args = parser.parse_args()

    config = load_config()  # alias=None：公开键（logging/panel 等），零账号安全
    setup_logging(config)

    if args.list_accounts:
        for a in list_accounts():
            print(a)
        return

    if args.migrate:
        if not legacy_pending():
            print("未检测到旧版单账号数据，无需迁移。")
            return
        # P2-4：迁移占用守卫——期间拒绝任何运行/登录/同步（跨进程也拦），防 browser_data 被占用
        guard_err = acquire_run_guard(args.migrate)
        if guard_err:
            sys.exit(f"有任务正在运行（{guard_err}），请结束运行后再迁移。")
        try:
            res = migrate_legacy_to_account(args.migrate)
        finally:
            release_run_guard()
        if res["ok"]:
            print(f"迁移完成，已移入账号 {args.migrate!r}：{res['moved']}")
            print("提示：旧定时任务 DouyinAutoFire 可能仍在，请在面板执行"
                  "「同步注册新任务并删除旧任务」，或手动 schtasks /Delete /TN DouyinAutoFire /F")
        else:
            sys.exit(f"迁移未完成：{res['error']}")
        return

    if args.test:
        run_test(config)  # --test 免账号
        return

    if args.time or args.run_once or args.setup_login:
        alias = resolve_account(args.account)
        config = load_config(alias)
        setup_logging(config)
        if args.run_once:
            # 复用面板「一键触发」同一套逻辑（写执行记录、串行锁+守卫）。
            import panel
            texts = (config.get("message") or {}).get("texts", [])
            rid = panel.trigger_run([str(t) for t in texts], headless=None, account=alias)
            if rid is None:
                logging.error("已有任务在运行或登录窗口占用，--run-once 跳过。")
                return
            # 等待 worker 写完执行记录
            deadline = time.time() + 15 * 60
            while time.time() < deadline:
                meta = panel._load_meta(rid, alias)
                if meta and meta.get("status") != "running":
                    break
                time.sleep(3)
            return
        if args.setup_login:
            # P1-3/A2：登录窗口同样走跨进程守卫（另一账号定时任务并发时拒绝）
            logging.info("仅打开浏览器供手动登录 / 解验证码（账号 %s，不发送）。", alias)
            guard_err = acquire_run_guard(alias)
            if guard_err:
                logging.error("账号 %s 正在运行中，无法打开登录窗口：%s", alias, guard_err)
                return
            try:
                DouyinStreak(config).setup_login()
            finally:
                release_run_guard()
            return
        if args.time:
            setup_auto(args.time, alias)
            return
    # 无参数或纯交互：账号可空进 interactive（内部选号）
    interactive(args.account)


if __name__ == "__main__":
    main()
