# RSS collection workflow

**Source**: RSS/Atom feed URL (如 `https://example.com/feed.xml`、`/feed`、`/rss`) 或用户请求「RSS digest」「今日订阅摘要」等.

---

## 1. 必备的工具及环境

| 场景 | 要求 | 如何验证 |
|------|------|----------|
| 单 feed URL 拉取 | RSS/Atom 解析能力（如 HTTP GET + XML 解析）或 content-watcher / feed-digest | 能请求 feed URL 并解析出 title、link、published、description/content |
| 已配置 feed 的摘要 | content-watcher 或 feed-digest | 能执行 digest 命令并得到条目列表 |
| 单篇文章 URL（非 feed） | 不适用本 workflow | 由编排层识别为 generic，走 [generic.md](generic.md) |

若当前场景所需任一项不满足：向用户说明并终止，或退化为 generic（用 agent-browser 抓取 feed 索引页，仅作单页处理）。

---

## 2. 处理流程

### 场景 A：用户发送一条 feed URL（拉取该 feed）

1. 请求该 feed URL（HTTP GET），按 RSS/Atom 解析。
2. 对每条 item（或前 N 条，如 5–10）：提取 `title`、`link`、`published`/`updated`、`description` 或 `content`。
3. 对每条 item 组装 **collection payload**：
   - **title**: 条目标题。
   - **source**: 条目 link（文章 URL）。
   - **collected_at**: 条目日期或当日 `YYYY-MM-DD`。
   - **excerpt**: description 或 content 片段。
4. 返回多条 payload。编排层对每条执行一次 save-and-process。

### 场景 B：用户要求「RSS digest」（已配置的 feeds）

1. 执行 digest 工具（如 `content-watcher run` 或 feed-digest 等价命令），得到带 title、link、summary 的条目列表。
2. 对每条条目按场景 A 的格式组装 **collection payload**。
3. 返回 payload 列表；编排层对每条执行 save-and-process。

### 场景 C：用户发送的是单篇文章 URL（非 feed）

不在此 workflow 处理。编排层应将其识别为 generic，走 [generic.md](generic.md)。

---

输出：始终为结构化 payload（title, source, collected_at, excerpt）；**不要**在此 workflow 内写笔记文件或填写分类/takeaways。
