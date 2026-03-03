---
name: add-note
description: "Orchestrates link-to-notes pipeline: detect link source (Xiaohongshu, X, WeChat official, RSS), run the matching collection workflow, then save and process into notes with category, takeaways, and tags. Use when the user sends a link and wants it turned into a structured note, or says '整理这篇文章' / 'ingest' / '记笔记'."
---

# 文章笔记工作流

编排逻辑：**skill 被触发** → **确认是否执行** → **识别信息源** → **本地存在性核实** → **Preflight 门禁检查** → **执行采集 workflow** → **校验 payload** → **保存并加工**成笔记（分类、takeaways、标签）。

## 何时使用

- 用户发送一个或多个 URL，或说「整理这篇文章」「ingest」「记笔记」「save and tag」等（带链接或粘贴内容）→ 触发本 skill。
- 若用户只粘贴文字、无 URL：在用户确认后构造 payload（`title: "Pasted"`, `source: "Pasted"`, `collected_at`: 今日, `excerpt`: 粘贴内容），跳过 Step 2、4，直接执行 Step 5、6。

## 主流程

### Step 1：确认执行

1. Skill 被触发（用户发链接或说「整理/ingest/记笔记」等）。
2. 询问用户：是否需要执行笔记生产流程？简要说明：将根据链接采集内容并整理成带分类、takeaways、标签的笔记。
3. 用户选择 **y / 是 / 确认** → 继续 Step 2。
4. 用户选择 **n / 否 / 取消** → 结束，不执行。
5. 若用户问「是不是已经处理过」：必须先执行 Step 2.5 的本地核实命令，再回答；禁止直接凭记忆回复。

### Step 2：根据 URL 识别信息源（路由）

解析用户链接，选择对应 workflow：

| URL 模式 / 域名 | 信息源 | Workflow 文件 |
|-----------------|--------|---------------|
| `xiaohongshu.com`, `xhslink.com` | 小红书 | [workflows/xiaohongshu.md](workflows/xiaohongshu.md) |
| `x.com`, `twitter.com`（含 `/status/`） | X (Twitter) | [workflows/x.md](workflows/x.md) |
| `mp.weixin.qq.com` | 微信公众号 | [workflows/wechat-official.md](workflows/wechat-official.md) |
| RSS/Atom feed URL（如 `.xml`, `/feed`, `/rss`）或用户说「RSS 摘要」 | RSS | [workflows/rss.md](workflows/rss.md) |
| 其他（通用网页） | Generic | [workflows/generic.md](workflows/generic.md) |

多条链接时，对每条重复 Step 2～6（含 Step 2.5）。

### Step 2.5：本地存在性核实（必须）

- 对每条 URL，必须先执行：
  - `python3 scripts/check_existing_note.py --url <url> --manifest ./manifest.yaml`
- 判定规则：
  - 返回码 `0`（FOUND）：本地确有笔记包含该链接。可告知“已处理过”，并给出命中路径。
  - 返回码 `1`（MISS）：本地未命中，必须继续正常处理流程。
- 返回码 `2`：检查失败，需先修复再继续。
- **禁止**仅凭会话记忆/模型记忆判断“已处理过”；必须以本地文件核实结果为准。

### Step 3：执行 Preflight 门禁（必须）

- 先执行 [scripts/preflight_check.py](scripts/preflight_check.py)：
  - `python3 scripts/preflight_check.py --source <source> --manifest ./manifest.yaml`
  - 若是 RSS digest 场景，追加 `--require-digest`
- Preflight 必须覆盖：
  - 路径与写权限（`notes_path`、`attachments_path`、`index_file` 所在目录）。
  - 信息源所需工具/环境（见对应 workflow 的“必备的工具及环境”检查命令）。
- 小红书场景：Preflight 必须检查 `XHS_Downloader` 和 `minimax_coding_plan_mcp`；其中 minimax 仅按 MCP 配置与命令可执行性判定，不做包安装判定。
- 小红书场景：先 OCR 前两张做探测（`>20` 字符时由模型判断是否图片文本主导），但**只要有图片就必须全量 OCR 全部图片**；payload 的 `excerpt` 必须包含逐图 OCR 段落（`[图N OCR]`）以及原文图片列表。
- 任一门禁失败：明确告知失败项与修复建议，**终止流程**，不继续采集与写文件。

### Step 4：执行采集 workflow

- 打开上表中所选信息源对应的 workflow 文件。
- 按该 workflow 执行：先做**必备的工具及环境**检查，缺项则向用户说明并退出；通过后执行**处理流程**，得到**原始 payload**。
- 不在 workflow 内做分类或 takeaways，那是 Step 6。

