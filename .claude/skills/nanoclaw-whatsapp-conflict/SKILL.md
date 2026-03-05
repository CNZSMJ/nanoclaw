---
name: nanoclaw-whatsapp-conflict
description: |
  修复 WhatsApp 连接冲突导致消息不接收的问题。Use when:
  (1) WhatsApp 日志出现 "Stream Errored (conflict)" 错误,
  (2) 多个 node 进程同时连接 WhatsApp (用 lsof -i | grep whatsapp 检查),
  (3) 日志显示 "Timeout in AwaitingInitialSync" 但连接正常,
  (4) 消息发送成功但收不到回复。需要杀掉残留进程并重启。
author: Claude Code
version: 1.0.0
date: 2025-03-05
---

# NanoClaw WhatsApp 连接冲突修复

## Problem
WhatsApp 收不到回复，消息不同步。日志显示连接正常但消息无法接收。

## Context / Trigger Conditions
- WhatsApp 日志出现 `Stream Errored (conflict)` 错误
- 日志显示 `Timeout in AwaitingInitialSync`
- `lsof -i | grep whatsapp` 显示多个 node 进程同时连接
- 之前有过 nanoclaw 重启但进程未完全清理

## Solution

### 1. 检查是否有多个进程
```bash
lsof -i | grep web.whatsapp.com
# 或
pgrep -f "node.*nanoclaw"
```

### 2. 杀掉所有残留进程
```bash
pkill -9 -f "node.*index.js"
pkill -9 -f "node.*nanoclaw"
```

### 3. 确认进程已清理
```bash
pgrep -f "node.*nanoclaw"
# 应该返回空或只有一个进程
```

### 4. 重启 nanoclaw
```bash
npm run start
```

### 5. 验证连接状态
```bash
tail -10 logs/whatsapp.log
# 应该看到 "Connected to WhatsApp"
```

## Verification
1. 确认只有一个 nanoclaw 进程
2. WhatsApp 日志显示 "Connected to WhatsApp"
3. 发送测试消息，确认能收到回复

## Notes
- 问题根源：之前的 kill 命令没有彻底杀掉进程
- 多个进程同时连接 WhatsApp 会导致服务器拒绝连接
- 建议：重启前先确认没有残留进程

## References
- [Baileys - WhatsApp Web JS Library](https://github.com/WhiskeySockets/Baileys)
