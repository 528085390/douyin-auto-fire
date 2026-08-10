"""
抖音自动续火花 - 自动化核心
使用 Playwright 控制真实 Chromium 浏览器，复用持久化用户目录保存登录态。

流程：
  1. 启动持久化浏览器（登录态存于 user_data_dir）
  2. 访问抖音，检测是否已登录；未登录则等待人工扫码
  3. 从首页点击「消息」进入 IM，按名称匹配各目标会话（私聊/群聊均可）
  4. 逐个打开会话、输入并发送私信（匹配不到则留时间手动点）
"""
from __future__ import annotations

import json
import logging
import random
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import (
    Browser,
    Page,
    Playwright,
    sync_playwright,
)
from playwright.sync_api import TimeoutError as PWTimeout

logger = logging.getLogger("douyin-streak")


class RiskUnsolved(Exception):
    """风控自动解除失败，需用户在浏览器中手动验证。"""


DOUYIN_HOME = "https://www.douyin.com"
# 抖音改版：IM 已独立成单页，首页不再有「消息」浮层入口
DOUYIN_CHAT = "https://www.douyin.com/chat"

# 风控检测的高置信度关键词（仅验证专用文案；普通“验证码登录”等不计入，避免误报）
RISK_KEYWORDS = [
    "安全验证", "请完成安全验证", "请拖动滑块", "滑动验证", "滑块验证", "拖动滑块",
]

# 综合反指纹注入：去掉 webdriver、补全被自动化环境缺失的浏览器特征
STEALTH_JS = """
(() => {
  try { Object.defineProperty(navigator, 'webdriver', { get: () => undefined }); } catch (e) {}
  try { Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en-US', 'en'] }); } catch (e) {}
  try { Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] }); } catch (e) {}
  try {
    const ch = window.chrome || {};
    ch.runtime = {}; ch.loadTimes = () => {}; ch.csi = () => {};
    ch.app = { isInstalled: false, InstallState: {}, RunningState: {} };
    Object.defineProperty(window, 'chrome', { get: () => ch, configurable: true });
  } catch (e) {}
  try {
    // 抹掉自动化环境常见的权限查询差异
    const origQuery = window.navigator.permissions.query;
    if (origQuery) {
      window.navigator.permissions.query = (params) =>
        (params.name === 'notifications'
          ? Promise.resolve({ state: Notification.permission })
          : origQuery.call(window.navigator.permissions, params));
    }
  } catch (e) {}
})();
"""


