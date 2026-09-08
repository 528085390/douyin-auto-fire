"""定时任务守护进程（SCH-001 spec 4.3，常驻；面板 /api/scheduler/start 经 pythonw 拉起，
开机经注册表 Run 自启；零 schtasks 定时——拍板⑤）。

主循环每 POLL_SECONDS 一轮：写心跳 → 跨天重置 → 找今日到点未触发任务入队 → 逐条串行执行
（出队重读 → 预检 → 守卫等待 → 错峰 ≥15min → 两段式触发 → 轮询收尾 → 回写 fired）。
与手动/一键出发共用全局守卫 userdata/.running：撞车排队不跳过。错过当日时刻恢复后补跑一次；
fired 含日期跨天重置，不跨天补。

状态文件写方：本进程写 scheduler_state.json / scheduler_heartbeat.json；
面板仅经最小写集改 cancel_requested / stop_requested（先读最新 → 只改标志 → 原子落盘）。
任务条目（scheduler_jobs.json）由面板/迁移写，本进程只读（运行结果放 state，不写 jobs）。
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

from main import (ensure_userdata, USERDATA_DIR, RUN_GUARD_PATH,  # noqa: E402
                  _pid_alive, list_accounts, account_root)
from jobs import load_jobs  # noqa: E402
import panel  # noqa: E402  （smoke 可整体替换 scheduler_daemon.panel = FakePanel）

ensure_userdata()
CRASH_LOG = USERDATA_DIR / "run.log"
STATE_PATH = USERDATA_DIR / "scheduler_state.json"
HEARTBEAT_PATH = USERDATA_DIR / "scheduler_heartbeat.json"
DAEMON_STAGGER_MINUTES = 15        # 拍板④：错峰固定 ≥15（end→start），不暴露配置
POLL_SECONDS = 20                  # 主循环周期（面板判停阈值 ≥3× ≈60s，plan F7）
_GUARD_POLL = 5                    # 守卫/错峰等待内部步长
_META_POLL = 3                     # 轮询 run meta 步长
_RUN_DEADLINE = 15 * 60            # 单任务轮询兜底（runner.py 同款）
_DISPATCH_STALE = 120              # dispatching 无 run_id 判定「未真正触发」的陈旧秒数
AUTOSTART_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_VALUE = "DouyinAutoFireScheduler"


def _now() -> datetime:
    return datetime.now()


def _now_iso() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def _crash(msg: str) -> None:
    """任何早期失败留痕 run.log（runner.py 同款），不弹窗。"""
    try:
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{_now_iso()} [FATAL] scheduler_daemon: {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def _read_json(path: Path) -> dict:
    """读侧兜底：缺失/解析失败（含半写损坏）→ 空文档，不抛不自杀（BAT 纪律）。"""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_json(path: Path, data: dict) -> None:
    """唯一 tmp（带 pid 后缀）+ os.replace 原子写；Errno 13 共享冲突小重试。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    for attempt in range(3):  # noqa: B007
        try:
            os.replace(tmp, path)
            return
        except OSError:
            if attempt >= 2:
                # 重试耗尽：诚实失败（不静默吞），由调用方异常路径兜底
                os.replace(tmp, path)
            time.sleep(0.05)


def set_autostart(enabled: bool) -> bool:
    """注册表 Run 自启写/删（HKCU，无管理员需求）。返回操作结果。"""
    try:
        import winreg
        import pyenv
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
    except Exception:  # noqa: BLE001
        try:
            import winreg
            key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, AUTOSTART_RUN_KEY,
                                     0, winreg.KEY_SET_VALUE)
        except Exception as e:  # noqa: BLE001
            _crash(f"打开注册表 Run 键失败: {e}")
            return False
    try:
        import winreg
        if enabled:
            from pyenv import resolve_python
            python_exe = resolve_python(windowless=True)
            if python_exe is None:
                return False
            value = f'"{python_exe}" "{BASE / "scheduler_daemon.py"}"'
            winreg.SetValueEx(key, AUTOSTART_VALUE, 0, winreg.REG_SZ, value)
        else:
            try:
                winreg.DeleteValue(key, AUTOSTART_VALUE)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:  # noqa: BLE001
        _crash(f"写入注册表自启失败: {e}")
        return False


def _write_heartbeat(current: str, next_due: str | None) -> None:
    data = {
        "pid": os.getpid(),
        "ts": _now_iso(),
        "boot_at": getattr(_write_heartbeat, "_boot", _now_iso()),
        "current": current,
        "next_due": next_due,
    }
    _write_json(HEARTBEAT_PATH, data)


