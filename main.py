"""
抖音自动续火花 - 入口

交互模式（直接运行 python main.py）：
  1. 选择 手动触发 / 定时触发
  2. 输入要发送的信息（可多行，用于随机轮换）
  · 手动触发 -> 用本次输入的内容立即给所有目标发一次（不改配置文件）
  · 定时触发 -> 输入时间(HH:MM)，把时间与内容写入配置并注册 Windows 定时任务

非交互用法：
  python main.py --run-once      # 立即发送一次（使用 config.yaml 的内容）
  python main.py 21:30           # 非交互：直接设为每日 21:30 定时（使用 config.yaml 的内容）
  python main.py --setup-login   # 仅打开浏览器，手动登录/解验证码（不发送）
  python main.py --test          # 仅验证依赖与浏览器能否启动
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

from douyin import DouyinStreak

CONFIG_PATH = Path(__file__).parent / "config.yaml"
USER_DATA_PATH = Path(__file__).parent / "user_data.yaml"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
TASK_NAME = "DouyinAutoFire"  # 与 panel.py 保持一致

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
    """把 schedule.time 写回 user_data.yaml（私有，不进 git）。"""
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
    """把 targets 写回 user_data.yaml（私有，不进 git）。

    targets 为 [{name, type}, ...]，type 默认 private。
    """
    data = _load_user_data()
    data["targets"] = [{"name": str(t.get("name", "")).strip(),
                        "type": str(t.get("type", "private")).strip() or "private"}
                       for t in targets]
    _save_user_data(data)


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


def run_once_with_messages(texts: list[str]):
    """用指定内容立即发送一次（仅本次，不改动配置文件）。"""
    try:
        cfg = load_config()
        cfg.setdefault("message", {})["texts"] = texts
        cfg["message"]["random"] = len(texts) > 1
        DouyinStreak(cfg).run()
    except Exception as e:  # noqa: BLE001
        logging.getLogger("douyin-streak").exception("本次运行失败: %s", e)


def setup_auto_with_messages(time_str: str, texts: list[str]):
    """设定时：写回时间+发送内容到配置，并注册 Windows 定时任务。"""
    if not TIME_RE.match(time_str):
        logging.error("时间格式不正确，应为 HH:MM（24 小时制），例如 21:30")
        return
    update_schedule_time(time_str)
    update_message_texts(texts)
    logging.info("已将每日时间设为 %s，发送内容已更新（共 %d 条）。", time_str, len(texts))
    if try_register_task(time_str):
        logging.info(
            "✅ 已注册 Windows 定时任务，每天 %s 自动运行，可关闭本窗口。", time_str
        )
        return
    logging.error(
        "未能注册系统定时任务（schtasks 调用失败，多半需要管理员权限或被组策略禁用）。"
        "请检查后重试，或在任务计划程序里手动创建（命令见 docs/命令行与定时任务.md）。"
    )


def try_register_task(time_str: str) -> bool:
    """尝试用 Windows 任务计划程序注册每日定时任务。成功返回 True。

    与面板共用同一套逻辑：schtasks + pythonw runner.py，
    不再依赖 setup_windows_task.ps1（其 COM 调用在后台子进程里会失败）。
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
    trigger = f'"{python_exe}" "{runner}" --run-once'
    cmd = [
        "schtasks", "/Create", "/TN", TASK_NAME,
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


def setup_auto(time_str: str):
    if not TIME_RE.match(time_str):
        logging.error("时间格式不正确，应为 HH:MM（24 小时制），例如 21:30")
        return
    update_schedule_time(time_str)
    logging.info("已将每日发送时间设置为 %s", time_str)

    if try_register_task(time_str):
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
def interactive():
    print("=" * 42)
    print("       抖音自动续火花")
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
        logging.info("手动模式：用本次输入的内容立即发送一次。")
        run_once_with_messages(msgs)
        return

    # 定时模式：再问时间
    try:
        t = input("请输入每天发送时间（HH:MM，如 21:30）：").strip()
    except EOFError:
        t = ""
    setup_auto_with_messages(t, msgs)


def main():
    parser = argparse.ArgumentParser(description="抖音自动续火花")
    parser.add_argument("time", nargs="?", help="可选：传入 HH:MM 直接设为每日定时（非交互）")
    parser.add_argument("--run-once", action="store_true", help="立即发送一次后退出")
    parser.add_argument("--setup-login", action="store_true", help="仅打开浏览器登录/解验证码，不发送")
    parser.add_argument("--test", action="store_true", help="仅测试依赖与浏览器")
    args = parser.parse_args()

    config = load_config()
    setup_logging(config)

    if args.test:
        run_test(config)
        return
    if args.run_once:
        # 复用面板「一键触发」同一套逻辑（写执行记录、串行锁）。
        # 通过 panel.trigger_run 在 subprocess 内跑，与 runner.py 完全一致。
        import panel
        panel.setup_logging(config)
        texts = (config.get("message") or {}).get("texts", [])
        rid = panel.trigger_run([str(t) for t in texts], headless=None)
        if rid is None:
            logging.error("已有任务在运行或登录窗口占用，--run-once 跳过。")
            return
        # 等待 worker 写完执行记录
        import time
        deadline = time.time() + 15 * 60
        while time.time() < deadline:
            meta = panel._load_meta(rid)
            if meta and meta.get("status") != "running":
                break
            time.sleep(3)
        return
    if args.setup_login:
        logging.info("仅打开浏览器供手动登录 / 解验证码（不发送）。")
        DouyinStreak(config).setup_login()
        return
    if args.time:
        setup_auto(args.time)
        return
    # 无参数：交互模式
    interactive()


if __name__ == "__main__":
    main()