class DouyinStreak:
    def __init__(self, config: dict):
        self.config = config
        self.browser_cfg = config.get("browser", {})
        self.msg_cfg = config.get("message", {})
        # 支持多目标：targets 列表（私聊/群聊混合）；兼容旧版单 target 配置
        raw_targets = config.get("targets")
        if raw_targets:
            self.targets = raw_targets
        elif config.get("target"):
            self.targets = [config["target"]]
        else:
            self.targets = []
        self.page: Page | None = None
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        # Playwright Python 的 Mouse 没有 position 属性，需自行跟踪当前坐标
        self._mouse_x: float = 0.0
        self._mouse_y: float = 0.0
        # 证据截图目录（每次运行独立目录，由面板创建并传入）
        self.screenshot_dir: Path | None = None
        raw_dir = config.get("screenshot_dir")
        if raw_dir:
            self.screenshot_dir = Path(raw_dir)
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self._ss_counter = 0
        # 本次运行是否因风控自动解除失败、需要用户在浏览器中手动验证
        self.needs_verify: bool = False
        # 本次运行的发送结果统计（供 panel 判定执行记录状态，避免「日志说失败、面板显示成功」）
        self.failed_count: int = 0
        self.total_count: int = 0
        # 前台可见模式下的风控等待时长（秒）；0=后台模式立即停手
        self.verify_wait: int = 0
        # 发送成功强校验。默认严格（编辑器清空 + 气泡回读双条件）；
        # 若某账号下气泡 class 与锚点不匹配导致误判，可置 false 退化为仅查编辑器清空。
        self.strict_verify = bool(self.browser_cfg.get("strict_verify", True))
        # 进度回调：供面板实时展示阶段提示（非日志），签名为 fn(msg: str, context: dict)
        self._progress_callback = config.get("progress_callback")
        # 当前运行进度上下文（total: 总目标数，index: 当前第几个，target: 当前目标名）
        self._run_progress_context: dict = {"total": 0, "index": 0, "target": ""}

    def _progress(self, msg: str):
        """上报阶段提示到面板（不影响日志），同时附带当前进度上下文。"""
        if self._progress_callback:
            try:
                self._progress_callback(msg, self._run_progress_context)
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------ #
    # 上下文管理
    # ------------------------------------------------------------------ #
    def _open_browser(self):
        self._progress("正在打开浏览器…")
        # 真实有头浏览器（headless=False）：指纹正常，不会触发抖音滑块验证，
        # 窗口正常显示在屏幕内（不再挪到屏幕外隐藏）。
        #
        # 背景：headless=true 时抖音 100% 弹拼图验证 -> 任务直接停手；
        #       headless=false（有头）则可稳定发送，故始终用有头模式。
        headless = bool(self.browser_cfg.get("headless", False))
        # 可选：复用本机真实 Chrome 的登录态目录（指纹正常 + 设备已信任 + 已登录 → 不弹验证）
        user_data_dir = self.browser_cfg.get("user_data_dir", "./userdata/browser_data")
        if self.browser_cfg.get("real_chrome_profile"):
            real = self._detect_real_chrome_profile()
            if real:
                user_data_dir = real
                # 复用真实 Chrome 时强制走真实 Chrome，否则指纹仍会被识别为自动化
                self.browser_cfg["channel"] = "chrome"
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        extra_args = list(self.browser_cfg.get("extra_args", []) or [])

        self._pw = sync_playwright().start()
        launch_kwargs = dict(
            user_data_dir=user_data_dir,
            headless=headless,
            args=extra_args,
            locale="zh-CN",
            viewport={"width": 1280, "height": 900},
        )
        # 可选：使用本机安装的 Chrome/Edge（channel），指纹比自带 chromium 更“正常”
        channel = (self.browser_cfg.get("channel") or "").strip()
        if channel:
            launch_kwargs["channel"] = channel
        try:
            self._browser = self._pw.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as e:  # noqa: BLE001
            err = str(e)
            # persistent context 被占用通常是因为另一个浏览器实例还在使用同一 user_data_dir
            if "lock" in err.lower() or "user_data_dir" in err.lower() or "browser context" in err.lower():
                hint = "请先关闭其他浏览器窗口（含你正在用的 Chrome）后再试。" if self.browser_cfg.get("real_chrome_profile") else "请先关闭其他浏览器窗口后再试。"
                raise RuntimeError(
                    f"浏览器数据目录被占用，无法启动新浏览器（{hint}）"
                    f"原始错误：{err}"
                ) from e
            raise
        # 综合反指纹注入，降低被识别为自动化的概率（必须在 new_page 之前注入）
        if STEALTH_JS:
            try:
                self._browser.add_init_script(STEALTH_JS)
            except Exception:  # noqa: BLE001
                pass
        self.page = self._browser.new_page()
        self.page.set_default_timeout(self.browser_cfg.get("timeout", 60) * 1000)

    @staticmethod
    def _detect_real_chrome_profile() -> str | None:
        """探测本机真实 Chrome 的用户数据目录（已登录态所在位置）。"""
        import os
        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome Beta\User Data"),
            str(Path.home() / "AppData/Local/Google/Chrome/User Data"),
        ]
        for c in candidates:
            if c and Path(c).is_dir():
                return c
        return None

    def _close_browser(self):
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("关闭浏览器时出错: %s", e)
        finally:
            self._browser = None
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:  # noqa: BLE001
                    pass
            self._pw = None

    # ------------------------------------------------------------------ #
    # 登录
    # ------------------------------------------------------------------ #
    def _is_logged_in(self) -> bool:
        """在 /chat 上双向判定登录态。

        旧实现找「登录」二字，在 /chat 上不可靠：登录面板内有多处该字样，
        已登录页也可能出现。改用两个互斥的结构信号。
        """
        try:
            if self.page.query_selector(
                    '[data-e2e="conversation-item"], .conversationConversationListwrapper'):
                return True
            if self.page.query_selector(
                    "#login-panel-new, #douyin_login_comp_flat_panel"):
                return False
        except Exception:  # noqa: BLE001
            pass
        return False

    def _goto_chat(self):
        """直达 IM 独立页。取代旧的「首页点消息浮层」链路。"""
        self._progress("正在打开私信页…")
        self.page.goto(DOUYIN_CHAT, wait_until="domcontentloaded", timeout=60000)
        self._check_risk_stop()
        # 会话列表出现即视为 IM 就绪
        self.page.wait_for_selector(
            '[data-e2e="conversation-item"], .conversationConversationListwrapper',
            timeout=30000,
        )
        time.sleep(random.uniform(0.8, 1.6))

    def _ensure_login(self):
        assert self.page is not None
        self._progress("正在打开抖音私信页并检查登录态…")
        logger.info("打开抖音私信页...")
        self.page.goto(DOUYIN_CHAT, wait_until="domcontentloaded")
        time.sleep(2)

        if self._is_logged_in():
            self._progress("已检测到登录态，跳过扫码")
            logger.info("已检测到登录态，跳过扫码。")
            return

        self._progress("未登录，请在弹出的浏览器中扫码 / 登录（最多 5 分钟）")
        logger.info("未登录。请在弹出的浏览器中扫码 / 登录（最多等待 5 分钟）。")
        # 让浏览器可见，方便扫码
        deadline = time.time() + 300
        while time.time() < deadline:
            if self._is_logged_in():
                self._progress("检测到已登录，继续运行")
                logger.info("检测到已登录，继续。")
                return
            time.sleep(2)
        raise RuntimeError("登录超时，请检查网络或重新运行。")

    # ------------------------------------------------------------------ #
    # 仿人操作
    # ------------------------------------------------------------------ #
    def _human_move(self, x: float, y: float, steps: int | None = None):
        """带轻微随机抖动的鼠标移动，模拟人手的非直线轨迹。"""
        assert self.page is not None
        if steps is None:
            steps = random.randint(14, 30)
        cur_x, cur_y = self._mouse_x, self._mouse_y
        for i in range(1, steps + 1):
            t = i / steps
            # 越接近终点，轨迹抖动越小，形成自然的“减速贴靠”
            jitter = (1 - t) * random.uniform(-7, 7)
            nx = cur_x + (x - cur_x) * t + jitter
            ny = cur_y + (y - cur_y) * t + jitter * 0.6
            self.page.mouse.move(nx, ny)
            time.sleep(random.uniform(0.004, 0.018))
        self._mouse_x = x
        self._mouse_y = y

    def _human_click(self, handle, label: str = ""):
        """移动到元素内随机一点，按下-松开之间留人类时差。"""
        assert self.page is not None
        box = handle.bounding_box()
        if not box:
            raise RuntimeError(f"元素不可见，无法点击: {label}")
        cx = box["x"] + box["width"] * random.uniform(0.35, 0.65)
        cy = box["y"] + box["height"] * random.uniform(0.35, 0.65)
        self._human_move(cx, cy)
        time.sleep(random.uniform(0.05, 0.16))
        self.page.mouse.down()
        time.sleep(random.uniform(0.04, 0.12))
        self.page.mouse.up()
        time.sleep(random.uniform(0.12, 0.38))

    def _human_type(self, text: str):
        """以拟人的逐字节奏在“当前焦点”处输入文字。"""
        assert self.page is not None
        # 先清空可能残留内容（Ctrl+A 全选后删除）
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        time.sleep(random.uniform(0.1, 0.3))
        # 逐字输入，每字之间 70~170ms 随机停顿，偶尔来个更长的思考间隔
        for ch in text:
            self.page.keyboard.type(ch, delay=random.uniform(70, 170))
            if random.random() < 0.12:
                time.sleep(random.uniform(0.3, 0.9))

    def _screenshot(self, name: str):
        """保存关键节点截图作为证据（headless 与可见模式均适用）。"""
        if not self.screenshot_dir or self.page is None:
            return
        try:
            self._ss_counter += 1
            ts = datetime.now().strftime("%H%M%S")
            filename = f"{self._ss_counter:03d}_{ts}_{name}.png"
            path = self.screenshot_dir / filename
            self.page.screenshot(path=str(path), full_page=False)
            logger.info("[证据截图] 已保存: %s", filename)
        except Exception as e:  # noqa: BLE001
            logger.warning("[证据截图] 保存失败 (%s): %s", name, e)

    # ------------------------------------------------------------------ #
    # 风控检测
    # ------------------------------------------------------------------ #
    def _detect_risk_control(self) -> bool:
        """检测页面是否出现抖音安全验证（验证码/滑块/拼图）。

        验证通常渲染在一个独立的 iframe 里（主页面 body 在验证期间是空的），
        所以必须遍历所有 frame：检查每个 frame 的可见文本与 URL，命中即返回 True。
        """
        assert self.page is not None
        KEYWORDS = [
            "请完成下列验证后继续", "按住左边按钮", "拖动完成上方拼图", "拖动完成拼图",
            "请拖动滑块", "滑动验证", "滑块验证", "拖动滑块", "按住滑块",
            "拼图验证", "请滑动完成", "请滑动", "安全验证", "请完成安全验证",
            "验证滑块",
        ]
        CAPTCHA_URL_HINTS = (
            "captcha", "nocaptcha", "verifycenter", "rmc.bytedance",
            "geetest", "bscap", "yhgfb",
        )
        try:
            for f in self.page.frames:
                u = (f.url or "").lower()
                try:
                    txt = (
                        f.evaluate(
                            "() => (document.body && document.body.innerText) ? document.body.innerText : ''"
                        )
                        or ""
                    )
                except Exception:  # noqa: BLE001
                    txt = ""
                # 1) 文案命中真实挑战 → 强信号，直接判定
                for kw in KEYWORDS:
                    if kw in txt:
                        return True
                # 2) URL 像验证框架，但页面内容为空（抖音常预加载不可见的 nocaptcha 种子 iframe），
                #    这种「预加载、未激活」的框架不应阻断任务。只有框架里确实渲染了内容才视为验证。
                if any(h in u for h in CAPTCHA_URL_HINTS) and len(txt.strip()) > 0:
                    return True
            return False
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------ #
    # 风控处理：检测到滑块/安全验证即停止任务，交由用户在浏览器中手动处理
    # ------------------------------------------------------------------ #
    def _check_risk_stop(self, wait_sec: int = 0) -> bool:
        """检测到抖音安全验证（滑块/验证码/拼图）即返回 True，由调用方停止任务。

        wait_sec>0（前台可见模式）时：先保持浏览器打开、每隔几秒轮询验证是否已解除，
        解除则返回 False（继续运行）；超过 wait_sec 秒仍未解除才返回 True（停止）。
        """
        if not self._detect_risk_control():
            return False
        if wait_sec and wait_sec > 0:
            self._progress(f"检测到抖音安全验证，请在浏览器中手动处理（最多 {wait_sec} 秒）")
            logger.warning("⚠️ 检测到安全验证，已在可见浏览器中等待你手动处理（最多 %d 秒）…", wait_sec)
            deadline = time.time() + wait_sec
            while time.time() < deadline:
                time.sleep(3)
                if not self._detect_risk_control():
                    self._progress("安全验证已解除，继续运行")
                    logger.info("✅ 安全验证已解除，继续运行。")
                    return False
            logger.error("⚠️ 等待 %d 秒后安全验证仍未解除，停止任务。", wait_sec)
            return True
        return True

    # ------------------------------------------------------------------ #
    # 发送消息
    # ------------------------------------------------------------------ #
    def _pick_text(self) -> str:
        texts = self.msg_cfg.get("texts") or ["在吗"]
        if self.msg_cfg.get("random", True) and len(texts) > 1:
            return random.choice(texts)
        return texts[0]

    ITEM_SEL = '[data-e2e="conversation-item"]'
    LIST_SEL = ".conversationConversationListwrapper"
    ZWSP = "\u200b"

    def _list_conversation_items(self) -> list:
        """枚举当前已渲染的会话项（虚拟列表，只有可视区附近有 DOM）。"""
        return self.page.query_selector_all(self.ITEM_SEL)

    def _item_title(self, item) -> str:
        """会话名。DOM 文本完整，无需处理省略号。"""
        t = item.query_selector(".conversationConversationItemtitle")
        return (t.text_content() or "").strip() if t else ""

    def _item_kind(self, item) -> str:
        """群聊 / 私聊。两种头像节点互斥。"""
        if item.query_selector("img.commonConversationIconnoDrag"):
            return "group"
        return "private"

    def _find_conversation_item(self, name: str, max_scroll: int = 40):
        """在虚拟列表里精确等值查找会话项；找不到返回 None。

        虚拟列表只渲染可视区，必须边滚边找。用外层 data-index 判断是否到底：
        连续 3 屏没有出现新的 index，视为已到列表末尾。
        """
        seen_idx: set[str] = set()
        stagnant = 0
        for _ in range(max_scroll):
            for item in self._list_conversation_items():
                if self._item_title(item) == name:
                    return item
            idx = {
                (d.get_attribute("data-index") or "")
                for d in self.page.query_selector_all(f"{self.LIST_SEL} div[data-index]")
            }
            stagnant = stagnant + 1 if idx <= seen_idx else 0
            seen_idx |= idx
            if stagnant >= 3:
                break
            wrap = self.page.query_selector(self.LIST_SEL)
            if not wrap:
                break
            wrap.evaluate("el => el.scrollBy(0, el.clientHeight * 0.8)")
            time.sleep(random.uniform(0.4, 0.8))
        return None

    def _audit_dump(self, tag: str, name: str = ""):
        """审计：失败时截图 + dump 页面关键结构，用于判定「真找不到」还是「误判」。

        产出两份证据：
          - 截图 `NNN_HHMMSS_audit_<tag>.png`（面板执行记录里可直接查看）
          - JSON `audit_<tag>_<HHMMSS>.json`（含输入框/标题候选/目标名命中位置）
        同时把摘要写入日志，便于在执行记录里直接看到。
        """
        assert self.page is not None
        self._screenshot(f"audit_{tag}")
        try:
            probe = {
                "active": self._active_conversation_name(),
                "items": [
                    {"title": self._item_title(i),
                     "kind": self._item_kind(i),
                     "current": "curConversation" in (i.get_attribute("class") or "")}
                    for i in self._list_conversation_items()
                ],
                "editor": bool(self._locate_chat_input()),
                "editor_text_len": len(self._editor_text()),
            }
            extra_js = r"""
            (name) => {
                const vis = (el) => {
                    if (!el || el.offsetParent === null) return false;
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };
                const rectOf = (el) => {
                    const r = el.getBoundingClientRect();
                    return {x: Math.round(r.left), y: Math.round(r.top),
                            w: Math.round(r.width), h: Math.round(r.height)};
                };
                const out = {url: location.href, viewport: {w: innerWidth, h: innerHeight},
                             nameHits: [], listItems: []};
                // 页面上所有出现目标名的可见叶子节点（判断「页面上到底有没有这个名字」）
                if (name) {
                    for (const el of document.querySelectorAll('*')) {
                        if (!vis(el)) continue;
                        if (el.children.length > 1) continue;
                        const txt = (el.textContent || '').trim();
                        if (!txt.includes(name) || txt.length > 60) continue;
                        out.nameHits.push({txt: txt.slice(0, 60),
                                           cls: (el.getAttribute('class') || '').slice(0, 100),
                                           rect: rectOf(el)});
                        if (out.nameHits.length >= 12) break;
                    }
                }
                // 会话列表容器内的真实列表项（限定范围，避免抓到首页推荐视频）
                const list = document.querySelector('.conversationConversationListwrapper')
                    || document.querySelector('[class*="ConversationListwrapper"]')
                    || document.querySelector('[class*="conversationList"]');
                if (list) {
                    for (const el of list.querySelectorAll('*')) {
                        if (!vis(el)) continue;
                        if (el.children.length > 1) continue;
                        const txt = (el.textContent || '').trim();
                        if (!txt || txt.length < 2 || txt.length > 40) continue;
                        if (out.listItems.indexOf(txt) === -1) out.listItems.push(txt);
                        if (out.listItems.length >= 40) break;
                    }
                } else {
                    out.listContainerFound = false;
                }
                return out;
            }
            """
            extra = self.page.evaluate(extra_js, name or "")
            data = {"tag": tag, "target": name, "probe": probe, "page": extra}
            # 摘要进日志：一眼看出是真找不到还是误判
            logger.warning(
                "[审计-%s] 目标=%s | 右侧当前=%s | 编辑器=%s | 编辑器文本长度=%d | 列表项=%s",
                tag, name, probe.get("active"),
                probe.get("editor"), probe.get("editor_text_len"),
                [i.get("title") for i in probe.get("items", [])][:15],
            )
            if self.screenshot_dir:
                p = self.screenshot_dir / f"audit_{tag}_{datetime.now().strftime('%H%M%S')}.json"
                p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("[审计-%s] dump 失败: %s", tag, e)

    def _active_conversation_name(self) -> str | None:
        """右侧面板当前打开的会话名（群名会带 (人数) 后缀，此处去掉）。"""
        el = self.page.query_selector(".RightPanelHeadertitle")
        if not el:
            return None
        raw = (el.text_content() or "").strip()
        return re.sub(r"\(\d+\)$", "", raw).strip() or None

    def _conversation_is_open(self, name: str) -> bool:
        """双信号校验，任一命中即通过。

        信号 A：左侧该会话项带选中态 class（全列表恰好 1 项有）
        信号 B：右侧标题去后缀后等于目标名

        旧代码有第三态「什么都读不到就保守放行」，那是几何推断不可靠时的妥协。
        现在锚点确定，读不到就是真没打开——放行只会发错人。
        """
        for item in self._list_conversation_items():
            cls = item.get_attribute("class") or ""
            if "curConversation" in cls and self._item_title(item) == name:
                return True
        return self._active_conversation_name() == name

    def _locate_chat_input(self):
        """聊天输入框。/chat 上唯一，无需再排除搜索框。"""
        return self.page.query_selector(
            'div[data-slate-editor="true"][contenteditable="true"]')

    def _editor_text(self) -> str:
        """编辑器当前文本。空态是零宽字符，必须剥掉再判空。"""
        el = self._locate_chat_input()
        if not el:
            return ""
        return (el.text_content() or "").replace(self.ZWSP, "").strip()

    def _last_bubble(self) -> dict:
        """消息列表最后一条气泡：是否本人发出 + 文本内容。"""
        return self.page.evaluate(
            """() => {
                const box = Array.from(
                    document.querySelectorAll('[class*="messageMessageBoxcontentBox"]'));
                if (!box.length) return {from_me: false, text: ""};
                const last = box[box.length - 1];
                const t = last.querySelector('[class*="TextMessageTextpureText"]');
                return {
                    from_me: (last.getAttribute("class") || "").includes("isFromMe"),
                    text: t ? (t.textContent || "").trim() : "",
                };
            }"""
        )

    def _open_conversation(self, target: dict):
        """打开目标会话。/chat 独立页链路。"""
        name = (target.get("name") or "").strip()
        label = "群聊" if target.get("type") == "group" else "私聊"
        if not name:
            raise RuntimeError("目标会话名为空。")

        self._goto_chat()
        self._progress(f"正在查找{label}「{name}」")

        item = self._find_conversation_item(name)
        if item is None:
            # 点不到：列表里根本没有这个名字
            self._audit_dump("no_match", name)
            raise RuntimeError(
                f"未找到{label}「{name}」，请核对名称是否与抖音中显示的完全一致。")

        self._human_click(item, f"{label}「{name}」")
        try:
            self.page.wait_for_selector(
                'div[data-slate-editor="true"][contenteditable="true"]', timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(random.uniform(0.6, 1.2))

        if not self._conversation_is_open(name):
            # 点到了但校验不过：切换失败（与 no_match 语义区分开）
            self._audit_dump("switch_fail", name)
            raise RuntimeError(f"已点击{label}「{name}」但右侧未切换到该会话，跳过以免发错人。")

        self._check_risk_stop()

    def _send_text(self, text: str, target_name: str = ""):
        """发送并强校验。决策 1B：必须有正向证据，不能「没报错即成功」。"""
        if target_name and not self._conversation_is_open(target_name):
            self._audit_dump("wrong_conversation", target_name)
            raise RuntimeError(f"当前打开的不是目标会话「{target_name}」，已跳过以免发错人。")

        el = self._locate_chat_input()
        if not el:
            self._audit_dump("no_editor", target_name)
            raise RuntimeError("未找到聊天输入框。")

        self._human_click(el, "聊天输入框")
        self._human_type(text)
        time.sleep(random.uniform(0.3, 0.7))

        # 内容确实进了编辑器：发送按钮此时应变红
        if not self.page.query_selector("svg.e2e-send-msg-btn.publishRedBtn"):
            logger.warning("输入后发送按钮未变红，可能内容没进编辑器")

        self.page.keyboard.press("Enter")
        time.sleep(random.uniform(0.8, 1.5))

        # Enter 没生效则补点发送按钮
        if self._editor_text():
            btn = self.page.query_selector("svg.e2e-send-msg-btn")
            if btn:
                self._human_click(btn, "发送按钮")
                time.sleep(random.uniform(0.8, 1.5))

        # --- 强校验：两条都满足才算成功 ---
        if self._editor_text():
            self._audit_dump("send_fail", target_name)
            raise RuntimeError("发送后输入框仍有残留文字，判定未发出。")

        bubble = self._last_bubble()
        soft_failed = False
        if not bubble.get("from_me") or bubble.get("text") != text:
            if self.strict_verify:
                self._audit_dump("verify_fail", target_name)
                raise RuntimeError(
                    f"发送校验失败：最后一条气泡 from_me={bubble.get('from_me')} "
                    f"文本不匹配（收到 {len(bubble.get('text') or '')} 字）。"
                )
            # 退化模式：编辑器已清空即认为发出，气泡不符只告警并留证据
            soft_failed = True
            logger.warning(
                "气泡回读校验未通过（strict_verify=false，按发送成功处理）：from_me=%s 字数=%d",
                bubble.get("from_me"), len(bubble.get("text") or ""))
            self._audit_dump("verify_soft_fail", target_name)

        # 截图命名区分「校验通过」与「降级放行」，避免复盘时把降级件误读成成功件
        prefix = "sent_soft" if soft_failed else "sent"
        self._screenshot(f"{prefix}_{target_name}" if target_name else prefix)
        self._check_risk_stop()

    # ------------------------------------------------------------------ #
    # 扫描会话列表（供面板「选会话」一键同步）
    # ------------------------------------------------------------------ #
    def _extract_conversation_names(self, frame=None) -> list[str]:
        """从 IM 会话列表所在的 frame 内提取所有会话名字（去重、过滤无关项）。

        抖音的私信/群聊列表其实渲染在一个 iframe 里，主 document 的 DOM 里看不到，
        因此原先在主页面 evaluate 永远拿不到。这里支持传入具体 frame（IM 列表所在 iframe），
        不传则遍历页面所有 frame（含主帧）兜底提取。
        """
        ctx = frame if frame is not None else self.page
        SKIP = [
            "消息", "加载中", "登录", "注册", "关注", "朋友", "推荐", "发现", "首页", "我",
            "+", "更多", "设置", "通知", "私信", "视频", "聊天", "联系人", "互动", "全部",
            "精选", "直播", "放映厅", "短剧", "小游戏", "搜索", "投稿", "客户端", "壁纸",
            "AI抖音", "未读", "置顶", "暂无", "无消息", "看一下", "更多消息",
        ]
        js = r"""
        (() => {
          const SKIP = new Set(ARG_SKIP);
          const names = new Set();
          // 优先定位到 IM 会话列表容器，避免把首页导航、分类、视频作者等噪声抓进来。
          // 抖音消息浮层的会话列表有稳定的语义 class：conversationConversationListwrapper
          const root = document.querySelector('.conversationConversationListwrapper')
            || document.querySelector('[class*="ConversationListwrapper"]')
            || document.querySelector('[class*="conversationList"]')
            || document.querySelector('[class*="LeftPanelboxList"]')
            || document.querySelector('[class*="componentsLeftPanel"]')
            || document.body;
          if (!root) return [];

          // 1) 带 title / aria-label 的元素（昵称常放在这里，且通常不被截断）
          root.querySelectorAll('[title],[aria-label]').forEach(el => {
            const t = (el.getAttribute('title') || el.getAttribute('aria-label') || '').trim();
            const base = t.split(/[:：]/)[0].trim();
            if (base) names.add(base);
          });
          // 2) 列表项容器：class 含常见会话/消息项关键字
          const sels = ['[class*=conversation]','[class*=session]','[class*=chat]','[class*=contact]',
            '[class*=friend]','[class*=im-item]','[class*=msg]','[class*=list-item]',
            '[class*=cell]','[class*=row]','[class*=item]','[class*=user]','[class*=name-item]'];
          for (const s of sels) {
            root.querySelectorAll(s).forEach(el => {
              // 优先取容器内 class 含 name/nick/title 的子元素（通常是纯昵称）
              const nameEl = el.querySelector('[class*=name],[class*=nick],[class*=title],[class*=label]');
              if (nameEl) {
                const t = (nameEl.textContent || '').trim();
                if (t) names.add(t);
              }
              // 否则取容器内首行文本（昵称通常在第一行，避免把消息预览也带进来）
              const t = (el.innerText || '').trim().split('\n')[0].trim();
              if (t) names.add(t);
            });
          }
          // 3) 头像 + 昵称：找每个 <img>，向上取 4 层祖先，取其首行文本作为昵称
          root.querySelectorAll('img').forEach(img => {
            let p = img.parentElement;
            for (let i = 0; i < 4 && p; i++) p = p.parentElement;
            if (p) {
              const t = (p.innerText || '').trim().split('\n')[0].trim();
              if (t) names.add(t);
            }
          });
          // 注：不采用「短文本叶子节点」兜底，因为会话项里的消息预览、续火花状态
          //（如 "示例内容一" / "重燃中 2/3"）也是叶子节点，会被误当成会话名。
          // 通过 title/aria-label、容器首行、头像祖先已能稳定拿到真实昵称。
          const result = [];
          for (let n of names) {
            if (!n) continue;
            // 去掉末尾的时间戳（抖音列表常把最后消息时间跟昵称排在同一行，如 "示例用户A01:18"）
            n = n.replace(/\d{1,2}:\d{2}(?::\d{2})?$/, '').trim();
            if (!n) continue;
            if (n.length < 2 || n.length > 30) continue;
            if (SKIP.has(n)) continue;
            if (/^\d+$/.test(n)) continue;                        // 纯数字（未读数等）
            if (/^\d{1,2}:\d{2}(?::\d{2})?$/.test(n)) continue;  // 纯时间
            if (/^\d+(\.\d+)?[万亿]$/.test(n)) continue;         // 播放量/点赞数（15.3万）
            if (/^\d{4}[\-/]\d{2}[\-/]\d{2}/.test(n)) continue;  // 日期
            if (/\d\s*\/\s*\d/.test(n)) continue;                 // 状态比例（"重燃中 2/3"）
            if (n.indexOf(' ') !== -1 && n.length > 12) continue; // 长句（消息预览）
            if (/[@#\/\\]/.test(n) && n.length > 12) continue;    // 带 @/# 的长串
            // 消息预览常见带中文冒号或逗号，且多为长句
            if ((n.indexOf('：') !== -1 || n.indexOf('，') !== -1 || n.indexOf('。') !== -1) && n.length > 12) continue;
            result.push(n);
          }
          return result;
        })()
        """
        try:
            data = ctx.evaluate(js.replace("ARG_SKIP", json.dumps(SKIP, ensure_ascii=False)))
            if isinstance(data, list):
                return [str(x) for x in data]
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning("提取会话名字失败: %s", e)
            return []

    def scan_conversations(self) -> list[str]:
        """打开抖音 IM 消息列表，扫描并返回所有私信/群聊会话名字。

        先打开「消息」浮层、等待列表加载完成，再遍历所有「非验证」 frame（含主页面与可能的
        IM 列表 iframe）提取会话名；随后滚动收集长列表里的会话。返回去重后的会话名字列表。
        """
        assert self.page is not None
        self._progress("正在进入私信列表…")
        self._navigate_to_im()
        # 点「消息」后若弹安全验证，前台保持浏览器打开，等用户手动解完再继续
        if self._check_risk_stop(self.verify_wait):
            logger.warning("扫描时检测到抖音安全验证，已停止扫描，请手动处理验证后重试。")
            return []
        self._wait_im_list_ready(timeout=120)
        # 尝试切到「私信/聊天」会话列表（避免停在互动消息 tab）
        self._try_switch_to_chat_tab()
        time.sleep(random.uniform(1.0, 2.0))

        # 遍历所有“非验证” frame 提取（会话列表可能在主页面，也可能在某个 iframe 里）
        def _non_captcha_frames():
            hints = ("captcha", "nocaptcha", "verifycenter", "rmc.bytedance", "geetest", "bscap", "yhgfb")
            return [f for f in self.page.frames if not any(h in (f.url or "").lower() for h in hints)]

        frames = _non_captcha_frames()
        self._progress("正在扫描会话列表…")
        logger.info("扫描 IM 会话列表（容器数=%d）…", len(frames))
        seen: set[str] = set()
        for f in frames:
            for n in self._extract_conversation_names(f):
                seen.add(n)

        scrolled = 0
        stable = 0
        while scrolled < 15:
            for f in frames:
                try:
                    f.evaluate("() => { const el = document.scrollingElement || document.body; if (el) el.scrollTop += 1200; }")
                except Exception:  # noqa: BLE001
                    try:
                        self.page.mouse.wheel(0, 1200)
                    except Exception:  # noqa: BLE001
                        pass
            time.sleep(random.uniform(0.5, 1.0))
            scrolled += 1
            added = 0
            for f in frames:
                for n in self._extract_conversation_names(f):
                    if n not in seen:
                        seen.add(n)
                        added += 1
            if added == 0:
                stable += 1
                # 连续 4 屏无新增，视为列表已到底
                if stable >= 4:
                    break
            else:
                stable = 0
        names = sorted(seen)
        self._progress(f"扫描完成，共发现 {len(names)} 个会话")
        logger.info("扫描完成，共发现 %d 个会话。", len(names))
        # 若扫到 0 条且未触发风控，自动把页面 DOM 结构落到本地文件，便于校准提取规则
        if not names and not self._detect_risk_control():
            self._dump_scan_debug(frames)
        return names

    def _dump_scan_debug(self, frames):
        """扫描结果为 0 且未触发风控时，把各 frame 的文本/URL 与主页面 HTML 落盘，便于校准。"""
        try:
            lines = ["=== SCAN DEBUG (0 results, no risk-control) ==="]
            for i, f in enumerate(frames):
                try:
                    u = f.url or ""
                    txt = (f.evaluate("() => (document.body ? document.body.innerText : '').slice(0, 600)") or "")
                    lines.append(f"--- frame[{i}] url={u}")
                    lines.append("text: " + (txt or "").replace("\n", " ")[:600])
                except Exception as e:  # noqa: BLE001
                    lines.append(f"--- frame[{i}] err={e}")
            try:
                html = (self.page.content() or "")[:10000]
                lines.append("=== MAIN HTML (first 10000 chars) ===")
                lines.append(html)
            except Exception as e:  # noqa: BLE001
                lines.append(f"html err: {e}")
            Path("scan_debug.txt").write_text("\n".join(lines), encoding="utf-8")
            logger.warning("扫描结果为 0，已写入 scan_debug.txt 供排查（含页面结构）。")
        except Exception as e:  # noqa: BLE001
            logger.warning("dump scan debug failed: %s", e)

    def scan(self) -> list[str]:
        """打开浏览器、登录、扫描会话列表并关闭浏览器，返回会话名字列表。

        供面板「选会话」一键同步调用。扫描始终在可见浏览器中进行，遇到安全验证时会
        保持浏览器打开、等待用户手动解（最多 verify_wait 秒），解完再继续扫描。
        """
        self.verify_wait = 300  # 扫描必须可见，遇验证等用户手动解（最长 5 分钟）
        self._progress("开始扫描会话列表")
        try:
            self._open_browser()
            self._ensure_login()
            # 打开首页后若直接弹安全验证（风控），保持浏览器打开等用户手动解
            if self._check_risk_stop(self.verify_wait):
                logger.warning("扫描前检测到抖音安全验证，已停止，请手动处理验证后重试。")
                return []
            return self.scan_conversations()
        finally:
            self._close_browser()

    # ------------------------------------------------------------------ #
    # 对外接口
    # ------------------------------------------------------------------ #
    def run(self):
        """执行续火花。

        风控处理：检测到抖音安全验证（滑块/验证码）即停止任务，标记 needs_verify，
        交由用户在浏览器中手动完成验证后重新触发（不再尝试自动拖动滑块）。
        """
        self.needs_verify = False
        # 前台可见模式（headless=False）下，检测到验证时保持浏览器打开、等用户手动解；后台模式立即停手
        self.verify_wait = 0 if self.browser_cfg.get("headless", False) else 120
        if not self.targets:
            logger.warning("未配置任何目标（config.yaml 的 targets 为空），跳过。")
            return
        try:
            self._open_browser()
            self._ensure_login()
            if self._check_risk_stop(self.verify_wait):
                self.needs_verify = True
                logger.warning(
                    "⚠️ 检测到抖音安全验证，已停止任务。请在浏览器中手动完成后重新触发。"
                )
                return
            total = len(self.targets)
            aborted = False
            failed = 0
            self.total_count = total
            self.failed_count = 0
            for idx, target in enumerate(self.targets, 1):
                name = (target.get("name") or target.get("profile_url") or "?")
                self._run_progress_context = {"total": total, "index": idx, "target": name}
                self._progress(f"【{idx}/{total}】正在处理：{name}")
                logger.info("【%d/%d】处理目标: %s", idx, total, name)
                try:
                    if self._check_risk_stop(self.verify_wait):
                        self.needs_verify = True
                        aborted = True
                        logger.error(
                            "⚠️ 发送过程中触发抖音安全验证（滑块/拼图/验证码），已停止任务。请手动处理后重新触发。"
                        )
                        break
                    self._open_conversation(target)
                    self._send_text(self._pick_text(), target.get("name", ""))
                except RiskUnsolved as e:
                    self.needs_verify = True
                    aborted = True
                    logger.error("⚠️ %s", e)
                    break
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    self.failed_count = failed
                    logger.exception("处理目标「%s」时出错: %s", name, e)
                else:
                    if idx < total:
                        gap = random.uniform(15, 45)
                        logger.info(
                            "等待 %.0f 秒后处理下一个目标（降低风控概率）...", gap
                        )
                        time.sleep(gap)
            if aborted:
                self._progress("因安全验证已停止，请手动处理后重新触发")
                logger.warning("本次因风控已停止任务，未全部完成，请手动处理后重新触发。")
            elif failed:
                self._progress(f"本次有 {failed} 个目标未成功发送")
                logger.warning("本次有 %d 个目标未成功发送（详见上方错误）。", failed)
            else:
                self._progress("本次续火花完成 ✅")
                logger.info("本次续火花完成 ✅（共 %d 个目标）", total)
        except Exception as e:  # noqa: BLE001
            self._progress(f"运行出错：{e}")
            logger.exception("运行主流程出错: %s", e)
        finally:
            self._close_browser()

    def setup_login(self, wait_sec: int = 120):
        """仅打开浏览器供用户手动登录或完成风控验证，不做任何发送。"""
        try:
            self._open_browser()
            self._ensure_login()
            logger.info(
                "浏览器已就绪。若出现验证码/滑块/拼图，请在窗口中手动完成；"
                "完成后关闭窗口即可，程序会自动结束等待（最多 %d 秒）。", wait_sec,
            )
            # 监听浏览器关闭：用户手动关窗口时立即结束等待
            closed_event = threading.Event()
            self._browser.on("close", lambda _: closed_event.set())
            closed_event.wait(timeout=wait_sec)
            if closed_event.is_set():
                logger.info("检测到浏览器窗口已关闭，提前结束等待。")
        finally:
            self._close_browser()


def run_once(config: dict):
    DouyinStreak(config).run()


if __name__ == "__main__":
    # 方便单独测试：python douyin.py
    import yaml

    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logging.basicConfig(level=logging.INFO)
    run_once(cfg)
