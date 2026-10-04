# probes/ — 一次性只读勘察脚本

放**临时/一次性的只读探针**。目的是在动实现代码之前，先把「数据到底长什么样」摸清楚，
把结论写进 `docs/superpowers/specs/` 的证据表，然后就可以不再依赖它。

## 铁律

1. **严格只读**：只允许打开页面、读 DOM、监听网络响应、dump 产物。
   **不发送任何消息、不点击会话、不写账号配置、不改任何数据。**
2. **产物落 `userdata/`**：所有 dump 输出都写到 `userdata/probe_*/`（已在 `.gitignore` 里，不进 git）。
   仓库里只留脚本，不留抓下来的 HTML/JSON（那里面有真实会话名）。
3. **提交前脱敏**：脚本里**不得**出现真实账号别名、真实会话名、真实发送文案。
   账号一律用命令行参数传入，不要写默认值。

## 用法

```powershell
.venv\Scripts\python.exe probes\probe_spark.py <账号别名>
```

脚本从 `main.load_config(<别名>)` 取浏览器配置（复用该账号已登录的 `browser_data`），
所以**跑之前那个账号必须已经登录过**，否则会卡在等会话列表。

## 现有探针

| 脚本 | 用途 | 产物 | 结论归档 |
|---|---|---|---|
| `probe_spark.py` | 探测私信会话列表里「火花天数」的数据源：dump 每个会话项的 DOM 结构 + 监听 IM 相关 XHR | `userdata/probe_spark/{items.json,list.html,responses.json,page.html}` | `docs/superpowers/specs/2026-10-04-spark-days-display-design.md` 证据表 E1–E13 |

`probe_spark.py` 的结论（已固化进 SPK-001 实现，脚本本身留作改版排查用）：

- 天数节点：会话项内 `div.commonStreakstreakContainer > div.commonStreaknormalText`，文本即天数。
- 状态节点：同容器下的 `img.commonStreakicon`，`src` 含 `gray_normal` = 今天还没续，`normal_normal` = 今天已续。
- **无火花者没有该节点**（所以「无火花」≠「0 天」）。
- IM 接口（`imapi.douyin.com/v1/stranger/get_conversation_list` 等）全是 `application/x-protobuf`，拿不到明文，**不可行**。
