// Skills 市场管理模块
import { $, $$ } from './utils.js';

interface Skill {
    id: string;
    name: string;
    description: string;
    category: string;
    repo_url: string;
    stars: number;
    author: string;
}

interface InstalledSkill {
    name: string;
    dir_name: string;
    description: string;
    path: string;
    has_scripts: boolean;
}

export const Skills = {
    // 当前视图：'market' | 'installed'
    currentView: 'market' as 'market' | 'installed',
    
    // 已安装的 skills（用于检查状态）
    installedSkills: new Set<string>(),
    
    // 界面是否可见
    isVisible: false,
    
    init(): void {
        this.bindEvents();
        this.loadInstalledSkills();
    },
    
    bindEvents(): void {
        // 工具栏打开/关闭按钮
        const openBtn = $<HTMLElement>('#skills-market-btn');
        const chatBtn = $<HTMLElement>('#chat-view-btn');
        
        if (openBtn) {
            openBtn.addEventListener('click', () => {
                this.show();
            });
        }
        
        if (chatBtn) {
            chatBtn.addEventListener('click', () => {
                this.hide();
            });
        }
        
        // Skills 子 tab 切换（市场/已安装）
        $$<HTMLElement>('.skills-market-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const view = tab.dataset.skillsView as 'market' | 'installed';
                this.switchView(view);
            });
        });
        
        // 搜索输入和按钮
        const searchInput = $<HTMLInputElement>('#skills-search-input');
        const categorySelect = $<HTMLSelectElement>('#skills-category-select');
        const searchBtn = $<HTMLButtonElement>('#skills-search-btn');
        
        if (searchInput && categorySelect && searchBtn) {
            const doSearch = () => {
                this.searchSkills(searchInput.value, categorySelect.value);
            };
            
            // 点击搜索按钮触发搜索
            searchBtn.addEventListener('click', doSearch);
            
            // 输入框回车也触发搜索
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    doSearch();
                }
            });
            
            // 初始搜索(显示所有)
            this.searchSkills('', '');
        }
    },
    
    show(): void {
        const view = $<HTMLElement>('#skills-market-view');
        const chatView = $<HTMLElement>('#chat-view');
        const skillsBtn = $<HTMLElement>('#skills-market-btn');
        const chatBtn = $<HTMLElement>('#chat-view-btn');

        if (view && chatView) {
            view.classList.add('skills-market-view--active');
            chatView.classList.remove('chat-view--active');
            
            if (skillsBtn) skillsBtn.classList.add('toolbar__btn--active');
            if (chatBtn) chatBtn.classList.remove('toolbar__btn--active');

            this.isVisible = true;
            // 打开时加载数据
            if (this.currentView === 'installed') {
                this.loadInstalledSkills();
            }
        }
    },
    
    hide(): void {
        const view = $<HTMLElement>('#skills-market-view');
        const chatView = $<HTMLElement>('#chat-view');
        const skillsBtn = $<HTMLElement>('#skills-market-btn');
        const chatBtn = $<HTMLElement>('#chat-view-btn');

        if (view && chatView) {
            view.classList.remove('skills-market-view--active');
            chatView.classList.add('chat-view--active');
            
            if (skillsBtn) skillsBtn.classList.remove('toolbar__btn--active');
            if (chatBtn) chatBtn.classList.add('toolbar__btn--active');

            this.isVisible = false;
        }
    },
    
    switchView(view: 'market' | 'installed'): void {
        this.currentView = view;
        
        // 更新 tab 样式
        $$<HTMLElement>('.skills-market-tab').forEach(tab => {
            const isActive = tab.dataset.skillsView === view;
            tab.classList.toggle('skills-market-tab--active', isActive);
        });
        
        // 切换视图
        const marketContent = $<HTMLElement>('#skills-market-content');
        const installedContent = $<HTMLElement>('#skills-installed-content');
        
        if (marketContent && installedContent) {
            marketContent.classList.toggle('skills-market-content--active', view === 'market');
            installedContent.classList.toggle('skills-market-content--active', view === 'installed');
        }
        
        // 加载对应数据
        if (view === 'installed') {
            this.loadInstalledSkills();
        }
    },
    
    async searchSkills(query: string, category: string): Promise<void> {
        const skillsList = $<HTMLElement>('#skills-list');
        if (!skillsList) return;
        
        // 显示加载状态
        skillsList.innerHTML = '<div class="skills-empty"><div class="skills-empty__text">搜索中...</div></div>';
        
        try {
            const params = new URLSearchParams();
            if (query) params.append('q', query);
            if (category) params.append('category', category);
            
            const response = await fetch(`/api/skills/search?${params}`);
            const data = await response.json();
            
            if (data.success && data.skills && data.skills.length > 0) {
                this.renderSkillsList(data.skills);
            } else {
                skillsList.innerHTML = `
                    <div class="skills-empty">
                        <div class="skills-empty__icon">🔍</div>
                        <div class="skills-empty__text">未找到匹配的 Skills</div>
                    </div>
                `;
            }
        } catch (error) {
            skillsList.innerHTML = `
                <div class="skills-empty">
                    <div class="skills-empty__icon">⚠️</div>
                    <div class="skills-empty__text">搜索失败: ${error}</div>
                </div>
            `;
        }
    },
    
    renderSkillsList(skills: Skill[]): void {
        const skillsList = $<HTMLElement>('#skills-list');
        if (!skillsList) return;
        
        skillsList.innerHTML = '';
        
        skills.forEach(skill => {
            const isInstalled = this.installedSkills.has(skill.name.toLowerCase()) || 
                               this.installedSkills.has(skill.id);
            
            const card = document.createElement('div');
            card.className = 'skill-card';
            
            card.innerHTML = `
                <div class="skill-card__header">
                    <div>
                        <div class="skill-card__title">${this.escapeHtml(skill.name)}</div>
                        <div class="skill-card__author">by ${this.escapeHtml(skill.author)}</div>
                    </div>
                    <div class="skill-card__stats">
                        <span>⭐ ${skill.stars}</span>
                    </div>
                </div>
                <div class="skill-card__description">${this.escapeHtml(skill.description)}</div>
                <div class="skill-card__footer">
                    <span class="skill-card__category">${this.escapeHtml(skill.category)}</span>
                    <button class="skill-card__install-btn ${isInstalled ? 'skill-card__install-btn--installed' : ''}" 
                            data-skill-id="${skill.id}" 
                            data-skill-name="${this.escapeHtml(skill.name)}"
                            data-repo-url="${this.escapeHtml(skill.repo_url)}"
                            ${isInstalled ? 'disabled' : ''}>
                        ${isInstalled ? '已安装' : '安装'}
                    </button>
                </div>
            `;
            
            // 安装按钮事件
            const installBtn = card.querySelector('.skill-card__install-btn') as HTMLButtonElement;
            if (installBtn && !isInstalled) {
                installBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.installSkill(skill.id, skill.name, skill.repo_url, installBtn);
                });
            }
            
            skillsList.appendChild(card);
        });
    },
    
    async installSkill(skillId: string, skillName: string, repoUrl: string, button: HTMLButtonElement): Promise<void> {
        // 更新按钮状态
        button.disabled = true;
        button.classList.add('skill-card__install-btn--installing');
        button.textContent = '安装中...';
        
        try {
            const response = await fetch('/api/skills/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    skill_id: skillId,
                    skill_name: skillName,
                    repo_url: repoUrl
                })
            });
            
            const result = await response.json();
            
            if (result.success) {
                button.classList.remove('skill-card__install-btn--installing');
                button.classList.add('skill-card__install-btn--installed');
                button.textContent = '已安装';
                
                // 更新已安装列表
                this.installedSkills.add(skillName.toLowerCase());
                
                // 显示成功提示
                this.showToast('✅ 安装成功！', 'success');
            } else {
                button.disabled = false;
                button.classList.remove('skill-card__install-btn--installing');
                button.textContent = '安装';
                
                this.showToast(`❌ 安装失败: ${result.message}`, 'error');
            }
        } catch (error) {
            button.disabled = false;
            button.classList.remove('skill-card__install-btn--installing');
            button.textContent = '安装';
            
            this.showToast(`❌ 安装失败: ${error}`, 'error');
        }
    },
    
    async loadInstalledSkills(): Promise<void> {
        try {
            const response = await fetch('/api/skills/installed');
            const data = await response.json();
            
            if (data.success && data.skills) {
                // 更新已安装集合
                this.installedSkills.clear();
                data.skills.forEach((skill: InstalledSkill) => {
                    this.installedSkills.add(skill.name.toLowerCase());
                    this.installedSkills.add(skill.dir_name.toLowerCase());
                });
                
                // 如果当前在已安装视图，渲染列表
                if (this.currentView === 'installed') {
                    this.renderInstalledList(data.skills);
                }
            }
        } catch (error) {
            console.error('Failed to load installed skills:', error);
        }
    },
    
    renderInstalledList(skills: InstalledSkill[]): void {
        const installedList = $<HTMLElement>('#installed-list');
        if (!installedList) return;
        
        if (skills.length === 0) {
            installedList.innerHTML = `
                <div class="skills-empty">
                    <div class="skills-empty__icon">💭</div>
                    <div class="skills-empty__text">暂未安装任何 Skill</div>
                </div>
            `;
            return;
        }
        
        installedList.innerHTML = '';
        
        skills.forEach(skill => {
            const card = document.createElement('div');
            card.className = 'installed-card';
            
            card.innerHTML = `
                <div class="installed-card__header">
                    <div class="installed-card__name">${this.escapeHtml(skill.name)}</div>
                </div>
                <div class="installed-card__description">${this.escapeHtml(skill.description || '无描述')}</div>
                <div class="installed-card__footer">
                    <div class="installed-card__path">${this.escapeHtml(skill.dir_name)}</div>
                    <button class="installed-card__uninstall-btn" data-skill-name="${this.escapeHtml(skill.dir_name)}">
                        卸载
                    </button>
                </div>
            `;
            
            // 卸载按钮事件
            const uninstallBtn = card.querySelector('.installed-card__uninstall-btn') as HTMLButtonElement;
            if (uninstallBtn) {
                uninstallBtn.addEventListener('click', () => {
                    this.uninstallSkill(skill.dir_name, card);
                });
            }
            
            installedList.appendChild(card);
        });
    },
    
    async uninstallSkill(skillName: string, cardElement: HTMLElement): Promise<void> {
        if (!confirm(`确定要卸载 "${skillName}" 吗？`)) {
            return;
        }
        
        try {
            const response = await fetch(`/api/skills/${encodeURIComponent(skillName)}`, {
                method: 'DELETE'
            });
            
            const result = await response.json();
            
            if (result.success) {
                // 从 DOM 移除卡片
                cardElement.remove();
                
                // 更新已安装集合
                this.installedSkills.delete(skillName.toLowerCase());
                
                this.showToast('✅ 卸载成功！', 'success');
                
                // 检查是否列表为空
                const installedList = $<HTMLElement>('#installed-list');
                if (installedList && installedList.children.length === 0) {
                    this.renderInstalledList([]);
                }
            } else {
                this.showToast(`❌ 卸载失败: ${result.message}`, 'error');
            }
        } catch (error) {
            this.showToast(`❌ 卸载失败: ${error}`, 'error');
        }
    },
    
    showToast(message: string, type: 'success' | 'error'): void {
        // 简单的 toast 提示（可以后续优化为更好的 UI）
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 12px 20px;
            background: ${type === 'success' ? '#10b981' : '#ef4444'};
            color: white;
            border-radius: 8px;
            font-size: 14px;
            z-index: 10000;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        `;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    },
    
    escapeHtml(text: string): string {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};
