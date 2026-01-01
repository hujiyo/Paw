# Paw Electron Desktop Application

Paw AI Terminal Agent 的 Electron 桌面封装版本，提供原生桌面应用体验。

## 功能特点

- 原生桌面应用体验，启动画面
- 自动管理 Python 后端进程
- 跨平台支持（Windows、macOS、Linux）
- 完整的虚拟环境打包，无需用户安装 Python

## 快速开始

### 环境要求

1. **开发环境**:
   - Node.js 18+ 和 npm
   - Python 3.8+
   - 项目依赖（通过 `requirements.txt`）

2. **用户环境**（打包后）:
   - 无需安装 Python，所有依赖已内置

### 开发

```bash
# 1. 创建 Python 虚拟环境并安装依赖
cd ..  # 回到项目根目录
python -m venv paw_env
paw_env\Scripts\activate
pip install -r requirements.txt

# 2. 安装 Node 依赖
cd electron
npm install

# 3. 运行开发模式
npm start
```

### 打包

**⚠️ 打包前准备**

确保项目根目录的 `embedding/` 文件夹下有 embedding 模型文件：

```
项目根目录/
├── embedding/
│   └── *.gguf          # 必需：embedding 模型文件
```

> **推荐模型**：`Qwen3-Embedding-0.6B-Q8_0.gguf`
>
> <small>用户需自行下载 embedding 模型，并确保遵循对应模型的许可证条款。
> Paw 项目仅提供软件框架，不提供任何模型文件。用户因未遵循模型许可证
> 而产生的任何法律后果，与 Paw 项目及其开发者无关。</small>

**开始打包**

```bash
cd electron

# Windows
npm run build:win

# macOS
npm run build:mac

# Linux
npm run build:linux
```

安装包输出到 `dist/` 目录，约 150-200MB。

## 项目结构

```
electron/
├── main.js           # Electron 主进程
├── preload.js        # 预加载脚本（安全桥接）
├── loading.html      # 启动画面
├── package.json      # Node.js 依赖配置
└── resources/        # 应用图标
    ├── icon.ico      # Windows 图标
    ├── icon.icns     # macOS 图标
    └── icon.png      # Linux 图标

../  # 项目根目录
├── embedding/        # Embedding 模型（必需）
│   └── *.gguf
├── paw_env/          # Python 虚拟环境
└── paw.py            # 主程序入口
```

## 打包原理

应用启动流程：

```
1. 显示启动画面（Logo + 进度条）
2. 启动 Python 后端（使用内置虚拟环境）
3. 等待服务器就绪（检测 127.0.0.1:8080）
4. 切换到主界面（http://127.0.0.1:8080）
```

打包后的目录结构：

```
Paw/
├── Paw.exe                    # Electron 主程序
└── resources/
    ├── paw_env/               # Python 虚拟环境（内置）
    │   └── Scripts/python.exe
    └── paw-core/              # Paw 核心代码
        ├── paw.py
        ├── config.yaml
        └── ...
```

## 自定义图标

将图标放置在 `electron/resources/` 目录：

| 平台 | 文件名 | 推荐尺寸 |
|------|--------|----------|
| Windows | `icon.ico` | 256x256 |
| macOS | `icon.icns` | 512x512 |
| Linux | `icon.png` | 512x512 |

可以使用 [在线工具](https://icoconvert.com/) 转换图标格式。

## 配置文件

Paw 的配置文件 `config.yaml` 位于打包后的 `resources/paw-core/` 目录，用户可以修改：

```yaml
# API 配置
api:
  key: "your-api-key"
  url: "https://open.bigmodel.cn/api/paas/v4/chat/completions"
  model: null

# 终端配置
terminal:
  shell: 'powershell'
  encoding: 'utf-8'

# Web 工具配置
web:
  search_engine: 'duckduckgo'
  max_results: 5
  use_jina_reader: true
```

## 故障排除

### 开发模式问题

**Python 后端无法启动**
```bash
# 检查虚拟环境是否存在
ls paw_env/Scripts/python.exe

# 重新安装依赖
paw_env\Scripts\activate
pip install -r requirements.txt
```

**端口被占用**
```bash
# 检查 8080 端口
netstat -ano | findstr :8080

# 结束占用进程
taskkill /PID <pid> /F
```

### 打包后问题

**应用无法启动**
- 检查安装目录是否完整
- 确认 `resources/paw_env/` 存在

**启动后显示错误：未找到 embedding 模型文件**
- 确认打包前 `embedding/` 目录下有 `*.gguf` 模型文件
- 检查 `resources/paw-core/embedding/` 是否存在

**启动后显示错误：llama_cpp 相关错误**
- 确认虚拟环境正确安装了 `llama-cpp-python`
- 重新运行：`pip install llama-cpp-python`

**启动后显示错误**
- 查看 `config.yaml` 中 API 配置是否正确
- 检查防火墙是否阻止 `127.0.0.1:8080`

## 许可证

MIT
