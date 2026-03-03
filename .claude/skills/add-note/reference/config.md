# 配置说明

**配置值**在 skill 根目录 [manifest.yaml](../manifest.yaml) 中修改；执行 Step 6（保存并加工）及图片落盘时以该文件为准。

## 配置项说明

### config 段（路径、命名、写入策略）

| 配置项 | 说明 |
|--------|------|
| notes_path | 笔记 Markdown 文件所在目录。 |
| note_filename_format | 单条笔记文件名模板。占位符：`{slug}`（标题 slug）、`{date}`（`collected_at` 的日期部分）。 |
| attachments_path | 附件（图片等）目录。所有附件直接保存在此目录下，无子目录。 |
| attachment_filename_format | 单个附件文件命名。占位符：`{slug}`、`{index:02}`（01、02…）、`{ext}`。 |
| index_file | 可选；近期笔记索引文件路径。 |
| ensure_dirs | `true` 时，Preflight 会自动创建缺失目录（`notes_path`、`attachments_path`、`index_file` 的父目录）。 |
| atomic_write | `true` 时，写文件采用“临时文件 + rename”原子替换。 |
| note_conflict_strategy | 同名文件冲突策略。推荐 `suffix-date-counter`。 |
| download_timeout_seconds | 图片下载超时时间（秒）。 |
| max_images | 单篇最多下载图片数，超出部分保留远程 URL。 |
| xhs_downloader_path | 小红书工具目录。默认 `groups/main/XHS-Downloader`（相对 workspace）。 |
| xhs_auto_install | 小红书流程缺少工具时是否自动安装。默认 `true`。 |
| xhs_install_method | 自动安装依赖方式：`auto` / `uv` / `pip`。 |
| xhs_install_repo | 缺失时 clone 的仓库地址。 |
| minimax_mcp_auto_install | 缺少 `minimax-coding-plan-mcp` 时是否自动安装。默认 `true`。 |
| minimax_mcp_package | MiniMax Coding Plan MCP 包名。默认 `minimax-coding-plan-mcp`。 |
| minimax_mcp_install_method | MiniMax MCP 安装方式：`auto` / `uv` / `pip`。默认 `auto`（先 uv，失败回退 pip）。 |
| minimax_uv_cache_dir | `uv tool` 使用的缓存目录，避免沙箱环境无法写 `~/.cache/uv`。默认 `/tmp/uv-cache`。 |
| minimax_uv_tool_dir | `uv tool` 安装目录，避免沙箱环境无法写 `~/.local/share/uv/tools`。默认 `/tmp/uv-tools`。 |

### categories（与 config 同级）

主分类列表：键为分类 id，值为简短定义；Step 6 加工时从中选一个写入 frontmatter 的 `category`。
规则：每条笔记只选一个最贴近核心结论的主分类。

### tag_rules（与 config 同级）

标签约定：
- `source_tags` 固定规则：从原文提取 `#tag`，按出现顺序去重，写入时去掉 `#` 前缀；若无则 `[]`。
- `style`：统一 `lowercase-kebab-case`。
- `ai_min_tags` / `ai_max_tags`：每条笔记 `ai_tags` 数量范围。
- `include_topic_tag=true`：至少包含一个主题标签（例如 `llm`、`product`、`ux`）。
- `prefer_existing_tags`、`max_new_tags_per_note`：控制标签稳定性，避免无限扩散。
- `forbidden_tags`：禁止使用的无信息量标签（如 `misc`）。
- `normalization`：大小写与分隔符标准化策略。

## 严格执行要求

1. 先跑 Preflight：`python3 scripts/preflight_check.py --source <source> --manifest ./manifest.yaml`（RSS digest 额外加 `--require-digest`）。
2. 目录不可写或工具缺失时立即失败并退出，不写任何文件。
3. 保存前必须通过 payload 校验：`python3 scripts/validate_payload.py --input <payload.json>`。
4. 命名冲突时必须按策略生成新文件名，不允许覆盖旧文件。
5. `source=xiaohongshu` 时，Preflight 会检查 `XHS_Downloader` 与 `minimax-coding-plan-mcp`；缺失且对应 auto install 为 `true` 时自动安装。
6. 小红书流程固定先 OCR 前两张图：若两张 OCR 合计字符数 `>20`，再由模型判断正文是否大概率在图片中；若是，则 payload 的 excerpt 必须同时包含页面正文与图片 OCR 文字。
7. 分类保持单分类；`source_tags` 保留原文标签，`ai_tags` 由模型按语义生成。
8. frontmatter 必须包含 `source`、`title`、`collected_at`、`category`、`source_tags`、`ai_tags`；其中 `source` 必须为固定来源名（禁止 URL）。

## 命名冲突策略（suffix-date-counter）

以 `note_filename_format` 代入后的文件名为基准：

1. 若不存在，直接使用。
2. 若已存在，追加 `-{date}`（如 `my-note-2026-03-03.md`）。
3. 仍冲突时，继续追加 `-{n}`（`-2`, `-3`, ...）直到不冲突。

## 图片落盘与引用

- 采集 workflow（Step 4）只产出 excerpt 中的图片 URL，不下载。
- Step 6 下载图片到 `attachments_path`，按 `attachment_filename_format` 命名，在笔记「原文」中将 URL 替换为相对路径。
- 下载失败或超时：保留原始 URL，并在日志/回复中记录失败原因。
