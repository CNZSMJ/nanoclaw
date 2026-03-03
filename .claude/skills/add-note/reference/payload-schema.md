# Payload Schema

`collection payload` 必须是单对象或对象数组，字段如下。

## 必填字段

| 字段 | 类型 | 约束 |
|------|------|------|
| title | string | 非空 |
| source | string | 非空；必须是固定来源名之一：`小红书` / `X` / `微信公众号` / `RSS` / `网页` / `Pasted`；禁止 URL |
| collected_at | string | `YYYY-MM-DD` 或 ISO 8601 |
| excerpt | string | 非空；可含 Markdown 图片 URL，不允许 `data:image/...` base64 内联 |

### 小红书附加约束（source=`小红书`）

- 若 `excerpt` 含图片（`![...](...)`），必须包含覆盖全部图片的逐图 OCR 段落：
  - `[图1 OCR]`
  - `[图2 OCR]`
  - ...
  - `[图N OCR]`
- 缺任一图片对应 OCR 段时，`validate_payload.py` 返回失败。

## 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| author | string | 作者名或账号 |

## 校验方式（必须）

```bash
python3 scripts/validate_payload.py --input <payload.json>
```

返回码约定：

- `0`：通过。
- `1`：字段校验失败。
- `2`：输入格式错误（非 JSON 或结构不合法）。
