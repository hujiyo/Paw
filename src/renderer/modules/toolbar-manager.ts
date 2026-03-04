// 工具栏管理模块

import { UIStateManager } from './ui-state.js';

export class ToolbarManager {
    private uiState: UIStateManager;
    private sidebar: HTMLElement;
    private sidebarRight: HTMLElement;
    private main: HTMLElement;
    private toggleSidebarBtn: HTMLElement;
    private toggleRightSidebarBtn: HTMLElement;
    private toggleWorkspaceFilesSidebarBtn: HTMLElement;
    private newChatToolbarBtn: HTMLElement;
    private toolbarDivider: HTMLElement;

    constructor(uiState: UIStateManager) {
        this.uiState = uiState;
        this.sidebar = document.querySelector('.sidebar')!;
        this.sidebarRight = document.getElementById('sidebar-right')!;
        this.main = document.querySelector('.main')!;
        this.toggleSidebarBtn = document.getElementById('toggle-sidebar')!;
        this.toggleRightSidebarBtn = document.getElementById('toggle-right-sidebar')!;
        this.toggleWorkspaceFilesSidebarBtn = document.getElementById('toggle-workspace-files-sidebar')!;
        this.newChatToolbarBtn = document.getElementById('new-chat-toolbar')!;
        this.toolbarDivider = document.getElementById('toolbar-divider')!;
    }

    init(): void {
        this.setupEventListeners();
        this.initSidebarState();
    }

    private setupEventListeners(): void {
        this.toggleSidebarBtn.addEventListener('click', () => {
            this.toggleSidebar();
        });

        this.toggleRightSidebarBtn.addEventListener('click', () => {
            this.toggleRightSidebar();
        });

        document.addEventListener('keydown', (e: KeyboardEvent) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
                e.preventDefault();
                this.toggleSidebar();
            }
            if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
                e.preventDefault();
                this.toggleRightSidebar();
            }
        });

        this.uiState.subscribe((key, value) => {
            if (key === 'sidebarVisible' || key === 'rightSidebarVisible') {
                this.updateToolbarVisibility();
            }
        });
    }

    private initSidebarState(): void {
        const sidebarVisible = this.uiState.get('sidebarVisible');
        const rightSidebarVisible = this.uiState.get('rightSidebarVisible');

        this.sidebar.classList.toggle('sidebar--hidden', !sidebarVisible);
        this.main.classList.toggle('main--full-width', !sidebarVisible);
        this.toggleSidebarBtn.classList.toggle('toolbar__btn--active', sidebarVisible);

        this.sidebarRight.classList.toggle('sidebar-right--visible', rightSidebarVisible);
        this.main.classList.toggle('main--with-right-sidebar', rightSidebarVisible);
        this.toggleRightSidebarBtn.classList.toggle('toolbar__btn--active', rightSidebarVisible);

        this.updateToolbarVisibility();
    }

    private toggleSidebar(): void {
        this.uiState.toggleSidebar();
        const visible = this.uiState.get('sidebarVisible');

        this.sidebar.classList.toggle('sidebar--hidden', !visible);
        this.main.classList.toggle('main--full-width', !visible);
        this.toggleSidebarBtn.classList.toggle('toolbar__btn--active', visible);
    }

    private toggleRightSidebar(): void {
        this.uiState.toggleRightSidebar();
        const visible = this.uiState.get('rightSidebarVisible');

        this.sidebarRight.classList.toggle('sidebar-right--visible', visible);
        this.main.classList.toggle('main--with-right-sidebar', visible);
        this.toggleRightSidebarBtn.classList.toggle('toolbar__btn--active', visible);
    }

    private updateToolbarVisibility(): void {
        const sidebarVisible = this.uiState.get('sidebarVisible');
        const rightSidebarVisible = this.uiState.get('rightSidebarVisible');

        this.toggleRightSidebarBtn.style.display = '';
        this.toggleSidebarBtn.style.display = '';
        this.newChatToolbarBtn.style.display = rightSidebarVisible ? 'none' : '';
        this.toolbarDivider.style.display = rightSidebarVisible ? 'none' : '';
        this.toggleWorkspaceFilesSidebarBtn.style.display = rightSidebarVisible ? '' : 'none';
    }
}
