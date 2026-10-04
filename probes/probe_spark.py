"""只读探针：探测抖音私信会话列表里「火花天数」的数据源。

严格只读：不发送任何消息、不点击任何会话、不改动任何数据。
只做两件事：
  1) 打开 /chat，dump 会话项的完整 DOM 结构（找火花/连续聊天天数节点）
  2) 挂 page.on("response") 记录 IM 相关 XHR 的 URL 与响应片段（找结构化字段）

用法：
    .venv\Scripts\python.exe probes\probe_spark.py <账号别名>
输出目录：userdata/probe_spark/
    items.json        每个会话项的结构化 dump（text / 子元素 class+text / 属性 / 匹配命中）
    list.html         整个会话列表容器的 outerHTML
    responses.json    捕获到的 IM 相关 XHR 记录
    page.html         整页 HTML（兜底）
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # 仓库根（探针脚本位于 probes/ 下）
sys.path.insert(0, str(BASE))

from main import load_config  # noqa: E402

if len(sys.argv) < 2:
    print("用法: .venv\\Scripts\\python.exe probes\\probe_spark.py <账号别名>")
    sys.exit(2)
ALIAS = sys.argv[1]
OUT = BASE / "userdata" / "probe_spark"
OUT.mkdir(parents=True, exist_ok=True)

from playwright.sync_api import sync_playwright  # noqa: E402

ITEM_SEL = '[data-e2e="conversation-item"]'
LIST_SEL = ".conversationConversationListwrapper"

# 网络捕获：只看可能承载私信列表/会话元数据的接口
URL_HINTS = ("im/", "conversation", "message", "chat", "user/list", "friend", "session")

cfg = load_config(ALIAS)
browser_cfg = cfg.get("browser", {}) or {}
user_data_dir = browser_cfg.get("user_data_dir")
print(f"[probe] alias={ALIAS}")
print(f"[probe] user_data_dir={user_data_dir}")
print(f"[probe] headless={browser_cfg.get('headless')} channel={browser_cfg.get('channel')}")

captured: list[dict] = []

# 在页面里跑的 DOM 提取器：对每个会话项，返回结构化描述
EXTRACT_JS = r"""
(sel) => {
  const items = Array.from(document.querySelectorAll(sel));
  const out = [];
  for (const it of items) {
    const rec = { index: out.length };
    rec.text = (it.innerText || "").replace(/\s+/g, " ").trim();
    rec.dataIndex = it.getAttribute("data-index");
    rec.outerHTML = it.outerHTML;
    // 递归收集所有后代元素：tag / class / 直接文本 / 关键属性
    const nodes = [];
    const walk = (el, depth) => {
      if (depth > 8) return;
      const kids = Array.from(el.children);
      const ownText = Array.from(el.childNodes)
        .filter(n => n.nodeType === 3)
        .map(n => n.textContent.trim())
        .filter(Boolean)
        .join("|");
      const attrs = {};
      for (const a of el.attributes) attrs[a.name] = a.value;
      nodes.push({
        depth,
        tag: el.tagName.toLowerCase(),
        cls: el.className && el.className.baseVal !== undefined ? el.className.baseVal : (el.className || ""),
        ownText,
        attrs,
        rect: (() => { const r = el.getBoundingClientRect(); return { w: Math.round(r.width), h: Math.round(r.height), x: Math.round(r.x), y: Math.round(r.y) }; })(),
        childCount: kids.length,
      });
      for (const k of kids) walk(k, depth + 1);
    };
    walk(it, 0);
    rec.nodes = nodes;
    // 关键词命中：文本里出现数字+天 / 火花 / 连续
    rec.textHits = [];
    const re = /(火花|连续|天|streak|spark|flame|fire)/i;
    for (const n of nodes) {
      if (n.ownText && re.test(n.ownText)) rec.textHits.push({ depth: n.depth, cls: n.cls, text: n.ownText });
    }
    // 属性/类名命中
    rec.attrHits = [];
    for (const n of nodes) {
      const hay = (n.cls + " " + JSON.stringify(n.attrs)).toLowerCase();
      if (/(spark|streak|flame|fire|blaze|hot|连续|火花)/i.test(hay)) {
        rec.attrHits.push({ depth: n.depth, tag: n.tag, cls: n.cls, attrs: n.attrs });
      }
    }
    out.push(rec);
  }
  return out;
}
"""


def on_response(resp):
    url = resp.url
    low = url.lower()
    if not any(h in low for h in URL_HINTS):
        return
    entry = {
        "url": url,
        "status": resp.status,
        "method": resp.request.method,
        "resource_type": resp.request.resource_type,
    }
    try:
        ct = (resp.headers or {}).get("content-type", "")
        entry["content_type"] = ct
        if "json" in ct or "text" in ct:
            body = resp.text()
            entry["len"] = len(body)
            entry["body_head"] = body[:6000]
    except Exception as e:  # noqa: BLE001
        entry["error"] = f"{type(e).__name__}: {e}"
    captured.append(entry)
    print(f"[net] {resp.status} {url[:160]}")


with sync_playwright() as p:
    kwargs = dict(
        user_data_dir=user_data_dir,
        headless=bool(browser_cfg.get("headless", False)),
        locale="zh-CN",
        viewport={"width": 1280, "height": 900},
        args=list(browser_cfg.get("extra_args", []) or []),
    )
    ch = (browser_cfg.get("channel") or "").strip()
    if ch:
        kwargs["channel"] = ch
    ctx = p.chromium.launch_persistent_context(**kwargs)
    page = ctx.new_page()
    page.set_default_timeout(60000)
    page.on("response", on_response)

    print("[probe] goto /chat ...")
    page.goto("https://www.douyin.com/chat", wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector(f"{ITEM_SEL}, {LIST_SEL}", timeout=30000)
        print("[probe] 会话列表已出现")
    except Exception as e:  # noqa: BLE001
        print(f"[probe] 等会话列表超时（可能未登录）：{type(e).__name__}: {e}")

    # 等网络静默，让列表接口响应都落袋
    time.sleep(10)

    # 滚动两屏，触发更多会话项渲染（只读，不点击）
    try:
        page.mouse.wheel(0, 1200)
        time.sleep(2)
        page.mouse.wheel(0, -1200)
        time.sleep(2)
    except Exception:  # noqa: BLE001
        pass

    items = page.evaluate(EXTRACT_JS, ITEM_SEL)
    print(f"[probe] 抓到 {len(items)} 个会话项")

    (OUT / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "responses.json").write_text(json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "page.html").write_text(page.content(), encoding="utf-8")
    try:
        lst = page.query_selector(LIST_SEL)
        if lst:
            (OUT / "list.html").write_text(lst.evaluate("e => e.outerHTML"), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[probe] dump list.html 失败: {e}")

    # 控制台摘要：每个会话项的文本 + 文本命中
    print("=" * 60)
    for rec in items:
        print(f"- [{rec['index']}] {rec['text'][:120]}")
        for h in rec.get("textHits", [])[:8]:
            print(f"    hit d{h['depth']} .{h['cls']} :: {h['text'][:80]}")
        for h in rec.get("attrHits", [])[:8]:
            print(f"    attr d{h['depth']} <{h['tag']} class={h['cls'][:60]}> {json.dumps(h['attrs'], ensure_ascii=False)[:200]}")
    print("=" * 60)
    print(f"[probe] 网络捕获 {len(captured)} 条，已写入 {OUT}")
    for c in captured[:40]:
        print(f"  {c['status']} {c['method']} {c['url'][:150]}")

    print("[probe] 保持窗口 15 秒后关闭（可人工观察）...")
    time.sleep(15)
    ctx.close()
print("[probe] done")
