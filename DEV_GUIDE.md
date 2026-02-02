# Paw 开发指南

## 开发环境启动

### 标准开发流程（推荐）

**终端1 - 监听前端代码变化**：
```bash
npm run watch
```
保持运行，TypeScript 修改后会自动编译。

**终端2 - 启动应用**：
```bash
npm run start
```

### 快速启动

```bash
npm run start
```

**注意**：只适合单次测试。修改代码后需要关闭并重新运行。

## 代码修改后如何看到效果

### 前端代码修改（src/renderer/**/*）
- **自动编译**：`npm run watch` 会自动编译
- **刷新页面**：在 Electron 中按 `Ctrl+R` 或 `F5`

### 后端代码修改（src/backend/**/*）
- **关闭应用**：在终端2 按 `Ctrl+C`
- **重新启动**：重新运行 `npm run start`

### 主进程代码修改（src/main/**/*）
- **关闭应用**：在终端2 按 `Ctrl+C`
- **重新编译启动**：先运行 `npm run compile`，再运行 `npm run start`

## 为什么不能自动重启？

Electron + Python 混合架构的限制：
- **Python 后端**：不支持热重载，必须重启进程
- **Electron 主进程**：不支持热重载，必须重启应用
- **前端渲染进程**：可以刷新页面

这是 Electron 的技术限制，不是配置问题。

## 验证保存功能

运行 `npm run start` 后，在终端中会看到调试日志：
```bash
[DEBUG] Stream end, saving session...
[DEBUG] _save_session called: session_id=xxx, chunks=4
[DEBUG] Session saved successfully to file
[DEBUG] Save result: True
```

- 看到 `Save result: True` 表示保存成功
- 关闭应用后重新运行，检查消息是否恢复

## 常见问题

### Q: 为什么不能像网页开发那样自动刷新？
A: Electron 主进程和 Python 后端都不支持热重载。这是技术限制，所有 Electron 应用都这样。

### Q: 修改代码后看不到效果？
A: 检查以下几点：
1. 前端代码：检查终端1是否有编译输出？刷新浏览器了吗？
2. 后端代码：关闭应用了吗？重新运行 `npm run start` 了吗？
3. 查看终端中的 `[DEBUG]` 日志，确认代码是否被加载

### Q: tsc -w 监听不到文件变化？
A: 确保文件已保存，检查终端是否有编译输出。

## 构建生产版本

```bash
npm run build
```

构建产物位于 `dist-build/` 目录。
