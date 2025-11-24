#!/usr/bin/env python
"""
工具错误处理模块 - 提供统一的错误消息格式
"""

class ToolError:
    """工具错误格式化"""
    
    @staticmethod
    def parameter_error(param_name: str, expected: str, got: str = None) -> str:
        """参数错误"""
        if got:
            return f"错误：参数 '{param_name}' 不正确，期望 {expected}，实际得到 {got}"
        else:
            return f"错误：缺少必需参数 '{param_name}'，期望 {expected}"
    
    @staticmethod
    def path_not_found(path: str) -> str:
        """路径不存在"""
        return f"错误：路径不存在 - {path}"
    
    @staticmethod
    def file_not_found(file: str) -> str:
        """文件不存在"""
        return f"错误：文件不存在 - {file}"
    
    @staticmethod
    def permission_denied(path: str) -> str:
        """权限不足"""
        return f"错误：权限不足，无法访问 - {path}"
    
    @staticmethod
    def empty_result(query: str = None) -> str:
        """空结果"""
        if query:
            return f"结果：未找到匹配 '{query}' 的内容"
        else:
            return "结果：目录为空或没有匹配项"
    
    @staticmethod
    def io_error(operation: str, detail: str) -> str:
        """IO错误"""
        return f"错误：{operation}失败 - {detail}"
    
    @staticmethod
    def timeout_error(seconds: int) -> str:
        """超时错误"""
        return f"错误：操作超时（{seconds}秒）"
    
    @staticmethod
    def invalid_format(expected_format: str) -> str:
        """格式错误"""
        return f"错误：格式不正确，期望 {expected_format}"
    
    @staticmethod
    def success(operation: str, detail: str = None) -> str:
        """成功消息"""
        if detail:
            return f"成功：{operation} - {detail}"
        else:
            return f"成功：{operation}完成"


# 导出
__all__ = ['ToolError']