def load_state() -> dict:
    """与磁盘合并的默认状态。fired/last_results 键为 job_id。"""
    base = {
        "date": _today(),
        "fired": {},
        "last_results": {},
        "queue": [],
        "cancel_requested": False,
        "stop_requested": False,
        "prev_run_end": None,
    }
    disk = _read_json(STATE_PATH)
    for k in ("fired", "last_results", "queue"):
        if isinstance(disk.get(k), (dict, list)):
            base[k] = disk[k]
    for k in ("date", "prev_run_end"):
        if isinstance(disk.get(k), str):
            base[k] = disk[k]
    for k in ("cancel_requested", "stop_requested"):
        if isinstance(disk.get(k), bool):
            base[k] = disk[k]
    return base


def _reset_if_new_day(st: dict) -> dict:
    """date 变化 → 对「已入队未触发」条目记跨天结果，再重置 fired/queue/标志。
    last_results 保留最近一次供展示；prev_run_end 保留（不受日期影响）。"""
    if st.get("date") == _today():
        return st
    for jid in st.get("queue", []):
        if jid not in st.get("fired", {}):
            _record(st, jid, {"status": "skipped", "reason": "跨天未及触发"})
    st["date"] = _today()
    st["fired"] = {}
    st["queue"] = []
    st["cancel_requested"] = False
    st["stop_requested"] = False
    return st


def _record(st: dict, job_id: str, fields: dict) -> None:
    """同时维护 fired（当日触发记录）与 last_results（跨天展示）。"""
    fired = dict(st.get("fired") or {})
    fired[job_id] = dict(fired.get(job_id) or {}, **fields)
    st["fired"] = fired
    results = dict(st.get("last_results") or {})
    results[job_id] = dict(results.get(job_id) or {}, **fields)
    st["last_results"] = results


def _reload_job(job_id: str) -> dict | None:
    """出队执行前从磁盘重读任务条目（评审 F4）：不存在/已停用 → None。"""
    for job in load_jobs():
        if job.get("id") == job_id:
            if job.get("enabled") is False:
                return None
            return job
    return None


def _due_jobs(st: dict) -> list[dict]:
    """今日到点 & 今日未 fired & enabled 的任务，按 (time, created_at) 升序。"""
    now_hhmm = _now().strftime("%H:%M")
    due = []
    for job in load_jobs():
        if not job.get("enabled"):
            continue
        if not isinstance(job.get("time"), str) or job["time"] > now_hhmm:
            continue
        if job["id"] in st.get("fired", {}):
            continue
        due.append(job)
    due.sort(key=lambda x: (x.get("time", ""), x.get("created_at", "")))
    return due


