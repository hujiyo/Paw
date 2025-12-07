#!/usr/bin/env python
"""
Web 工具模块 - 提供联网搜索和网页阅读能力

工具列表:
1. search_web: 搜索引擎搜索，返回前5条结果摘要
2. load_url_content: 加载网页内容到内存，分页并生成摘要
3. read_page: 按页码读取已加载的内容
"""

import aiohttp
import asyncio
import hashlib
import random
import string
import re
from typing import Dict, List, Any, Optional
from urllib.parse import quote_plus, urlparse
from bs4 import BeautifulSoup
import html2text


class WebTools:
    """
    Web 工具类 - 提供搜索和网页阅读功能
    """
    
    def __init__(self, config: dict, api_url: str, model_getter, api_key: Optional[str] = None):
        """
        初始化 Web 工具
        
        Args:
            config: web 配置字典
            api_url: API 地址（用于生成摘要）
            model_getter: 获取当前模型名称的函数（动态获取）
            api_key: API 密钥
        """
        self.config = config or {}
        self.api_url = api_url
        self._model_getter = model_getter  # 动态获取模型
        self.api_key = api_key
        
        # 配置项
        self.search_engine = self.config.get('search_engine', 'duckduckgo')
        self.max_results = self.config.get('max_results', 5)
        self.page_size = self.config.get('page_size', 4096)  # 每页最大 4KB
        self.use_jina_reader = self.config.get('use_jina_reader', True)  # 默认启用 Jina Reader
        
        # 内存存储: page_id -> {"content": str, "url": str, "summary": str}
        self.pages: Dict[str, Dict[str, str]] = {}
        
        # URL 到 page_ids 的映射
        self.url_pages: Dict[str, List[str]] = {}
        
        # 搜索结果 URL 映射: url_id -> url
        self.url_refs: Dict[str, str] = {}
        
        # 已使用的 ID 集合（防止重复，page_id 和 url_id 共用）
        self.used_ids: set = set()
        
        # html2text 转换器配置
        self.h2t = html2text.HTML2Text()
        self.h2t.ignore_links = False
        self.h2t.ignore_images = True
        self.h2t.ignore_emphasis = False
        self.h2t.body_width = 0  # 不自动换行
    
    @property
    def model(self) -> str:
        """动态获取当前模型名称"""
        return self._model_getter() if callable(self._model_getter) else str(self._model_getter)
    
    def _generate_page_id(self) -> str:
        """生成全局唯一的 4 位 page_id (base62)"""
        chars = string.ascii_lowercase + string.ascii_uppercase + string.digits
        while True:
            page_id = ''.join(random.choices(chars, k=4))
            if page_id not in self.used_ids:
                self.used_ids.add(page_id)
                return page_id
    
    async def search_web(self, query: str, num_results: int = None) -> Dict[str, Any]:
        """
        搜索引擎搜索
        
        Args:
            query: 搜索关键词，支持搜索语法
            num_results: 返回结果数量（默认使用配置值）
            
        Returns:
            搜索结果字典
        """
        num_results = num_results or self.max_results
        
        try:
            if self.search_engine == 'duckduckgo':
                results = await self._search_duckduckgo(query, num_results)
            else:
                # 默认使用 DuckDuckGo
                results = await self._search_duckduckgo(query, num_results)
            
            # 为每个结果分配 4 字符 ID
            for r in results:
                url_id = self._generate_page_id()  # 复用 ID 生成器
                r["id"] = url_id
                self.url_refs[url_id] = r["url"]
            
            return {
                "success": True,
                "query": query,
                "engine": self.search_engine,
                "results": results,
                "count": len(results)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"搜索失败: {str(e)}",
                "query": query
            }
    
    async def _search_duckduckgo(self, query: str, num_results: int) -> List[Dict[str, str]]:
        """使用 DuckDuckGo 搜索"""
        from ddgs import DDGS
        
        results = []
        
        # DuckDuckGo 搜索（同步库，在线程中运行）
        def do_search():
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=num_results))
        
        # 在线程池中执行同步操作
        loop = asyncio.get_event_loop()
        search_results = await loop.run_in_executor(None, do_search)
        
        for item in search_results:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", "")[:200]  # 摘要限制 200 字符
            })
        
        return results
    
    async def load_url_content(self, url: str) -> Dict[str, Any]:
        """
        加载网页内容到内存，分页并生成摘要
        
        Args:
            url: 要加载的网页 URL，或者 search_web 返回的 4 字符 ID
            
        Returns:
            加载结果，包含页码信息和每页摘要
        """
        # 支持 4 字符 ID 引用
        url_id = None
        if len(url) == 4 and url in self.url_refs:
            url_id = url
            url = self.url_refs[url]
        
        try:
            # 获取网页内容
            raw_content = await self._fetch_url(url)
            
            # 检查是否是 Jina 返回的 Markdown
            if raw_content.startswith("__JINA_MARKDOWN__\n"):
                # Jina 已经返回 Markdown，直接使用
                markdown_content = raw_content[len("__JINA_MARKDOWN__\n"):]
                # 从 Markdown 中提取标题（第一个 # 开头的行）
                title = self._extract_title_from_markdown(markdown_content)
            else:
                # 原始 HTML，需要转换
                markdown_content = self._html_to_markdown(raw_content)
                title = self._extract_title(raw_content)
            
            # 分页
            pages_content = self._split_into_pages(markdown_content)
            
            # 为每页生成 ID
            page_ids = [self._generate_page_id() for _ in pages_content]
            total_pages = len(pages_content)
            
            # 并行生成所有摘要（大幅提升速度）
            import asyncio
            summary_tasks = [
                self._generate_summary(content, i + 1, total_pages)
                for i, content in enumerate(pages_content)
            ]
            summaries = await asyncio.gather(*summary_tasks)
            
            # 存储到内存并构建返回信息
            page_infos = []
            for i, (page_id, content, summary) in enumerate(zip(page_ids, pages_content, summaries)):
                self.pages[page_id] = {
                    "content": content,
                    "url": url,
                    "page_num": i + 1,
                    "total_pages": total_pages,
                    "summary": summary
                }
                
                page_infos.append({
                    "page_id": page_id,
                    "page_num": i + 1,
                    "summary": summary,
                    "size": len(content)
                })
            
            # 记录 URL 到 pages 的映射
            self.url_pages[url] = page_ids
            
            result = {
                "success": True,
                "url": url,
                "title": title,
                "total_pages": len(pages_content),
                "total_size": len(markdown_content),
                "pages": page_infos
            }
            # 如果是通过 ID 加载的，附上 ID
            if url_id:
                result["url_id"] = url_id
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": f"加载失败: {str(e)}",
                "url": url
            }
    
    async def _fetch_url(self, url: str) -> str:
        """获取网页内容（支持 Jina Reader 代理）"""
        
        if self.use_jina_reader:
            # 使用 Jina Reader API（自动处理 JS 渲染）
            return await self._fetch_via_jina(url)
        else:
            # 直接获取（仅支持静态页面）
            return await self._fetch_direct(url)
    
    async def _fetch_via_jina(self, url: str) -> str:
        """通过 Jina Reader API 获取网页内容（返回 Markdown）"""
        jina_url = f"https://r.jina.ai/{url}"
        
        headers = {
            "Accept": "text/plain",
            "User-Agent": "Paw/1.0"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                jina_url, 
                headers=headers, 
                timeout=aiohttp.ClientTimeout(total=60)  # Jina 可能需要更长时间渲染
            ) as response:
                if response.status != 200:
                    # Jina 失败，回退到直接获取
                    return await self._fetch_direct(url)
                
                content = await response.text()
                
                # Jina 返回的已经是 Markdown，标记一下
                return f"__JINA_MARKDOWN__\n{content}"
    
    async def _fetch_direct(self, url: str) -> str:
        """直接获取网页 HTML 内容"""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")
                
                # 尝试检测编码
                content_type = response.headers.get('Content-Type', '')
                if 'charset=' in content_type:
                    encoding = content_type.split('charset=')[-1].split(';')[0].strip()
                else:
                    encoding = 'utf-8'
                
                try:
                    return await response.text(encoding=encoding)
                except:
                    return await response.text(encoding='utf-8', errors='ignore')
    
    def _html_to_markdown(self, html: str) -> str:
        """将 HTML 转换为 Markdown"""
        # 使用 BeautifulSoup 清理 HTML
        soup = BeautifulSoup(html, 'html.parser')
        
        # 移除脚本、样式等无用元素
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'noscript', 'iframe']):
            tag.decompose()
        
        # 尝试找到主要内容区域
        main_content = (
            soup.find('main') or 
            soup.find('article') or 
            soup.find('div', class_=re.compile(r'content|main|article|post', re.I)) or
            soup.find('body')
        )
        
        if main_content:
            html_str = str(main_content)
        else:
            html_str = str(soup)
        
        # 转换为 Markdown
        markdown = self.h2t.handle(html_str)
        
        # 清理多余空行
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        return markdown.strip()
    
    def _extract_title(self, html: str) -> str:
        """提取网页标题"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # 优先使用 <title> 标签
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            return title_tag.string.strip()[:100]
        
        # 其次使用 <h1>
        h1_tag = soup.find('h1')
        if h1_tag:
            return h1_tag.get_text().strip()[:100]
        
        return "无标题"
    
    def _extract_title_from_markdown(self, markdown: str) -> str:
        """从 Markdown 内容中提取标题"""
        lines = markdown.strip().split('\n')
        
        for line in lines[:20]:  # 只检查前 20 行
            line = line.strip()
            # 匹配 # 开头的标题
            if line.startswith('# '):
                return line[2:].strip()[:100]
            # 匹配 Title: 开头（Jina 有时会这样返回）
            if line.lower().startswith('title:'):
                return line[6:].strip()[:100]
        
        return "无标题"
    
    def _split_into_pages(self, content: str) -> List[str]:
        """将内容分割为多个页面"""
        pages = []
        
        # 按字节大小分割
        content_bytes = content.encode('utf-8')
        total_size = len(content_bytes)
        
        if total_size <= self.page_size:
            return [content]
        
        # 按段落分割，尽量不打断段落
        paragraphs = content.split('\n\n')
        current_page = ""
        current_size = 0
        
        for para in paragraphs:
            para_size = len(para.encode('utf-8'))
            
            if current_size + para_size + 2 > self.page_size:
                if current_page:
                    pages.append(current_page.strip())
                current_page = para
                current_size = para_size
            else:
                current_page += "\n\n" + para if current_page else para
                current_size += para_size + 2
        
        if current_page:
            pages.append(current_page.strip())
        
        return pages if pages else [content]
    
    async def _generate_summary(self, content: str, page_num: int, total_pages: int) -> str:
        """使用 LLM 生成页面摘要（10-30字）"""
        
        # 如果内容为空，直接返回
        if not content or not content.strip():
            return "(空页面)"
        
        # 截取内容的前 500 字符用于生成摘要
        preview = content[:500] if len(content) > 500 else content
        
        prompt = f"""请用10-30个中文字符总结以下内容的主题。只输出总结，不要其他内容。

