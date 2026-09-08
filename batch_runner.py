"""一键出发批量执行器（BAT-001 spec 4.2，独立进程，与面板生命周期解耦）。

用法（由面板 /api/trigger-all 经 pythonw 拉起，也可手动 CLI 调试）：
    python batch_runner.py --batch-all [--stagger-minutes N]
    --stagger-minutes 默认 15（spec 拍板错峰下限）；显式传更小值仅供测试/演示，
    面板启动路径固定不传该参数。执行进度写 userdata/batch_state.json（原子写），
    面板轮询渲染；本进程退出不影响已排队列继续执行。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))

# 守卫/账号工具与 runner.py 同源（runner.py 先例：独立进程 import 模块复用）
from main import (ensure_userdata, USERDATA_DIR, RUN_GUARD_PATH,
                  _pid_alive, list_accounts, account_root)  # noqa: E402
import panel  # noqa: E402  （trigger_run / api_state / list_runs / _load_meta / load_config）

ensure_userdata()
CRASH_LOG = USERDATA_DIR / "run.log"
BATCH_STATE_PATH = USERDATA_DIR / "batch_state.json"


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _log(msg: str) -> None:
    """进度/异常统一落 userdata/run.log（[BATCH] 前缀），与 runner 的 run.log 同源。"""
    try:
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{_now_iso()} [BATCH] {msg}\n")
    except Exception:  # noqa: BLE001
        pass
    print(f"[BATCH] {msg}")


def _crash(msg: str) -> None:
    """任何早期失败都要留下痕迹（镜像 runner._crash）。"""
    try:
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{_now_iso()} [BATCH][FATAL] {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def _read_state() -> dict | None:
    # Windows 下 os.replace 与并发读存在瞬时共享冲突（Errno 13），小重试吸收；
    # FileNotFoundError（未建档/已被清理）直接视为 None。
    for _ in (1, 2, 3):
        try:
            return json.loads(BATCH_STATE_PATH.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except OSError:
            time.sleep(0.05)
        except ValueError:  # JSONDecodeError：损坏/半写文件（O_EXCL 建档被杀）→ None → 走重建自愈
            return None
    return None


def _write_state(st: dict) -> None:
    """原子写（spec 4.2 两写方约定：先读最新 → 只改自己字段 → tmp + os.replace）。

    唯一 tmp（评审 P2-F7）：与面板 /api/batch-cancel 不再共用同名 tmp，
    杜绝互相 os.replace 掉对方文件的 lost-update 窗口。
    """
    tmp = Path(str(BATCH_STATE_PATH) + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    for _ in (1, 2, 3):
        try:
            os.replace(tmp, BATCH_STATE_PATH)
            return
        except OSError:
            time.sleep(0.05)
    # 重试后仍失败：让调用方异常路径兜底（run_batch 收尾置 crashed），不静默吞
    os.replace(tmp, BATCH_STATE_PATH)


def _stale_guard_cleanup() -> bool:
    """守卫文件在但持有 pid 已死 → 删残留。返回是否清理（供外层立即重试）。

    既有自愈（main.acquire_run_guard）只在创建尝试时触发；执行器被动等待期
    无人 acquire，不主动清就会永久 waiting_guard（评审 P1-F1）。
    """
    try:
        raw = RUN_GUARD_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    try:
        pid = int(json.loads(raw).get("pid") or 0)
    except Exception:
        return False  # 解析失败不擅动，交给 acquire 自愈
    if pid and not _pid_alive(pid):
        # 复读确认仍为同一死 pid 才删（评审 P2-F6）：避免毫秒窗口内另一路触发
        # 已对同一陈旧文件做 acquire 自愈重建（活守卫）后被本方误删。
        try:
            cur2 = json.loads(RUN_GUARD_PATH.read_text(encoding="utf-8"))
        except Exception:
            return False
        if int(cur2.get("pid") or 0) != pid:
            return False
        try:
            RUN_GUARD_PATH.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        return True  # 外层守卫等待循环回到循环头重探测；文件再现且 pid 活 → 正常等待
    return False


def _execute_account(st: dict, acc: str, stagger_minutes: int) -> None:
    """按 spec 4.2 逐号流程：预检 → 守卫等待 → 错峰等待 → 防双发 → 触发 → 轮询收尾。

    任何单号异常只落该号 error，不中断整批；取消标志以磁盘 batch_state.json 为准
    （每次 wake 重读，不信任内存副本，评审 P2-F3）。
    """
    # ① 预检（跳过项不占错峰等待，无浏览器动作）
    if acc not in list_accounts():
        st["items"][acc].update(status="skipped", reason="账号不存在")
        _write_state(st)
        return
    try:
        cfg = panel.load_config(acc)
    except Exception as e:  # noqa: BLE001
        st["items"][acc].update(status="error", reason=f"读取账号配置失败: {e}")
        _write_state(st)
        return
    texts = [str(t) for t in (cfg.get("message") or {}).get("texts", [])]
    if not texts:
        st["items"][acc].update(status="skipped", reason="未保存内容，请先为该号保存文案")
        _write_state(st)
        return
    if not (cfg.get("targets") or []):
        st["items"][acc].update(status="skipped", reason="未配置目标会话")
        _write_state(st)
        return
    if not (account_root(acc) / "browser_data").is_dir():
        st["items"][acc].update(status="skipped", reason="尚未登录，请先为该号扫码登录")
        _write_state(st)
        return

    # ② 守卫等待（pid 感知；取消以磁盘为准——评审 P2-F3）
    while True:
        st = _read_state() or st
        item = st["items"][acc]
        if st.get("cancel_requested"):
            item.update(status="skipped", reason="用户取消")
            _write_state(st)
            return
        if not RUN_GUARD_PATH.exists():
            break
        if _stale_guard_cleanup():
            continue  # 删残留后回循环头重探测（P2-F6 外层复查）
        item.update(status="waiting_guard", reason=None)
        _write_state(st)
        time.sleep(5)

    # ③ 错峰等待：上一号实际运行 end + stagger 分钟起算（stagger 默认 15；
    #    功能冒烟用 --stagger-minutes 1 覆盖，故基准必须用参数而非写死 15）；首号
    #    取下限 max(now, 本号最近 run end + stagger)（评审 P2-F3）。
    st = _read_state() or st
    item = st["items"][acc]
    base = st.get("_prev_run_end")
    if not base:
        latest = panel.list_runs(acc, keep=1)  # 防双发同源读取
        if latest and latest[0].get("end"):
            base = latest[0]["end"]
    if base:
        try:
            nxt = datetime.strptime(str(base), "%Y-%m-%d %H:%M:%S") \
                + timedelta(minutes=stagger_minutes)
        except ValueError:
            nxt = datetime.now()
        while datetime.now() < nxt:
            st = _read_state() or st
            item = st["items"][acc]
            if st.get("cancel_requested"):
                item.update(status="skipped", reason="用户取消")
                _write_state(st)
                return
            item.update(status="waiting_stagger",
                        next_start_at=nxt.strftime("%Y-%m-%d %H:%M:%S"))
            _write_state(st)
            time.sleep(5)

    # ④ 防双发复查：本批量 started_at 后该号已被执行过（定时/手动抢先）→ 跳过
    st = _read_state() or st
    item = st["items"][acc]
    latest = panel.list_runs(acc, keep=1)
    if latest and latest[0].get("end") \
            and str(latest[0]["end"]) >= str(st.get("started_at") or ""):
        item.update(status="skipped", reason="本批量开始后已执行过，防同号双发")
        _write_state(st)
        return

    # ⑤ 触发：各号已保存文案，headless=None 走该号 config（同 runner.py 语义）。
    #    trigger_run 返回 None = 守卫被占/内部繁忙 → 回守卫等待语义重试（上限 3 次），
    #    而非原地空等后误报 error（评审 P2-F5）。
    st = _read_state() or st
    item = st["items"][acc]
    item.update(status="running", run_id=None, reason=None, error=None)
    _write_state(st)
    run_id = None
    for _attempt in (1, 2, 3):
        st = _read_state() or st
        item = st["items"][acc]
        if st.get("cancel_requested"):
            item.update(status="skipped", reason="用户取消")
            _write_state(st)
            return
        if RUN_GUARD_PATH.exists() and not _stale_guard_cleanup():
            item.update(status="waiting_guard", reason=None)
            _write_state(st)
            time.sleep(5)
            continue
        run_id = panel.trigger_run(
            panel.api_state(acc).get("message_texts") or texts,
            headless=None, account=acc)
        if run_id:
            break
        time.sleep(5)
    if not run_id:
        item.update(status="error",
                    reason="触发被拒（守卫被占/内部繁忙，重试 3 次后放弃）")
        _write_state(st)
        return
    st = _read_state() or st
    item = st["items"][acc]
    item.update(run_id=run_id)
    _write_state(st)

    # ⑥ 轮询 run meta 至非 running（每 ~3s；运行中号自然收尾，不中途杀浏览器）。
    #    15 分钟 deadline 兜底（镜像 runner.py:101-111）：meta 异常卡 running 时
    #    不拖死整批（评审 P2-F8）。取消由 run_batch 逐号读磁盘 cancel 实现：
    #    本号收尾后自然停整批。
    deadline = time.time() + 15 * 60
    while True:
        meta = panel._load_meta(run_id, acc)
        if meta and meta.get("status") != "running":
            break
        if time.time() > deadline:
            _crash(f"账号 {acc} run {run_id} 超过 15 分钟仍未结束，记 error 继续下一号。")
            break
        time.sleep(3)
    meta = panel._load_meta(run_id, acc) or {}
    status = meta.get("status", "error")
    if status == "running":  # 超时兜底
        status = "error"
        meta = {**meta, "end": _now_iso(), "error": "运行超时（>15 分钟未结束）"}

    # ⑦ 单号收尾显式原子落盘（评审 P2-F4）：不落盘则末号永久 running、
    #    后序号从磁盘读不到 _prev_run_end → 号间错峰基准丢失。
    st = _read_state() or st
    item = st["items"][acc]
    item.update(status=status, end=meta.get("end"),
                failed_targets=list(meta.get("failed_targets") or []),
                error=meta.get("error"))
    st["_prev_run_end"] = meta.get("end") or _now_iso()  # 下一号错峰基准
    _write_state(st)
    _log(f"账号 {acc} 完成：{status}（run {run_id}）")


def run_batch(accounts: list[str], stagger_minutes: int) -> int:
    for acc in accounts:
        st = _read_state()
        if st is None:
            return 1
        if st.get("cancel_requested"):
            _log("收到取消请求，停止后续账号。")
            break
        _execute_account(st, acc, stagger_minutes)
    st = _read_state()
    if st is None:
        return 1
    if st.get("cancel_requested"):
        st["phase"] = "cancelled"
        for it in st["items"].values():
            if it.get("status") in ("pending", "waiting_guard", "waiting_stagger"):
                it.update(status="skipped", reason="用户取消")
    else:
        st["phase"] = "finished"
    st["finished_at"] = _now_iso()
    _write_state(st)
    return 0


def _try_claim(accounts: list[str], stagger_minutes: int) -> bool:
    """独占建档（O_EXCL，同守卫模式）；已激活且 pid 存活 → False。

    陈旧残留（pid 已死）删除后重试一次；终态旧文件（finished/cancelled）同样
    由 pid 探测覆盖——上次进程早已退出 → 删除重建。
    """
    data = {
        "pid": os.getpid(),
        "started_at": _now_iso(),
        "stagger_minutes": stagger_minutes,
        "accounts": accounts,
        "cancel_requested": False,
        "phase": "running",
        "finished_at": None,
        "crashed": False,
        "items": {a: {"status": "pending", "reason": None} for a in accounts},
    }
    for _ in (1, 2):
        try:
            fd = os.open(BATCH_STATE_PATH,
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except FileExistsError:
            cur = _read_state() or {}
            pid = int(cur.get("pid") or 0)
            if pid and _pid_alive(pid):
                return False
            try:
                BATCH_STATE_PATH.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001
                return False
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一键出发批量执行器（BAT-001）")
    parser.add_argument("--batch-all", action="store_true",
                        help="跑全部已添加账号")
    parser.add_argument("--stagger-minutes", type=int, default=15,
                        help="号间错峰分钟数（默认 15；仅测试/演示可传更小值）")
    args = parser.parse_args(argv)
    if not args.batch_all:
        parser.print_usage()
        return 2
    accounts = list_accounts()
    if not accounts:
        _crash("没有已添加账号，退出。")
        return 0
    if not _try_claim(accounts, args.stagger_minutes):
        _crash("已有批量在运行（batch_state.json 记录的 pid 存活），退出。")
        return 2
    _log(f"批量一键出发开始：{len(accounts)} 个账号，错峰 {args.stagger_minutes} 分钟。")
    try:
        rc = run_batch(accounts, args.stagger_minutes)
    except Exception:  # noqa: BLE001
        _crash("批量执行器异常退出（可重按面板「一键出发」或对剩余账号单号补跑）：\n"
               + traceback.format_exc())
        st = _read_state()
        if st is not None:
            st["crashed"] = True
            _write_state(st)
        return 1
    _log("批量一键出发结束。")
    return rc


if __name__ == "__main__":
    sys.exit(main())
