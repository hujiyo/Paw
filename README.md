# Paw 🐾

Paw 是一个基于大语言模型（LLM）的智能终端助手，旨在成为你开发环境中的“数字生命体”。它提供了一个统一的、上帝视角的命令行入口，通过简约的可视化界面和强大的工具集，协助你完成编码、系统管理和自动化任务。

## ✨ 核心特性

*   **统一交互入口**: 极简的 CLI 界面，Claude Code 风格的色彩输出，清晰区分用户、AI、工具和系统状态。
*   **MCP 标准工具集**: 内置遵循 Model Context Protocol (MCP) 标准的原子工具，支持文件操作、搜索、Shell 命令执行和多语言脚本运行（Python, Bash, Node, PowerShell）。
*   **智能上下文管理**: 采用独特的 Chunk System（语块系统），高效管理长上下文（支持 64k+ tokens），确保 AI 始终了解项目全貌。
*   **动态状态评估**: 内置 `AutoStatus` 系统，实时评估任务执行状态并动态调整系统提示词。
*   **全功能终端**: 支持持久化的 Shell 会话，实时捕获输出，就像与一位即时响应的结对程序员并肩工作。

## 🚀 快速开始

### 1. 环境准备
*   Python 3.8+
*   Git

### 2. 安装
```bash
git clone https://github.com/yourusername/Paw.git
cd Paw
pip install -r requirements.txt
```

### 3. 配置
在项目根目录找到 `config.yaml`，根据你的 LLM 提供商（如 OpenAI, 智谱 AI, 本地模型等）配置 API 信息：

```yaml
api:
  key: "your-api-key"
  url: "https://open.bigmodel.cn/api/paas/v4/chat/completions" # 示例地址
  model: null # 留空则在启动时自动检测选择
```

### 4. 运行
**Windows 用户:**
*   直接运行 `scripts/paw.bat`
*   或者运行 `python paw.py`

**添加至 PATH (推荐):**
运行 `scripts/add_to_path.ps1` 将 Paw 添加到环境变量，之后可在任意位置通过 `paw` 命令启动。

## 📖 使用指南

启动 Paw 后，你可以直接用自然语言描述你的任务。此外，Paw 还支持以下内置指令：

*   `/clear`: 清除当前对话历史和上下文。
*   `/model`: 重新扫描并切换 AI 模型。
*   `/chunks`: 查看当前的上下文语块详情（调试用）。
*   `/messages`: 查看完整的消息历史（调试用）。

## 🛠️ 项目结构

*   `paw.py`: 主程序入口与生命周期管理。
*   `tools.py`: 核心工具集实现 (File I/O, Terminal, Search)。
*   `chunk_system.py`: 智能上下文语块管理器。
*   `autostatus.py`: 动态状态评估系统。
*   `config.yaml`: 核心配置文件。

---
*Paw - 你的数字生命体终端助手*
