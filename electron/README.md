# Paw Electron Desktop Application

这是 Paw AI Terminal Agent 的 Electron 桌面封装版本。

## 功能特点

- 原生桌面应用体验
- 自动管理 Python 后端进程
- 跨平台支持（Windows、macOS、Linux）
- 单文件安装包分发

## 开发

### 前置要求

1. Node.js 18+ 和 npm
2. Python 3.10+
3. Paw 项目依赖（通过 requirements.txt）

### 安装依赖

```bash
cd electron
npm install
```

### 开发模式运行

```bash
npm run dev
```

这会启动 Electron 应用并打开开发者工具。

### 正常运行

```bash
npm start
```

## 构建安装包

### 构建所有平台

```bash
npm run build
```

### 仅构建 Windows

```bash
npm run build:win
```

### 仅构建 macOS

```bash
npm run build:mac
```

### 仅构建 Linux

```bash
npm run build:linux
```

构建产物会输出到 `dist` 目录。

## 项目结构

```
electron/
├── main.js           # Electron 主进程
├── preload.js        # 预加载脚本（安全桥接）
├── package.json      # Node.js 依赖配置
├── resources/        # 应用图标等资源
└── README.md         # 本文件
```

## 图标

将应用图标放置在 `resources/` 目录：
- Windows: `icon.ico`
- macOS: `icon.icns`
- Linux: `icon.png`

可以使用在线工具将 PNG 转换为 ICO/ICNS 格式。

## 环境变量

- `PAW_HOME`: Paw 工作目录（自动设置为项目根目录）
- `PAW_ELECTRON_MODE`: 设置为 '1' 时，Web UI 不会自动打开浏览器

## 故障排除

### Python 进程无法启动

1. 检查 Python 路径是否正确
2. 确保虚拟环境已配置（paw_env/Scripts/python.exe）
3. 查看开发者工具控制台日志

### WebSocket 连接失败

1. 确保 Python 后端已成功启动
2. 检查端口 8080 是否被占用
3. 查看主进程日志输出

## 许可证

MIT
