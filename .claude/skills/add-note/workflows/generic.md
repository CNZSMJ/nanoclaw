# Generic (web) collection workflow

**Source**: 未被识别为 小红书、X、微信公众号、RSS 的任意链接（如博客、新闻、文档页）.

---

## 1. 必备的工具及环境

| 检查项 | 检查命令 | 通过条件 | 失败处理 |
|------|----------|----------|----------|
| agent-browser 可执行 | `command -v agent-browser` | 返回码 0 | 提示用户安装/启用 `agent-browser`，终止 |
| 页面可访问 | `agent-browser open <url>` | 能正常打开且无权限错误 | 提示用户页面无法访问（登录/反爬/网络），终止 |
| 可提取正文 | `agent-browser snapshot -c` | snapshot 中存在正文节点（article/main） | 提示用户页面结构不可提取，终止 |

若任一项不满足：向用户说明并终止，不继续执行。

---

## 2. 处理流程

1. 从用户消息中取得 URL。
2. 打开页面并提取主内容：
   - 执行 `agent-browser open <url>`（或等价方式），再 snapshot，提取：页面标题、主正文（优先 `<article>` 或主内容容器；去掉导航、页脚、广告）。
   - 提取正文中的图片 URL，用 `![描述](图片URL)` 保留在正文对应位置（不要用 base64）。
3. 组装 **collection payload**：
   - **title**: 文档标题或首级标题。
   - **source**: 固定写 `网页`。
   - **collected_at**: 当日 `YYYY-MM-DD` 或 ISO。
   - **excerpt**: 先写 `原文链接：<url>`，再写正文全文（保留 Markdown 格式、代码块、图片链接）；若正文存在 hashtag（`#xxx`），必须原样保留。
4. 执行 payload 校验：
   - `python3 scripts/validate_payload.py --input <payload.json>`
5. 校验通过后返回 payload 给编排层。编排层必须准备 `metadata.json` 并调用 `python3 scripts/run_add_note.py ...` 执行落盘；**不要**在此处手工写笔记文件或附件。
