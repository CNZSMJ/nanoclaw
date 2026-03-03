# 保存并加工（共用步骤）

在任意信息源 workflow 返回采集结果**之后**执行。输入：`title`、`source`（URL 或标签）、`collected_at`、`excerpt`（原文内容）；若有作者信息可一并写入。

**excerpt**：可为纯文本、文本+图片、文本+代码块、纯图片；在笔记中以 **Markdown** 形式写入。图片使用 `![描述](图片URL)`，不要使用 base64 内联。

## slug 生成规则

由 payload 的 `title` 生成，用于笔记文件名和媒体文件名中的 `{slug}` 占位符。

1. **中文标题**：保留中文原文，去除标点和特殊字符（`！？。，、：；""''【】《》…` 等），空格替换为 `-`，连续 `-` 合并为一个，首尾 `-` 去除。示例：`小红书2024年度总结` → `小红书2024年度总结`。
2. **英文标题**：转小写，非字母数字字符替换为 `-`，连续 `-` 合并为一个，首尾 `-` 去除。示例：`How to Build a RAG System` → `how-to-build-a-rag-system`。
3. **中英混合**：按上述规则处理各部分，保留中文、英文转小写，标点替换为 `-`。
4. **最大长度**：80 字符，超出则截断到最后一个完整词（或中文字符）处。

## 特殊情况：原文仅为图片且文字全在图中

例如小红书推文只有多张图、所有文字都在图片里。此时：

- **若 excerpt 中已包含「图中识别文字」**（由采集 workflow 通过 OCR/视觉从图中提取）：以该识别文字作为**源文**做语言判断、生成 AI Takeaways 与译文（若为英文）；笔记「原文」部分保留：图中识别文字 + 原文图片（Markdown），便于溯源。
- **若 excerpt 中仅有图片、无识别文字**：无法自动做语言判断与 Takeaways。应在采集阶段（如 [workflows/xiaohongshu.md](../workflows/xiaohongshu.md)）支持对图中文字做识别并写入 excerpt；若本步具备视觉能力，也可先对图片做识别得到源文，再继续排版与加工。

## 拿到正文后的排版规则

1. **判断源文语言**：若 excerpt 主体为**英文**，需要生成**译文**，按「标题、作者 → AI Takeaways → 译文 → 原文」顺序排版。若源文为**中文**，不生成译文，按「标题、作者 → AI Takeaways → 原文」排版，且笔记中**不保留 `## 译文` 节**（包括标题，整节删除）。
2. **AI Takeaways**：放在**标题、作者下面**，3～5 条，每条应可执行或高信息量。
3. **译文**：仅当源文为英文时存在；排在 AI Takeaways 之后、原文之前；译文需通顺、保留关键术语与结构。

## 1. 保存与排版

- **读取配置**：从 skill 根目录 [manifest.yaml](../manifest.yaml) 的 **config** 段读取路径与命名配置。由 payload 的 `title` 按上述「slug 生成规则」生成 slug，代入 `note_filename_format` 得到笔记文件名。
- **图片落盘**：若 excerpt 中含有图片 URL（`![...](https://...)`），在写笔记前：
  - 按顺序下载每张图到 `assets_path`，按 `asset_filename_format` 命名（代入 slug、index、ext）；
  - 在写入「原文」时，将 excerpt 中的图片 URL 替换为从笔记文件到该媒体文件的**相对路径**。若环境无法下载，保留原始 URL。
- **新建笔记文件**：路径为 `{notes_path}/{note_filename_format}`（代入 slug）。使用 [note-template.md](note-template.md)，按排版规则填写：
  - 标题（与 frontmatter `title` 一致）、作者（若有）。
  - **AI Takeaways**（3～5 条）。
  - **译文**（仅当源文为英文时，在 `## 译文` 下排版；中文源文则**删除整个 `## 译文` 节**）。
  - **原文**：在 `## 原文` 下写 excerpt 全文（保留 Markdown、代码块；图片已用本地相对路径或保留 URL）。
- frontmatter：`source`、`title`、`collected_at`、`category`、`tags`。

## 2. 加工（分类、标签）

- 在同一笔记中补充 **category**（一个主分类）、**tags**（条数按 manifest 的 `tag_rules`，风格小写连字符）：优先用该 group 的 CLAUDE.md 约定，否则用 [manifest.yaml](../manifest.yaml) 的 `categories` 与 `tag_rules`（与 config 同级）。说明见 [config.md](config.md)。
- 不覆盖、不删除已排版的标题 / 作者 / Takeaways / 译文 / 原文 结构。

## 3. 可选

- 按 manifest.yaml 的 config 段中 `index_file` 追加或更新一行：日期、标题、分类、标签，便于快速浏览。
