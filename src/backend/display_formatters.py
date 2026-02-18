"""
工具显示格式化函数

将工具执行结果格式化为前端可用的显示信息
函数签名: (args: dict, result: Any, success: bool) -> dict
返回:
  {
    "abstract": str,       # 摘要行，人类可读，显示在卡片 header（如文件名、关键词）
    "details": dict | None # 展开区域的结构化字段，None 表示无展开内容
  }

details 字段由各工具自定义，前端按 key 渲染为 label: value 列表。
"""

import json
import re
from typing import Any


def _short_path(path: str, max_len: int = 60) -> str:
    """将绝对路径缩短为相对路径风格，保留最后 N 段"""
    path = path.replace("\\", "/").rstrip("/")
    parts = path.split("/")
    # 去掉盘符或空段
    parts = [p for p in parts if p and p != "."]
    # 如果路径太长，保留最后几段
    result = "/".join(parts)
    if len(result) <= max_len:
        return result
    # 从后往前取，直到不超长
    for i in range(len(parts) - 1, 0, -1):
        candidate = "…/" + "/".join(parts[i:])
        if len(candidate) <= max_len:
            return candidate
    return parts[-1]


def format_read_file(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "读取失败", "details": None}

    path = args.get("file_path", "")
    content = str(result) if result else ""
    total_lines = content.count("\n") + 1 if content else 0

    offset = args.get("offset")
    limit = args.get("limit")
    if offset and limit:
        line_info = f"  :{offset}–{offset + limit - 1}"
    elif offset:
        line_info = f"  :{offset}–"
    else:
        line_info = f"  ({total_lines} 行)"

    details: dict = {"完整路径": path, "行数": f"{total_lines} 行"}
    if content.strip():
        details["内容"] = content

    return {
        "abstract": _short_path(path) + line_info,
        "details": details
    }


def format_edit_file(args: dict, result: Any, success: bool) -> dict:
    path = args.get("file_path", "")
    explanation = args.get("explanation", "")

    if not success:
        return {"abstract": f"{_short_path(path)}  编辑失败", "details": None}

    # abstract = 路径 + 说明摘要（最能说明"改了什么"）
    if explanation:
        expl_short = explanation[:50] + ("…" if len(explanation) > 50 else "")
        abstract = f"{_short_path(path)}  —  {expl_short}"
    else:
        abstract = _short_path(path)

    old_str = args.get("old_string", "")
    new_str = args.get("new_string", "")

    details = {"完整路径": path}
    if explanation:
        details["说明"] = explanation
    if new_str:
        details["新内容"] = new_str

    return {"abstract": abstract, "details": details}


def format_multi_edit_file(args: dict, result: Any, success: bool) -> dict:
    path = args.get("file_path", "")
    edits = args.get("edits", [])
    explanation = args.get("explanation", "")

    if not success:
        return {"abstract": f"{_short_path(path)}  编辑失败", "details": None}

    count = len(edits)
    if explanation:
        expl_short = explanation[:50] + ("…" if len(explanation) > 50 else "")
        abstract = f"{_short_path(path)}  —  {expl_short}"
    else:
        abstract = f"{_short_path(path)}  ({count} 处修改)"

    details = {"完整路径": path, "修改数": f"{count} 处"}
    if explanation:
        details["说明"] = explanation
    if edits:
        changes = []
        for i, e in enumerate(edits):
            new_str = e.get("new_string", "") if isinstance(e, dict) else ""
            if new_str:
                changes.append(f"[{i+1}] {new_str[:200]}")
        if changes:
            details["新内容"] = "\n\n".join(changes)

    return {"abstract": abstract, "details": details}


def format_file_operation(args: dict, result: Any, success: bool) -> dict:
    path = args.get("file_path", "")
    if not success:
        return {"abstract": f"{_short_path(path)}  失败", "details": None}
    return {
        "abstract": _short_path(path),
        "details": {"完整路径": path}
    }


def format_list_dir(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "列目录失败", "details": None}

    path = args.get("directory_path", ".")
    content = str(result) if result else ""
    lines = [l for l in content.split("\n") if l.strip()]
    count = len(lines)

    preview_items = []
    for l in lines:
        match = re.search(r"\] (.+?)(?: \(|$)", l)
        if match:
            preview_items.append(match.group(1))

    details = {"完整路径": path, "条目数": str(count)}
    if preview_items:
        details["内容"] = "\n".join(preview_items)

    return {"abstract": f"{_short_path(path)}/  ({count} 项)", "details": details}


def format_find_by_name(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "文件搜索失败", "details": None}

    pattern = args.get("pattern", "")
    directory = args.get("SearchDirectory", args.get("directory", ""))
    content = str(result) if result else ""
    items = [i for i in content.split("\n") if i.strip()]
    count = len(items)

    if count == 0:
        loc = f"  in {_short_path(directory)}" if directory else ""
        return {"abstract": f'"{pattern}"{loc}  — 无匹配', "details": None}

    loc = f"  in {_short_path(directory)}" if directory else ""
    details = {"模式": pattern, "匹配数": str(count), "文件": "\n".join(items)}
    if directory:
        details["目录"] = directory

    return {"abstract": f'"{pattern}"{loc}  — {count} 个文件', "details": details}


