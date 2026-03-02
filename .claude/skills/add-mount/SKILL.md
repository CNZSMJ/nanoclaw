# add-mount

为 NanoClaw 添加额外的目录挂载，让 agent 可以访问主机上的指定目录。

## 使用场景

- 让 agent 访问用户的 Obsidian 笔记目录
- 让 agent 访问某个项目文件夹
- 让 agent 访问下载目录等

## 步骤

### 1. 配置 mount-allowlist.json

创建或编辑 `~/.config/nanoclaw/mount-allowlist.json`：

```json
{
  "allowedRoots": [
    {
      "path": "/Users/huangjiahao",
      "allowReadWrite": true
    }
  ],
  "blockedPatterns": [],
  "nonMainReadOnly": false
}
```

**关键点**：
- `path`: 允许挂载的根目录
- `allowReadWrite`: 是否允许写入 (true/false)
- 必须用对象格式 `{"path": "..."}`，不是字符串数组

### 2. 配置 container_config

在数据库中配置 additionalMounts：

```bash
sqlite3 store/messages.db "UPDATE registered_groups SET container_config = '{\"additionalMounts\":[{\"hostPath\":\"/Users/huangjiahao/obsidian-reading\",\"containerPath\":\"obsidian\",\"readonly\":false}]}' WHERE folder = 'main';"
```

**关键点**：
- `hostPath`: 主机上的绝对路径
- `containerPath`: 容器内的相对路径（会自动加上 `/workspace/extra/` 前缀）
- **不要以 `/` 开头**，必须是相对路径如 `obsidian`，不是 `/workspace/obsidian`
- `readonly`: 是否只读

### 3. 重启服务

```bash
launchctl unload ~/Library/LaunchAgents/com.nanoclaw.plist
docker ps -q --filter "name=nanoclaw" | xargs docker kill
npx tsx setup/index.ts --step service
```

### 4. 验证

```bash
# 检查容器挂载
docker ps --format "{{.Names}}" | grep nanoclaw | head -1 | xargs -I {} docker inspect {} --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

容器内路径为 `/workspace/extra/{containerPath}`，如 `/workspace/extra/obsidian`

## 常见问题

### 挂载不生效

1. 检查 `mount-allowlist.json` 格式是否正确（必须是对象数组）
2. 检查 `containerPath` 是否以 `/` 开头（不能是绝对路径）
3. 检查主机路径是否存在
4. 查看日志 `logs/nanoclaw.error.log` 中的调试信息

### 调试

挂载验证逻辑在 `src/mount-security.ts`，可以添加 console.error 调试。
