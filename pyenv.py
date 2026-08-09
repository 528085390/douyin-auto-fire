"""Python 解释器定位。

定时任务、bat/vbs 启动脚本都需要知道「哪个 python.exe 装了 playwright」。
以前这个路径是硬编码的（%USERPROFILE%\\.workbuddy\\...\\envs\\douyin-auto-fire），
一旦那个 venv 被删除或迁移，定时任务就会静默失败：
弹一个 cmd 窗口 -> 找不到 python.exe -> 立刻退出（exit 1）-> run.log 一个字都不写。

这里统一做「探测 + 校验」：候选路径必须真实存在，且能 import playwright。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent

# 探测顺序：项目内 venv 优先，其次当前解释器，最后历史遗留 / PATH。
_CANDIDATE_DIRS = (
    BASE / ".venv" / "Scripts",
    BASE / "venv" / "Scripts",
    BASE / ".venv" / "bin",
    BASE / "venv" / "bin",
)


def _legacy_env_dir() -> Path | None:
    home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    p = Path(home) / ".workbuddy" / "binaries" / "python" / "envs" / "douyin-auto-fire" / "Scripts"
    return p if p.exists() else None


def _exe_names(windowless: bool) -> tuple[str, ...]:
    if sys.platform != "win32":
        return ("python3", "python")
    # windowless=True 时优先 pythonw.exe（无控制台窗口）
    return ("pythonw.exe", "python.exe") if windowless else ("python.exe",)


def _has_playwright(exe: Path) -> bool:
    """校验该解释器确实装了 playwright（避免选到一个空的系统 python）。"""
    try:
        res = subprocess.run(
            [str(exe), "-c", "import playwright"],
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return res.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def iter_candidates(windowless: bool = False):
    """按优先级产出候选解释器路径（已确认文件存在，未校验依赖）。"""
    dirs = list(_CANDIDATE_DIRS)
    legacy = _legacy_env_dir()
    if legacy:
        dirs.append(legacy)
    for d in dirs:
        for name in _exe_names(windowless):
            exe = d / name
            if exe.exists():
                yield exe

    # 当前正在运行的解释器（面板/main.py 自身）
    cur = Path(sys.executable)
    if cur.exists():
        if windowless and sys.platform == "win32":
            w = cur.with_name("pythonw.exe")
            if w.exists():
                yield w
        yield cur


def resolve_python(windowless: bool = False, verify: bool = True) -> Path | None:
    """返回可用的 python 解释器路径；找不到返回 None。

    windowless=True 时优先返回 pythonw.exe（定时任务用，避免弹控制台窗口）。
    verify=True 时会实际执行 `python -c "import playwright"` 做一次校验。
    """
    fallback: Path | None = None
    for exe in iter_candidates(windowless):
        if fallback is None:
            fallback = exe
        if not verify:
            return exe
        # pythonw 无法回读 stdout，用同目录 python.exe 校验
        probe = exe.with_name("python.exe") if exe.name == "pythonw.exe" else exe
        if not probe.exists():
            probe = exe
        if _has_playwright(probe):
            return exe
    return fallback


def describe() -> str:
    """诊断输出：列出所有候选及其校验结果。"""
    lines = []
    for exe in iter_candidates(windowless=False):
        lines.append(f"  {exe}  playwright={'OK' if _has_playwright(exe) else 'MISSING'}")
    return "\n".join(lines) or "  (未找到任何候选解释器)"


if __name__ == "__main__":
    print("候选解释器：")
    print(describe())
    print("\n选中（有窗口）:", resolve_python())
    print("选中（无窗口）:", resolve_python(windowless=True))
