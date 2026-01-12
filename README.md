<img src="core/logo/图标2.png" width="128" height="128" alt="Paw">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="core/logo/图标3.png" width="128" height="128" alt="Paw">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="core/logo/图标.png" width="128" height="128" alt="Paw">

# Paw - 桌面 AI Agent

Paw 是一个基于 Electron 的使用TypeScript+Python打造的桌面级桌面 AI Agent 应用平台，支持文件操作、终端控制、Web 搜索等丰富的工具链，并具备会话管理、记忆系统和 Skill 扩展能力。。

## 特性

- **Electron 桌面应用**：原生桌面体验，自动管理 Python 后端，内置虚拟环境
- **丰富的工具链**：
  - 文件操作：读取、创建、编辑、删除文件
  - 目录搜索：按名称搜索、grep 内容搜索
  - 异步终端：run_command 执行命令，支持中断
  - Web 搜索：DuckDuckGo 搜索 + Jina Reader 网页阅读
- **会话管理**：自动保存对话历史，支持多会话切换
- **Skill 系统**：用户可在 `~/.paw/skills/` 自定义扩展能力
- **上下文管理**：智能管理 64K+ tokens 大窗口上下文
- **记忆系统**（可选）：基于 RAG 的对话记忆检索

## 快速开始

```bash
# 1. 创建 Python 虚拟环境
python -m venv paw_env

# 激活虚拟环境
# Windows:
paw_env\Scripts\activate
# macOS/Linux:
# source paw_env/bin/activate

# 2. 安装 Python 依赖
pip install -r core/requirements.txt

# 3. 安装 Node 依赖并启动
cd electron
npm install
npm start
```

## 打包安装

打包后的应用内置 Python 虚拟环境，用户无需安装 Python 即可使用。

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

## 内置指令

| 指令 | 说明 |
|------|------|
| `/new` | 开始新对话 |
| `/sessions` | 显示会话列表 |
| `/load <id>` | 恢复指定会话 |
| `/delete-session <id>` | 删除会话 |
| `/model` | 重新选择模型 |
| `/clear` | 清空对话历史 |
| `/edit` | 进入对话编辑模式 |
| `/memory` | 查看记忆状态 |
| `/ctx` | 手动触发上下文优化 |
| `/stop` | 停止当前生成 |

## 项目结构

```
Paw/
├── core/                   # Python 后端核心代码
│   ├── paw.py              # 主程序入口
│   ├── config.yaml         # 配置文件
│   ├── requirements.txt    # Python 依赖
│   │
│   ├── tools.py            # 基础工具（文件/终端/Web）
│   ├── tool_definitions.py # 工具 Schema 定义
│   ├── tool_registry.py    # 工具注册中心
│   │
│   ├── chunk_system.py     # 上下文管理
│   ├── context_branch.py   # 上下文分支编辑
│   ├── branch_executor.py  # 分支执行器
│   │
│   ├── memory.py           # 记忆系统
│   ├── session_manager.py  # 会话管理
│   │
│   ├── prompts.py          # 提示词配置
│   ├── call.py             # LLM API 客户端
│   ├── ui_web.py           # Web UI 服务
│   ├── terminal.py         # 异步终端管理
│   │
│   ├── templates/          # 前端 HTML 模板
│   ├── static/             # 前端静态资源
│   │   ├── css/
│   │   └── js/
│   └── logo/               # 应用图标
│
├── electron/               # Electron 桌面封装
│   ├── main.js             # Electron 主进程
│   ├── preload.js          # 预加载脚本
│   ├── package.json        # Node.js 配置
│   └── resources/          # 应用图标资源
│
├── paw_env/                # Python 虚拟环境
├── skills/                 # 用户自定义 Skill
└── dist/                   # 打包输出目录
```

## 依赖

**Python 依赖** (core/requirements.txt):
- pyyaml, colorama, requests
- fastapi, uvicorn, websockets, aiohttp
- ddgs (DuckDuckGo 搜索)
- beautifulsoup4, html2text

**Node.js 依赖** (electron/package.json):
- electron, electron-builder
- js-yaml

## Paw记忆意图判断机制

Paw 采用了一种创新的**记忆意图判断机制**，这种机制能在 RAG 检索前先以几乎无成本的方式判断用户问题是否需要记忆系统参与历史回忆。有效地规避了原native RAG机制响应延迟大、过度检索导致的信息冗余、记忆注入破坏对话连贯性等问题。

#### 具体来说
Paw的记忆系统会预计算一个"回忆意图锚点向量 B"，描述"回忆型问题"的语义特征：

```
用户输入 → 计算 embedding → 与 B 比较相似度
                              ↓
                    相似度 < 阈值 → 跳过记忆系统的回忆阶段（如"今天天气怎么样"）
                    相似度 ≥ 阈值 → 触发 RAG 检索（如"之前说的那个函数"）
```

## License

MIT License
