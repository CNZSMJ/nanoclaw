# RSS collection workflow

**Source**: RSS/Atom feed URL (如 `https://example.com/feed.xml`、`/feed`、`/rss`) 或用户请求「RSS digest」「今日订阅摘要」等.

---

## 1. 必备的工具及环境

| 检查项 | 检查命令 | 通过条件 | 失败处理 |
|------|----------|----------|----------|
| feed URL 可达 | `curl -fsSL <feed_url> | head -c 200` | 返回码 0 且内容含 `<rss`/`<feed` | 提示 feed 不可达或非 feed，终止或改走 generic |
| digest 工具可用（可选） | `command -v content-watcher || command -v feed-digest` | 任一返回码 0 | 若用户要求 digest 且无工具，提示先安装并终止 |
| 非 feed URL 路由 | URL 规则检查 | 识别为非 feed | 交给 [generic.md](generic.md) |

若当前场景所需任一项不满足：向用户说明并终止，或退化为 generic（用 agent-browser 抓取 feed 索引页，仅作单页处理）。
若用户请求的是 digest，Preflight 必须使用 `--require-digest`。

---

## 2. 处理流程

### 场景 A：用户发送一条 feed URL（拉取该 feed）

1. 请求该 feed URL（HTTP GET），按 RSS/Atom 解析。
2. 对每条 item（或前 N 条，如 5–10）：提取 `title`、`link`、`published`/`updated`、`description` 或 `content`。
3. 对每条 item 组装 **collection payload**：
   - **title**: 条目标题。
   - **source**: 固定写 `RSS`。
   - **collected_at**: 条目日期或当日 `YYYY-MM-DD`。
   - **excerpt**: 先写 `原文链接：<item.link>`，再写 description 或 content 片段；若原文存在 hashtag（`#xxx`），必须原样保留。
4. 对每条 payload 执行校验：
   - `python3 scripts/validate_payload.py --input <payload.json>`
5. 返回通过校验的 payload 列表。编排层对每条准备 metadata，并逐条调用 `python3 scripts/run_add_note.py ...` 落盘。

### 场景 B：用户要求「RSS digest」（已配置的 feeds）

1. 执行 digest 工具（如 `content-watcher run` 或 feed-digest 等价命令），得到带 title、link、summary 的条目列表。
2. 对每条条目按场景 A 的格式组装 **collection payload**。
3. 对每条 payload 执行校验：`python3 scripts/validate_payload.py --input <payload.json>`。
4. 返回通过校验的 payload 列表；编排层对每条准备 metadata，并逐条调用 `python3 scripts/run_add_note.py ...` 落盘。

### 场景 C：用户发送的是单篇文章 URL（非 feed）

不在此 workflow 处理。编排层应将其识别为 generic，走 [generic.md](generic.md)。

---

输出：始终为结构化 payload（title, source, collected_at, excerpt）；`source` 固定为 `RSS`。**不要**在此 workflow 内写笔记文件或填写分类/takeaways。
