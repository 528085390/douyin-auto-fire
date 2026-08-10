"""自检脚本：`python verify.py`

项目没有单元测试，这个脚本承担「改完代码后能不能放心用」的验证职责。
不发送任何消息、不改动已注册的定时任务，可随时安全运行。

覆盖历史上真实踩过的坑：
  1. 定时任务指向了一个已不存在的 python.exe（venv 被删/迁移）
     -> 到点弹一下黑框就 exit 1，浏览器不启动，日志一个字都不写
  2. headless: true 被抖音风控 100% 拦截（拼图滑块），一条也发不出去
  3. bat/vbs 里硬编码的解释器路径同样失效
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

FAILS: list[str] = []
PASSES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    (PASSES if cond else FAILS).append(f"{name}{' :: ' + detail if detail else ''}")


def strip_comments(text: str, kind: str) -> str:
    """剥掉注释，避免把「说明已经不用它了」的注释误判成还在用。"""
    if kind == "vbs":
        return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("'"))
    if kind == "bat":
        return "\n".join(
            l for l in text.splitlines()
            if not l.lstrip().lower().startswith(("rem ", "::"))
        )
    text = re.sub(r'"""[\s\S]*?"""', "", text)
    return "\n".join(l.split("#", 1)[0] for l in text.splitlines())


def read(name: str) -> str:
    return (BASE / name).read_bytes().decode("utf-8", "replace")


# --- 1. 解释器探测 ------------------------------------------------------------
import pyenv  # noqa: E402

py = pyenv.resolve_python(windowless=True)
check("解释器可解析", py is not None)
if py:
    check("解释器文件存在", py.exists(), str(py))
    check("解释器指向项目 .venv", ".venv" in str(py), str(py))
    check("解释器装有 playwright", pyenv._has_playwright(py.with_name("python.exe")))
    check("未解析到已失效的 .workbuddy 路径", ".workbuddy" not in str(py))

# --- 2. runner.py 兜底行为 ----------------------------------------------------
import runner  # noqa: E402

rsrc = read("runner.py")
check("runner 会 chdir 到项目根", "os.chdir(BASE)" in rsrc)
check("runner 默认 --run-once", "--run-once" in rsrc)

tmp = Path(tempfile.mkdtemp(prefix="hermes-verify-"))
orig = runner.CRASH_LOG
try:
    runner.CRASH_LOG = tmp / "run.log"
    runner._crash("verify-probe")
    check("runner 早期异常会写入日志",
          runner.CRASH_LOG.exists()
          and "verify-probe" in runner.CRASH_LOG.read_text(encoding="utf-8"))
finally:
    runner.CRASH_LOG = orig
    for f in tmp.glob("*"):
        f.unlink(missing_ok=True)
    tmp.rmdir()

# --- 3. 已注册的定时任务 ------------------------------------------------------
import panel  # noqa: E402

task = panel.query_system_task()
if task and task.get("exists"):
    cmd = task.get("command", "")
    check("任务不再套 cmd /c（不弹黑框）", not cmd.lower().startswith("cmd /c"))
    check("任务入口是 runner.py", "runner.py" in cmd)
    # 抓出命令里所有 .exe，逐一确认存在。不能只匹配开头的引号形式，
    # 否则退化成 cmd /c 包装时这条断言会「消失」而不是失败。
    exes = re.findall(r'"([^"]+\.exe)"|(\S+\.exe)', cmd, re.I)
    exes = [a or b for a, b in exes]
    check("任务命令可解析出解释器", bool(exes), cmd[:70])
    for e in exes:
        check(f"★任务引用的 exe 真实存在（原 bug 复现点）", Path(e).exists(), e)
    # 定时任务必须复用面板「一键触发」同一套逻辑（写执行记录、串行锁），
    # 而不是绕过 trigger_run 的旁路。runner.py 应当 import panel 并调用 trigger_run。
    rsrc = (BASE / "runner.py").read_text(encoding="utf-8")
    check("runner.py 复用 panel.trigger_run（合流手动触发逻辑）",
          "import panel" in rsrc and "panel.trigger_run" in rsrc)
    check("runner 用真实有头浏览器（不强制 headless=False 可见）",
          "headless=None" in rsrc and "headless=False" not in rsrc.split("trigger_run")[-1])
    check("runner.py 不再直接调 main.job 旁路",
          not re.search(r'^\s*main\.job\s*\(', rsrc, re.M)
          and not re.search(r'DouyinStreak\(cfg\)\.run\(\)\s*$', rsrc, re.M))
else:
    check("定时任务已注册", False, "未找到 DouyinAutoFire（请在面板注册）")

# --- 4. 面板健康自检能识别故障 ------------------------------------------------
_q, _l = panel.query_system_task, panel.load_config
try:
    panel.query_system_task = lambda *a, **k: {
        "exists": True, "command": r'"C:\gone\python.exe" runner.py'}
    h = panel.api_tasks()["health"]
    check("能识别失效的解释器路径",
          not h["ok"] and any("不存在" in p for p in h["problems"]))

    panel.query_system_task = _q
    panel.load_config = lambda: {"browser": {"headless": True}}
    h = panel.api_tasks()["health"]
    check("能识别 headless 会被风控拦截",
          not h["ok"] and any("headless" in p for p in h["problems"]))
finally:
    panel.query_system_task, panel.load_config = _q, _l

h = panel.api_tasks()["health"]
check("当前工程状态健康", h["ok"], str(h["problems"]))

# --- 5. 真实有头浏览器语义（不启动浏览器） -----------------------------------
d = read("douyin.py")
check("不把窗口挪到屏幕外", "--window-position=-32000,-32000" not in d
      and "--start-minimized" not in d)
check("不再读取 offscreen 配置", "offscreen" not in d)
check("extra_args 为拷贝而非别名", 'list(self.browser_cfg.get("extra_args"' in d)

# --- 5b. /chat 独立页链路（2026-08-10 迁移） ----------------------------------
# 抖音改版后首页「消息」浮层入口消失，IM 独立成 /chat 单页。
# 这些断言锁住迁移后的形态，防止回退到浮层时代的补偿逻辑。
import ast  # noqa: E402

dtree = ast.parse(d)
dfuncs = {n.name for n in ast.walk(dtree) if isinstance(n, ast.FunctionDef)}

check("douyin.py 定义 DOUYIN_CHAT 常量", "DOUYIN_CHAT" in d)
check("douyin.py 不再保留 DOUYIN_IM（/im/ 旧页）", "DOUYIN_IM" not in d)
check("导航直达 /chat", "douyin.com/chat" in d)

# 浮层时代的补偿代码必须整体消失（AST 级，避免注释里提到就算数）
for dead in ("_navigate_to_im", "_try_switch_to_chat_tab", "_wait_im_frame",
             "_locator_by_name_prefix", "_chat_panel_probe", "_extract_conversation_names"):
    check(f"已删除浮层时代函数 {dead}", dead not in dfuncs)
check("已删除几何推断 _PROBE_JS", "_PROBE_JS" not in d)

# 新链路必须使用确定性语义锚点
check("使用 data-e2e 会话项埋点", 'data-e2e="conversation-item"' in d)
check("使用 slate 编辑器锚点", "data-slate-editor" in d)
check("使用发送按钮 e2e 锚点", "e2e-send-msg-btn" in d)
check("使用选中态 class 校验会话", "curConversation" in d)
check("使用右侧标题锚点校验会话", "RightPanelHeadertitle" in d)

# ★ C12b 地雷：编辑器空态 textContent 是零宽字符，不是 ""
check("★编辑器判空处理零宽字符 \\u200b（原地雷点）", "\\u200b" in d)

# ★ 1B 强校验：必须有正向证据，不能「没报错即成功」
check("★发送后校验最后一条气泡来自本人（isFromMe）", "isFromMe" in d)

# 决策 2：手动兜底整体移除
check("已删除 30 秒手动兜底", "manual_select_sec" not in d)
check("config.yaml 不再含 manual_select_sec",
      "manual_select_sec" not in read("config.yaml"))

# 审计 tag 齐备：spec 五、错误处理登记的 tag 必须都在代码里发得出来
# （注意：verify_soft_fail 是降级路径的"假成功"标记，绝不能漏——漏了会让
#  verify.py 假绿放过对强校验的误删，正是"verify 没拦住回归"的反面教材）
# 注：verify_fail 硬失败 tag 已在迁移中移除——气泡文本比对不可靠（抖音合并/乱序），
# 真实发送改用「输入框清空+最后 isFromMe 容器」铁证判定，气泡失配只记 verify_soft_fail 不阻断。
for tag in ("no_match", "switch_fail", "wrong_conversation",
            "no_editor", "send_fail", "verify_soft_fail"):
    check(f"审计 tag {tag} 已实现", f'"{tag}"' in d)

# ★ _audit_dump 不能再引用已删的几何探针（否则失败时二次崩溃，吞掉真实原因）
check("★_audit_dump 不再依赖 _chat_panel_probe", "_chat_panel_probe" not in d)

# 强校验退化开关：spec 七、风险第 4 条要求「用户可决策」，必须是可切的代码路径
check("★strict_verify 退化开关存在", "strict_verify" in d)
check("config.yaml 提供 strict_verify", "strict_verify" in read("config.yaml"))

# 风控检测必须保留（/chat 确实存在 nocaptcha 隐藏帧，删了就瞎了）
check("★保留风控检测遍历 frames", "_detect_risk_control" in dfuncs
      and "self.page.frames" in d)

# 扫描结果升级为 [{"name","type"}]，群聊能自动识别
check("扫描区分群聊/私聊", "commonConversationIconnoDrag" in d)

# --- 6. 配置未处于会被风控拦截的状态 ------------------------------------------
import yaml  # noqa: E402

b = yaml.safe_load(read("config.yaml"))["browser"]
check("配置不会触发抖音风控", not b.get("headless"),
      f"headless={b.get('headless')}")

# --- 7. 无残留死路径 ----------------------------------------------------------
for f, kind in {"启动面板.bat": "bat", "抖音续火花.bat": "bat",
                "启动面板.vbs": "vbs", "panel.py": "py", "main.py": "py"}.items():
    if (BASE / f).exists():
        check(f"{f} 无 .workbuddy 死路径", ".workbuddy" not in strip_comments(read(f), kind))

m = strip_comments(read("main.py"), "py")
check("main.py 用 schtasks 注册", '"schtasks", "/Create"' in m)
check("main.py 动态探测解释器", "resolve_python(" in m)
check("已移除 setup_windows_task.ps1", not (BASE / "setup_windows_task.ps1").exists())

# --- 8. .vbs 必须是纯 ASCII ---------------------------------------------------
# cscript/wscript 按 ANSI(中文系统=GBK) 解析 .vbs；若文件存成 UTF-8 且含中文，
# 字符串字面量会被撕裂，双击直接报「未终止的字符串常量」而根本起不来。
for f in BASE.glob("*.vbs"):
    bad = [i + 1 for i, line in enumerate(f.read_bytes().split(b"\n"))
           if any(b > 127 for b in line)]
    check(f"{f.name} 为纯 ASCII（否则 cscript 解析失败）", not bad,
          f"非 ASCII 行: {bad[:5]}" if bad else "")

# --- 汇总 ---------------------------------------------------------------------
print(f"\n通过 {len(PASSES)} / 失败 {len(FAILS)}\n")
for p in PASSES:
    print("  [ok]  ", p)
for f in FAILS:
    print("  [FAIL]", f)
print()
sys.exit(1 if FAILS else 0)
