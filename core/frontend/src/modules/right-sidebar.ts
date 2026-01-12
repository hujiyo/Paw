
import { $, $$ } from './utils.js';
import { AppState } from './store.js';
import { escapeHtml } from './utils.js';
import { Browser } from './browser.js';

interface FileTab {
    id: string;      // 唯一标识（使用文件路径的 hash）
    path: string;    // 文件路径
    name: string;    // 文件名
    content: string; // 文件内容
}

export class RightSidebar {
    private static tabsContainer: HTMLElement;
    private static panelsContainer: HTMLElement;
    private static fileTabs: Map<string, FileTab> = new Map();
    private static activeTabId: string = 'terminal';
    
    static init() {
        this.tabsContainer = $('#editor-tabs')!;
        this.panelsContainer = $('#editor-panels')!;
        
        // 绑定常驻标签页点击事件
        this.tabsContainer?.addEventListener('click', (e) => {
            const target = e.target as HTMLElement;
            const tab = target.closest('.editor-tab') as HTMLElement;
            const closeBtn = target.closest('.editor-tab__close') as HTMLElement;
            
            if (closeBtn && tab) {
                // 点击关闭按钮
                e.stopPropagation();
                const tabId = tab.dataset.tabId;
                if (tabId && tab.dataset.pinned !== 'true') {
                    this.closeFileTab(tabId);
                }
            } else if (tab) {
                // 点击标签页
                const tabId = tab.dataset.tabId;
                if (tabId) {
                    this.switchToTab(tabId);
                }
            }
        });
        
        // Load saved state or default
        const savedTab = localStorage.getItem('paw-right-sidebar-tab') || 'terminal';
        this.switchToTab(savedTab);
    }
    
    // 切换到指定标签页
    static switchToTab(tabId: string) {
        this.activeTabId = tabId;
        
        // 更新所有标签页的激活状态
        this.tabsContainer?.querySelectorAll('.editor-tab').forEach(tab => {
            const el = tab as HTMLElement;
            el.classList.toggle('editor-tab--active', el.dataset.tabId === tabId);
        });
        
        // 更新所有面板的显示状态
        this.panelsContainer?.querySelectorAll('.editor-panel').forEach(panel => {
            const el = panel as HTMLElement;
            el.classList.toggle('editor-panel--active', el.id === `panel-${tabId}`);
        });

        // 切换到 Web 标签页时，主动刷新内容
        if (tabId === 'browser') {
            Browser.refresh();
        }
        
        // 保存状态（只保存常驻标签页）
        if (['terminal', 'plan', 'browser'].includes(tabId)) {
            localStorage.setItem('paw-right-sidebar-tab', tabId);
        }
        
        // 确保右侧边栏可见
        if (!AppState.rightSidebarVisible) {
            $<HTMLElement>('#toggle-right-sidebar')?.click();
        }
    }
    
    // 兼容旧版 switchView 方法
    static switchView(viewName: string) {
        // 映射旧的 view 名称到新的 tab id
        const tabMap: Record<string, string> = {
            'terminal': 'terminal',
            'plan': 'plan',
            'browser': 'browser',
            'files': 'terminal' // files 视图已移除，默认切换到 terminal
        };
        this.switchToTab(tabMap[viewName] || viewName);
    }
    
    // 打开文件标签页
    static openFileTab(path: string, name: string, content: string) {
        // 生成唯一 ID
        const tabId = 'file-' + this.hashCode(path);
        
        // 如果已存在，直接切换
        if (this.fileTabs.has(tabId)) {
            this.switchToTab(tabId);
            return;
        }
        
        // 创建新标签页
        const fileTab: FileTab = { id: tabId, path, name, content };
        this.fileTabs.set(tabId, fileTab);
        
        // 创建标签页 DOM
        const tabEl = document.createElement('div');
        tabEl.className = 'editor-tab';
        tabEl.dataset.tabId = tabId;
        tabEl.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>
                <polyline points="13 2 13 9 20 9"></polyline>
            </svg>
            <span class="editor-tab__title" title="${escapeHtml(path)}">${escapeHtml(name)}</span>
            <span class="editor-tab__close">×</span>
        `;
        this.tabsContainer?.appendChild(tabEl);
        
        // 创建内容面板 DOM
        const panelEl = document.createElement('div');
        panelEl.className = 'editor-panel editor-panel--file';
        panelEl.id = `panel-${tabId}`;
        panelEl.innerHTML = `
            <div class="file-panel-header">
                <div>
                    <span class="file-panel-name">${escapeHtml(name)}</span>
                    <span class="file-panel-path">${escapeHtml(path)}</span>
                </div>
            </div>
            <pre><code id="code-${tabId}"></code></pre>
        `;
        this.panelsContainer?.appendChild(panelEl);
        
        // 填充内容并高亮
        const codeEl = panelEl.querySelector(`#code-${tabId}`);
        if (codeEl) {
            codeEl.textContent = content;
            if ((window as any).hljs) {
                (window as any).hljs.highlightElement(codeEl);
            }
        }
        
        // 切换到新标签页
        this.switchToTab(tabId);
    }
    
    // 关闭文件标签页
    static closeFileTab(tabId: string) {
        if (!this.fileTabs.has(tabId)) return;
        
        // 删除数据
        this.fileTabs.delete(tabId);
        
        // 删除 DOM
        this.tabsContainer?.querySelector(`[data-tab-id="${tabId}"]`)?.remove();
        this.panelsContainer?.querySelector(`#panel-${tabId}`)?.remove();
        
        // 如果关闭的是当前标签页，切换到其他标签
        if (this.activeTabId === tabId) {
            // 优先切换到其他文件标签，否则切换到 terminal
            const nextFileTab = this.fileTabs.keys().next().value;
            this.switchToTab(nextFileTab || 'terminal');
        }
    }
    
    // 简单的字符串 hash 函数
    private static hashCode(str: string): string {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash).toString(36);
    }
}