def _recover_interrupted(st: dict) -> dict:
    """守护重启复核（评审 F1）：

    - fired.running（带 run_id）→ 轮询既有 run 收尾，不重新触发；
    - fired.dispatching 且无 run_id → at 已陈旧且守卫空闲视为未触发 → 移除条目，
      当天允许重新入队补跑一次。
    """
    fired = dict(st.get("fired") or {})
    changed = False
    for job_id, entry in list(fired.items()):
        status = entry.get("status")
        run_id = entry.get("run_id")
        if status == "running" and run_id:
            meta = _poll_run(run_id, entry.get("account") or "")
            st = _record(st, job_id, {
                "status": meta.get("status", "error"),
                "run_id": run_id,
                "at": entry.get("at"),
                "end": meta.get("end"),
                "error": meta.get("error"),
                "failed_targets": list(meta.get("failed_targets") or []),
            })
            st["prev_run_end"] = meta.get("end") or st.get("prev_run_end")
            changed = True
        elif status == "dispatching" and not run_id:
            try:
                stale_at = datetime.strptime(str(entry.get("at")), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                stale_at = _now()
            guard_free = not RUN_GUARD_PATH.exists()
            if (_now() - stale_at).total_seconds() > _DISPATCH_STALE and guard_free:
                fired.pop(job_id, None)
                st["fired"] = fired
                changed = True
    if changed:
        _write_state(st)
    return st


def _poll_run(run_id: str, account: str) -> dict:
    """轮询 run meta 至非 running；15 分钟 deadline 兜底（runner.py 同款）。"""
    deadline = time.time() + _RUN_DEADLINE
    while True:
        try:
            meta = panel._load_meta(run_id, account)
        except Exception:  # noqa: BLE001
            meta = None
        if meta and meta.get("status") != "running":
            return meta
        if time.time() > deadline:
            return {"status": "error", "end": _now_iso(),
                    "error": "运行超时（>15 分钟未结束）"}
        time.sleep(_META_POLL)


def _clean_stale_guard() -> bool:
    """守卫文件在但持有 pid 已死 → 删残留（返回是否清理）。
    解析失败不擅动（交给 acquire 自愈）；复读确认同一死 pid 才删。"""
    try:
        raw = RUN_GUARD_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    try:
        pid = int(json.loads(raw).get("pid") or 0)
    except Exception:  # noqa: BLE001
        return False
    if pid and not _pid_alive(pid):
        try:
            cur2 = json.loads(RUN_GUARD_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return False
        if int(cur2.get("pid") or 0) != pid:
            return False
        try:
            RUN_GUARD_PATH.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        return True
    return False


def _wait_guard_free(st: dict, jid: str) -> str | None:
    """守卫等待：被占则排队等；陈旧残留自清。返回退出原因（cancel/stop）或 None。"""
    while RUN_GUARD_PATH.exists():
        st = _load_state()
        if st.get("cancel_requested") or st.get("stop_requested"):
            return "用户取消" if st.get("cancel_requested") else "用户停止"
        if _clean_stale_guard():
            continue
        st = _load_state()
        st["queue"] = st.get("queue") or []
        time.sleep(_GUARD_POLL)
    return None


def _latest_run_end_any_account() -> str | None:
    """启动基线：各账号最近一条 run 的 end 取最大（覆盖手动/一键刚跑完的情形）。"""
    latest: str | None = None
    for acc in list_accounts():
        try:
            runs = panel.list_runs(acc, keep=1)
        except Exception:  # noqa: BLE001
            continue
        if runs and runs[0].get("end"):
            end = str(runs[0]["end"])
            if latest is None or end > latest:
                latest = end
    return latest


def _parse_time(txt: str) -> datetime:
    try:
        return datetime.strptime(str(txt), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return _now()


def _execute_job(job: dict, st: dict) -> None:
    """单个任务完整执行（评审 F1/F2/F3/F4 全部语义落点；镜像 batch_runner ①~⑦）。"""
    job_id = job["id"]
    account = job["account"]
    st["queue"] = [x for x in st.get("queue", []) if x != job_id]

    # ① 预检（跳过项不占错峰等待；缺项不拖垮后续任务）
    job = _reload_job(job_id)
    if job is None:
        _record(st, job_id, {"status": "skipped", "reason": "任务已删除/停用"})
        _write_state(st)
        return
    if account not in list_accounts():
        _record(st, job_id, {"status": "skipped", "reason": "账号不存在"})
        _write_state(st)
        return
    if not (job.get("targets") and job.get("texts")):
        _record(st, job_id, {"status": "skipped", "reason": "任务缺少目标或文案"})
        _write_state(st)
        return
    if not (account_root(account) / "browser_data").is_dir():
        _record(st, job_id, {"status": "skipped", "reason": "尚未登录，请先为该号扫码登录"})
        _write_state(st)
        return

    # ② 守卫等待（pid 感知自清；取消/停止以磁盘为准，每轮重读）
    reason = _wait_guard_free(st, job_id)
    if reason:
        _record(st, job_id, {"status": "skipped", "reason": reason})
        _write_state(st)
        return

    # ③ 错峰等待：start ≥ max(now, prev_run_end + 15min)（end→start，拍板④）
    nxt = None
    if st.get("prev_run_end"):
        nxt = _parse_time(st["prev_run_end"]) + timedelta(minutes=DAEMON_STAGGER_MINUTES)
    while nxt and _now() < nxt:
        st = _load_state()
        if st.get("cancel_requested") or st.get("stop_requested"):
            st["queue"] = st.get("queue") or []
            reason = "用户取消" if st.get("cancel_requested") else "用户停止"
            _record(st, job_id, {"status": "skipped", "reason": reason})
            _write_state(st)
            return
        st["current"] = {"job_id": job_id, "account": account,
                         "phase": "waiting_stagger",
                         "next_start_at": nxt.strftime("%Y-%m-%d %H:%M:%S")}
        _write_state(st)
        time.sleep(_GUARD_POLL)
    st = _load_state()
    if st.get("cancel_requested") or st.get("stop_requested"):
        reason = "用户取消" if st.get("cancel_requested") else "用户停止"
        _record(st, job_id, {"status": "skipped", "reason": reason})
        _write_state(st)
        return

    # ④ 两段式落盘（评审 F1）：触发前先写 dispatching，成功后补 run_id/running
    fired = dict(st.get("fired") or {})
    fired[job_id] = {"status": "dispatching", "at": _now_iso(), "account": account}
    st["fired"] = fired
    st["current"] = {"job_id": job_id, "account": account, "phase": "running"}
    _write_state(st)

    run_id = None
    for _attempt in (1, 2, 3):
        st = _load_state()
        if st.get("cancel_requested") or st.get("stop_requested"):
            _record(st, job_id, {"status": "skipped",
                                 "reason": "用户取消" if st.get("cancel_requested")
                                 else "用户停止"})
            _write_state(st)
            return
        if RUN_GUARD_PATH.exists() and not _clean_stale_guard():
            time.sleep(_GUARD_POLL)
            continue
        run_id = panel.trigger_run(
            [str(t) for t in job["texts"]],
            headless=None, account=account,
            targets=[dict(t) for t in job["targets"]],
            persist_texts=False)
        if run_id:
            break
        time.sleep(_GUARD_POLL)
    if not run_id:
        st = _load_state()
        _record(st, job_id,
                {"status": "error", "reason": "触发被拒（守卫被占/内部繁忙，重试 3 次后放弃）"})
        st["queue"] = st.get("queue") or []
        _write_state(st)
        return
    st = _load_state()
    st["fired"] = dict(st.get("fired") or {})
    entry = st["fired"].get(job_id) or {}
    st["fired"][job_id] = {**entry, "run_id": run_id, "status": "running"}
    _write_state(st)

    # ⑤ 轮询收尾（运行中自然收尾，不中途杀浏览器）
    meta = _poll_run(run_id, account)
    status = meta.get("status", "error")
    _record(st, job_id, {
        "status": status,
        "run_id": run_id,
        "at": (entry or {}).get("at") or _now_iso(),
        "end": meta.get("end"),
        "error": meta.get("error"),
        "failed_targets": list(meta.get("failed_targets") or []),
    })
    st = _load_state()
    st["prev_run_end"] = meta.get("end") or _now_iso()
    st["current"] = None
    _write_state(st)


def _skip_remaining(st: dict, reason: str) -> None:
    for jid in list(st.get("queue", [])):
        if jid not in st.get("fired", {}):
            _record(st, jid, {"status": "skipped", "reason": reason})
    st["queue"] = []
    st["cancel_requested"] = False
    st["stop_requested"] = False
    st["current"] = None
    _write_state(st)


def _next_due_str() -> str | None:
    """今日下一个未来时刻（心跳/面板展示用）；无则 None。"""
    now_hhmm = _now().strftime("%H:%M")
    times = [job["time"] for job in load_jobs()
             if job.get("enabled") and isinstance(job.get("time"), str)
             and job["time"] > now_hhmm]
    return min(times) if times else None


def run_daemon() -> int:
    """主循环。返回 0（stop 优雅退出）或异常上抛由调用方兜底。"""
    _write_heartbeat._boot = _now_iso()  # type: ignore[attr-defined]
    st = load_state()
    st = _recover_interrupted(st)
    st = _reset_if_new_day(st)
    if not st.get("prev_run_end"):
        st["prev_run_end"] = _latest_run_end_any_account()
    st.setdefault("queue", [])
    _write_state(st)

    while True:
        st = _load_state()
        st = _reset_if_new_day(st)
        if st.get("stop_requested"):
            _write_heartbeat("stopped", None)
            return 0

        # 队列空 → 补今日到点未触发任务（含错过补跑；重启/唤醒后首次即补）
        if not st.get("queue"):
            due = _due_jobs(st)
            if due:
                st["queue"] = [j["id"] for j in due]
                _write_state(st)

        if not st.get("queue"):
            _write_heartbeat("idle", _next_due_str())
            time.sleep(POLL_SECONDS)
            continue

        jid = st["queue"][0]
        job = _reload_job(jid)
        if job is None:
            _record(st, jid, {"status": "skipped", "reason": "任务已删除/停用"})
            st["queue"] = st["queue"][1:]
            _write_state(st)
            continue

        _write_heartbeat("running_job", None)
        try:
            _execute_job(job, st)
        except Exception as e:  # noqa: BLE001
            _crash(f"任务 {jid} 执行异常: {e}")
            st = _load_state()
            _record(st, jid, {"status": "error", "error": f"守护执行异常: {e}"})
            st.setdefault("queue", [])
            _write_state(st)

        # 单个任务收尾后重新读盘判定 cancel/stop（磁盘为准）
        st = _load_state()
        if st.get("cancel_requested"):
            _skip_remaining(st, "用户取消")
        elif st.get("stop_requested"):
            _skip_remaining(st, "用户停止")
            _write_heartbeat("stopped", None)
            return 0


def main() -> int:
    """防双开：读心跳 pid，存活则退出（记日志）；否则进主循环。"""
    try:
        hb = _read_json(HEARTBEAT_PATH)
        pid = int(hb.get("pid") or 0)
        if pid and pid != os.getpid() and _pid_alive(pid):
            _crash(f"已有守护实例（pid {pid}）在运行，本次启动退出。")
            return 3
    except Exception:  # noqa: BLE001
        pass
    try:
        return run_daemon()
    except Exception as e:  # noqa: BLE001
        _crash(f"守护主循环崩溃: {e}")
        _write_heartbeat("crashed", None)
        return 1


if __name__ == "__main__":
    sys.exit(main())
