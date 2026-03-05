# X (Twitter) collection workflow

**Source**: Links from `x.com` or `twitter.com` (e.g. `https://x.com/username/status/123456`).

---

## 1. 必备的工具及环境

| 检查项 | 检查命令 | 通过条件 | 失败处理 |
|------|----------|----------|----------|
| x-integration 已接入 | `test -f .claude/skills/x-integration/agent.ts` | 返回码 0 | 提示用户先安装/接入 x-integration，终止 |
| X 登录态存在 | `test -f data/x-auth.json` | 返回码 0 | 提示用户先执行 x setup，终止 |
| `x_read_tweet` 工具可见 | 在当前会话工具列表中检查 `x_read_tweet` | 工具可调用 | 提示用户重启服务/重建容器后重试，终止 |
| minimax_coding_plan_mcp 可用 (仅当使用 OCR 时) | 用户需在后续步骤确认触发 OCR 时检查。这里可预留检查逻辑：`python3 scripts/preflight_check.py --source xiaohongshu --manifest ./manifest.yaml` （借用小红书检查）| 输出包含 `[OK] minimax-coding-plan-mcp` | 若调用 OCR 时失败，提示检查 MCP 配置，但仍保留非 OCR 的推文内容并继续 |

若前三项任一项不满足：向用户说明并终止，不继续执行。

---

## 2. 处理流程

1. 从用户消息中取得该条 X 链接（已被编排层识别为 X 的 URL）。
2. 使用 **x_read_tweet** 调用该 URL 获取原始推文数据，包含：
   - 核心参数：作者(`author/handle`)、推文正文(`text`)、发布时间(`timestamp`)、包含的图片(`photos`)。
   - 统计互动数据 (`metrics`)：查看数(`views`)、点赞数(`likes`)、转发数(`retweets`)、回复数(`replies`)。
   - 回复列表（如果有）。
3. **图片与 OCR 交互分支**：
   - 若 `photos` 存在且不为空，则**必须触发交互询问**：“检测到该推文包含图片，是否需要执行 OCR 识别？提取图中文字有助于归档‘一图流’长图。(y/n)”。
   - 若用户回答 `y` / `是`，则依次下载推文中的每一张图，调用 `minimax_coding_plan_mcp` 的 `understand_image` 提取文字。
   - 若用户回答 `n` / `否` 或无图片，则直接进入下一步。
4. **组装 collection payload**：
   - **title**: 推文首行或 "Tweet by @{handle}"（若无明显正文）。
   - **source**: 固定写 `X`。
   - **collected_at**: 当日 `YYYY-MM-DD` 或 ISO 时间（可从推文 `timestamp` 提取）。
   - **excerpt**: 严格按以下顺序组装，确保推文互动数据和排版完整：
     - **第一部分（原文链接）**：`原帖链接：<tweet_url>`
     - **第二部分（互动数据）**：`🕒 <timestamp> | 👀 Views: <views> | ❤️ Likes: <likes> | 🔁 Retweets: <retweets> | 💬 Replies: <replies>` (如有缺失项可留空或写 0)
     - `---` (分割线)
     - **第三部分（推文原文）**：原样填入推文正文(`text`)。换行和 `#hashtag` 必须原封不动保留，不作任何清洗。
     - **第四部分（原文图片）**：将提取到的 `photos` 数组转换为 Markdown 图片格式 `![图片描述](图片URL)` (禁止 base64)。
     - **第五部分（OCR文字 - 可选）**：如执行了全量 OCR，则在图片下方或分割线后，以小红书标准格式列出：
       ```
       以下文字自图中识别（全量）：

       [图1 OCR]
       [识别文字；无文字写“（无明显文字）”]
       ...
       ```
     - **第六部分（回复 - 可选）**：如果一并拉取了主干回复，可追加 "Replies:" 及 3-5 条关键回复内容。
5. 执行 payload 校验：
   - `python3 scripts/validate_payload.py --input <payload.json>`
6. 校验通过后返回 payload 给编排层。编排层准备 `metadata.json` 并调用统一脚本 `run_add_note.py` 执行落盘（包括翻译与排版）；**不要**自主写入笔记文件。
