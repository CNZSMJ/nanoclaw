# X (Twitter) collection workflow

**Source**: Links from `x.com` or `twitter.com` (e.g. `https://x.com/username/status/123456`).

---

## 1. 必备的工具及环境

| 项 | 要求 | 如何验证 |
|----|------|----------|
| x-integration skill | 已安装并可用 | Agent 具备 X 相关工具（如 x_read_tweet） |
| X 登录态 | 已完成 X 登录 | 存在 `data/x-auth.json` 或按 skill 说明完成 setup |

若任一项不满足：向用户说明并终止，不继续执行。

---

## 2. 处理流程

1. 从用户消息中取得该条 X 链接（已被编排层识别为 X 的 URL）。
2. 使用 **x_read_tweet** 调用该 URL（或执行 read_tweet 脚本并传入 URL），获取：作者/handle、推文正文、可选回复列表。
3. 组装 **collection payload**（供后续 save-and-process 使用）：
   - **title**: 推文首行或 "Tweet by @{handle}"（无正文时）。
   - **source**: 该条推文 URL。
   - **collected_at**: 当日 `YYYY-MM-DD` 或 ISO 时间。
   - **excerpt**: 完整推文正文。若推文包含图片或视频预览图，用 `![描述](图片URL)` 写入 excerpt（不要用 base64）。若拉取了回复，可追加 "Replies:" 及前 N 条回复内容（如 3–5 条）以保留上下文。
4. 将 payload 返回给编排层。**不要**在此处写笔记文件或填写分类/takeaways；编排层会接着执行 [reference/save-and-process.md](../reference/save-and-process.md)。