def format_grep_search(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "搜索失败", "details": None}

    query = args.get("query", "")
    search_path = args.get("SearchPath", args.get("path", ""))
    content = str(result).strip() if result else ""

    if not content or "no matches" in content.lower():
        loc = f"  in {_short_path(search_path)}" if search_path else ""
        return {"abstract": f'"{query}"{loc}  — 无匹配', "details": None}

    lines = [l for l in content.split("\n") if l.strip()]
    count = len(lines)
    loc = f"  in {_short_path(search_path)}" if search_path else ""

    details = {"关键词": query, "匹配行数": str(count), "结果": "\n".join(lines)}
    if search_path:
        details["路径"] = search_path

    return {"abstract": f'"{query}"{loc}  — {count} 处', "details": details}


def format_search_web(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "搜索失败", "details": None}

    query = args.get("query", "")
    content = str(result) if result else ""

    try:
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            data = json.loads(json_match.group(0))
            results = data.get("results", [])
            titles = [f"[{r.get('id', '?')}] {r.get('title', '')}" for r in results]
            details = {"关键词": query, "结果数": str(len(results)), "结果": "\n".join(titles)}
            return {"abstract": f'"{query}"  — {len(results)} 条结果', "details": details}
    except (json.JSONDecodeError, TypeError):
        pass

    return {"abstract": f'"{query}"', "details": None}


def format_load_url_content(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "加载失败", "details": None}

    url = args.get("url", "")
    content = str(result) if result else ""

    try:
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            data = json.loads(json_match.group(0))
            title = (data.get("title") or "")[:60]
            url_id = data.get("url_id", "")
            pages = data.get("pages", [])
            page_summaries = [f"[{p.get('page_id', '?')}] {p.get('summary', '')}" for p in pages]

            # abstract 优先用标题，没有标题用域名
            if title:
                abstract = title
            else:
                domain = re.sub(r"https?://([^/]+).*", r"\1", url)
                abstract = domain[:60]

            details = {"URL": url}
            if url_id:
                details["ID"] = url_id
            if page_summaries:
                details["分页"] = "\n".join(page_summaries)

            return {"abstract": abstract, "details": details}
    except (json.JSONDecodeError, TypeError):
        pass

    domain = re.sub(r"https?://([^/]+).*", r"\1", url)
    return {"abstract": domain[:60], "details": {"URL": url}}


def format_read_page(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "读取页面失败", "details": None}

    page_id = args.get("page_id", "")
    content = str(result) if result else ""

    try:
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            data = json.loads(json_match.group(0))
            page_num = data.get("page_num", "?")
            total = data.get("total_pages", "?")
            size = data.get("size", 0)
            details = {"页面 ID": page_id, "页码": f"{page_num} / {total}", "大小": f"{size} 字节"}
            return {"abstract": f"[{page_id}]  第 {page_num} / {total} 页", "details": details}
    except (json.JSONDecodeError, TypeError):
        pass

    return {"abstract": f"[{page_id}]", "details": None}


def format_todo_operation(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "操作失败", "details": None}

    # create_todo_list: title 字段
    title = args.get("title", "")
    if title:
        return {"abstract": title[:60], "details": None}

    # add_todos: todos 列表
    todos = args.get("todos", [])
    if todos:
        if isinstance(todos, list) and len(todos) > 0:
            first = todos[0]
            content_str = first.get("content", "") if isinstance(first, dict) else str(first)
            suffix = f"  (+{len(todos) - 1})" if len(todos) > 1 else ""
            return {"abstract": f"{content_str[:50]}{suffix}", "details": None}

    # mark_todo_as_done: todo_id
    todo_id = args.get("todo_id", "")
    if todo_id:
        return {"abstract": f"完成 #{todo_id}", "details": None}

    return {"abstract": "已更新", "details": None}


def format_wait(args: dict, result: Any, success: bool) -> dict:
    seconds = args.get("seconds", 0)
    return {"abstract": f"等待 {seconds} 秒", "details": None}


def format_run_command(args: dict, result: Any, success: bool) -> dict:
    command = args.get("command", "")
    abstract = command[:70] + ("…" if len(command) > 70 else "")

    content = str(result) if result else ""
    lines = [l for l in content.split("\n") if l.strip()]
    details = None
    if lines:
        details = {"命令": command, "输出": "\n".join(lines)}

    return {"abstract": abstract, "details": details}


def format_default(args: dict, result: Any, success: bool) -> dict:
    if not success:
        return {"abstract": "执行失败", "details": None}

    content = str(result).strip() if result else ""
    if not content:
        return {"abstract": "已完成", "details": None}

    lines = [l for l in content.split('\n') if l.strip()]
    if len(lines) <= 1:
        return {"abstract": content[:80], "details": None}

    return {
        "abstract": lines[0][:80] + ("…" if len(lines[0]) > 80 else ""),
        "details": {"输出": "\n".join(lines)},
    }
