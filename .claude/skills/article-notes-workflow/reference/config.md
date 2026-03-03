# 配置说明

**配置值**在 skill 根目录 [manifest.yaml](../manifest.yaml) 中修改；执行 Step 4（保存并加工）及图片落盘时以该文件为准。

## 配置项说明

### config 段（路径与命名）

| 配置项 | 说明 |
|--------|------|
| notes_path | 笔记 Markdown 文件所在目录。 |
| note_filename_format | 单条笔记文件名。占位符：`{slug}` 为文章标题生成的 slug（规则见 [save-and-process.md](save-and-process.md) 的「slug 生成规则」）。 |
| assets_path | 媒体（图片等）目录。所有媒体直接保存在此目录下，无子目录。 |
| asset_filename_format | 单张媒体文件命名。占位符：`{slug}` 同笔记，`{index:02}` 为两位序号（01、02…），`{ext}` 为扩展名（png、jpg 等）。 |
| index_file | 可选；近期笔记索引文件路径。 |

### categories（与 config 同级）

主分类列表：键为分类 id（如 tech、product），值为简短说明；Step 4 加工时从中选一个写入笔记 frontmatter 的 `category`，用于筛选与索引。

**用途**：
- 每条笔记选**一个主分类**，便于按分类过滤笔记、在索引中按分类汇总、保持一致的分类体系。

### tag_rules（与 config 同级）

标签约定：
- `style`：标签书写约定（如小写、连字符）。
- `min_tags` / `max_tags`：每条笔记的标签数量范围；与已有笔记的标签保持可复用、便于筛选。

## 使用方式

- 修改路径或命名：编辑 **manifest.yaml** 中 **config** 段对应键值即可（占位符含义不变，仅路径或格式可改）。
- 修改分类或标签规则：编辑 manifest 中 **categories** 与 **tag_rules**（与 config 同级）。
- 相对路径计算：笔记文件为 `{notes_path}/{note_filename_format}` 代入 slug。媒体文件为 `{assets_path}/{asset_filename_format}` 代入 slug、index、ext。笔记内引用图片时使用从笔记所在目录到媒体文件的**相对路径**。

## 图片落盘与引用

- 采集 workflow（Step 3）只产出 excerpt 中的图片 URL，不下载。
- Step 4 下载图片到 `assets_path`，按 `asset_filename_format` 命名，在笔记「原文」中将 URL 替换为相对路径。
- 若环境无法下载，保留原始 URL。
