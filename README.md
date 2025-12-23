# Paw 🐾

**Paw** 是一个基于大语言模型的智能终端 Agent，支持任意兼容 OpenAI API 的模型（智谱 GLM、本地 LLM 等）。它通过 Function Calling 实现文件操作、终端控制、Web 搜索等能力，并配备 RAG 记忆系统，让 AI 真正成为你的编程伙伴。

## ✨ 核心特性

### 🔧 完整的工具链
- **文件操作**: `read_file`, `write_to_file`, `edit`, `multi_edit`, `delete_file`
- **目录搜索**: `list_dir`, `find_by_name`, `grep_search`
- **终端控制**: `open_shell`, `run_command`, `interrupt_command` - 持久化 Shell 会话
- **Web 能力**: `search_web` (DuckDuckGo), `load_url_content`, `read_page` - 支持 Jina Reader 代理

### 🧠 RAG 记忆系统
- **规则层**: 用户规则 (`~/.paw/rules.yaml`) + 项目规范 (`{project}/.paw/conventions.yaml`)
- **对话存储**: 基于 ChromaDB 的向量检索，自动召回相关历史对话
- **生命值机制**: 高相关记忆持续被唤醒保留，临时记忆自然遗忘

### 📦 语块系统 (Chunk System)
- 智能管理 64K+ tokens 上下文窗口
- 支持 System / User / Assistant / Tool / Shell 等多种语块类型
- 动态刷新终端输出，AI 实时感知 Shell 状态

### 🎨 现代化 UI
- Claude Code 风格的彩色终端输出
- 流式响应，实时显示 AI 思考过程
- 工具调用状态可视化

## 🚀 快速开始

### 环境要求
- Python 3.8+
- Windows (目前终端功能仅支持 Windows)

### 安装

```bash
git clone https://github.com/hujiyo/Paw.git
cd Paw
pip install -r requirements.txt
```

首次运行会自动下载多语言 Embedding 模型 (`paraphrase-multilingual-MiniLM-L12-v2`)。

### 配置

编辑 `config.yaml`：

```yaml
# 身份配置（可选，自定义 AI 称呼）
identity:
  name: "Paw"
  username: "your_name"
  honey: "主人"

# API 配置（必填）
api:
  key: "your-api-key"
  url: "https://open.bigmodel.cn/api/paas/v4/chat/completions"
  model: null  # 留空则启动时选择

# 终端配置
terminal:
  shell: 'powershell'  # 或 'cmd'
  encoding: 'utf-8'

# Web 工具配置
web:
  search_engine: 'duckduckgo'
  max_results: 5
  use_jina_reader: true  # 推荐开启，支持 JS 动态渲染
```

### 运行

```bash
# 直接运行
python paw.py

# 或使用批处理脚本
scripts/paw.bat

# 添加到 PATH（推荐）
# 运行 scripts/add_to_path.ps1 后，可在任意位置使用 paw 命令
```

## 📖 使用指南

启动后直接用自然语言描述任务即可。内置指令：

| 指令 | 说明 |
|------|------|
| `/clear` | 清空对话历史和上下文 |
| `/model` | 重新选择 AI 模型 |
| `/chunks` | 查看当前语块详情（调试） |
| `/messages` | 查看完整消息历史（调试） |
| `/memory` | 查看记忆系统状态 |

## 🏗️ 项目架构

```
Paw/
├── paw.py              # 主程序入口，生命周期管理
├── config.yaml         # 核心配置文件
│
├── tools.py            # 基础工具集（文件/搜索）
├── terminal.py         # 线程化终端管理器
├── web_tools.py        # Web 搜索与网页阅读
├── tool_definitions.py # 工具 Schema 定义与注册
├── tool_registry.py    # 工具注册中心
│
├── chunk_system.py     # 语块系统，上下文管理
├── memory.py           # RAG 记忆系统
├── autostatus.py       # 动态状态评估
│
├── context_branch.py   # 上下文分支管理
├── branch_executor.py  # 分支执行器
│
├── prompts.py          # 提示词配置
├── ui.py               # 终端 UI 系统
│
└── scripts/
    ├── paw.bat         # Windows 启动脚本
    └── add_to_path.ps1 # PATH 环境变量配置
```

## 📦 依赖

```
# 核心
aiohttp, pyyaml, colorama, tiktoken

# Web 工具
ddgs, beautifulsoup4, html2text

# 记忆系统
llama-cpp-python, sqlite
```

## 📜 模型与许可证

- 本项目使用 Qwen 系列 GGUF 权重（embedding 目录），模型遵循 Apache License 2.0。  
- 权重未做修改；Apache 2.0 许可证文件已放置于 `embedding/` 目录。  
- 若分发本项目，请一并附带该许可证文件。

## 📄 License

MIT License

---

*Paw - 你的 AGI 级终端伙伴* 🐱
