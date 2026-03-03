# 小红书 collection workflow

**Source**: Links from `xiaohongshu.com` or `xhslink.com` (笔记或主页链接).

---

## 1. 必备的工具及环境

| 检查项 | 检查命令 | 通过条件 | 失败处理 |
|------|----------|----------|----------|
| XHS_Downloader 可用 | `python3 scripts/preflight_check.py --source xiaohongshu --manifest ./manifest.yaml` | 输出包含 `[OK] xhs-downloader` | 若缺失则自动安装（clone + 依赖安装）；安装失败则终止并提示日志 |
| minimax_coding_plan_mcp 可用 | `python3 scripts/preflight_check.py --source xiaohongshu --manifest ./manifest.yaml` | 输出包含 `[OK] minimax-coding-plan-mcp` | 仅按 MCP 配置检测（`/workspace/global/.mcp.json`、`.claude/mcp.json`）并验证命令可执行（支持 `uvx` / `uv tool run`）；失败则终止并提示日志 |
| 小红书链接可解析 | 使用 XHS_Downloader 的 API/CLI 读取 URL | 能返回标题/作者/正文或媒体信息 | 提示用户链接失效、风控或 Cookie 问题，终止 |
| OCR/视觉能力（纯图场景） | 调用 minimax_coding_plan_mcp 的 `understand_image` | 能稳定返回图中文字 | 若调用失败则终止并提示检查 MCP 配置/API Key |

若任一项不满足：向用户说明并终止，不继续执行。当帖子为纯图且无 OCR/视觉时，可说明无法生成 Takeaways/译文，仅保存图片链接。
`XHS_Downloader` 的自动安装目标目录默认是 `/workspace/group/XHS-Downloader`（可在 manifest config 覆盖）。
`minimax_coding_plan_mcp` 只按 MCP 配置检测（服务名默认 `minimax`），配置运行方式可为 `uvx minimax-coding-plan-mcp` 或 `uv tool run minimax-coding-plan-mcp`。

---

## 2. 处理流程

1. 从用户消息中取得小红书 URL。
2. 使用 **XHS_Downloader** 提取内容（API 或命令行模式均可）：
   - 从解析结果识别：是**纯正文**、**正文+图**，还是**仅多图且文字全在图中**（如只有多张图、无独立正文）。
3. **图片探测（必须）**：
   - 若有图片，固定先下载并识别**前两张图片**（不足两张则全识别）。
   - 必须调用 `minimax_coding_plan_mcp` 的 `understand_image`，建议 OCR prompt：
     - `请提取图片中所有可见文字，逐行输出，不要总结，不要改写。`
   - 先计算两张图 OCR 文本合计长度（去空白后）`total_probe_chars`。
   - 若 `total_probe_chars <= 20`：默认 `image_text_dominant=false`（图片文字较少，按常规正文优先处理）。
   - 若 `total_probe_chars > 20`：由当前模型做语义判断是否“正文大概率在图片中”，输出 `image_text_dominant=true/false` 与一句理由。
4. **全量 OCR（必须）**：
   - 只要存在图片，就必须对**全部图片**做 OCR（按图片顺序 1..N，不允许截断到前 5 张或任意子集）。
   - 即使 `image_text_dominant=false` 也要做全量 OCR；若某图无明显文字，仍需保留占位：`[图N OCR]` 下写 `（无明显文字）`。
   - 图片较多时可分批调用（例如每批 3-5 张），但最终必须覆盖全部图片。
   - OCR 结果必须按以下格式写入 excerpt，供校验脚本检查覆盖率：
     - `[图1 OCR]`
     - `[图2 OCR]`
     - ...
     - `[图N OCR]`
5. **常规情况**（有独立正文或正文+图，且 `image_text_dominant=false`）：
   - 提取笔记标题、正文、作者（若有）、图片 URL（若有）。正文与代码块、图片 URL 按 Markdown 组织；若正文含 hashtag（如 `#穿搭`），必须原样保留。
   - 组装 payload：**title**、**source**=`小红书`、**collected_at**、**excerpt**（在正文前加入原帖链接行：`原帖链接：<url>`；随后正文、全量 OCR 区块、图片 Markdown）。
6. **图片文本主导或纯图场景**（`image_text_dominant=true` 或仅多图无正文）：
   - 提取所有图片 URL，准备放入 excerpt。
   - **必须同时处理正文与图片文字**：
     - 若有页面正文：保留页面正文；
     - 同时对全部图片做 OCR（覆盖 1..N），将 OCR 结果并入 excerpt。
   - **源文用于后续判断**：`正文 + OCR 文字` 的合并文本共同作为 Step 6 的语言判断和 Takeaways 输入。
   - excerpt 推荐格式：先写「页面正文（若有）」+「图中识别文字（全量，逐图）」+「原文图片」。例如：
     ```
     页面正文：

     [页面正文；若无可省略本段]

     ---

     以下文字自图中识别（全量）：

     [图1 OCR]
     [识别文字；无文字写“（无明显文字）”]

     [图2 OCR]
     [识别文字；无文字写“（无明显文字）”]

     ---

     原文图片：
     ![图1](url1)
     ![图2](url2)
     ```
   - 组装 payload：**title**（可用笔记首行或「小红书笔记-图片」）、**source**=`小红书`、**collected_at**、**excerpt**（在最前面加入 `原帖链接：<url>`，后接上述「正文 + 图中文字 + 原文图片」）。
7. 执行 payload 校验：
   - `python3 scripts/validate_payload.py --input <payload.json>`
8. 校验通过后返回 payload 给编排层。编排层必须准备 `metadata.json` 并调用 `python3 scripts/run_add_note.py ...` 执行落盘；**不要**在此处手工写笔记文件或附件。
