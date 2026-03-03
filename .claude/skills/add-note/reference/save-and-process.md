# 保存并加工（Step 6，共用步骤）

在任意信息源 workflow 返回采集结果且 payload 校验通过后执行。输入：`title`、`source`、`collected_at`、`excerpt`（可选 `author`）。
其中 `source` 必须是固定来源名：`小红书` / `X` / `微信公众号` / `RSS` / `网页` / `Pasted`。

## 0. 执行门禁（必须）

1. Preflight 必须已通过（见 [scripts/preflight_check.py](../scripts/preflight_check.py)）。
2. Payload 必须已通过校验（见 [scripts/validate_payload.py](../scripts/validate_payload.py)）。
3. 任一条件不满足：停止流程，不写文件。

## 1. slug 生成规则

由 payload 的 `title` 生成，用于 `{slug}` 占位符。

1. 中文：保留中文，去除常见标点和控制字符，空格转 `-`。
2. 英文：转小写，非字母数字转 `-`。
3. 中英混排：中文保留、英文小写，分隔符统一为 `-`。
4. 连续 `-` 合并，去除首尾 `-`，最大 80 字符。

## 2. 语言与排版

1. 判断源文语言（以 excerpt 主体为准）。
2. 英文源文：`标题/作者 -> AI Takeaways -> 译文 -> 原文`。
3. 中文源文：`标题/作者 -> AI Takeaways -> 原文`，并删除整个 `## 译文` 小节。
4. AI Takeaways 固定 3-5 条，要求可执行或高信息量。

## 3. 路径、命名、冲突处理

读取 [manifest.yaml](../manifest.yaml) 的 `config` 段：

1. 计算笔记路径：`{notes_path}/{note_filename_format}`（代入 `{slug}`、`{date}`）。
2. 命名冲突策略：按 [config.md](config.md) 的 `suffix-date-counter` 执行，禁止覆盖已有文件。
3. 图片命名：`attachment_filename_format` 代入 `{slug}`、`{index}`、`{ext}`。

## 4. 图片落盘与链接替换

1. 识别 excerpt 中 Markdown 图片 URL：`![alt](http...)`。
2. 按顺序下载（受 `download_timeout_seconds`、`max_images` 限制）。
3. 下载成功：URL 替换为“笔记相对路径”。
4. 下载失败：保留原 URL，不中断整篇写入。

## 5. 写文件（原子写入）

1. 按 [note-template.md](note-template.md) 生成内容，填充 frontmatter：
   - `source`、`title`、`collected_at`、`category`、`source_tags`、`ai_tags`
   - `source` 为独立必填字段：只写固定来源名，不写 URL。
2. 若 `atomic_write=true`：先写 `*.tmp`，再 `rename` 到目标文件。
3. 严禁直接覆盖未备份的已有文件。

## 6. 加工（分类、标签）

1. 分类：优先 group 的 `CLAUDE.md` 约定，否则用 `manifest.yaml` 的 `categories`。
2. `source_tags`：从 excerpt 的原文内容中提取 hashtag（如 `#AI`、`#创业`），按出现顺序去重；默认去掉 `#` 前缀后写入，若原文无标签则写 `[]`。
3. `ai_tags`：按 `tag_rules` 生成（数量与风格按配置执行），不要覆盖 `source_tags`。
4. 不得破坏正文结构（标题/作者/Takeaways/译文/原文）。

## 7. 可选：更新索引

如果存在 `index_file`，追加或更新一行：日期、标题、分类、`source_tags`、`ai_tags`。

## 特殊情况：原文仅为图片且文字在图中

- 若 excerpt 已有 OCR/视觉识别文字：按识别文字做语言判断和 Takeaways。
- 若 excerpt 仅有图片 URL：先补 OCR，再进入排版；无 OCR 能力时仅保存图片链接并标注“未提取图中文字”。

## 特殊情况：页面正文与图片文字并存

- 若上游 workflow 判定为“图片文本主导”，excerpt 应同时包含页面正文与图片 OCR 文字。
- Step 6 在做语言判断、Takeaways、译文时，以“正文 + OCR 合并文本”为准，不可仅使用其一。
