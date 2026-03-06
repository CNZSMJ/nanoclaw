# X (Twitter) collection workflow

**Source**: Links from `x.com` or `twitter.com` (e.g. `https://x.com/username/status/123456`).

---

## 1. 必备的工具及环境

| 检查项 | 检查命令 | 通过条件 | 失败处理 |
|------|----------|----------|----------|
| x-integration 已接入 | `test -f .claude/skills/x-integration/agent.ts` | 返回码 0 | 提示用户先安装/接入 x-integration，终止 |
| X 登录态存在 | `test -f /workspace/project/data/x-auth.json` | 返回码 0 | 提示用户先执行 x setup，终止 |
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
   - **excerpt**: 严格按以下规则组装。**原则：保持 X 原帖的线性阅读感（文字、图片、文字、图片交错）。**
     - **第一部分（原文链接）**：`原帖链接：<tweet_url>`
     - **第二部分（互动数据）**：`🕒 <timestamp> | 👀 Views: <views> | ❤️ Likes: <likes> | 🔁 Retweets: <retweets> | 💬 Replies: <replies>`
     - `---`
     - **第三部分：主体内容（按顺序组装）**：
       - 对于 `main_tweet`（主推文）及其后续的 `context_or_replies`（Thread 串联），**必须**依次遍历每一个推文节点。
       - 针对每个节点，优先使用 **`ordered_content`** 数组：
         - 若类型为 `text`：原样保留换行和 `#hashtag` 填入。
         - 若类型为 `photo`：立即下方紧随 Markdown 格式 `![图片描述](图片URL)`。
         - 每个节点处理完后，添加一个空行。
       - *特殊情况*：若 `ordered_content` 缺失，则使用 `text` + `photos` 数组兜底（先文后图）。
     - **第四部分（OCR文字 - 可选）**：如执行了全量 OCR，则在**对应的图片下方**或段落末尾，以小红书标准格式列出：
       ```
       以下文字自图中识别（全量）：
       [图1 OCR]
       ...
       ```
     - **第五部分（回复 - 可选）**：若未作为 Thread 处理，可在此追加关键回复。
   - **translation (in metadata.json)**: **必须采用镜像排版原则。**
     - 不要只提供纯文本，应完整保留原文中的图片 Markdown 标签位。
     - 格式应为：`[译文1] -> ![图片1] -> [译文2] -> ![图片2]`。
     - 确保用户在阅读译文时能获得与原文一致的图文沉浸感。
5. 执行 payload 校验：
   - `python3 scripts/validate_payload.py --input <payload.json>`
6. 校验通过后返回 payload 给编排层。编排层准备 `metadata.json` 并调用统一脚本 `run_add_note.py` 执行落盘（包括翻译与排版）；**不要**自主写入笔记文件。
