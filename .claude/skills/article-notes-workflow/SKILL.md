---
name: article-notes-workflow
description: Orchestrates link-to-notes pipeline: detect link source (Xiaohongshu, X, WeChat official, RSS), run the matching collection workflow, then save and process into notes with category, takeaways, and tags. Use when the user sends a link and wants it turned into a structured note, or says "整理这篇文章" / "ingest" / "记笔记".
---

# 文章笔记工作流

编排逻辑：**skill 被触发** → **先询问用户是否执行笔记生产流程** → 用户确认后：识别**信息源** → 执行**该源对应的采集 workflow** → **保存并加工**成笔记（分类、takeaways、标签）。

## 何时使用

- 用户发送一个或多个 URL，或说「整理这篇文章」「ingest」「记笔记」「save and tag」等（带链接或粘贴内容）→ 触发本 skill。
- 若用户只粘贴文字、无 URL：在用户确认后构造 payload（`title: "Pasted"`, `source: "Pasted"`, `collected_at`: 今日, `excerpt`: 粘贴内容），跳过 Step 2、3，直接执行 Step 4。

## 主流程

### Step 1：确认执行

1. Skill 被触发（用户发链接或说「整理/ingest/记笔记」等）。
2. 询问用户：是否需要执行笔记生产流程？简要说明：将根据链接采集内容并整理成带分类、takeaways、标签的笔记。
3. 用户选择 **y / 是 / 确认** → 继续 Step 2。
4. 用户选择 **n / 否 / 取消** → 结束，不执行。

### Step 2：根据 URL 识别信息源

解析用户链接，选择对应 workflow：

| URL 模式 / 域名 | 信息源 | Workflow 文件 |
|-----------------|--------|---------------|
| `xiaohongshu.com`, `xhslink.com` | 小红书 | [workflows/xiaohongshu.md](workflows/xiaohongshu.md) |
| `x.com`, `twitter.com`（含 `/status/`） | X (Twitter) | [workflows/x.md](workflows/x.md) |
| `mp.weixin.qq.com` | 微信公众号 | [workflows/wechat-official.md](workflows/wechat-official.md) |
| RSS/Atom feed URL（如 `.xml`, `/feed`, `/rss`）或用户说「RSS 摘要」 | RSS | [workflows/rss.md](workflows/rss.md) |
| 其他（通用网页） | Generic | [workflows/generic.md](workflows/generic.md) |

多条链接时，对每条重复 Step 2～4。

### Step 3：执行采集 workflow

- 打开上表中所选信息源对应的 workflow 文件。
- 按该 workflow 执行：先做**必备的工具及环境**检查，缺项则向用户说明并退出；通过后执行**处理流程**，得到**原始 payload**。
- 不在 workflow 内做分类或 takeaways，那是 Step 4。

### Step 4：保存并加工

- 使用 Step 3 返回的 payload，按 [reference/save-and-process.md](reference/save-and-process.md) 执行。
- **排版规则**：
  - **源文为英文**：标题、作者 → AI Takeaways → 译文 → 原文。
  - **源文为中文**：标题、作者 → AI Takeaways → 原文（**删除整个 `## 译文` 节**，不留空节）。
- 分类与标签：从 [manifest.yaml](manifest.yaml) 读取 `categories`、`tag_rules`（与 config 同级）；若该 group 的 CLAUDE.md 有定义则优先用 group 的约定。说明见 [reference/config.md](reference/config.md)。

## Payload 字段说明（Step 3 产出，Step 4 使用）

| 字段 | 含义 |
|------|------|
| `title` | 内容标题（如文章标题、推文首行）。 |
| `source` | 来源 URL 或标签（如 "Pasted"）。 |
| `collected_at` | 采集时间（YYYY-MM-DD 或 ISO）。 |
| `excerpt` | **原文内容**：从该来源抓取到的完整或代表性内容，形态可为 **纯文本**、**文本+图片**、**文本+代码块**、**纯图片**。图片一律用 `![描述](图片URL)` 引用，**不要用 base64 内联**。 |

**说明**：excerpt 中的图片 URL 由 Step 4 下载到本地并替换为相对路径；逻辑见 [reference/save-and-process.md](reference/save-and-process.md)，配置项见 [reference/config.md](reference/config.md)。

## 流程概览

```
Step 1: 确认执行
  → 用户确认 → 继续
  → 用户拒绝 → 结束
Step 2: 识别信息源（解析 URL → 选 workflow）
Step 3: 执行 workflow（工具检查 → 拉取 → 组装 payload）
Step 4: 保存并加工（排版 → 图片落盘 → 分类/标签 → 写笔记文件）
```

## 文件结构（可配置）

路径与命名**一律以** skill 根目录 [manifest.yaml](manifest.yaml) 的 **config** 段为准；执行时读取该文件，不要使用文档中的示例值。配置项说明见 [reference/config.md](reference/config.md)。

Workflow 标准见 [reference/workflow-template.md](reference/workflow-template.md)，各源入口：

- [workflows/xiaohongshu.md](workflows/xiaohongshu.md)
- [workflows/x.md](workflows/x.md)
- [workflows/wechat-official.md](workflows/wechat-official.md)
- [workflows/rss.md](workflows/rss.md)
- [workflows/generic.md](workflows/generic.md)
