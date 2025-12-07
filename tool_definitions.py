"""
工具定义与注册 - 将所有工具注册到 ToolRegistry

本文件负责：
1. 定义所有工具的 OpenAI schema
2. 注册工具到 ToolRegistry（包含上下文策略）
3. 提供 TOOLS_SCHEMA 供 API 调用使用

架构重构说明：
- 本次重构保持功能逻辑完全一致
- shell 相关工具使用 singleton 模式（已有优化）
- 其他工具暂时使用默认策略（unlimited）
- 后续可逐步添加压缩策略
"""

from tool_registry import (
    ToolRegistry, 
    register_tool, 
    key_constant, 
    key_by_arg,
    transform_to_summary,
    transform_truncate
)


# ============================================================
# Schema 定义（保持与原 tools_schema.py 完全一致）
# ============================================================

SCHEMA_READ_FILE = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Reads a file at the specified path. The file_path parameter must be an absolute path. You can optionally specify offset and limit to read large files. Text files are returned with 1-indexed line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to read. Must be an absolute path."
                },
                "offset": {
                    "type": "integer",
                    "description": "The 1-indexed line number to start reading from."
                },
                "limit": {
                    "type": "integer",
                    "description": "The number of lines to read."
                }
            },
            "required": ["file_path"]
        }
    }
}

SCHEMA_WRITE_TO_FILE = {
    "type": "function",
    "function": {
        "name": "write_to_file",
        "description": "Use this tool to create new files. The file and any parent directories will be created for you if they do not already exist. NEVER use this tool to modify or overwrite existing files. Always first confirm that file_path does not exist before calling this tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The target file to create and write code to."
                },
                "content": {
                    "type": "string",
                    "description": "The code contents to write to the file."
                }
            },
            "required": ["file_path", "content"]
        }
    }
}

SCHEMA_DELETE_FILE = {
    "type": "function",
    "function": {
        "name": "delete_file",
        "description": "Delete a file or directory at the specified path. Use with caution as this operation cannot be undone. For directories, this will recursively delete all contents.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file or directory to delete"
                }
            },
            "required": ["file_path"]
        }
    }
}

SCHEMA_EDIT = {
    "type": "function",
    "function": {
        "name": "edit",
        "description": "Performs exact string replacements in files. You must use read_file at least once before editing. The edit will FAIL if old_string is not unique in the file. Use replace_all to change every instance. The edit will FAIL if old_string and new_string are identical.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to modify, absolute path"
                },
                "old_string": {
                    "type": "string",
                    "description": "The text to replace. MUST be unique in the file unless replace_all is true"
                },
                "new_string": {
                    "type": "string",
                    "description": "The text to replace it with (must be different from old_string)"
                },
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences of old_string (default false)"
                }
            },
            "required": ["file_path", "old_string", "new_string"]
        }
    }
}

SCHEMA_MULTI_EDIT = {
    "type": "function",
    "function": {
        "name": "multi_edit",
        "description": "This is a tool for making multiple edits to a single file in one operation. All edits are applied in sequence. Each edit operates on the result of the previous edit. All edits must be valid for the operation to succeed - if any edit fails, none will be applied.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The path to the file to modify, absolute path"
                },
                "edits": {
                    "type": "array",
                    "description": "Array of edit operations to perform sequentially on the file",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_string": {
                                "type": "string",
                                "description": "The text to replace"
                            },
                            "new_string": {
                                "type": "string",
                                "description": "The text to replace it with (must be different from old_string)"
                            },
                            "replace_all": {
                                "type": "boolean",
                                "description": "Replace all occurrences of old_string (default false)"
                            }
                        },
                        "required": ["old_string", "new_string"]
                    }
                }
            },
            "required": ["file_path", "edits"]
        }
    }
}

SCHEMA_FIND_BY_NAME = {
    "type": "function",
    "function": {
        "name": "find_by_name",
        "description": "Search for files and subdirectories within a specified directory. Pattern uses the glob format. Results are capped at 50 matches.",
        "parameters": {
            "type": "object",
            "properties": {
                "search_directory": {
                    "type": "string",
                    "description": "The directory to search within"
                },
                "pattern": {
                    "type": "string",
                    "description": "Pattern to search for, supports glob format"
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Optional, maximum depth to search"
                },
                "type": {
                    "type": "string",
                    "enum": ["file", "directory", "any"],
                    "description": "Optional, type filter"
                }
            },
            "required": ["search_directory", "pattern"]
        }
    }
}

SCHEMA_GREP_SEARCH = {
    "type": "function",
    "function": {
        "name": "grep_search",
        "description": "A powerful search tool(仅本地文件系统内搜索). Set is_regex to True to support full regex syntax. Filter files with includes parameter in glob format.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search term or pattern to look for within files."
                },
                "search_path": {
                    "type": "string",
                    "description": "The path to search. This can be a directory or a file."
                },
                "includes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns to filter files, e.g., '*.py' to only include Python files."
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "If true, performs a case-sensitive search. Defaults to false."
                },
                "is_regex": {
                    "type": "boolean",
                    "description": "If true, treats query as a regular expression pattern."
                }
            },
            "required": ["query", "search_path"]
        }
    }
}

