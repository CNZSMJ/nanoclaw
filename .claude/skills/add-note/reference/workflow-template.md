# Workflow 标准模板

`workflows/` 下每个信息源 workflow 必须且仅包含两个小节：

---

## 1. 必备的工具及环境

- 列出所需工具、技能或运行环境（如 agent-browser、x-integration、RSS 解析器、登录态等）。
- 必须给出**可执行检查命令**与**通过判定**（例如 `command -v agent-browser`、`test -f data/x-auth.json`）。
- 任一项不满足：向用户说明并退出，不继续执行。
- 建议格式（必须包含这 4 列）：
  - `检查项` / `检查命令` / `通过条件` / `失败处理`
- 命令默认在 **skill 根目录** 执行（即 `add-note/`）。
- 对可自动补齐的依赖（如小红书的 `XHS_Downloader`）：
  - 检查失败时可先执行自动安装；
  - 自动安装后必须再次校验通过，否则仍判定失败。

---

## 2. 处理流程

- 按顺序：从该源拉取内容 → 组装 **collection payload**。
- Payload 字段：`title`、`source`、`collected_at`、**`excerpt`**。`excerpt` 为**原文内容**，形态可为：纯文本；文本+图片（图片用 URL，Markdown `![alt](url)`）；文本+代码块（Markdown 代码块）；纯图片（多图时用多行 `![描述](url)`，可加简短描述）。不在 payload 中使用 base64 图片。若原文含 `#tag`，需在 excerpt 保留原始 hashtag，供 Step 6 生成 `source_tags`。
- `source` 必须写固定来源名（如 `小红书`、`X`、`微信公众号`、`RSS`、`网页`、`Pasted`），不要写 URL；原始链接放进 `excerpt`。
- 处理流程最后必须执行 payload 校验（`scripts/validate_payload.py`），校验失败不得返回到编排层。
- 最后一步：将 payload 交回编排层。不在 workflow 内写笔记文件或填分类/takeaways，由编排层随后执行 save-and-process。

---

Workflow 不重复「保存并加工」（分类、takeaways、标签）的逻辑，该部分在 [save-and-process.md](../reference/save-and-process.md)。
