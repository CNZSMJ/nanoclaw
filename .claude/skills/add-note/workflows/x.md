# X (Twitter) collection workflow

**Source**: Links from `x.com` or `twitter.com` (e.g. `https://x.com/username/status/123456`).

---

## 1. 必备的工具及环境

| 检查项 | 检查命令 | 通过条件 | 失败处理 |
|------|----------|----------|----------|
| x-integration 已接入 | `test -f .claude/skills/x-integration/agent.ts` | 返回码 0 | 提示用户先安装/接入 x-integration，终止 |
| X 登录态存在 | `test -f data/x-auth.json` | 返回码 0 | 提示用户先执行 x setup，终止 |
| `x_read_tweet` 工具可见 | 在当前会话工具列表中检查 `x_read_tweet` | 工具可调用 | 提示用户重启服务/重建容器后重试，终止 |

若任一项不满足：向用户说明并终止，不继续执行。

---

## 2. 处理流程

1. 从用户消息中取得该条 X 链接（已被编排层识别为 X 的 URL）。
2. 使用 **x_read_tweet** 调用该 URL（或执行 read_tweet 脚本并传入 URL），获取：作者/handle、推文正文、可选回复列表。
3. 组装 **collection payload**（供后续 save-and-process 使用）：
   - **title**: 推文首行或 "Tweet by @{handle}"（无正文时）。
   - **source**: 固定写 `X`。
   - **collected_at**: 当日 `YYYY-MM-DD` 或 ISO 时间。
   - **excerpt**: 先写 `原帖链接：<tweet_url>`，再写完整推文正文。若正文含 hashtag（如 `#AI`），必须原样保留，不要清洗。若推文包含图片或视频预览图，用 `![描述](图片URL)` 写入 excerpt（不要用 base64）。若拉取了回复，可追加 "Replies:" 及前 N 条回复内容（如 3–5 条）以保留上下文。
4. 执行 payload 校验：
   - `python3 scripts/validate_payload.py --input <payload.json>`
5. 校验通过后返回 payload 给编排层。**不要**在此处写笔记文件或填写分类/takeaways；编排层会接着执行 [reference/save-and-process.md](../reference/save-and-process.md)。
