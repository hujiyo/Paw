#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""工具目录：把实现层的方法注册成 Agent 可调用的工具。

schema 与执行函数在这里成对出现，注册表即是唯一真相。
"""

from typing import Any, Dict, List, Optional

from core.tools import ToolRegistry, ToolSpec
from display_formatters import (
    format_default,
    format_edit_file,
    format_file_operation,
    format_find_by_name,
    format_grep_search,
    format_list_dir,
    format_load_url_content,
    format_multi_edit_file,
    format_read_file,
    format_read_page,
    format_run_command,
    format_search_web,
    format_todo_operation,
    format_wait,
)


def _obj(properties: Dict[str, Any], required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


TODO_ITEM = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Short summary of the task"},
        "details": {"type": "string", "description": "Additional context or details"},
    },
    "required": ["title", "details"],
}


def build_registry(base_tools, web_tools) -> ToolRegistry:
    registry = ToolRegistry()
    # 供 agent 层读取待办与终端状态
    registry.todo_plan = lambda: getattr(base_tools, "_todo_plan", [])
    registry.shell_snapshot = lambda: (
        base_tools.async_shell.get_screen_snapshot()
        if base_tools.async_shell.is_shell_open()
        else ""
    )

    t = base_tools
    w = web_tools

    registry.register(ToolSpec(
        name="read_file",
        description=(
            "Reads a file at the specified path. The file_path parameter must be an absolute path. "
            "You can optionally specify offset and limit to read large files. "
            "Text files are returned with 1-indexed line numbers."
        ),
        parameters=_obj({
            "file_path": {"type": "string", "description": "The path to the file to read."},
            "offset": {"type": "integer", "description": "The 1-indexed line number to start reading from."},
            "limit": {"type": "integer", "description": "The number of lines to read."},
        }, ["file_path"]),
        handler=t.read_file,
        display=format_read_file,
    ))

    registry.register(ToolSpec(
        name="write_to_file",
        description=(
            "Create new files. The file and any parent directories will be created for you if they do "
            "not already exist. NEVER use this tool to modify existing files; use edit instead."
        ),
        parameters=_obj({
            "file_path": {"type": "string", "description": "The target file to create and write to."},
            "content": {"type": "string", "description": "The content to write to the file."},
        }, ["file_path", "content"]),
        handler=t.write_to_file,
        display=format_file_operation,
    ))

    registry.register(ToolSpec(
        name="delete_file",
        description=(
            "Delete a file or directory at the specified path. Use with caution as this operation "
            "cannot be undone. For directories, this recursively deletes all contents."
        ),
        parameters=_obj({
            "file_path": {"type": "string", "description": "The path to the file or directory to delete"},
        }, ["file_path"]),
        handler=t.delete_file,
        display=format_file_operation,
    ))

    registry.register(ToolSpec(
        name="edit",
        description=(
            "Performs exact string replacements in files. You must use read_file at least once before "
            "editing. The edit FAILS if old_string is not unique unless replace_all is true, and FAILS "
            "if old_string and new_string are identical."
        ),
        parameters=_obj({
            "file_path": {"type": "string", "description": "The path to the file to modify."},
            "old_string": {"type": "string", "description": "The text to replace. Must be unique unless replace_all is true."},
            "new_string": {"type": "string", "description": "The replacement text (must differ from old_string)."},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences (default false)."},
        }, ["file_path", "old_string", "new_string"]),
        handler=t.edit,
        display=format_edit_file,
    ))

    registry.register(ToolSpec(
        name="multi_edit",
        description=(
            "Make multiple edits to a single file in one operation. Edits apply in sequence, each "
            "operating on the result of the previous one. If any edit fails, none are applied."
        ),
        parameters=_obj({
            "file_path": {"type": "string", "description": "The path to the file to modify."},
            "edits": {
                "type": "array",
                "description": "Edit operations to perform sequentially.",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_string": {"type": "string", "description": "The text to replace"},
                        "new_string": {"type": "string", "description": "The replacement text"},
                        "replace_all": {"type": "boolean", "description": "Replace all occurrences (default false)."},
                    },
                    "required": ["old_string", "new_string"],
                },
            },
        }, ["file_path", "edits"]),
        handler=t.multi_edit,
        display=format_multi_edit_file,
    ))

    registry.register(ToolSpec(
        name="find_by_name",
        description=(
            "Search for files and subdirectories within a directory. Pattern uses glob format. "
            "Results are capped at 50 matches."
        ),
        parameters=_obj({
            "search_directory": {"type": "string", "description": "The directory to search within"},
            "pattern": {"type": "string", "description": "Glob pattern to match names against"},
            "max_depth": {"type": "integer", "description": "Maximum search depth"},
            "type": {"type": "string", "enum": ["file", "directory", "any"], "description": "Type filter"},
        }, ["search_directory", "pattern"]),
        handler=t.find_by_name,
        display=format_find_by_name,
    ))

    registry.register(ToolSpec(
        name="grep_search",
        description=(
            "Search file contents. Set is_regex to true for full regex syntax. Filter files with the "
            "includes parameter in glob format. Results are capped at 100 matches."
        ),
        parameters=_obj({
            "query": {"type": "string", "description": "Search term or pattern"},
            "search_path": {"type": "string", "description": "File or directory to search"},
            "includes": {"type": "array", "items": {"type": "string"}, "description": "Glob filters, e.g. [\"*.py\"]"},
            "case_sensitive": {"type": "boolean", "description": "Case-sensitive search (default false)"},
            "is_regex": {"type": "boolean", "description": "Treat query as a regular expression"},
        }, ["query", "search_path"]),
        handler=t.grep_search,
        display=format_grep_search,
    ))

    registry.register(ToolSpec(
        name="list_dir",
        description="List files and directories in the given absolute directory path.",
        parameters=_obj({
            "directory_path": {"type": "string", "description": "Absolute path to the directory to list"},
        }, ["directory_path"]),
        handler=t.list_dir,
        display=format_list_dir,
    ))

    registry.register(ToolSpec(
        name="run_command",
        description=(
            "Run a command in the shared async terminal. The terminal is opened automatically if "
            "needed. Output is captured from the terminal screen; use wait() when the command is long "
            "running."
        ),
        parameters=_obj({
            "command": {"type": "string", "description": "The exact command line to execute"},
            "cwd": {"type": "string", "description": "Working directory hint (informational)"},
            "blocking": {"type": "boolean", "description": "Accepted for compatibility"},
        }, ["command"]),
        handler=t.run_command,
        display=format_run_command,
        timeout=60.0,
        shell=True,
        max_call_pairs=4,
    ))

    registry.register(ToolSpec(
        name="open_shell",
        description="Start the shared async terminal and wait until it is ready.",
        parameters=_obj({}),
        handler=t.open_shell,
        timeout=20.0,
        shell=True,
    ))

    registry.register(ToolSpec(
        name="interrupt_command",
        description="Interrupt the currently running command (equivalent to Ctrl+C).",
        parameters=_obj({}),
        handler=t.interrupt_command,
        shell=True,
    ))

    registry.register(ToolSpec(
        name="wait",
        description="Wait for a number of seconds, used to synchronize async terminal operations.",
        parameters=_obj({
            "seconds": {"type": "number", "description": "Seconds to wait, integer or decimal"},
        }, ["seconds"]),
        handler=t.wait,
        display=format_wait,
        timeout=120.0,
        max_call_pairs=3,
    ))

    registry.register(ToolSpec(
        name="create_todo_list",
        description=(
            "Create a new todo list to track tasks. Replaces any existing list. Use this when starting "
            "a task that needs multiple steps."
        ),
        parameters=_obj({
            "todos": {"type": "array", "description": "Todo items", "items": TODO_ITEM},
        }, ["todos"]),
        handler=t.create_todo_list,
        display=format_todo_operation,
    ))

    registry.register(ToolSpec(
        name="add_todos",
        description="Add one or more items to the current todo list.",
        parameters=_obj({
            "todos": {"type": "array", "description": "Todo items to add", "items": TODO_ITEM},
        }, ["todos"]),
        handler=t.add_todos,
        display=format_todo_operation,
        max_call_pairs=5,
    ))

    registry.register(ToolSpec(
        name="mark_todo_as_done",
        description="Mark one or more todo items as completed.",
        parameters=_obj({
            "todo_ids": {"type": "array", "items": {"type": "string"}, "description": "IDs to mark done"},
        }, ["todo_ids"]),
        handler=t.mark_todo_as_done,
        display=format_todo_operation,
        max_call_pairs=5,
    ))

    registry.register(ToolSpec(
        name="read_todos",
        description="Read the current todo list and progress.",
        parameters=_obj({}),
        handler=t.read_todos,
        display=format_todo_operation,
        max_call_pairs=1,
    ))

    registry.register(ToolSpec(
        name="load_skill",
        description=(
            "Load a skill by reading its SKILL.md. Automatically includes reference.md and examples.md "
            "if present, and lists available scripts. Use when a task matches a skill's purpose."
        ),
        parameters=_obj({
            "skill_name": {"type": "string", "description": "Skill directory name under ~/.paw/skills/"},
            "include_reference": {"type": "boolean", "description": "Include reference.md (default true)"},
            "include_examples": {"type": "boolean", "description": "Include examples.md (default true)"},
        }, ["skill_name"]),
        handler=t.load_skill,
        max_call_pairs=1,
    ))

    registry.register(ToolSpec(
        name="run_skill_script",
        description=(
            "Execute a script from a skill's scripts/ directory. Supports .py, .sh, .bat, .ps1, .js. "
            "Runs with the skill directory as working directory."
        ),
        parameters=_obj({
            "skill_name": {"type": "string", "description": "Skill directory name"},
            "script_name": {"type": "string", "description": "Script filename in scripts/"},
            "args": {"type": "string", "description": "Command line arguments (optional)"},
        }, ["skill_name", "script_name"]),
        handler=t.run_skill_script,
        max_call_pairs=3,
    ))

    registry.register(ToolSpec(
        name="stay_silent",
        description=(
            "Produce no response. ONLY use when the user's message clearly needs no reply (e.g. 'ok', "
            "'thanks'). Do NOT use after completing a task."
        ),
        parameters=_obj({
            "reason": {"type": "string", "description": "Why silence is appropriate"},
        }),
        handler=t.stay_silent,
        max_call_pairs=1,
    ))

    registry.register(ToolSpec(
        name="search_web",
        description=(
            "Search the web. Returns results with a 4-char ID, title, URL and snippet. Use the ID with "
            "load_url_content to load a result."
        ),
        parameters=_obj({
            "query": {"type": "string", "description": "Search query"},
        }, ["query"]),
        handler=w.search_web,
        display=format_search_web,
        timeout=60.0,
    ))

    registry.register(ToolSpec(
        name="load_url_content",
        description=(
            "Load a webpage into memory and split it into pages. Returns page IDs with summaries; "
            "use read_page to read a page."
        ),
        parameters=_obj({
            "url": {"type": "string", "description": "URL or 4-char ID from search_web results"},
        }, ["url"]),
        handler=w.load_url_content,
        display=format_load_url_content,
        timeout=120.0,
    ))

    registry.register(ToolSpec(
        name="read_page",
        description="Read a loaded page's content by its 4-character page ID.",
        parameters=_obj({
            "page_id": {"type": "string", "description": "4-character page ID from load_url_content"},
        }, ["page_id"]),
        handler=w.read_page,
        display=format_read_page,
    ))

    return registry


def register_memory_tools(registry: ToolRegistry, memory) -> None:
    """记忆系统启用后才注册，避免给模型一套不可用的工具。"""

    def search_memory(query: str, limit: int = 5) -> Dict[str, Any]:
        results = memory.recall(query, n_results=limit, min_score=0.3)
        return {
            "success": True,
            "results": [
                {"content": item} for item in (results or [])
            ],
            "count": len(results or []),
        }

    def save_memory(content: str) -> Dict[str, Any]:
        memory.save_conversation("[手动记录]", content)
        return {"success": True, "message": "已写入记忆"}

    registry.register(ToolSpec(
        name="memory_search",
        description="Search past conversation memories by meaning. Returns the most relevant stored exchanges.",
        parameters=_obj({
            "query": {"type": "string", "description": "What to look for"},
            "limit": {"type": "integer", "description": "Max results (default 5)"},
        }, ["query"]),
        handler=search_memory,
    ))
    registry.register(ToolSpec(
        name="memory_write",
        description="Store a durable fact into long-term memory for later recall.",
        parameters=_obj({
            "content": {"type": "string", "description": "The fact to remember"},
        }, ["content"]),
        handler=save_memory,
    ))
