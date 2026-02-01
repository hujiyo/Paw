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
        
        # 缓存搜索结果（避免频繁请求）
        self._search_cache: Dict[str, Any] = {}
        
        # 设置请求超时
        self.timeout = 30
    
    def search_skills(self, query: str = "", category: str = "", page: int = 1, 
                     use_ai_search: bool = False) -> Dict[str, Any]:
        """
        搜索 Skills
        
        Args:
            query: 搜索关键词
            category: 分类筛选
            page: 页码
            use_ai_search: 是否使用 AI 语义搜索
            
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
                "error": "error message if failed"
            }
        """
        # 检查缓存
        cache_key = f"{query}:{category}:{page}:{use_ai_search}"
        if cache_key in self._search_cache:
            return self._search_cache[cache_key]
        
        try:
            # 从 GitHub 获取
            result = self._fetch_from_github(query, category, page)
            
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
                "error": str(e)
            }
    
    def _fetch_from_github(self, query: str, category: str, page: int) -> Dict[str, Any]:
        """
        从 GitHub 多个源聚合 skills
        """
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'Paw-Skills-Browser'
            }
            
            all_skills = []
            
            # 源 1: anthropics/skills
            try:
                api_url = "https://api.github.com/repos/anthropics/skills/contents/skills"
                response = requests.get(api_url, headers=headers, timeout=10, verify=False)
                if response.status_code == 200:
                    data = response.json()
                    for item in data:
                        if item['type'] == 'dir':
                            all_skills.append({
                                'id': f"anthropics-{item['name']}",
                                'name': item['name'].replace('-', ' ').title(),
                                'description': f"Official skill: {item['name']}",
                                'category': 'official',
                                'repo_url': f"https://github.com/anthropics/skills/tree/main/skills/{item['name']}",
                                'stars': 0,
                                'author': 'anthropics'
                            })
            except:
                pass
            
            # 源 2: 直接搜索 GitHub 仓库
            if query or not all_skills:
                search_query = query if query else "claude skill SKILL.md"
                search_url = f"https://api.github.com/search/repositories?q={requests.utils.quote(search_query)}&sort=stars&per_page=20"
                try:
                    response = requests.get(search_url, headers=headers, timeout=10, verify=False)
                    if response.status_code == 200:
                        data = response.json()
                        for repo in data.get('items', []):
                            all_skills.append({
                                'id': repo['full_name'].replace('/', '-'),
                                'name': repo['name'].replace('-', ' ').title(),
                                'description': repo.get('description', '') or 'No description',
                                'category': 'community',
                                'repo_url': repo['html_url'],
                                'stars': repo.get('stargazers_count', 0),
                                'author': repo['owner']['login']
                            })
                except:
                    pass
            
            # 关键词过滤
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
                    'error': 'No skills found'
                }
            
            return {
                'success': True,
                'skills': all_skills,
                'total': len(all_skills),
                'page': page
            }
            
        except Exception as e:
            return {
                'success': False,
                'skills': [],
                'total': 0,
                'page': page,
                'error': str(e)
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
