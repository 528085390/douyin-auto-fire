"""
抖音自动续火花 - 本地管理面板（Web）

纯标准库实现，无需额外 pip 依赖。启动后用浏览器打开面板：
    python panel.py
    # 默认 http://127.0.0.1:8765

面板包含三大块：
  1) 一键触发  —— 填消息内容，点一下立即给所有目标发一次（默认后台/无头运行，不弹浏览器窗口）
  2) 定时任务  —— 查看/设置每日定时（写入 config.yaml 并注册 Windows 任务计划程序）
  3) 执行记录  —— 每一次运行的开始/结束时间、状态、目标、完整日志

注意：
  - 浏览器默认无头（headless）后台运行，不弹窗口。登录态保存在 browser_data/，
    失效时请在面板点「扫码登录」按钮（临时弹出可见浏览器扫码），扫完自动关闭。
  - 同一时刻只能有一个浏览器在跑（user_data_dir 锁冲突），面板会拦截并发触发。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import yaml

try:
    from douyin import DouyinStreak
except Exception:  # noqa: BLE001
    DouyinStreak = None  # 测试/导入失败时仍能让面板启动

from main import (
    update_schedule_time,
    update_message_texts,
    update_targets,
    load_config as _main_load_config,
    ensure_userdata,
    USERDATA_DIR,
)
# 模块加载即确保 userdata/ 骨架存在（缺失自动新建）
ensure_userdata()

from pyenv import resolve_python

BASE = Path(__file__).parent
CONFIG_PATH = BASE / "config.yaml"

# 在 Windows 下以「无窗口」方式运行外部命令（schtasks / powershell 等），
# 避免面板在查询/注册系统定时任务时弹出控制台窗口。
if sys.platform == "win32":
    _HIDDEN_STARTUP = subprocess.STARTUPINFO()
    _HIDDEN_STARTUP.dwFlags = subprocess.STARTF_USESHOWWINDOW
    _HIDDEN_STARTUP.wShowWindow = subprocess.SW_HIDE
else:
    _HIDDEN_STARTUP = None


def _decode_output(raw: bytes, encoding: str = "utf-8") -> str:
    """解码子进程输出。Windows 中文系统常见命令（schtasks/powershell）
    常使用系统默认编码（GBK/CP936），而面板统一用 UTF-8，需要容错回退。"""
    if not raw:
        return ""
    # 优先按调用者指定编码尝试
    try:
        return raw.decode(encoding)
    except UnicodeDecodeError:
        pass
    # Windows 中文环境常见回退编码
    for enc in ("gbk", "gb2312", "cp936"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _run_hidden(cmd, **kw):
    kw["capture_output"] = True
    kw["text"] = False  # 先拿字节，再由 _decode_output 做编码回退
    if sys.platform == "win32":
        kw.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
        kw["startupinfo"] = _HIDDEN_STARTUP
    encoding = kw.pop("encoding", "utf-8")
    # errors 我们自己用，不要传给 subprocess.run，否则 Python 会自动开启 text 模式
    kw.pop("errors", None)
    res = subprocess.run(cmd, **kw)
    if isinstance(res.stdout, bytes):
        res.stdout = _decode_output(res.stdout, encoding)
    if isinstance(res.stderr, bytes):
        res.stderr = _decode_output(res.stderr, encoding)
    return res
RUNS_DIR = USERDATA_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)
HTML_PATH = BASE / "panel.html"
TASK_NAME = "DouyinAutoFire"
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# ---- 全局运行状态（串行执行，避免 user_data_dir 锁冲突） ----
_run_lock = threading.Lock()
_current_run: str | None = None
_login_running: bool = False  # 登录/手动处理窗口（可见浏览器）是否打开中
_sync_running: bool = False   # 选会话：一键同步（扫描 IM 列表）是否进行中
_conversations: list[str] = []  # 最近一次同步扫描到的会话名字
# 会话列表持久化缓存：面板重启后仍能显示上次扫描到的会话，不会「重启即没」
_CONV_CACHE_PATH = USERDATA_DIR / "conversations_cache.json"


def _load_conversations_cache() -> list[str]:
    """启动时从磁盘缓存恢复上一次同步扫到的会话列表。"""
    try:
        if _CONV_CACHE_PATH.exists():
            data = json.loads(_CONV_CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(x) for x in data if x]
    except Exception:  # noqa: BLE001
        pass
    return []


def _save_conversations_cache() -> None:
    """把当前会话列表写回磁盘缓存。"""
    try:
        _CONV_CACHE_PATH.write_text(
            json.dumps(_conversations, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:  # noqa: BLE001
        pass


# 启动时恢复缓存
_conversations = _load_conversations_cache()

# 当前运行任务的阶段提示（给首页实时卡片展示，非原始日志）
# 额外保存本次运行总目标数、当前序号、当前目标名，供前端组合展示进度
_current_progress: dict = {
    "phase": "idle",
    "message": "就绪",
    "total": 0,
    "index": 0,
    "target": "",
    "updated": 0.0,
}


def _set_progress(message: str, context: dict | None = None) -> None:
    """更新阶段提示，由 DouyinStreak 的 progress_callback 调用。

    context 包含 total/index/target，用于前端显示「本次共 X 条 · 已发 Y 条 · 正在给 Z 发送」。
    """
    global _current_progress
    ctx = context or {}
    _current_progress = {
        "phase": "running",
        "message": message,
        "total": int(ctx.get("total") or 0),
        "index": int(ctx.get("index") or 0),
        "target": ctx.get("target") or "",
        "updated": time.time(),
    }
    logger.info("[进度] %s", message)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# 后台（pythonw）运行时没有控制台，统一把日志写入 panel.log
_panel_log = USERDATA_DIR / "panel.log"
try:
    _fh = logging.FileHandler(_panel_log, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logging.getLogger().addHandler(_fh)
except Exception:  # noqa: BLE001
    pass
logger = logging.getLogger("douyin-streak")


# --------------------------------------------------------------------------- #
# 配置读写
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    # 复用 main.load_config：它已做 config.yaml + user_data.yaml 的分层合并
    # （message / targets / schedule 等私有键优先从 user_data.yaml 覆盖），
    # 否则保存进 user_data.yaml 的内容在 /api/state 读不回来，导致刷新后丢失。
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"找不到配置文件: {CONFIG_PATH}")
    return _main_load_config()


# --------------------------------------------------------------------------- #
# 运行记录（每次执行一个目录：<id>.json 元数据 + <id>.log 日志）
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _meta_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.json"


def _log_path(run_id: str) -> Path:
    return RUNS_DIR / f"{run_id}.log"


def _run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def _save_meta(meta: dict):
    with _meta_path(meta["id"]).open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _load_meta(run_id: str) -> dict | None:
    p = _meta_path(run_id)
    if not p.exists():
        return None
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _delete_run(rid: str) -> bool:
    """删除一次运行的元数据、日志和截图目录，返回是否全部成功删除。"""
    ok = True
    for p in (_meta_path(rid), _log_path(rid)):
        try:
            if p.exists():
                p.unlink()
        except Exception as e:  # noqa: BLE001
            logger.warning("删除运行记录文件失败 %s: %s", p, e)
            ok = False
    try:
        d = _run_dir(rid)
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            if d.exists():
                ok = False
    except Exception as e:  # noqa: BLE001
        logger.warning("删除运行截图目录失败 %s: %s", d, e)
        ok = False
    return ok


def list_runs(keep: int | None = 3) -> list[dict]:
    runs = []
    for p in RUNS_DIR.glob("*.json"):
        try:
            with p.open("r", encoding="utf-8") as f:
                runs.append(json.load(f))
        except Exception:  # noqa: BLE001
            continue
    runs.sort(key=lambda m: m.get("id", ""), reverse=True)
    if keep is not None and keep > 0:
        runs = runs[:keep]
    return runs


def prune_runs(keep: int = 3, max_delete: int = 1):
    """只保留最近 keep 条运行记录，超出部分连同元数据、日志和截图目录一并彻底删除。

    为避开沙箱批量删除限制，默认每次只删最旧的 1 条；多次运行/请求后会逐步清完。
    """
    all_runs = []
    for p in RUNS_DIR.glob("*.json"):
        try:
            with p.open("r", encoding="utf-8") as f:
                all_runs.append(json.load(f))
        except Exception:  # noqa: BLE001
            continue
    all_runs.sort(key=lambda m: m.get("id", ""), reverse=True)
    if len(all_runs) <= keep:
        return
    deleted = 0
    # 从最旧的开始删，避免并发时误删正在进行的最新运行
    for old in reversed(all_runs[keep:]):
        rid = old.get("id")
        if not rid:
            continue
        if _delete_run(rid):
            logger.info("已自动清理旧运行记录（含截图目录）：%s", rid)
            deleted += 1
            if deleted >= max_delete:
                break
        else:
            logger.warning("运行记录清理未完全成功（可能受沙箱限制）：%s", rid)


# --------------------------------------------------------------------------- #
# 触发一次运行（后台线程）
# --------------------------------------------------------------------------- #
def _worker(run_id: str, texts: list[str], headless: bool | None = None):
    global _current_run
    log_path = _log_path(run_id)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(fh)
    meta = _load_meta(run_id) or {"id": run_id}
    try:
        if DouyinStreak is None:
            raise RuntimeError("douyin 模块未能加载，无法运行。")
        cfg = load_config()
        # 面板触发统一为可见浏览器（前台），便于实时观察和手动处理安全验证
        cfg["browser"] = {**(cfg.get("browser") or {}), "headless": False}
        if texts:
            cfg.setdefault("message", {})["texts"] = texts
            cfg["message"]["random"] = len(texts) > 1
        # 把本次运行的截图目录传给 DouyinStreak
        ss_dir = str(_run_dir(run_id).resolve())
        cfg["screenshot_dir"] = ss_dir
        cfg["progress_callback"] = _set_progress
        _set_progress("正在启动任务…")
        streak = DouyinStreak(cfg)
        streak.run()
        failed_n = int(getattr(streak, "failed_count", 0) or 0)
        total_n = int(getattr(streak, "total_count", 0) or 0)
        meta["failed"] = failed_n
        meta["total"] = total_n
        if getattr(streak, "needs_verify", False):
            meta["status"] = "needs_verify"
            meta["error"] = meta.get("error") or (
                "触发抖音安全验证（滑块/拼图/验证码），已停止。请在浏览器中手动处理后重新触发。"
            )
        elif failed_n:
            # 关键：有目标没发出去时绝不能记 success，
            # 否则会出现「日志写着未成功发送、执行记录却显示绿色成功」的误导。
            meta["status"] = "partial" if failed_n < total_n else "error"
            meta["error"] = meta.get("error") or (
                f"共 {total_n} 个目标，其中 {failed_n} 个未成功发送（多为未匹配到会话）。"
                "请检查会话名是否与抖音列表完全一致，或在弹出的浏览器中手动点击该会话。"
            )
        else:
            meta["status"] = "success"
    except Exception as e:  # noqa: BLE001
        meta["status"] = "error"
        meta["error"] = str(e)
        logger.exception("本次运行出错: %s", e)
    finally:
        # 无论下面任何清理步骤是否抛异常，都必须释放 _current_run，
        # 否则会出现「任务已结束但面板仍显示运行中、无法再次触发」的状态漂移。
        try:
            meta["end"] = _now_iso()
            _save_meta(meta)
            # 把本次发送内容写回 config.yaml，下次打开面板自动带出，不再被重置
            if texts:
                try:
                    update_message_texts([str(t) for t in texts])
                except Exception as e:  # noqa: BLE001
                    logger.warning("保存发送内容到配置文件失败: %s", e)
            # 只保留最近 3 条，旧的连同截图目录一并彻底删除（不留残留）
            try:
                prune_runs(3)
            except Exception:  # noqa: BLE001
                pass
            logger.removeHandler(fh)
        except Exception as e:  # noqa: BLE001
            logger.exception("运行收尾清理失败（不影响状态重置）: %s", e)
        finally:
            with _run_lock:
                _current_run = None
            _set_progress("任务已结束")
            logger.info("运行 %s 已结束，释放触发锁。", run_id)


def trigger_run(texts: list[str], headless: bool | None = None) -> str | None:
    """启动一次运行。headless=None 用配置默认（默认无头后台）；
    传 False 则弹出可见浏览器供实时观察。若已有运行或登录窗口在进行则返回 None（被占用）。

    注意：登录/手动处理窗口（login_running）不阻塞新运行；若仍占用 browser_data，
    DouyinStreak 启动时会给出明确提示。
    """
    global _current_run
    with _run_lock:
        if _current_run or _login_running:
            return None
        run_id = _new_run_id()
        cfg = load_config()
        targets = [
            (t.get("name") or t.get("profile_url") or "?")
            for t in cfg.get("targets", [])
        ]
        meta = {
            "id": run_id,
            "start": _now_iso(),
            "end": None,
            "status": "running",
            "texts": texts or cfg.get("message", {}).get("texts", []),
            "targets": targets,
            "error": None,
        }
        _save_meta(meta)
        _run_dir(run_id).mkdir(parents=True, exist_ok=True)
        _current_run = run_id
    t = threading.Thread(target=_worker, args=(run_id, texts, headless), daemon=True)
    t.start()
    return run_id


def trigger_login() -> bool:
    """打开一个【可见】浏览器供用户扫码登录（后台运行模式下的登录入口）。

    返回 False 表示当前已有运行或登录窗口在进行，被占用。
    """
    global _login_running
    with _run_lock:
        if _current_run or _login_running:
            return False
        _login_running = True
    t = threading.Thread(target=_login_worker, daemon=True)
    t.start()
    return True


def _login_worker():
    global _login_running
    try:
        if DouyinStreak is None:
            logger.error("douyin 模块未加载，无法打开登录窗口。")
            return
        cfg = load_config()
        # 登录必须可见：强制 headless=False 弹出真实浏览器供扫码
        login_cfg = dict(cfg)
        login_cfg["browser"] = {**(cfg.get("browser") or {}), "headless": False}
        try:
            DouyinStreak(login_cfg).setup_login(wait_sec=240)
            logger.info("登录/验证窗口已关闭。若已扫码或完成验证，下次后台运行将自动复用登录态。")
        except Exception as e:  # noqa: BLE001
            logger.exception("登录/验证窗口运行出错: %s", e)
    finally:
        _login_running = False


def trigger_login_reset() -> bool:
    """强制重置登录/验证窗口状态（浏览器已关闭但面板仍卡住时的兜底）。"""
    global _login_running
    with _run_lock:
        _login_running = False
    logger.warning("已强制重置登录/验证窗口状态。")
    return True


def trigger_run_reset() -> bool:
    """强制重置运行锁（运行已结束但面板仍显示运行中时的兜底）。"""
    global _current_run
    with _run_lock:
        old = _current_run
        _current_run = None
    logger.warning("已强制重置运行状态（原运行 ID: %s）。", old)
    return True


# --------------------------------------------------------------------------- #
# 选会话：一键同步（扫描 IM 私信/群聊列表）
# --------------------------------------------------------------------------- #
def trigger_sync() -> bool:
    """启动一次会话扫描（可见浏览器）。占用 user_data_dir，故与其他运行互斥。"""
    global _sync_running
    with _run_lock:
        if _current_run or _login_running or _sync_running:
            return False
        _sync_running = True
    t = threading.Thread(target=_sync_worker, daemon=True)
    t.start()
    return True


def _sync_worker():
    global _sync_running, _conversations
    try:
        if DouyinStreak is None:
            logger.error("douyin 模块未加载，无法扫描会话。")
            return
        cfg = load_config()
        # 扫描必须可见：强制 headless=False 弹出真实浏览器，IM 列表在有头下更稳
        sync_cfg = dict(cfg)
        sync_cfg["browser"] = {**(cfg.get("browser") or {}), "headless": False}
        try:
            sync_cfg["progress_callback"] = _set_progress
            _set_progress("正在扫描会话列表…")
            _conversations = DouyinStreak(sync_cfg).scan()
            _set_progress(f"扫描完成，共发现 {len(_conversations)} 个会话")
            logger.info("会话扫描完成，发现 %d 个会话。", len(_conversations))
            _save_conversations_cache()
        except Exception as e:  # noqa: BLE001
            logger.exception("会话扫描失败: %s", e)
    finally:
        _sync_running = False



def _delayed_exit():
    """延迟后退出进程（给 HTTP 响应留出时间）。"""
    time.sleep(0.4)
    os._exit(0)


# --------------------------------------------------------------------------- #
# Windows 定时任务
# --------------------------------------------------------------------------- #
def query_system_task(name: str = TASK_NAME) -> dict | None:
    try:
        res = _run_hidden(
            ["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/V"],
            encoding="utf-8", timeout=20,
        )
    except Exception as e:  # noqa: BLE001
        return {"name": name, "exists": False, "error": str(e)}
    if res.returncode != 0:
        return {"name": name, "exists": False}
    # 解析中文字段（不同系统版本标签可能略有差异，做宽松匹配）
    info: dict[str, str] = {}
    for line in res.stdout.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            info[k.strip()] = v.strip()
    status = info.get("状态") or info.get("Status") or ""
    next_run = info.get("下次运行时间") or info.get("Next Run Time") or ""
    last_result = info.get("上次运行结果") or info.get("Last Result") or info.get("上次结果") or ""
    command = info.get("要运行的任务") or info.get("Task To Run") or ""
    return {
        "name": name,
        "exists": True,
        "status": status,
        "enabled": "已禁用" not in status and "Disabled" not in status,
        "next_run": next_run,
        "last_result": last_result,
        "command": command,
    }


def create_task(time_str: str, texts: list[str]) -> dict:
    if not TIME_RE.match(time_str or ""):
        return {"ok": False, "error": "时间格式不正确，应为 HH:MM（24 小时制）。"}
    try:
        update_schedule_time(time_str)
        if texts:
            update_message_texts(texts)
    except PermissionError as e:
        return {
            "ok": False,
            "error": f"无法写入 config.yaml（权限不足或被其他程序占用）：{e}。请关闭可能锁定该文件的编辑器/终端，或尝试以管理员身份重新启动面板。",
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"保存配置失败: {e}"}

    # 用 schtasks 注册普通用户级每日任务（无需管理员权限，登录时运行即可）。
    # 注意：/RL HIGHEST 需要管理员，普通用户会“拒绝访问”，故不指定。
    #
    # 解释器不能用 sys.executable 硬写：面板可能是用一个后来被删除/迁移的 venv 启动的，
    # 那样注册出来的任务到点只会闪一个 cmd 窗口然后 exit 1（run.log 一个字都不写）。
    # 改为每次注册时重新探测并校验（必须能 import playwright）。
    python_exe = resolve_python(windowless=True)
    if python_exe is None:
        return {
            "ok": False,
            "error": (
                "找不到可用的 Python 解释器（需已安装 playwright）。"
                "请在项目目录执行：uv venv .venv && uv pip install -r requirements.txt"
            ),
        }
    # 直接用 pythonw.exe 起 runner.py，不再套 cmd /c：
    #   1) pythonw 无控制台窗口，到点不会弹黑框；
    #   2) runner.py 自己 chdir 到项目根，路径依然正确；
    #   3) 少一层 shell 引号嵌套，schtasks 不容易解析错。
    trigger = f'"{python_exe}" "{BASE / "runner.py"}" --run-once'
    cmd = [
        "schtasks", "/Create", "/TN", TASK_NAME,
        "/TR", trigger, "/SC", "DAILY", "/ST", time_str, "/F",
    ]
    try:
        res = _run_hidden(cmd, encoding="utf-8", errors="replace", timeout=60)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"调用任务计划程序失败: {e}"}
    if res.returncode == 0:
        return {
            "ok": True,
            "message": (res.stdout.strip() or "已创建定时任务。"),
            "task": query_system_task(),
        }
    err = (res.stderr or res.stdout).strip()
    if "拒绝访问" in err or "Access is denied" in err:
        err = "创建系统定时任务被拒绝访问。请尝试“以管理员身份运行”启动本面板，或在任务计划程序里手动创建。"
    return {"ok": False, "error": err[-600:]}


def change_task(action: str) -> dict:
    """action: disable / enable / delete"""
    current = query_system_task()
    if not current.get("exists"):
        if action == "delete":
            return {"ok": True, "task": current, "message": "系统定时任务不存在，无需删除。"}
        return {
            "ok": False,
            "error": "系统定时任务尚未注册，请先点击下方「保存并注册定时任务」。",
        }
    if action == "delete":
        cmd = ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]
    else:
        flag = "/Disable" if action == "disable" else "/Enable"
        cmd = ["schtasks", "/Change", "/TN", TASK_NAME, flag]
    try:
        res = _run_hidden(cmd, encoding="utf-8", timeout=30)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
    if res.returncode == 0:
        return {"ok": True, "task": query_system_task()}
    return {"ok": False, "error": (res.stderr or res.stdout).strip()[-400:]}


# --------------------------------------------------------------------------- #
# API 数据
# --------------------------------------------------------------------------- #
def api_state() -> dict:
    cfg = load_config()
    return {
        "running": _current_run is not None,
        "current_run": _current_run,
        "login_running": _login_running,
        "schedule_time": (cfg.get("schedule") or {}).get("time"),
        "message_texts": (cfg.get("message") or {}).get("texts", []),
        "targets": cfg.get("targets", []),
        "headless": bool((cfg.get("browser") or {}).get("headless", False)),
        "progress": _current_progress.get("message", "就绪"),
        "run_total": _current_progress.get("total", 0),
        "run_index": _current_progress.get("index", 0),
        "run_target": _current_progress.get("target", ""),
    }


def api_tasks() -> dict:
    cfg = load_config()
    task = query_system_task()
    # 健康检查：定时任务注册的解释器路径是否还存在。
    # 历史故障：venv 被删后任务仍指向旧路径，到点只闪一个窗口就 exit 1，日志无任何输出。
    health: dict = {"ok": True, "problems": []}
    if task and task.get("exists"):
        cmdline = task.get("command") or ""
        m = re.match(r'^"([^"]+\.exe)"', cmdline)
        if m and not Path(m.group(1)).exists():
            health["ok"] = False
            health["problems"].append(
                f"定时任务指向的 Python 不存在：{m.group(1)}。请点「保存并注册定时任务」重新注册。"
            )
    if resolve_python(windowless=True, verify=False) is None:
        health["ok"] = False
        health["problems"].append("本机找不到可用的 Python 虚拟环境（.venv）。")
    browser = cfg.get("browser") or {}
    if browser.get("headless"):
        health["ok"] = False
        health["problems"].append(
            "config.yaml 中 headless: true —— "
            "抖音会弹出滑块验证导致定时任务无法发送。请改为 headless: false（真实有头浏览器）。"
        )
    return {
        "schedule_time": (cfg.get("schedule") or {}).get("time"),
        "message_texts": (cfg.get("message") or {}).get("texts", []),
        "system_task": task,
        "health": health,
    }


def api_run_detail(run_id: str) -> dict:
    meta = _load_meta(run_id)
    if meta is None:
        return {"error": "not found"}
    log = ""
    lp = _log_path(run_id)
    if lp.exists():
        try:
            log = lp.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            log = ""
    is_current = run_id == _current_run
    progress_msg = _current_progress.get("message", "就绪") if is_current else ""
    return {
        "meta": meta,
        "log": log,
        "progress": progress_msg,
        "run_total": _current_progress.get("total", 0) if is_current else 0,
        "run_index": _current_progress.get("index", 0) if is_current else 0,
        "run_target": _current_progress.get("target", "") if is_current else "",
    }


def api_run_screenshots(run_id: str) -> list[dict]:
    """列出某次运行的所有截图证据。"""
    d = _run_dir(run_id)
    if not d.exists():
        return []
    shots = []
    for p in sorted(d.glob("*.png")):
        shots.append({
            "filename": p.name,
            "url": f"/api/screenshots/{run_id}/{p.name}",
            "size": p.stat().st_size,
        })
    return shots


def api_conversations() -> dict:
    """返回会话同步状态：是否扫描中、最近一次扫描结果、当前已保存的目标。"""
    cfg = load_config()
    saved = cfg.get("targets", []) or []
    return {
        "syncing": _sync_running,
        "list": list(_conversations),
        "saved": saved,
    }


# --------------------------------------------------------------------------- #
# HTTP 服务
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    # 不往 stdout 打每行请求，避免刷屏
    def log_message(self, fmt, *args):  # noqa: A003
        logger.info("面板请求: " + (fmt % args))

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self):
        html = HTML_PATH.read_text(encoding="utf-8")
        data = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_screenshot(self, run_id: str, filename: str):
        """安全地返回 runs/<run_id>/<filename> 图片文件。"""
        base = _run_dir(run_id).resolve()
        try:
            target = (base / filename).resolve()
            # 防止路径遍历
            if not str(target).startswith(str(base)) or not target.is_file():
                self.send_response(404)
                self.end_headers()
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception:  # noqa: BLE001
            self.send_response(404)
            self.end_headers()

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._send_html()
            if path == "/api/state":
                return self._send_json(api_state())
            if path == "/api/runs":
                # 每次读取列表前都尝试裁剪，确保前端永远看不到超过 3 条
                try:
                    prune_runs(3)
                except Exception:  # noqa: BLE001
                    pass
                return self._send_json({"runs": list_runs()})
            if path == "/api/conversations":
                return self._send_json(api_conversations())
            if path.startswith("/api/runs/"):
                parts = path.strip("/").split("/")
                # /api/runs/<id>/screenshots
                if len(parts) == 4 and parts[-1] == "screenshots":
                    return self._send_json({"screenshots": api_run_screenshots(parts[2])})
                # /api/runs/<id>
                if len(parts) == 3:
                    return self._send_json(api_run_detail(parts[2]))
                return self._send_json({"error": "path not found"}, 404)
            if path.startswith("/api/screenshots/"):
                parts = path.strip("/").split("/")
                if len(parts) == 4:
                    _, _, rid, filename = parts
                    return self._send_screenshot(rid, filename)
                return self._send_json({"error": "path not found"}, 404)
            if path == "/api/tasks":
                return self._send_json(api_tasks())
            self.send_response(404)
            self.end_headers()
        except Exception as e:  # noqa: BLE001
            # 兜底：任何异常都返回 200 + 错误信息，避免前端出现空白“加载失败”
            logger.exception("API GET 出错: %s", e)
            return self._send_json({"error": str(e)}, 200)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._read_body()
            if path == "/api/setup-login":
                ok = trigger_login()
                if not ok:
                    return self._send_json(
                        {"error": "已有任务或登录窗口在运行，请稍后再试。"}, 409
                    )
                return self._send_json(
                    {"ok": True, "message": "已打开可见浏览器，请手动完成登录或安全验证，完成后关闭窗口。"}
                )
            if path == "/api/login-reset":
                trigger_login_reset()
                return self._send_json(
                    {"ok": True, "message": "已强制重置登录窗口状态，可以重新触发运行。"}
                )
            if path == "/api/run-reset":
                trigger_run_reset()
                return self._send_json(
                    {"ok": True, "message": "已强制重置运行状态，可以重新触发。"}
                )
            if path == "/api/sync-conversations":
                ok = trigger_sync()
                if not ok:
                    return self._send_json(
                        {"error": "已有任务、登录窗口或同步在进行中，请稍后再试。"}, 409
                    )
                return self._send_json(
                    {"ok": True, "message": "已开始扫描会话，请在弹出的浏览器中稍候…"}
                )
            if path == "/api/save-targets":
                targets = body.get("targets") or []
                # 校验：只保留含 name 的合法项
                clean = []
                for t in targets:
                    name = (t.get("name") or "").strip()
                    if not name:
                        continue
                    ptype = (t.get("type") or "private").strip() or "private"
                    clean.append({"name": name, "type": ptype})
                if not clean:
                    return self._send_json({"error": "未选择任何会话。"}, 400)
                try:
                    update_targets(clean)
                    # 把已保存的会话名并入缓存列表，保证重启后仍可见（即便未重新扫描）
                    for t in clean:
                        if t["name"] not in _conversations:
                            _conversations.append(t["name"])
                    _save_conversations_cache()
                    return self._send_json(
                        {"ok": True, "message": f"已保存 {len(clean)} 个会话。"}
                    )
                except Exception as e:  # noqa: BLE001
                    return self._send_json({"error": f"保存失败: {e}"}, 200)
            if path == "/api/shutdown":
                self._send_json({"ok": True})
                threading.Thread(target=_delayed_exit, daemon=True).start()
                return
            if path == "/api/trigger":
                texts = body.get("texts") or []
                # 面板触发统一前台（可见浏览器），headless 字段忽略
                rid = trigger_run([str(t) for t in texts], headless=False)
                if rid is None:
                    return self._send_json({"error": "已有任务在运行，请稍后再试。"}, 409)
                return self._send_json({"run_id": rid, "headless": False})
            if path == "/api/save-message":
                texts = body.get("texts") or []
                try:
                    update_message_texts([str(t) for t in texts])
                    return self._send_json({"ok": True, "message": "已保存发送内容。"})
                except Exception as e:  # noqa: BLE001
                    return self._send_json({"error": f"保存失败: {e}"}, 200)
            if path == "/api/tasks":
                res = create_task(body.get("time", ""), body.get("texts") or [])
                return self._send_json(res, 200 if res.get("ok") else 400)
            if path == "/api/tasks/disable":
                return self._send_json(change_task("disable"))
            if path == "/api/tasks/enable":
                return self._send_json(change_task("enable"))
            if path == "/api/tasks/delete":
                return self._send_json(change_task("delete"))
            self.send_response(404)
            self.end_headers()
        except Exception as e:  # noqa: BLE001
            logger.exception("API POST 出错: %s", e)
            return self._send_json({"ok": False, "error": str(e)}, 500)


def main():
    port = 8765
    try:
        cfg = load_config()
        port = int((cfg.get("panel") or {}).get("port", 8765))
    except Exception:  # noqa: BLE001
        pass
    # 启动时先清理旧记录（处理上次异常退出未删干净的残留）
    try:
        prune_runs(3)
    except Exception:  # noqa: BLE001
        pass
    # 若会话缓存为空，则用 config.yaml 里已保存的 targets 作为种子，
    # 保证重启后无需重新扫描也能看到已保存的会话列表。
    global _conversations
    if not _conversations:
        try:
            cfg = load_config()
            for t in (cfg.get("targets") or []):
                name = (t.get("name") or "").strip()
                if name and name not in _conversations:
                    _conversations.append(name)
            if _conversations:
                _save_conversations_cache()
        except Exception:  # noqa: BLE001
            pass
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        logger.error("端口 %s 已被占用，可能已有面板实例在运行：%s", port, e)
        sys.exit(1)
    url = f"http://127.0.0.1:{port}"
    logger.info("管理面板已启动：%s  （Ctrl+C 退出）", url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("正在关闭面板...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