SCHEMA_LIST_DIR = {
    "type": "function",
    "function": {
        "name": "list_dir",
        "description": "Lists files and directories in a given path. The path parameter must be an absolute path to a directory that exists. For each item, output will have: relative path, and size in bytes if file.",
        "parameters": {
            "type": "object",
            "properties": {
                "directory_path": {
                    "type": "string",
                    "description": "The absolute path to the directory to list (must be absolute, not relative)"
                }
            },
            "required": ["directory_path"]
        }
    }
}

SCHEMA_RUN_COMMAND = {
    "type": "function",
    "function": {
        "name": "run_command",
        "description": "PROPOSE a command to run on behalf of the user. Make sure to specify command exactly as it should be run in the shell.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The exact command line string to execute."
                },
                "cwd": {
                    "type": "string",
                    "description": "The current working directory for the command"
                },
                "blocking": {
                    "type": "boolean",
                    "description": "If true, the command will block until finished. Default is true."
                }
            },
            "required": ["command"]
        }
    }
}

SCHEMA_OPEN_SHELL = {
    "type": "function",
    "function": {
        "name": "open_shell",
        "description": "Start a shared async terminal window. Will wait for the command prompt to appear before returning, ensuring the terminal is fully ready.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

SCHEMA_INTERRUPT_COMMAND = {
    "type": "function",
    "function": {
        "name": "interrupt_command",
        "description": "Interrupt the currently running long-running command, equivalent to sending Ctrl+C signal.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}

SCHEMA_WAIT = {
    "type": "function",
    "function": {
        "name": "wait",
        "description": "Wait for a specified duration (in seconds), used for synchronizing async operations.",
        "parameters": {
            "type": "object",
            "properties": {
                "seconds": {
                    "type": "number",
                    "description": "The number of seconds to wait, can be integer or decimal"
                }
            },
            "required": ["seconds"]
        }
    }
}

# ============================================================
# Web 工具 Schema
# ============================================================

SCHEMA_SEARCH_WEB = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "Search the web. Returns 5 results with 4-char ID, title, URL and snippet. Use the ID with load_url_content to load a result.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Supports syntax: \"exact phrase\", -exclude, site:example.com"
                }
            },
            "required": ["query"]
        }
    }
}

SCHEMA_LOAD_URL_CONTENT = {
    "type": "function",
    "function": {
        "name": "load_url_content",
        "description": "Load a webpage content into memory. Returns page IDs with summaries. Use read_page to read content.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL or 4-char ID from search_web results"
                }
            },
            "required": ["url"]
        }
    }
}

SCHEMA_READ_PAGE = {
    "type": "function",
    "function": {
        "name": "read_page",
        "description": "Read the content of a loaded page by its 4-character page ID. Must call load_url_content first to get page IDs.",
        "parameters": {
            "type": "object",
            "properties": {
                "page_id": {
                    "type": "string",
                    "description": "The 4-character unique page ID returned by load_url_content"
                }
            },
            "required": ["page_id"]
        }
    }
}


# ============================================================
# 工具注册函数
# ============================================================

def register_all_tools(tools_instance):
    """
    注册所有工具到 ToolRegistry
    
    Args:
        tools_instance: BaseTools 实例，提供工具的执行函数
    
    注意：
    - handler 绑定到具体实例的方法
    - 上下文策略在这里声明
    - 本次重构保持功能一致，暂不添加压缩策略
    """
    
    # === 文件读写工具 ===
    
    register_tool(
        name="read_file",
        schema=SCHEMA_READ_FILE,
        handler=tools_instance.read_file,
        # 暂时不压缩，保持原有行为
        # 后续可添加: singleton_key=key_by_arg("file_path"), max_instances=5
        category="file"
    )
    
    register_tool(
        name="write_to_file",
        schema=SCHEMA_WRITE_TO_FILE,
        handler=tools_instance.write_to_file,
        # 暂时不压缩，保持原有行为
        # 后续可添加: result_transform=transform_to_summary("✓ 写入 {file_path}")
        category="file"
    )
    
    register_tool(
        name="delete_file",
        schema=SCHEMA_DELETE_FILE,
        handler=tools_instance.delete_file,
        category="file"
    )
    
    # === 文件编辑工具 ===
    
    register_tool(
        name="edit",
        schema=SCHEMA_EDIT,
        handler=tools_instance.edit,
        category="edit"
    )
    
    register_tool(
        name="multi_edit",
        schema=SCHEMA_MULTI_EDIT,
        handler=tools_instance.multi_edit,
        category="edit"
    )
    
    # === 搜索工具 ===
    
    register_tool(
        name="find_by_name",
        schema=SCHEMA_FIND_BY_NAME,
        handler=tools_instance.find_by_name,
        category="search"
    )
    
    register_tool(
        name="grep_search",
        schema=SCHEMA_GREP_SEARCH,
        handler=tools_instance.grep_search,
        category="search"
    )
    
    register_tool(
        name="list_dir",
        schema=SCHEMA_LIST_DIR,
        handler=tools_instance.list_dir,
        category="search"
    )
    
    # === Shell 工具（已有 singleton 优化）===
    # 这些工具共享一个 "shell" chunk，通过 ChunkType.SHELL 实现
    # 注意：shell 的 singleton 逻辑目前在 ChunkManager 中特殊处理
    # 这里只是标记，实际逻辑保持不变
    
    register_tool(
        name="run_command",
        schema=SCHEMA_RUN_COMMAND,
        handler=tools_instance.run_command,
        # shell chunk 的管理目前由 _refresh_shell_chunk 处理
        # 这里的 singleton_key 暂时不生效，保持兼容
        singleton_key=key_constant("shell"),
        category="shell"
    )
    
    register_tool(
        name="open_shell",
        schema=SCHEMA_OPEN_SHELL,
        handler=tools_instance.open_shell,
        singleton_key=key_constant("shell"),
        category="shell"
    )
    
    register_tool(
        name="interrupt_command",
        schema=SCHEMA_INTERRUPT_COMMAND,
        handler=tools_instance.interrupt_command,
        singleton_key=key_constant("shell"),
        category="shell"
    )
    
    # === 辅助工具 ===
    
    register_tool(
        name="wait",
        schema=SCHEMA_WAIT,
        handler=tools_instance.wait,
        max_call_pairs=3,  # 只保留最近3次调用（tool_call + tool_result 配对）
        category="utility"
    )


