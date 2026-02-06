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
    is_repo_entry?: boolean;
    repo_path?: string;
}

interface InstalledSkill {
    name: string;
    dir_name: string;
    description: string;
    path: string;
    has_scripts: boolean;
}

// 默认索引库
const DEFAULT_INDEX = 'hujiyo/skills-index';

export const Skills = {
    currentView: 'market' as 'market' | 'installed',
    installedSkills: new Set<string>(),
    isVisible: false,
    currentRepo: DEFAULT_INDEX,
    // 仓库导航栈：支持返回
    repoStack: [DEFAULT_INDEX] as string[],

    init(): void {
        this.bindEvents();
        setTimeout(() => this.loadInstalledSkills(), 150);
    },

    bindEvents(): void {
        // 子标签切换（市场/已安装）
        $$<HTMLElement>('.skills-subtab').forEach(tab => {
            tab.addEventListener('click', () => {
                const view = tab.dataset.skillsView as 'market' | 'installed';
                this.switchView(view);
            });
        });

        // 仓库地址输入框：回车前往
        const repoInput = $<HTMLInputElement>('#skills-repo-input');
        if (repoInput) {
            repoInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    const repo = repoInput.value.trim();
                    if (repo) this.switchRepository(repo);
                }
            });
        }

        // 前往按钮
        const goBtn = $<HTMLElement>('#skills-repo-go-btn');
        if (goBtn) {
            goBtn.addEventListener('click', () => {
                const input = $<HTMLInputElement>('#skills-repo-input');
                if (input) {
                    const repo = input.value.trim();
                    if (repo) this.switchRepository(repo);
                }
            });
        }

        // 搜索输入（仅关键词搜索）
        const searchInput = $<HTMLInputElement>('#skills-search-input');
        if (searchInput) {
            let debounceTimer: ReturnType<typeof setTimeout>;
            searchInput.addEventListener('input', () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    this.searchSkills(searchInput.value, '');
                }, 300);
            });
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    clearTimeout(debounceTimer);
                    this.searchSkills(searchInput.value, '');
                }
            });
        }

        // 返回按钮
        const backBtn = $<HTMLElement>('#skills-back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => this.navigateBack());
        }

        // 面包屑点击
        const breadcrumb = $<HTMLElement>('#skills-breadcrumb');
        if (breadcrumb) {
            breadcrumb.addEventListener('click', (e) => {
                const item = (e.target as HTMLElement).closest('.skills-breadcrumb__item') as HTMLElement | null;
                if (item && item.dataset.repo) {
                    this.navigateToRepo(item.dataset.repo);
                }
            });
        }

        // 初始加载默认索引仓库
        setTimeout(() => this.searchSkills('', ''), 100);
    },

    show(): void {
        const view = $<HTMLElement>('#skills-market-view');
        const chatView = $<HTMLElement>('#chat-view');
        if (view && chatView) {
            view.classList.add('skills-market-view--active');
            chatView.classList.remove('chat-view--active');
            this.isVisible = true;

            // 每次进入 skills 界面，重置为默认索引仓库
            this.currentRepo = DEFAULT_INDEX;
            this.repoStack = [DEFAULT_INDEX];
            this.updateBreadcrumb();
            this.updateRepoInput();
            this.clearSearch();
            this.switchView('market');
            this.searchSkills('', '');
        }
    },

    hide(): void {
        const view = $<HTMLElement>('#skills-market-view');
        const chatView = $<HTMLElement>('#chat-view');
        if (view && chatView) {
            view.classList.remove('skills-market-view--active');
            chatView.classList.add('chat-view--active');
            this.isVisible = false;
        }
    },

    switchView(view: 'market' | 'installed'): void {
        this.currentView = view;
        $$<HTMLElement>('.skills-subtab').forEach(tab => {
            tab.classList.toggle('skills-subtab--active', tab.dataset.skillsView === view);
        });
        const marketContent = $<HTMLElement>('#skills-market-content');
        const installedContent = $<HTMLElement>('#skills-installed-content');
        if (marketContent && installedContent) {
            marketContent.classList.toggle('skills-market-content--active', view === 'market');
            installedContent.classList.toggle('skills-market-content--active', view === 'installed');
        }
        if (view === 'installed') {
            this.loadInstalledSkills();
        }
    },

    // 更新面包屑导航
    updateBreadcrumb(): void {
        const breadcrumb = $<HTMLElement>('#skills-breadcrumb');
        const backBtn = $<HTMLElement>('#skills-back-btn');
        if (!breadcrumb) return;

        const stack = this.repoStack;
        breadcrumb.innerHTML = '';

        stack.forEach((repo, i) => {
            if (i > 0) {
                const sep = document.createElement('span');
                sep.className = 'skills-breadcrumb__sep';
                sep.textContent = '>';
                breadcrumb.appendChild(sep);
            }
            const item = document.createElement('span');
            item.className = 'skills-breadcrumb__item';
            if (i === stack.length - 1) {
                item.classList.add('skills-breadcrumb__item--active');
            }
            item.textContent = repo;
            item.dataset.repo = repo;
            breadcrumb.appendChild(item);
        });

        // 显示/隐藏返回按钮
        if (backBtn) {
            backBtn.style.display = stack.length > 1 ? '' : 'none';
        }
    },

    navigateBack(): void {
        if (this.repoStack.length <= 1) return;
        this.repoStack.pop();
        this.currentRepo = this.repoStack[this.repoStack.length - 1];
        this.updateBreadcrumb();
        this.updateRepoInput();
        this.clearSearch();
        this.searchSkills('', '');
    },

    navigateToRepo(repo: string): void {
        // 找到该 repo 在栈中的位置，截断到那里
        const idx = this.repoStack.indexOf(repo);
        if (idx >= 0) {
            this.repoStack = this.repoStack.slice(0, idx + 1);
        }
        this.currentRepo = repo;
        this.updateBreadcrumb();
        this.updateRepoInput();
        this.clearSearch();
        this.searchSkills('', '');
    },

    switchRepository(repo: string): void {
        if (!repo || !repo.includes('/')) {
            this.showToast('仓库格式错误，请使用 "owner/repo" 格式', 'error');
            return;
        }
        // 如果和当前仓库相同，只刷新不重复推栈
        if (repo !== this.currentRepo) {
            this.currentRepo = repo;
            this.repoStack.push(repo);
            this.updateBreadcrumb();
        }
        this.updateRepoInput();
        this.clearSearch();
        this.searchSkills('', '');
    },

    updateRepoInput(): void {
        const repoInput = $<HTMLInputElement>('#skills-repo-input');
        if (repoInput) repoInput.value = this.currentRepo;
    },

    clearSearch(): void {
        const searchInput = $<HTMLInputElement>('#skills-search-input');
        if (searchInput) searchInput.value = '';
    },

    async searchSkills(query: string, category: string): Promise<void> {
        const skillsList = $<HTMLElement>('#skills-list');
        if (!skillsList) return;

        skillsList.innerHTML = '<div class="skills-empty"><div class="skills-empty__text">搜索中...</div></div>';

        try {
            const params = new URLSearchParams();
            if (query) params.append('q', query);
            if (category) params.append('category', category);
            if (this.currentRepo) params.append('repo', this.currentRepo);

            const response = await fetch(`/api/skills/search?${params}`);
            const data = await response.json();

            if (data.current_repo && data.current_repo !== this.currentRepo) {
                this.currentRepo = data.current_repo;
                this.repoStack[this.repoStack.length - 1] = data.current_repo;
                this.updateBreadcrumb();
            }

            if (data.success && data.skills && data.skills.length > 0) {
                if (data.is_index) {
                    this.renderIndexList(data.skills);
                } else {
                    this.renderSkillsList(data.skills);
                }
            } else {
                const errorMsg = data.error || '未找到匹配的 Skills';
                skillsList.innerHTML = `
                    <div class="skills-empty">
                        <div class="skills-empty__icon">
                            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                        </div>
                        <div class="skills-empty__text">${this.escapeHtml(errorMsg)}</div>
                    </div>
                `;
            }
        } catch (error) {
            skillsList.innerHTML = `
                <div class="skills-empty">
                    <div class="skills-empty__icon">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                    </div>
                    <div class="skills-empty__text">加载失败: ${error}</div>
                </div>
            `;
        }
    },

    renderIndexList(repos: Skill[]): void {
        const skillsList = $<HTMLElement>('#skills-list');
        if (!skillsList) return;
        skillsList.innerHTML = '';

        repos.forEach(repo => {
            const card = document.createElement('div');
            card.className = 'skill-card skill-card--index';
            const repoPath = repo.repo_path || repo.author + '/' + repo.name;

            card.innerHTML = `
                <div class="skill-card__header">
                    <div class="skill-card__title">${this.escapeHtml(repo.name)}</div>
                    <div class="skill-card__description">${this.escapeHtml(repo.description)}</div>
                    <div class="skill-card__author">${this.escapeHtml(repo.author)}</div>
                </div>
                <div class="skill-card__footer">
                    <span class="skill-card__category skill-card__category--index">${this.escapeHtml(repo.category)}</span>
                    <button class="skill-card__install-btn skill-card__install-btn--navigate" data-repo-path="${this.escapeHtml(repoPath)}">
                        浏览 →
                    </button>
                </div>
            `;

            const navigateBtn = card.querySelector('.skill-card__install-btn--navigate') as HTMLButtonElement;
            if (navigateBtn) {
                navigateBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const path = navigateBtn.dataset.repoPath;
                    if (path) this.switchRepository(path);
                });
            }
            // 整个卡片也可点击
            card.addEventListener('click', () => this.switchRepository(repoPath));

            skillsList.appendChild(card);
        });
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
                    <div class="skill-card__title">${this.escapeHtml(skill.name)}</div>
                    <div class="skill-card__description">${this.escapeHtml(skill.description)}</div>
                    <div class="skill-card__author">by ${this.escapeHtml(skill.author)} · ⭐ ${skill.stars}</div>
                </div>
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
        button.disabled = true;
        button.classList.add('skill-card__install-btn--installing');
        button.textContent = '安装中...';

        try {
            const response = await fetch('/api/skills/install', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ skill_id: skillId, skill_name: skillName, repo_url: repoUrl })
            });
            const result = await response.json();

            if (result.success) {
                button.classList.remove('skill-card__install-btn--installing');
                button.classList.add('skill-card__install-btn--installed');
                button.textContent = '已安装';
                this.installedSkills.add(skillName.toLowerCase());
                this.showToast('安装成功', 'success');
            } else {
                button.disabled = false;
                button.classList.remove('skill-card__install-btn--installing');
                button.textContent = '安装';
                this.showToast(`安装失败: ${result.message}`, 'error');
            }
        } catch (error) {
            button.disabled = false;
            button.classList.remove('skill-card__install-btn--installing');
            button.textContent = '安装';
            this.showToast(`安装失败: ${error}`, 'error');
        }
    },

    async loadInstalledSkills(): Promise<void> {
        try {
            const response = await fetch('/api/skills/installed');
            const data = await response.json();
            if (data.success && data.skills) {
                this.installedSkills.clear();
                data.skills.forEach((skill: InstalledSkill) => {
                    this.installedSkills.add(skill.name.toLowerCase());
                    this.installedSkills.add(skill.dir_name.toLowerCase());
                });
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
                    <div class="skills-empty__icon">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
                    </div>
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
                    <div class="installed-card__description">${this.escapeHtml(skill.description || '无描述')}</div>
                </div>
                <div class="installed-card__footer">
                    <div class="installed-card__path">${this.escapeHtml(skill.dir_name)}</div>
                    <button class="installed-card__uninstall-btn" data-skill-name="${this.escapeHtml(skill.dir_name)}">卸载</button>
                </div>
            `;

            const uninstallBtn = card.querySelector('.installed-card__uninstall-btn') as HTMLButtonElement;
            if (uninstallBtn) {
                uninstallBtn.addEventListener('click', () => this.uninstallSkill(skill.dir_name, card));
            }
            installedList.appendChild(card);
        });
    },

    async uninstallSkill(skillName: string, cardElement: HTMLElement): Promise<void> {
        if (!confirm(`确定要卸载 "${skillName}" 吗？`)) return;

        try {
            const response = await fetch(`/api/skills/${encodeURIComponent(skillName)}`, { method: 'DELETE' });
            const result = await response.json();

            if (result.success) {
                cardElement.remove();
                this.installedSkills.delete(skillName.toLowerCase());
                this.showToast('卸载成功', 'success');
                const installedList = $<HTMLElement>('#installed-list');
                if (installedList && installedList.children.length === 0) {
                    this.renderInstalledList([]);
                }
            } else {
                this.showToast(`卸载失败: ${result.message}`, 'error');
            }
        } catch (error) {
            this.showToast(`卸载失败: ${error}`, 'error');
        }
    },

    showToast(message: string, type: 'success' | 'error'): void {
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 16px;
            background: ${type === 'success' ? 'var(--accent-assistant, #10b981)' : 'var(--error-color, #ef4444)'};
            color: white;
            border-radius: 8px;
            font-size: 13px;
            z-index: 10000;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            transition: opacity 0.3s;
        `;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(() => {
            toast.style.opacity = '0';
            setTimeout(() => toast.remove(), 300);
        }, 2500);
    },

    escapeHtml(text: string): string {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
};
