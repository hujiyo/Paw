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
    },
    {
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
    },
    {
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
    },
    {
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
    },
    {
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
    },
    {
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
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "A powerful search tool. Set is_regex to True to support full regex syntax. Filter files with includes parameter in glob format.",
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
    },
    {
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
    },
    {
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
    },
    {
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
    },
    {
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
    },
    {
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
]