def register_web_tools(web_tools_instance):
    """
    注册 Web 工具到 ToolRegistry
    
    Args:
        web_tools_instance: WebTools 实例
    """
    
    register_tool(
        name="search_web",
        schema=SCHEMA_SEARCH_WEB,
        handler=web_tools_instance.search_web,
        category="web"
    )
    
    register_tool(
        name="load_url_content",
        schema=SCHEMA_LOAD_URL_CONTENT,
        handler=web_tools_instance.load_url_content,
        category="web"
    )
    
    register_tool(
        name="read_page",
        schema=SCHEMA_READ_PAGE,
        handler=web_tools_instance.read_page,
        category="web"
    )


def get_tools_schema():
    """获取所有工具的 OpenAI schema（用于 API 调用）"""
    return ToolRegistry.get_schemas()


# 为了向后兼容，保留 TOOLS_SCHEMA 变量
# 但现在它是动态生成的，需要先调用 register_all_tools
def get_legacy_tools_schema():
    """
    获取传统格式的 TOOLS_SCHEMA
    
    注意：这个函数需要在 register_all_tools 之后调用
    """
    return ToolRegistry.get_schemas()


# ============================================================
# 向后兼容：静态 TOOLS_SCHEMA
# ============================================================
# 在工具未注册时，提供静态 schema 供导入使用
# 这样 paw.py 中的 from tools_schema import TOOLS_SCHEMA 仍然有效

TOOLS_SCHEMA = [
    SCHEMA_READ_FILE,
    SCHEMA_WRITE_TO_FILE,
    SCHEMA_DELETE_FILE,
    SCHEMA_EDIT,
    SCHEMA_MULTI_EDIT,
    SCHEMA_FIND_BY_NAME,
    SCHEMA_GREP_SEARCH,
    SCHEMA_LIST_DIR,
    SCHEMA_RUN_COMMAND,
    SCHEMA_OPEN_SHELL,
    SCHEMA_INTERRUPT_COMMAND,
    SCHEMA_WAIT,
    # Web 工具
    SCHEMA_SEARCH_WEB,
    SCHEMA_LOAD_URL_CONTENT,
    SCHEMA_READ_PAGE,
]


if __name__ == "__main__":
    # 测试
    print("=== 工具定义测试 ===")
    print(f"静态 TOOLS_SCHEMA 数量: {len(TOOLS_SCHEMA)}")
    
    # 模拟注册（需要 tools 实例）
    class MockTools:
        def read_file(self, **kwargs): pass
        def write_to_file(self, **kwargs): pass
        def delete_file(self, **kwargs): pass
        def edit(self, **kwargs): pass
        def multi_edit(self, **kwargs): pass
        def find_by_name(self, **kwargs): pass
        def grep_search(self, **kwargs): pass
        def list_dir(self, **kwargs): pass
        def run_command(self, **kwargs): pass
        def open_shell(self, **kwargs): pass
        def interrupt_command(self, **kwargs): pass
        def wait(self, **kwargs): pass
    
    mock_tools = MockTools()
    register_all_tools(mock_tools)
    
    print(f"注册后 schema 数量: {len(get_tools_schema())}")
    
    # 检查 wait 工具的 no_context 设置
    wait_config = ToolRegistry.get("wait")
    print(f"wait.no_context = {wait_config.no_context}")
    
    # 检查 shell 工具的 singleton_key
    run_cmd_config = ToolRegistry.get("run_command")
    print(f"run_command.singleton_key = {run_cmd_config.singleton_key}")
    
    print("测试完成")