### Step 5：校验 payload（必须）

- 采集完成后，先执行 [scripts/validate_payload.py](scripts/validate_payload.py)。
- 必填字段：`title`、`source`、`collected_at`、`excerpt`（均为非空字符串）。
- `collected_at` 仅允许 `YYYY-MM-DD` 或 ISO 8601。
- 小红书场景：若 excerpt 含图片，必须包含覆盖全部图片的 OCR 段落（`[图1 OCR] ... [图N OCR]`），否则校验失败。
- 校验失败则终止，不得进入保存阶段。

### Step 6：保存并加工

- 使用 Step 4 返回并在 Step 5 通过校验的 payload，**必须**调用统一执行器：
  - `python3 scripts/run_add_note.py --source <source> --payload <payload.json> --metadata <metadata.json> --manifest ./manifest.yaml --report-out <report.json>`
- `metadata.json` 至少包含：`category`、`ai_tags`、`takeaways`（英文源文还需 `translation`）。
- **排版规则**：
  - **源文为英文**：标题、作者 → AI Takeaways → 译文 → 原文。
  - **源文为中文**：标题、作者 → AI Takeaways → 原文（**删除整个 `## 译文` 节**，不留空节）。
- 分类与标签：从 [manifest.yaml](manifest.yaml) 读取 `categories`、`tag_rules`（与 config 同级）；其中 `source_tags` 来自原文 hashtag，`ai_tags` 由模型生成。若该 group 的 CLAUDE.md 有定义则优先用 group 的约定。说明见 [reference/config.md](reference/config.md)。
- **禁止**在该 skill 里直接用 `Edit/Bash` 手工写入笔记或附件目录；写入必须由 [scripts/save_and_process.py](scripts/save_and_process.py) 执行。
- 执行器包含 postcheck：出现 `./media/` 路径或 frontmatter 缺字段会直接失败。

## Payload 字段说明（Step 4 产出，Step 6 使用）

| 字段 | 含义 |
|------|------|
| `title` | 内容标题（如文章标题、推文首行）。 |
| `source` | 来源名称（固定值之一）：`小红书` / `X` / `微信公众号` / `RSS` / `网页` / `Pasted`。**禁止填 URL**。 |
| `collected_at` | 采集时间（YYYY-MM-DD 或 ISO）。 |
| `excerpt` | **原文内容**：从该来源抓取到的完整或代表性内容，形态可为 **纯文本**、**文本+图片**、**文本+代码块**、**纯图片**。图片一律用 `![描述](图片URL)` 引用，**不要用 base64 内联**。 |

**说明**：excerpt 中的图片 URL 由 Step 6 下载到本地并替换为相对路径；逻辑见 [reference/save-and-process.md](reference/save-and-process.md)，配置项见 [reference/config.md](reference/config.md)。payload 约束见 [reference/payload-schema.md](reference/payload-schema.md)。

## Metadata 字段（Step 6 必填）

| 字段 | 含义 |
|------|------|
| `category` | 主分类；必须在 `manifest.yaml` 的 `categories` 中。 |
| `ai_tags` | 模型生成标签；数量需满足 `tag_rules.ai_min_tags`～`ai_max_tags`，默认使用 `#标签` 形式（如 `#AI`、`#创业`）。 |
| `takeaways` | 3-5 条要点。 |
| `translation` | 仅英文源文必填。 |
| `author` | 可选。 |
| `notes` | 可选。 |

## 流程概览

```
Step 1: 确认执行
  → 用户确认 → 继续
  → 用户拒绝 → 结束
Step 2: 识别信息源（解析 URL → 选 workflow）
Step 2.5: 本地存在性核实（check_existing_note）
Step 3: 执行 preflight（路径可写 + 工具可用）
Step 4: 执行 workflow（拉取 → 组装 payload）
Step 5: 校验 payload（字段/格式）
Step 6: 保存并加工（排版 → 图片落盘 → 分类/标签 → 原子写文件）
```

## 文件结构（可配置）

路径与命名**一律以** skill 根目录 [manifest.yaml](manifest.yaml) 的 **config** 段为准；执行时读取该文件，不要使用文档中的示例值。配置项说明见 [reference/config.md](reference/config.md)。

Workflow 标准见 [reference/workflow-template.md](reference/workflow-template.md)，各源入口：

- [workflows/xiaohongshu.md](workflows/xiaohongshu.md)
- [workflows/x.md](workflows/x.md)
- [workflows/wechat-official.md](workflows/wechat-official.md)
- [workflows/rss.md](workflows/rss.md)
- [workflows/generic.md](workflows/generic.md)
