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
            probe = self._chat_panel_probe(name)
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
                "[审计-%s] 目标=%s | 输入框=%s | 标题=%s | 候选=%s | 左侧选中=%s | 页面命中目标名=%d处 | 列表项=%s",
                tag, name, probe.get("hasInput"), probe.get("title"),
                probe.get("candidates"), probe.get("activeItems"),
                len(extra.get("nameHits") or []),
                (extra.get("listItems") or [])[:15],
            )
            if self.screenshot_dir:
                p = self.screenshot_dir / f"audit_{tag}_{datetime.now().strftime('%H%M%S')}.json"
                p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("[审计-%s] dump 失败: %s", tag, e)

    def _conversation_is_open(self, name: str, probe: dict | None = None) -> bool:
        """判断右侧聊天面板当前是否确实打开了目标会话。"""
        if not name:
            return False
        p = probe if probe is not None else self._chat_panel_probe(name)
        if not p.get("hasInput"):
            return False
        if p.get("hasName") or p.get("nameInActive"):
            return True
        title = p.get("title") or ""
        return bool(title and name in title)

    def _active_conversation_name(self) -> str | None:
        """读取右侧聊天面板顶部当前显示的会话名，用于验证会话切换成功。"""
        assert self.page is not None
        # 优先使用语义明显的 header title/name 选择器
        selectors = [
            '[class*="chatHeader"] [class*="title"]',
            '[class*="chatHeader"] [class*="name"]',
            '[class*="conversationHeader"] [class*="title"]',
            '[class*="conversationHeader"] [class*="name"]',
            '[class*="sessionHeader"] [class*="title"]',
            '[class*="sessionHeader"] [class*="name"]',
            '[class*="imHeader"] [class*="title"]',
            '[class*="imHeader"] [class*="name"]',
            '[class*="rightPanel"] [class*="title"]',
            '[class*="rightPanel"] [class*="name"]',
            '[class*="chatPanel"] [class*="title"]',
            '[class*="chatPanel"] [class*="name"]',
            '[class*="conversationMain"] [class*="title"]',
            '[class*="conversationMain"] [class*="name"]',
        ]
        for s in selectors:
            try:
                el = self.page.query_selector(s)
                if el and el.is_visible():
                    txt = (el.text_content() or "").strip()
                    if txt and 2 <= len(txt) <= 50:
                        return txt
            except Exception:  # noqa: BLE001
                continue

        # 兜底：用几何探测（输入框正上方同列 + 浮层边界）推断标题
        probe = self._chat_panel_probe()
        title = probe.get("title")
        return str(title) if title else None

    def _locate_chat_input(self):
        """在当前已打开的会话里找聊天输入框（contenteditable），排除搜索框。

        取可见且尺寸最大的 contenteditable/textarea（聊天框明显大于搜索框）。
        同时兼容首页「消息」浮层与完整 IM 页面。
        会话刚打开时输入框可能需要一点时间渲染，因此先等待其可见再定位。
        """
        assert self.page is not None

        def _is_search(el) -> bool:
            ph = (el.get_attribute("placeholder") or "") + (
                el.get_attribute("aria-label") or ""
            )
            cls = el.get_attribute("class") or ""
            return ("搜索" in ph) or ("search" in (ph + cls).lower())

        # 先等输入框出现（点击会话后右侧聊天区/输入框需要渲染时间）
        try:
            self.page.wait_for_selector(
                "div[contenteditable='true'], textarea",
                state="visible", timeout=15000,
            )
        except Exception:  # noqa: BLE001
            pass

        best = None
        best_area = -1
        for h in self.page.query_selector_all("div[contenteditable='true'], textarea"):
            if _is_search(h):
                continue
            if not h.is_visible():
                continue
            b = h.bounding_box()
            if not b:
                continue
            if b["width"] > 80 and b["height"] > 15:
                area = b["width"] * b["height"]
                if area > best_area:
                    best = h
                    best_area = area
        if best is not None:
            return best
        raise RuntimeError("未找到聊天输入框（可能会话未真正打开）。")

    def _open_conversation(self, target: dict):
        """打开单个目标会话（私聊或群聊）。

        流程：仅通过首页「消息」入口进入 IM 浮层 → 等待会话列表加载完成
        （列表显示「加载中」时持续等待，最多 2 分钟）→ 按名称匹配并点击会话。
        严格禁止使用搜索框。若仍匹配不到，留时间人工点击。
        """
        assert self.page is not None
        name = (target.get("name") or "").strip()
        ptype = (target.get("type") or "private").lower()
        label = "群聊" if ptype == "group" else "私聊"

        # 仅通过首页「消息」入口进入 IM，不使用搜索
        self._navigate_to_im()
        # 确保当前在「私信/聊天」列表 tab（某些版本默认停在「互动/通知」）
        self._try_switch_to_chat_tab()

        if name:
            # 列表若正在「加载中」，就一直等它加载完（最多 2 分钟）
            self._progress(f"正在查找{label}会话「{name}」")
            self._wait_im_list_ready(timeout=120)
            logger.info("匹配%s会话: %s", label, name)
            if self._click_conversation(name, timeout=30000):
                # 点击后给右侧聊天面板切换留出时间，避免还没切过去就填消息
                time.sleep(random.uniform(2.0, 3.0))
                self._progress(f"已打开{label}会话「{name}」")
                logger.info("已打开%s会话。", label)
                return
            # 列表可能很长，向下滚动后再试一次（避免名字在视口外）
            self._progress("会话列表较长，正在滚动查找…")
            logger.info("首次未命中，尝试滚动列表后再次匹配…")
            try:
                self.page.mouse.wheel(0, 1500)
                time.sleep(random.uniform(1.5, 2.5))
            except Exception:  # noqa: BLE001
                pass
            if self._click_conversation(name, timeout=30000):
                time.sleep(random.uniform(2.0, 3.0))
                self._progress(f"已打开{label}会话「{name}」")
                logger.info("已打开%s会话。", label)
                return
            logger.warning("自动未匹配到%s「%s」。", label, name)
            # 审计：两次都没命中，留下截图与结构快照供事后核对
            self._audit_dump("no_match", name)

        manual = int(self.browser_cfg.get("manual_select_sec", 30))
        self._progress(f"未自动匹配到{label}「{name}」，请在 {manual} 秒内手动点击该会话")
        logger.info(
            "请在 %d 秒内手动点击目标%s会话，脚本随后会自动填写并发送。",
            manual,
            label,
        )
        time.sleep(manual)
        # 手动兜底结束后再探测一次：用户可能已手动点开会话
        if name:
            p = self._chat_panel_probe(name)
            if self._conversation_is_open(name, probe=p):
                logger.info("手动兜底后检测到会话「%s」已打开（标题=%s）", name, p.get("title"))
                self._progress(f"已打开{label}会话「{name}」")
            else:
                self._audit_dump("manual_timeout", name)

    def _send_text(self, text: str, target_name: str = ""):
        assert self.page is not None
        # 发送前再确认一次风控：若已触发验证，直接停止交由用户手动处理
        if self._check_risk_stop():
            raise RiskUnsolved("发送前检测到抖音风控，已停止，请手动处理后重新触发。")
        self._progress("正在填写消息内容…")
        logger.info("定位聊天输入框并填入: %s", text)
        box = self._locate_chat_input()

        # 双保险：确认当前右侧聊天面板确实打开的是目标会话，避免发错人。
        # 三态判定，避免「读不到」被当成「切错了」而误伤：
        #   A. 探测到目标名        → 校验通过，正常发送
        #   B. 探测到别的会话名    → 确认切错，重切；重切后仍是别人则跳过
        #   C. 什么都探测不到      → 无法判断，留审计证据后放行（否则一条都发不出去）
        if target_name:
            p = self._chat_panel_probe(target_name)
            if self._conversation_is_open(target_name, probe=p):
                logger.info("会话校验通过：当前=%s，目标=%s", p.get("title"), target_name)
            elif p.get("title") or p.get("candidates"):
                # 能读到面板内容，但不是目标 → 确认切错
                logger.warning(
                    "会话校验不通过：当前=「%s」，目标=「%s」，候选=%s，准备重切…",
                    p.get("title"), target_name, p.get("candidates"),
                )
                self._audit_dump("wrong_conversation", target_name)
                self._progress(f"会话校验失败，正在重切到「{target_name}」…")
                if not self._click_conversation(target_name):
                    logger.error("无法切换到目标会话「%s」，跳过发送", target_name)
                    self._progress(f"未能切换到「{target_name}」，已跳过")
                    raise RuntimeError(f"未能切换到目标会话「{target_name}」，消息未发送")
                # 重切后输入框可能重新渲染，再定位一次
                time.sleep(random.uniform(1.5, 2.5))
                box = self._locate_chat_input()
                p2 = self._chat_panel_probe(target_name)
                if self._conversation_is_open(target_name, probe=p2):
                    logger.info("重切后校验通过：当前=%s", p2.get("title"))
                elif p2.get("title") or p2.get("candidates"):
                    self._audit_dump("reswitch_wrong", target_name)
                    raise RuntimeError(
                        f"重切后仍停留在「{p2.get('title')}」而非「{target_name}」，消息未发送"
                    )
                else:
                    logger.warning("重切后探测为空，无法校验，留审计证据后继续发送。")
                    self._audit_dump("reswitch_probe_empty", target_name)
            else:
                # 探测不到任何面板内容：可能是 DOM 结构变化导致探测失效。
                # 此时输入框已找到，说明确有会话打开，保守放行并留下证据供核对。
                logger.warning(
                    "无法探测当前会话标题（输入框=%s，候选为空），跳过校验直接发送，请核对审计截图。",
                    p.get("hasInput"),
                )
                self._audit_dump("probe_empty", target_name)

        self._human_click(box, "聊天输入框")
        time.sleep(random.uniform(0.2, 0.5))
        self._human_type(text)
        time.sleep(random.uniform(0.2, 0.5))
        # 回车发送（抖音聊天框回车即发送）
        self.page.keyboard.press("Enter")
        time.sleep(random.uniform(1.5, 2.5))
        # 兜底：只在输入框仍残留文字时才补点「发送」按钮，避免 Enter 已发出又重复点击
        try:
            def _still_has_text(el):
                try:
                    tag = el.evaluate("e => e.tagName.toLowerCase()")
                    txt = (
                        el.input_value()
                        if tag == "textarea"
                        else (el.text_content() or "").replace("\u200b", "")
                    )
                    # 输入框里仍完整保留待发送文字，说明 Enter 没发出去，才需要补点发送按钮
                    return text.strip() in (txt or "").strip()
                except Exception:  # noqa: BLE001
                    return False

            if _still_has_text(box):
                send_btn = self.page.query_selector("text=发送")
                if send_btn is not None:
                    self._progress("正在点击发送按钮…")
                    self._human_click(send_btn, "发送按钮")
                    time.sleep(random.uniform(0.5, 1.0))
        except Exception:  # noqa: BLE001
            pass
        time.sleep(random.uniform(0.5, 1.5))
        self._screenshot("after_send")
        # 发送后再确认一次，若已弹验证则报错（消息很可能没真正发出）
        if self._check_risk_stop(self.verify_wait):
            raise RiskUnsolved("发送后检测到抖音风控，消息可能未真正发出，请手动处理后重新触发。")
        self._progress("消息已发送 ✅")
        logger.info("消息已发送。")

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
