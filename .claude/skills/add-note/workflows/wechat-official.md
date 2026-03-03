# 微信公众号 collection workflow

**Source**: Links from `mp.weixin.qq.com` (公众号文章).

---

## 1. 必备的工具及环境

| 检查项 | 检查命令 | 通过条件 | 失败处理 |
|------|----------|----------|----------|
| agent-browser 可执行 | `command -v agent-browser` | 返回码 0 | 提示用户安装/启用 `agent-browser`，终止 |
| 链接可访问 | `agent-browser open <url>` | 页面可打开，无 4xx/5xx/权限错误 | 提示用户需要登录或链接失效，终止 |
| 正文可提取 | `agent-browser snapshot -c` | 能识别到标题与正文容器 | 提示用户页面结构变化，终止 |

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
   - **source**: 固定写 `微信公众号`。
   - **collected_at**: 当日 `YYYY-MM-DD` 或 ISO。
   - **excerpt**: 先写 `原文链接：<url>`，再写正文全文（保留 Markdown 格式、代码块、图片链接）；若正文存在 hashtag（`#xxx`），必须原样保留。
4. 执行 payload 校验：
   - `python3 scripts/validate_payload.py --input <payload.json>`
5. 校验通过后返回 payload 给编排层。编排层必须准备 `metadata.json` 并调用 `python3 scripts/run_add_note.py ...` 执行落盘；**不要**在此处手工写笔记文件或附件。
