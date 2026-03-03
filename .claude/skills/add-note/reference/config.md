# 配置说明

**配置值**在 skill 根目录 [manifest.yaml](../manifest.yaml) 中修改；执行 Step 6（保存并加工）及图片落盘时以该文件为准。

## 配置项说明

### config 段（路径、命名、写入策略）

| 配置项 | 说明 |
|--------|------|
| notes_path | 笔记 Markdown 文件所在目录。 |
| note_filename_format | 单条笔记文件名模板。占位符：`{slug}`（标题 slug）、`{date}`（`collected_at` 的日期部分）。 |
| attachments_path | 附件（图片等）目录。所有附件直接保存在此目录下，无子目录。 |
| attachment_filename_format | 单个附件文件命名。占位符：`{slug}`、`{index:02}`（01、02…）、`{ext}`。其中 `{slug}` 使用“最终笔记文件名 stem”，保证附件与笔记同名基准。 |
| index_file | 可选；近期笔记索引文件路径。 |
| ensure_dirs | `true` 时，Preflight 会自动创建缺失目录（`notes_path`、`attachments_path`、`index_file` 的父目录）。 |
| atomic_write | `true` 时，写文件采用“临时文件 + rename”原子替换。 |
| note_conflict_strategy | 同名文件冲突策略。推荐 `suffix-date-counter`。 |
| download_timeout_seconds | 图片下载超时时间（秒）。 |
| max_images | 单篇最多下载图片数，超出部分保留远程 URL。 |
| xhs_downloader_path | 小红书工具目录。默认 `/app/XHS-Downloader`（容器内建路径）。 |
| xhs_auto_install | 小红书流程缺少工具时是否自动安装。默认 `true`。 |
| xhs_install_method | 自动安装依赖方式：`auto` / `uv` / `pip`。 |
| xhs_install_repo | 缺失时 clone 的仓库地址。 |
| minimax_mcp_server_name | MCP 服务名（用于从 `/workspace/global/.mcp.json` 与 `<workspace>/.claude/mcp.json` 检测 minimax 服务）。默认 `minimax`。 |

### categories（与 config 同级）

主分类列表：键为分类 id，值为简短定义；Step 6 加工时从中选一个写入 frontmatter 的 `category`。
规则：每条笔记只选一个最贴近核心结论的主分类。

### tag_rules（与 config 同级）

标签约定：
- `source_tags` 固定规则：从原文提取 `#tag`，按出现顺序去重，写入时去掉 `#` 前缀；若无则 `[]`。
- `style`：统一 `hashtag-zh-cn`（`#标签` 形式，支持中文与英文，如 `#AI`、`#创业`）。
- `ai_min_tags` / `ai_max_tags`：每条笔记 `ai_tags` 数量范围。
- `include_topic_tag=true`：至少包含一个主题标签（例如 `llm`、`product`、`ux`）。
- `prefer_existing_tags`、`max_new_tags_per_note`：控制标签稳定性，避免无限扩散。
- `forbidden_tags`：禁止使用的无信息量标签（如 `misc`）。
- `normalization`：大小写与分隔符标准化策略。

## 严格执行要求

1. 一律通过统一入口执行：`python3 scripts/run_add_note.py --source <source> --payload <payload.json> --metadata <metadata.json> --manifest ./manifest.yaml --report-out <report.json>`。
2. `run_add_note.py` 会先跑 Preflight（RSS digest 额外 `--require-digest`）；任一失败立即终止。
3. 对每条 URL，保存前必须先执行 `python3 scripts/check_existing_note.py --url <url> --manifest ./manifest.yaml` 做本地存在性核实；禁止仅凭记忆判断“已处理过”。
4. 目录不可写或工具缺失时立即失败并退出，不写任何文件。
5. 保存前必须通过 payload 校验；metadata 必须含 `category`、`ai_tags`、`takeaways`（英文源文需 `translation`）。
6. 命名冲突时必须按策略生成新文件名，不允许覆盖旧文件。
7. `source=xiaohongshu` 时，Preflight 会检查 `XHS_Downloader` 与 minimax：minimax 仅按 MCP 配置检测 `minimax_mcp_server_name`（读取顺序：`/workspace/global/.mcp.json`、`<workspace>/.claude/mcp.json`），并校验启动命令可执行（支持 `uvx` 与 `uv tool run`）。
8. 小红书流程固定先 OCR 前两张图做探测；但只要存在图片，必须全量 OCR 全部图片（可分批调用），并在 excerpt 中按 `[图N OCR]` 输出逐图结果；缺任一图片 OCR 段则 payload 校验失败。
9. 分类保持单分类；`source_tags` 保留原文标签，`ai_tags` 由模型按语义生成。
10. frontmatter 必须包含 `source`、`title`、`collected_at`、`category`、`source_tags`、`ai_tags`；其中 `source` 必须为固定来源名（禁止 URL）。
11. 禁止手工 `Edit/Bash` 直接写笔记与附件；postcheck 发现 `./media/` 路径将直接失败。

## 命名冲突策略（suffix-date-counter）

以 `note_filename_format` 代入后的文件名为基准：

1. 若不存在，直接使用。
2. 若已存在，追加 `-{date}`（如 `my-note-2026-03-03.md`）。
3. 仍冲突时，继续追加 `-{n}`（`-2`, `-3`, ...）直到不冲突。

## 图片落盘与引用

- 采集 workflow（Step 4）只产出 excerpt 中的图片 URL，不下载。
- Step 6 将图片统一落盘到 `attachments_path`（远程 URL 下载、本地图片复制），按 `attachment_filename_format` 命名，在笔记「原文」中替换为相对路径。
- 下载失败或超时：保留原始 URL，并在日志/回复中记录失败原因。
