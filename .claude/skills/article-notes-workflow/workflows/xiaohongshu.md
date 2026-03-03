# 小红书 collection workflow

**Source**: Links from `xiaohongshu.com` or `xhslink.com` (笔记或主页链接).

---

## 1. 必备的工具及环境

| 项 | 要求 | 如何验证 |
|----|------|----------|
| agent-browser | 容器内可用（Bash + agent-browser） | 可执行 `agent-browser open <url>` 并做 snapshot 提取正文/图片 |
| OCR 或视觉能力（仅当笔记为「仅图、文字在图中」时） | 能从图片中识别文字（OCR 或多模态视觉 API） | 能对页面中的图片做文字提取或理解，用于生成 excerpt 中的「图中识别文字」 |

若任一项不满足：向用户说明并终止，不继续执行。当帖子为纯图且无 OCR/视觉时，可说明无法生成 Takeaways/译文，仅保存图片链接。

---

## 2. 处理流程

1. 从用户消息中取得小红书 URL。
2. 打开页面并提取内容：
   - 执行 `agent-browser open <url>`（或等价方式），再 snapshot，从主内容区识别：是**纯正文**、**正文+图**，还是**仅多图且文字全在图中**（如推文只有 5 张图、所有字都在图里）。
3. **常规情况**（有独立正文或正文+图）：
   - 提取笔记标题、正文、作者（若有）、图片 URL（若有）。正文与代码块、图片 URL 按 Markdown 组织。
   - 组装 payload：**title**、**source**、**collected_at**、**excerpt**（正文 + 若有图片则 `![描述](url)`）。
4. **特殊情况：仅多图、文字全在图中**（如仅 5 张图且无页面正文）：
   - 提取所有图片 URL，准备放入 excerpt。
   - **必须对图片做文字识别**（OCR 或视觉/多模态能力）：将识别出的文字作为「源文」供 Step 4 做语言判断、Takeaways 与译文。若当前环境无法做图中文字识别，向用户说明并终止（或仅保存图片链接，不生成 Takeaways/译文）。
   - excerpt 推荐格式：先写「以下文字自图中识别：」+ 识别出的全文，再「---」+「原文图片：」+ 每张图一行 `![图N](url)`。例如：
     ```
     以下文字自图中识别：

     [识别出的完整或分段文字]

     ---

     原文图片：
     ![图1](url1)
     ![图2](url2)
     ```
   - 组装 payload：**title**（可用笔记首行或「小红书笔记-图片」）、**source**、**collected_at**、**excerpt**（上述「图中文字 + 原文图片」）。
5. 将 payload 返回给编排层。编排层会执行 [reference/save-and-process.md](../reference/save-and-process.md)；**不要**在此处填写分类/takeaways。
