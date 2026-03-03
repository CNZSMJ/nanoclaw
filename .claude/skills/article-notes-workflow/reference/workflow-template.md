# Workflow 标准模板

`workflows/` 下每个信息源 workflow 必须且仅包含两个小节：

---

## 1. 必备的工具及环境

- 列出所需工具、技能或运行环境（如 agent-browser、x-integration、RSS 解析器、登录态等）。
- 说明如何验证（如「agent 具备 x_read_tweet」「存在 data/x-auth.json」）。
- 任一项不满足：向用户说明并退出，不继续执行。

---

## 2. 处理流程

- 按顺序：从该源拉取内容 → 组装 **collection payload**。
- Payload 字段：`title`、`source`、`collected_at`、**`excerpt`**。`excerpt` 为**原文内容**，形态可为：纯文本；文本+图片（图片用 URL，Markdown `![alt](url)`）；文本+代码块（Markdown 代码块）；纯图片（多图时用多行 `![描述](url)`，可加简短描述）。不在 payload 中使用 base64 图片。
- 最后一步：将 payload 交回编排层。不在 workflow 内写笔记文件或填分类/takeaways，由编排层随后执行 save-and-process。

---

Workflow 不重复「保存并加工」（分类、takeaways、标签）的逻辑，该部分在 [save-and-process.md](../reference/save-and-process.md)。
