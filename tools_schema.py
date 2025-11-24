#!/usr/bin/env python
"""
工具定义 - OpenAI Function Calling 格式
符合 JSON Schema 规范
"""

# 所有可用工具的 OpenAI 格式定义
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文件内容，支持按行读取",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径（相对于工作空间或绝对路径）"
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "起始行号（可选，从1开始）"
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "结束行号（可选）"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "创建或覆盖文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "content": {
                        "type": "string",
                        "description": "文件内容"
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "删除文件或目录（包括目录下的所有内容）",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "要删除的文件或目录路径"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "编辑文件的指定行",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "line_number": {
                        "type": "integer",
                        "description": "行号（从1开始）"
                    },
                    "new_content": {
                        "type": "string",
                        "description": "新内容"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["replace", "insert", "delete"],
                        "description": "操作类型：replace(替换), insert(插入), delete(删除)"
                    }
                },
                "required": ["path", "line_number", "new_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "replace_in_file",
            "description": "在文件中替换文本",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "old_text": {
                        "type": "string",
                        "description": "要替换的文本"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "新文本"
                    }
                },
                "required": ["path", "old_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "multi_edit",
            "description": "批量编辑文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "edits": {
                        "type": "array",
                        "description": "编辑操作列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_string": {
                                    "type": "string",
                                    "description": "要替换的文本"
                                },
                                "new_string": {
                                    "type": "string",
                                    "description": "新文本"
                                }
                            },
                            "required": ["old_string", "new_string"]
                        }
                    }
                },
                "required": ["path", "edits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_files",
            "description": "按文件名搜索文件",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（支持通配符，如 *.py）"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径（默认为当前目录）"
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "最大搜索深度"
                    }
                },
                "required": ["pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "在文件内容中搜索文本",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词"
                    },
                    "path": {
                        "type": "string",
                        "description": "搜索路径"
                    },
                    "includes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "包含的文件模式列表"
                    },
                    "case_insensitive": {
                        "type": "boolean",
                        "description": "是否忽略大小写"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_in_file",
            "description": "在单个文件中搜索",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文件路径"
                    },
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式"
                    }
                },
                "required": ["path", "pattern"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "列出目录内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径（默认为当前目录）"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "在持久化终端中执行命令。终端保持状态，可以使用cd切换目录，目录状态会在多次命令间保持。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的命令（如 'ls'、'cd data'、'python script.py'）"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "超时时间（秒）"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_script",
            "description": "运行脚本代码",
            "parameters": {
                "type": "object",
                "properties": {
                    "lang": {
                        "type": "string",
                        "enum": ["python", "bash", "javascript", "powershell"],
                        "description": "脚本语言"
                    },
                    "code": {
                        "type": "string",
                        "description": "脚本代码"
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "脚本参数"
                    }
                },
                "required": ["lang", "code"]
            }
        }
    }
]
