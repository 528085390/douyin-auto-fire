"""定时任务专用入口。

Windows 任务计划程序直接调用：
    pythonw.exe D:\\...\\runner.py --run-once

设计目标：让定时触发 **复用和面板「一键触发」完全相同的代码路径**，
而不是另起一套绕过面板的旁路逻辑。这样：

  * 定时任务和手动触发合流到 panel.trigger_run() -> _worker() 同一套代码，
    行为一致，维护只有一份；
  * 执行记录（runs/<id>.json / 截图 / 执行记录页）照常生成 ——
    以前 runner 直接调 main.job()，绕过了 trigger_run，故「执行记录」里看不到；
  * 不弹命令窗口：用 pythonw + 真实有头 chromium（config 里 headless:false），
    浏览器窗口正常显示在屏幕内（运行定时任务时会有一个可见窗口），指纹正常不会被风控拦截；
  * 最外层兜底仍把任何早期异常（依赖缺失等）写进 run.log，杜绝「exit 1 但日志空白」。

runner 在自己的进程里 import panel 并调用 trigger_run()，与「面板正在运行与否」
无关 —— 这也是与「让 schtasks 直接 curl /api/trigger」方案的本质区别：
后者要求面板常驻，违背定时任务「人不在也能跑」的初衷。
"""
from __future__ import annotations

import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
CRASH_LOG = BASE / "run.log"


def _crash(msg: str) -> None:
    """任何早期失败（依赖缺失、config 损坏）都要留下痕迹。"""
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with CRASH_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{stamp} [FATAL] runner: {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    os.chdir(BASE)
    if str(BASE) not in sys.path:
        sys.path.insert(0, str(BASE))

    # 加载面板模块（含 trigger_run / _worker / DouyinStreak）。失败也留痕。
    try:
        import panel
    except Exception:  # noqa: BLE001
        _crash("导入 panel 模块失败（依赖未安装？）:\n" + traceback.format_exc())
        return 2
    # 关键：让面板日志也写进 run.log，定时运行的痕迹统一在这里
    panel.logger.addHandler(
        __import__("logging").FileHandler(CRASH_LOG, encoding="utf-8")
    )

    if getattr(panel, "DouyinStreak", None) is None:
        _crash("douyin 模块未能加载，无法运行。请确认 playwright 已安装。")
        return 2

    # 复用面板「一键触发」逻辑。headless=None -> 用 config 的 headless 设置
    # （真实有头浏览器，窗口正常显示在屏幕内），而不是手动触发那种强制可见浏览器。
    texts = []
    try:
        if len(sys.argv) > 1 and sys.argv[1] == "--run-once":
            ric = panel.api_state().get("message_texts") or []
            texts = [str(t) for t in ric]
        run_id = panel.trigger_run(texts, headless=None)
    except Exception:  # noqa: BLE001
        _crash("调用 trigger_run 失败:\n" + traceback.format_exc())
        return 1

    if run_id is None:
        _crash("trigger_run 返回 None：当前已有任务在运行或登录窗口占用，已跳过。")
        return 0

    # 等待 worker 线程结束（它是 daemon，但我们要等它把执行记录写完再退）。
    # 轮询 run_id 对应的 meta，直到状态不再是 running 或超时。
    deadline = time.time() + 15 * 60
    while time.time() < deadline:
        try:
            meta = panel._load_meta(run_id)
        except Exception:  # noqa: BLE001
            meta = None
        if meta and meta.get("status") != "running":
            return 0
        time.sleep(3)
    _crash(f"运行 {run_id} 超过 15 分钟仍未结束，runner 进程退出（worker 仍在后台）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
