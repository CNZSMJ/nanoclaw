# 微信公众号 collection workflow

**Source**: Links from `mp.weixin.qq.com` (公众号文章).

---

## 1. 必备的工具及环境

| 项 | 要求 | 如何验证 |
|----|------|----------|
| agent-browser | 容器内可用 | 可执行 `agent-browser open <url>` 并做 snapshot 提取正文 |

若任一项不满足：向用户说明并终止，不继续执行。

---

## 2. 处理流程

1. 从用户消息中取得公众号文章 URL。
2. 打开页面并提取文章内容：
   - 执行 `agent-browser open <url>`（或等价方式），再 snapshot，提取：文章标题、公众号名称、发布时间（若有）、正文。
   - 仅保留正文区域；忽略侧栏、广告等。若需微信登录或无法访问，向用户说明并终止。
   - 提取正文中的图片 URL，用 `![描述](图片URL)` 保留在正文对应位置（不要用 base64）。
3. 组装 **collection payload**：
   - **title**: 页面文章标题。
   - **source**: 该条 mp.weixin.qq.com URL。
   - **collected_at**: 当日 `YYYY-MM-DD` 或 ISO。
   - **excerpt**: 正文全文（保留 Markdown 格式、代码块、图片链接）。
4. 将 payload 返回给编排层。编排层会执行 [reference/save-and-process.md](../reference/save-and-process.md)；**不要**在此处填写分类/takeaways。
