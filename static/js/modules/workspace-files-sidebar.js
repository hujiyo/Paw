// 工作区文件目录侧边栏模块
// 覆盖层式侧边栏，不挤压AI聊天区
import { $ } from './utils.js';
import { escapeHtml } from './utils.js';
export class WorkspaceFilesSidebar {
    static init() {
        // 工作区文件目录侧边栏元素
        this.sidebar = $('#workspace-files-sidebar');
        this.treeContainer = $('#workspace-file-tree');
        this.toggleBtn = $('#toggle-workspace-files-sidebar');
        // 绑定事件
        this.toggleBtn?.addEventListener('click', () => this.toggle());
        $('#workspace-files-close-btn')?.addEventListener('click', () => this.hide());
        $('#workspace-files-refresh-btn')?.addEventListener('click', () => this.loadPath(this.currentPath));
        // 点击AI聊天区未被遮挡的部分关闭侧边栏
        const messagesWrapper = $('#messages-wrapper');
        const inputArea = $('.input-area');
        messagesWrapper?.addEventListener('click', (e) => {
            if (this.isVisible) {
                this.hide();
            }
        });
        inputArea?.addEventListener('click', (e) => {
            // 不在输入框内点击时关闭（输入框内点击不关闭）
            const target = e.target;
            if (this.isVisible && !target.closest('#input') && !target.closest('#send-btn')) {
                this.hide();
            }
        });
        // 键盘快捷键 Ctrl+Shift+E
        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'E') {
                e.preventDefault();
                this.toggle();
            }
        });
    }
    // 注册文件打开回调
    static onFileOpen(callback) {
        this.onFileOpenCallback = callback;
    }
    static show() {
        this.isVisible = true;
        this.sidebar?.classList.add('workspace-files-sidebar--visible');
        this.toggleBtn?.classList.add('toolbar__btn--active');
        // 首次打开时加载文件
        if (this.treeContainer && !this.treeContainer.innerHTML.trim()) {
            this.loadPath('.');
        }
    }
    static hide() {
        this.isVisible = false;
        this.sidebar?.classList.remove('workspace-files-sidebar--visible');
        this.toggleBtn?.classList.remove('toolbar__btn--active');
    }
    static toggle() {
        if (this.isVisible) {
            this.hide();
        }
        else {
            this.show();
        }
    }
    static setButtonVisible(visible) {
        if (this.toggleBtn) {
            this.toggleBtn.style.display = visible ? '' : 'none';
        }
    }
    static async loadPath(path) {
        try {
            const res = await fetch('/api/fs/list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path })
            });
            const data = await res.json();
            if (data.success) {
                this.currentPath = data.current_path;
                this.renderTree(data.items, data.parent_path);
            }
            else {
                console.error('Failed to load files:', data.error);
                this.treeContainer.innerHTML = `<div style="color:var(--error-color);padding:1rem">Error: ${escapeHtml(data.error)}</div>`;
            }
        }
        catch (e) {
            console.error('Error loading files:', e);
        }
    }
    static renderTree(items, parentPath) {
        let html = '';
        // Parent directory link
        if (parentPath && parentPath !== this.currentPath) {
            html += `<div class="file-tree__item file-tree__item--dir" data-path="${escapeHtml(parentPath)}">..</div>`;
        }
        if (items.length === 0) {
            html += `<div style="color:var(--text-secondary);padding:1rem;font-size:0.8rem">Empty directory</div>`;
        }
        else {
            items.forEach(item => {
                const icon = item.is_dir ? '📁' : '📄';
                const typeClass = item.is_dir ? 'file-tree__item--dir' : '';
                html += `
                    <div class="file-tree__item ${typeClass}" data-path="${escapeHtml(item.path)}" data-is-dir="${item.is_dir}" data-name="${escapeHtml(item.name)}">
                        <span class="file-icon">${icon}</span> ${escapeHtml(item.name)}
                    </div>
                `;
            });
        }
        this.treeContainer.innerHTML = html;
        // Bind events
        this.treeContainer.querySelectorAll('.file-tree__item').forEach(el => {
            el.addEventListener('click', (e) => {
                const target = e.currentTarget;
                const path = target.dataset.path;
                const isDir = target.dataset.isDir === 'true';
                const name = target.dataset.name || target.textContent?.trim() || 'file';
                if (target.textContent?.trim() === '..') {
                    this.loadPath(path);
                }
                else if (isDir) {
                    this.loadPath(path);
                }
                else {
                    // 点击文件：加载内容并通知右侧边栏打开标签页
                    this.openFileInEditor(path, name);
                }
            });
        });
    }
    // 在右侧边栏编辑器中打开文件
    static async openFileInEditor(path, name) {
        try {
            const res = await fetch('/api/fs/content', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path })
            });
            const data = await res.json();
            if (data.success) {
                // 调用回调，通知右侧边栏打开文件标签
                if (this.onFileOpenCallback) {
                    this.onFileOpenCallback(path, name, data.content);
                }
            }
            else {
                console.error('Failed to load file:', data.error);
            }
        }
        catch (e) {
            console.error('Error loading file:', e);
        }
    }
}
WorkspaceFilesSidebar.currentPath = '.';
WorkspaceFilesSidebar.isVisible = false;
WorkspaceFilesSidebar.onFileOpenCallback = null;
