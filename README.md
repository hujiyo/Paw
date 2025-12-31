# Paw

一个智能桌面 Agent

## 特性

- **工具链**: 文件操作、目录搜索、终端控制、Web 搜索、网页阅读
- **记忆系统**: 基于 RAG 的本地向量检索，支持规则层和对话历史
- **会话管理**: 保存/恢复/删除对话历史，支持多会话切换
- **Skill 系统**: 用户自定义脚本扩展能力
- **Web UI**: 现代化的浏览器界面
- **上下文管理**: 智能管理大窗口上下文 (64K+ tokens)

## 快速开始

### 环境要求

- Python 3.8+
- Windows / Linux / macOS

### 安装

```bash
git clone https://github.com/hujiyo/Paw.git
cd Paw
pip install -r requirements.txt
```

### 配置

编辑 `config.yaml` 配置 API 和其他设置：

```yaml
# API 配置
api:
  key: "your-api-key"
  url: "https://open.bigmodel.cn/api/paas/v4/chat/completions"
  model: null  # 留空则启动时选择

# 终端配置
terminal:
  shell: 'powershell'  # 或 'cmd' / 'bash'
  encoding: 'utf-8'

# Web 工具配置
web:
  search_engine: 'duckduckgo'
  max_results: 5
  use_jina_reader: true  # 推荐，支持 JS 渲染
```

### 运行

```bash
python paw.py <workspace_dir>
```

或设置环境变量后直接运行：

```bash
set PAW_HOME=<workspace_dir>
python paw.py
```

默认启动 Web UI: http://127.0.0.1:8080

## 内置指令

| 指令 | 说明 |
|------|------|
| `/clear` | 清空对话历史 |
| `/model` | 重新选择模型 |
| `/new` | 开始新对话 |
| `/sessions` | 显示会话列表 |
| `/load <id>` | 恢复指定会话 |
| `/delete-session <id>` | 删除会话 |
| `/edit` | 进入对话编辑模式 |
| `/memory` | 查看记忆状态 |
| `/memory edit` | 管理记忆记录 |
| `/chunks` | 查看上下文详情 |
| `/messages` | 查看消息历史 |
| `/ctx` | 手动触发上下文优化 |

## 项目结构

```
Paw/
├── paw.py              # 主程序入口
├── config.yaml         # 配置文件
├── requirements.txt    # 依赖列表
│
├── tools.py            # 基础工具（文件/终端）
├── tool_definitions.py # 工具 Schema 定义
├── tool_registry.py    # 工具注册中心
│
├── chunk_system.py     # 上下文管理
├── context_branch.py   # 上下文分支
├── branch_executor.py  # 分支执行器
│
├── memory.py           # 记忆系统
├── session_manager.py  # 会话管理
│
├── prompts.py          # 提示词配置
├── call.py             # LLM 客户端
├── ui_web.py           # Web UI
├── terminal.py         # 终端管理
│
├── templates/          # 前端模板
├── embedding/          # 本地 Embedding 模型
└── scripts/            # 启动脚本
```

## 依赖

- **核心**: requests, pyyaml, colorama, tiktoken
- **LLM**: llama-cpp-python (本地 Embeddings)
- **Web**: fastapi, uvicorn, websockets
- **搜索**: ddgs (DuckDuckGo)
- **解析**: beautifulsoup4, html2text

## License

MIT License