内容（第{page_num}页/共{total_pages}页）:
{preview}

总结:"""
        
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # 禁用推理模式，直接输出摘要
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一个精简的摘要生成器。只输出10-30字的中文摘要，不要任何其他内容。"},
                    {"role": "user", "content": prompt}
                ],
                "thinking": "disabled",  # 禁用推理模式
                "temperature": 0.3,
                "max_tokens": 50
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url, 
                    headers=headers, 
                    json=payload, 
                    timeout=aiohttp.ClientTimeout(total=15)  # 禁用推理后更快
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        # 直接提取 content，不管 reasoning_content
                        summary = result["choices"][0]["message"].get("content", "").strip()
                        if summary:
                            return summary[:30] if len(summary) > 30 else summary
                        else:
                            return self._simple_summary(content)
                    else:
                        return self._simple_summary(content)
                        
        except Exception as e:
            # 出错时使用简单摘要
            pass
        
        # 兜底：确保返回非空
        fallback = self._simple_summary(content)
        return fallback if fallback else f"第{page_num}页内容"
    
    def _simple_summary(self, content: str) -> str:
        """简单摘要（当 LLM 不可用时）"""
        if not content or not content.strip():
            return "(空页面)"
        
        # 提取有意义的内容作为摘要
        lines = content.strip().split('\n')
        candidates = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # 移除 Markdown 标记
                clean = re.sub(r'[#*_`\[\]\(\)]', '', line).strip()
                # 跳过太短的行（<5字符）和纯链接行
                if len(clean) >= 5 and not clean.startswith('http'):
                    candidates.append(clean)
        
        if candidates:
            # 选择第一个足够长的候选
            best = candidates[0]
            return best[:30] if len(best) > 30 else best
        
        # 如果没有候选，取前30个非空字符
        text = content.strip()[:50].replace('\n', ' ')
        return text[:30] if text else "(无内容)"
    
    def read_page(self, page_id: str) -> Dict[str, Any]:
        """
        读取指定页面的内容
        
        Args:
            page_id: 4位页面 ID
            
        Returns:
            页面内容
        """
        if page_id not in self.pages:
            return {
                "success": False,
                "error": f"页面 '{page_id}' 不存在。请先使用 load_url_content 加载网页。"
            }
        
        page_data = self.pages[page_id]
        
        return {
            "success": True,
            "page_id": page_id,
            "url": page_data["url"],
            "page_num": page_data["page_num"],
            "total_pages": page_data["total_pages"],
            "content": page_data["content"],
            "size": len(page_data["content"])
        }
    
    def get_loaded_urls(self) -> Dict[str, Any]:
        """获取已加载的 URL 列表（调试用）"""
        return {
            "urls": list(self.url_pages.keys()),
            "total_pages": len(self.pages)
        }
    
    def clear_cache(self) -> Dict[str, Any]:
        """清空缓存"""
        count = len(self.pages)
        self.pages.clear()
        self.url_pages.clear()
        # 不清空 used_ids，保证 ID 全局唯一
        return {
            "success": True,
            "cleared_pages": count
        }


# 测试代码
if __name__ == "__main__":
    async def test():
        # 创建实例
        web = WebTools(
            config={"search_engine": "duckduckgo", "max_results": 3},
            api_url="http://localhost:1234/v1/chat/completions",
            model="test"
        )
        
        print("=== 测试 search_web ===")
        result = await web.search_web("Python asyncio tutorial")
        print(f"搜索结果: {result}")
        
        if result["success"] and result["results"]:
            url = result["results"][0]["url"]
            print(f"\n=== 测试 load_url_content: {url} ===")
            load_result = await web.load_url_content(url)
            print(f"加载结果: {load_result}")
            
            if load_result["success"] and load_result["pages"]:
                page_id = load_result["pages"][0]["page_id"]
                print(f"\n=== 测试 read_page: {page_id} ===")
                page_result = web.read_page(page_id)
                print(f"页面内容前200字: {page_result.get('content', '')[:200]}")
    
    asyncio.run(test())
