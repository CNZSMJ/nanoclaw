---
name: x-integration-chrome-path-fix
description: |
  Fix Chrome path errors when running x-integration on macOS. Use when:
  (1) Error "Failed to launch chromium because executable doesn't exist",
  (2) x-integration fails with Chrome path issues,
  (3) CDP connection fails. Updates fallback path in x-integration-host.ts
  and ensures Chrome is started with remote debugging port.
author: Claude Code
version: 1.0.0
date: 2025-03-05
---

# X-Integration Chrome 路径修复 (macOS)

## Problem
x-integration 执行失败，报错 "Failed to launch chromium because executable doesn't exist at /Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

## Context / Trigger Conditions
- 在 macOS 上运行 x-integration
- nanoclaw 主进程没有正确配置 CHROME_PATH 环境变量
- x-integration-host.ts 中的 fallback 路径是 Linux 路径 `/usr/bin/chromium`

## Solution

### 1. 修改 x-integration-host.ts fallback 路径
文件: `src/x-integration-host.ts`

```typescript
// 修改前
CHROME_PATH: process.env.CHROME_PATH || '/usr/bin/chromium',

// 修改后
CHROME_PATH: process.env.CHROME_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
```

### 2. 重新编译并重启 nanoclaw
```bash
npm run build
# 重启 nanoclaw
```

### 3. 启动 Chrome 并开启远程调试（如果使用 CDP 模式）
```bash
open -a "Google Chrome" --args --remote-debugging-port=9222
```

## Verification
1. 确认端口 9222 监听: `lsof -i :9222`
2. 测试 x-integration 功能

## Notes
- nanoclaw 启动时不自动加载 .env 到 process.env，所以环境变量需要手动配置
- 如果不使用 CDP 模式，可以注释掉 CHROME_REMOTE_DEBUG_PORT，让 Playwright 自动启动 Chrome

## References
- [Playwright Chrome Launch](https://playwright.dev/docs/browsers#launching-chrome)
