#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SkillsMP 市场集成模块
负责与 SkillsMP.com API 交互，下载和管理 Skills
"""

import os
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests
from urllib.parse import urlparse

from lib.skills_index_interface import SkillsIndexHub, SkillsIndexEntry


class SkillMarketplace:
    """SkillsMP 市场管理器"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初始化市场管理器
        
        Args:
            api_key: SkillsMP API Key（可选，用于访问 API）
        """
        self.api_key = api_key or os.getenv('SKILLSMP_API_KEY', '')
        self.base_url = "https://skillsmp.com/api/v1"
        self.skills_dir = Path.home() / ".paw" / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        
        # 初始化 SkillsIndexHub（默认连接官方索引库）
        self.index_hub = SkillsIndexHub()
        self.index_hub.connect()
        
        # 缓存搜索结果（避免频繁请求）
        self._search_cache: Dict[str, Any] = {}
        
        # 索引仓库判断缓存（避免每次搜索都发HTTP请求）
        self._index_repo_cache: Dict[str, bool] = {}
        
        # 设置请求超时
        self.timeout = 30
    
    def search_skills(self, query: str = "", category: str = "", page: int = 1,
                     use_ai_search: bool = False, repo: str = "") -> Dict[str, Any]:
        """
        搜索 Skills

        Args:
            query: 搜索关键词
            category: 分类筛选
            page: 页码
            use_ai_search: 是否使用 AI 语义搜索
            repo: 指定仓库，格式 "owner/repo"，如 "anthropics/skills" 或 "hujiyo/vibe-coding"

        Returns:
            搜索结果字典，格式：
            {
                "success": True/False,
                "skills": [
                    {
                        "id": "skill-id",
                        "name": "skill-name",
                        "description": "...",
                        "category": "development",
                        "repo_url": "https://github.com/...",
                        "stars": 123,
                        "author": "username"
                    },
                    ...
                ],
                "total": 100,
                "page": 1,
                "current_repo": "hujiyo/skills-index",
                "is_index": False,  # 是否为索引仓库
                "error": "error message if failed"
            }
        """
        # 检查缓存
        cache_key = f"{repo}:{query}:{category}:{page}:{use_ai_search}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]

        try:
            # 检查是否为索引仓库（包含 "awesome" 或 "index" 关键词）
            target_repo = repo if repo else "hujiyo/skills-index"
            is_index = self._is_index_repository(target_repo)

            if is_index:
                # 解析索引仓库
                result = self._fetch_index_repository(target_repo, query, page)
            else:
                # 从 GitHub 获取普通仓库
                result = self._fetch_from_github(query, category, page, repo)

            # 缓存结果
            if result["success"]:
                self._search_cache[cache_key] = result

            return result

        except Exception as e:
            return {
                "success": False,
                "skills": [],
                "total": 0,
                "page": page,
                "current_repo": repo,
                "is_index": False,
                "error": str(e)
            }
    
    def _fetch_from_github(self, query: str, category: str, page: int, repo: str = "") -> Dict[str, Any]:
        """
        从指定 GitHub 仓库获取 skills

        递归遍历仓库目录，识别任何包含 SKILL.md（不区分大小写）的目录作为 skill 包

        Args:
            query: 搜索关键词（用于过滤 skills）
            category: 分类筛选
            page: 页码
            repo: 仓库路径 "owner/repo"，默认为 "hujiyo/skills-index"
        """
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'Paw-Skills-Browser'
            }

            # 使用指定的仓库，默认为 hujiyo/skills-index
            target_repo = repo if repo else "hujiyo/skills-index"

            # 验证仓库格式
            if '/' not in target_repo:
                return {
                    'success': False,
                    'skills': [],
                    'total': 0,
                    'page': page,
                    'current_repo': target_repo,
                    'is_index': False,
                    'error': f'Invalid repository format. Use "owner/repo" format like "hujiyo/skills-index"'
                }

            owner, repo_name = target_repo.split('/', 1)
            
            # 递归搜索包含 SKILL.md 的目录
            all_skills = self._find_skills_in_repo(owner, repo_name, headers)

            if not all_skills:
                return {
                    'success': False,
                    'skills': [],
                    'total': 0,
                    'page': page,
                    'current_repo': target_repo,
                    'is_index': False,
                    'error': f'Repository "{target_repo}" 中未找到任何包含 SKILL.md 的 skill 目录'
                }

            # 关键词过滤（在已有 skills 中搜索）
            if query:
                query_lower = query.lower()
                all_skills = [s for s in all_skills
                             if query_lower in s['name'].lower()
                             or query_lower in s['description'].lower()]

            if not all_skills:
                return {
                    'success': False,
                    'skills': [],
                    'total': 0,
                    'page': page,
                    'current_repo': target_repo,
                    'is_index': False,
                    'error': f'No skills found in repository "{target_repo}"' + (f' matching "{query}"' if query else '')
                }

            return {
                'success': True,
                'skills': all_skills,
                'total': len(all_skills),
                'page': page,
                'current_repo': target_repo,
                'is_index': False
            }

        except Exception as e:
            return {
                'success': False,
                'skills': [],
                'total': 0,
                'page': page,
                'current_repo': repo if repo else "hujiyo/skills-index",
                'is_index': False,
                'error': str(e)
            }

    def _find_skills_in_repo(self, owner: str, repo_name: str, headers: Dict[str, str], 
                             path: str = "", visited: Optional[set] = None) -> List[Dict[str, Any]]:
        """
        递归搜索仓库中包含 SKILL.md 的目录

        Args:
            owner: 仓库所有者
            repo_name: 仓库名称
            headers: HTTP 请求头
            path: 当前搜索路径（递归用）
            visited: 已访问路径集合（防循环）

        Returns:
            skill 包列表
        """
        if visited is None:
            visited = set()

        # 防止重复访问
        current_path = f"{owner}/{repo_name}/{path}"
        if current_path in visited:
            return []
        visited.add(current_path)

        skills = []
        api_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{path}"
        
        try:
            response = requests.get(api_url, headers=headers, timeout=10, verify=False)
            if response.status_code != 200:
                return skills

            items = response.json()
            if not isinstance(items, list):
                return skills

            # 先检查当前目录是否包含 SKILL.md
            has_skill_md = any(
                item['type'] == 'file' and item['name'].upper() == 'SKILL.MD'
                for item in items
            )

            # 如果当前目录有 SKILL.md，这是一个 skill 包
            if has_skill_md:
                skill_name = path.split('/')[-1] if path else repo_name
                # 使用 HEAD 指代默认分支（自动适配 main/master）
                skills.append({
                    'id': f"{owner}-{skill_name}",
                    'name': skill_name,
                    'description': f"Skill from {owner}/{repo_name}: {path or 'root'}",
                    'category': 'community',
                    'repo_url': f"https://github.com/{owner}/{repo_name}/tree/HEAD/{path}" if path else f"https://github.com/{owner}/{repo_name}",
                    'stars': 0,
                    'author': owner,
                    'path': path  # 保存路径用于下载
                })

            # 递归遍历子目录（但不再深入已经识别为 skill 包的目录）
            if not has_skill_md:
                for item in items:
                    if item['type'] == 'dir':
                        # 跳过隐藏目录和常见非 skill 目录
                        if item['name'].startswith('.') or item['name'] in ('node_modules', '__pycache__', '.git'):
                            continue
                        
                        sub_path = f"{path}/{item['name']}" if path else item['name']
                        sub_skills = self._find_skills_in_repo(owner, repo_name, headers, sub_path, visited)
                        skills.extend(sub_skills)

        except Exception:
            # 网络错误或权限问题，跳过此目录
            pass

        return skills

    def _is_index_repository(self, repo: str) -> bool:
        """
        判断是否为索引仓库

        优先使用缓存结果，然后检查仓库是否包含 skills-index.md 文件，
        网络失败时回退到仓库名称关键词判断。

        Args:
            repo: 仓库路径 "owner/repo" 或 "local"（本地索引）

        Returns:
            是否为索引仓库
        """
        # 检查是否为本地索引
        if repo.lower() == 'local' or repo.lower() == 'paw':
            return True

        # 检查缓存
        if repo in self._index_repo_cache:
            return self._index_repo_cache[repo]

        if '/' not in repo:
            self._index_repo_cache[repo] = False
            return False

        # 基于仓库名称的快速判断（作为后备）
        repo_name_lower = repo.split('/', 1)[1].lower()
        name_hints = ('index', 'awesome', 'registry', 'catalog', 'hub')
        name_suggests_index = any(hint in repo_name_lower for hint in name_hints)

        # 检查远程仓库是否包含 skills-index.md
        try:
            owner, repo_name = repo.split('/', 1)

            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'Paw-Skills-Browser'
            }

            # 尝试获取 skills-index.md 文件
            index_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/skills-index.md"
            response = requests.get(index_url, headers=headers, timeout=10, verify=False)

            is_index = response.status_code == 200
            self._index_repo_cache[repo] = is_index
            return is_index

        except Exception as e:
            # 网络失败时回退到名称判断
            print(f"[SkillMarketplace] _is_index_repository network check failed for '{repo}': {e}, falling back to name heuristic: {name_suggests_index}")
            self._index_repo_cache[repo] = name_suggests_index
            return name_suggests_index

    def _fetch_local_index(self, query: str, page: int) -> Dict[str, Any]:
        """
        从本地 skills-index.md 文件获取技能仓库列表

        Args:
            query: 搜索关键词
            page: 页码

        Returns:
            索引结果字典
        """
        try:
            # 获取项目根目录
            import os
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            index_file = os.path.join(root_dir, 'skills-index.md')

            if not os.path.exists(index_file):
                return {
                    'success': False,
                    'skills': [],
                    'total': 0,
                    'page': page,
                    'current_repo': 'local',
                    'is_index': True,
                    'error': '本地索引文件 skills-index.md 不存在'
                }

            # 读取索引文件
            with open(index_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            repositories = []
            in_index = False
            current_category: Optional[str] = None

            for line in lines:
                line = line.strip()

                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue

                line_lower = line.lower()

                # 检查起始标记
                if line_lower == '>start':
                    in_index = True
                    current_category = None
                    continue

                # 检查结束标记
                if line_lower == '>end':
                    break

                # 分类标记：~类别名
                if in_index and line.startswith('~'):
                    current_category = line[1:].strip() or '未分类'
                    continue

                # 解析仓库地址
                if in_index and '/' in line:
                    parts = line.split('/')
                    if len(parts) >= 2:
                        owner = parts[0]
                        repo_name = parts[1]

                        # 检查是否有自定义路径
                        custom_path = '/'.join(parts[2:]) if len(parts) > 2 else None

                        repo_path = f"{owner}/{repo_name}"
                        display_name = repo_path
                        if custom_path:
                            display_name = f"{repo_path} (/{custom_path})"

                        repositories.append({
                            'id': repo_path.replace('/', '-'),
                            'name': display_name,
                            'description': f"点击浏览 {owner} 的 {repo_name} 技能仓库",
                            'category': current_category or '索引条目',
                            'repo_url': f"https://github.com/{repo_path}",
                            'stars': 0,
                            'author': owner,
                            'is_repo_entry': True,
                            'repo_path': repo_path,
                            'custom_path': custom_path  # 保存自定义路径
                        })

            if not repositories:
                return {
                    'success': False,
                    'skills': [],
                    'total': 0,
                    'page': page,
                    'current_repo': 'local',
                    'is_index': True,
                    'error': '本地索引文件中没有找到任何仓库地址'
                }

            # 关键词过滤
            if query:
                query_lower = query.lower()
                repositories = [r for r in repositories
                              if query_lower in r['name'].lower()
                              or query_lower in r['description'].lower()
                              or query_lower in r['author'].lower()]

            return {
                'success': True,
                'skills': repositories,
                'total': len(repositories),
                'page': page,
                'current_repo': 'local',
                'is_index': True
            }

        except Exception as e:
            return {
                'success': False,
                'skills': [],
                'total': 0,
                'page': page,
                'current_repo': 'local',
                'is_index': True,
                'error': f'读取本地索引文件失败: {str(e)}'
            }

    def _fetch_index_repository(self, repo: str, query: str, page: int) -> Dict[str, Any]:
        """
        从索引仓库获取技能仓库列表

        使用 SkillsIndexHub 解析 skills-index.md 格式

        Args:
            repo: 索引仓库路径 "owner/repo" 或 "local"（本地索引）
            query: 搜索关键词
            page: 页码

        Returns:
            索引结果字典
        """
        # 如果是本地索引，使用本地文件
        if repo.lower() in ['local', 'paw']:
            return self._fetch_local_index(query, page)

        try:
            # 使用 SkillsIndexHub 连接并解析远程索引
            hub = SkillsIndexHub()
            
            # 构造源路径（支持 owner/repo 格式）
            if '/' in repo:
                hub.connect(repo)
            else:
                return {
                    'success': False,
                    'skills': [],
                    'total': 0,
                    'page': page,
                    'current_repo': repo,
                    'is_index': True,
                    'error': f'仓库格式错误: {repo}，请使用 "owner/repo" 格式'
                }

            # 获取所有条目
            entries = hub.list_entries()
            
            # 转换为前端需要的格式
            repositories = []
            for entry in entries:
                repo_path = entry['repository']
                owner = entry['owner']
                name = entry['name']
                subpath = entry.get('subpath')
                category = entry.get('category') or '索引条目'
                description = entry.get('description') or f"点击浏览 {owner} 的 {name} 技能仓库"
                
                display_name = repo_path
                if subpath:
                    display_name = f"{repo_path} (/{subpath})"

                repositories.append({
                    'id': repo_path.replace('/', '-'),
                    'name': display_name,
                    'description': description,
                    'category': category,
                    'repo_url': f"https://github.com/{repo_path}",
                    'stars': 0,
                    'author': owner,
                    'is_repo_entry': True,
                    'repo_path': repo_path,
                    'custom_path': subpath
                })

            if not repositories:
                return {
                    'success': False,
                    'skills': [],
                    'total': 0,
                    'page': page,
                    'current_repo': repo,
                    'is_index': True,
                    'error': f'索引仓库 "{repo}" 中没有找到任何仓库地址'
                }

            # 关键词过滤
            if query:
                query_lower = query.lower()
                repositories = [r for r in repositories
                              if query_lower in r['name'].lower()
                              or query_lower in r['description'].lower()
                              or query_lower in r['author'].lower()]

            return {
                'success': True,
                'skills': repositories,
                'total': len(repositories),
                'page': page,
                'current_repo': repo,
                'is_index': True
            }

        except Exception as e:
            return {
                'success': False,
                'skills': [],
                'total': 0,
                'page': page,
                'current_repo': repo,
                'is_index': True,
                'error': f'解析索引仓库失败: {str(e)}'
            }


    def download_skill(self, skill_id: str, skill_name: str, repo_url: str) -> Dict[str, Any]:
        """
        下载并安装 Skill
        
        Args:
            skill_id: Skill ID
            skill_name: Skill 名称（用作目录名）
            repo_url: GitHub 仓库 URL
            
        Returns:
            安装结果字典：
            {
                "success": True/False,
                "message": "success/error message",
                "skill_path": "/path/to/skill"
            }
        """
        try:
            # 检查是否已安装
            skill_path = self.skills_dir / skill_name
            if skill_path.exists():
                return {
                    "success": False,
                    "message": f"Skill '{skill_name}' already installed. Please uninstall first.",
                    "skill_path": str(skill_path)
                }
            
            # 解析 GitHub URL
            parsed = urlparse(repo_url)
            if 'github.com' not in parsed.netloc:
                return {
                    "success": False,
                    "message": "Only GitHub repositories are supported",
                    "skill_path": None
                }
            
            # 从 URL 提取 owner/repo 信息
            # 支持两种格式：
            # 1. https://github.com/owner/repo
            # 2. https://github.com/owner/repo/tree/branch/path/to/skill
            path_parts = parsed.path.strip('/').split('/')
            if len(path_parts) < 2:
                return {
                    "success": False,
                    "message": "Invalid GitHub URL format",
                    "skill_path": None
                }
            
            owner = path_parts[0]
            repo = path_parts[1]
            
            # 判断是否是子目录 skill
            is_subdir = len(path_parts) > 2 and path_parts[2] == 'tree'
            subdir_path = '/'.join(path_parts[4:]) if is_subdir else None
            
            # 下载 ZIP
            zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
            result = self._download_from_github(zip_url, skill_name, subdir_path)
            
            if not result["success"]:
                # 尝试 master 分支
                zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/master.zip"
                result = self._download_from_github(zip_url, skill_name, subdir_path)
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to download skill: {str(e)}",
                "skill_path": None
            }
    
    def _download_from_github(self, zip_url: str, skill_name: str, 
                            subdir_path: Optional[str]) -> Dict[str, Any]:
        """
        从 GitHub 下载 ZIP 并解压
        
        Args:
            zip_url: ZIP 下载 URL
            skill_name: Skill 名称
            subdir_path: 子目录路径（如果 skill 在 repo 子目录中）
            
        Returns:
            操作结果字典
        """
        try:
            # 下载 ZIP
            response = requests.get(zip_url, timeout=30)
            response.raise_for_status()
            
            # 创建临时目录
            with tempfile.TemporaryDirectory() as temp_dir:
                zip_path = Path(temp_dir) / "skill.zip"
                zip_path.write_bytes(response.content)
                
                # 解压
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # 找到解压后的根目录（通常是 repo-name-branch）
                extracted_dirs = [d for d in Path(temp_dir).iterdir() if d.is_dir()]
                if not extracted_dirs:
                    return {
                        "success": False,
                        "message": "Failed to extract ZIP file",
                        "skill_path": None
                    }
                
                extracted_root = extracted_dirs[0]
                
                # 确定 skill 源目录
                if subdir_path:
                    skill_source = extracted_root / subdir_path
                else:
                    skill_source = extracted_root
                
                if not skill_source.exists():
                    return {
                        "success": False,
                        "message": f"Skill directory not found: {subdir_path or 'root'}",
                        "skill_path": None
                    }
                
                # 验证 SKILL.md 存在
                skill_md = skill_source / "SKILL.md"
                if not skill_md.exists():
                    return {
                        "success": False,
                        "message": "SKILL.md not found in the downloaded content",
                        "skill_path": None
                    }
                
                # 复制到目标目录
                skill_path = self.skills_dir / skill_name
                shutil.copytree(skill_source, skill_path)
                
                return {
                    "success": True,
                    "message": f"Successfully installed skill '{skill_name}'",
                    "skill_path": str(skill_path)
                }
                
        except requests.RequestException as e:
            return {
                "success": False,
                "message": f"Network error: {str(e)}",
                "skill_path": None
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Installation error: {str(e)}",
                "skill_path": None
            }
    
    def list_installed_skills(self) -> Dict[str, Any]:
        """
        列出已安装的 Skills
        
        Returns:
            已安装 Skills 列表：
            {
                "success": True,
                "skills": [
                    {
                        "name": "skill-name",
                        "path": "/path/to/skill",
                        "has_scripts": True/False
                    },
                    ...
                ]
            }
        """
        try:
            if not self.skills_dir.exists():
                return {"success": True, "skills": []}
            
            skills = []
            for skill_dir in self.skills_dir.iterdir():
                if not skill_dir.is_dir():
                    continue
                
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.exists():
                    continue
                
                # 检查是否有 scripts 目录
                scripts_dir = skill_dir / "scripts"
                has_scripts = scripts_dir.exists() and scripts_dir.is_dir()
                
                # 尝试读取 skill 名称和描述
                name = skill_dir.name
                description = ""
                try:
                    content = skill_md.read_text(encoding='utf-8')
                    # 简单解析 YAML frontmatter
                    if content.startswith('---'):
                        parts = content.split('---', 2)
                        if len(parts) >= 3:
                            import yaml
                            metadata = yaml.safe_load(parts[1])
                            if isinstance(metadata, dict):
                                name = metadata.get('name', name)
                                description = metadata.get('description', '')
                except Exception:
                    pass
                
                skills.append({
                    "name": name,
                    "dir_name": skill_dir.name,
                    "description": description,
                    "path": str(skill_dir),
                    "has_scripts": has_scripts
                })
            
            return {"success": True, "skills": skills}
            
        except Exception as e:
            return {
                "success": False,
                "skills": [],
                "error": str(e)
            }
    
    def uninstall_skill(self, skill_name: str) -> Dict[str, Any]:
        """
        卸载 Skill
        
        Args:
            skill_name: Skill 目录名称
            
        Returns:
            卸载结果字典
        """
        try:
            skill_path = self.skills_dir / skill_name
            if not skill_path.exists():
                return {
                    "success": False,
                    "message": f"Skill '{skill_name}' not found"
                }
            
            # 删除目录
            shutil.rmtree(skill_path)
            
            return {
                "success": True,
                "message": f"Successfully uninstalled skill '{skill_name}'"
            }
            
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to uninstall skill: {str(e)}"
            }
