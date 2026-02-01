// 新建对话配置模块
import { $ } from './utils.js';
import { Settings } from './settings.js';
export const NewChatDialog = {
    view: null,
    send: null,
    init(sendFn) {
        this.send = sendFn;
        this.view = $('#new-chat-view');
        if (!this.view) {
            console.warn('[NewChatDialog] 未找到配置界面元素');
            return;
        }
        // 绑定关闭事件
        $('#new-chat-close-btn')?.addEventListener('click', () => this.close());
        $('#new-chat-cancel-btn')?.addEventListener('click', () => this.close());
        // 绑定浏览按钮
        $('#new-chat-browse-btn')?.addEventListener('click', async () => {
            if (window.electronAPI) {
                // Electron 环境
                const path = await window.electronAPI.selectFolder();
                if (path) {
                    this.handleBrowseResult(path);
                }
            }
            else {
                // Web 环境 (降级)
                const input = $('#new-chat-workspace');
                if (input) {
                    input.focus();
                    Settings.showToast('Web模式下请手动输入路径', 'error');
                }
            }
        });
        // 绑定创建按钮
        $('#new-chat-create-btn')?.addEventListener('click', () => {
            const workspace = $('#new-chat-workspace')?.value.trim();
            const title = $('#new-chat-title')?.value.trim();
            const model = $('#new-chat-model')?.value;
            const systemPrompt = $('#new-chat-system-prompt')?.value.trim();
            if (!workspace) {
                Settings.showToast('请输入工作区目录', 'error');
                return;
            }
            // 添加到最近列表
            this.addRecentWorkspace(workspace);
            // 发送创建请求
            if (this.send) {
                this.send(JSON.stringify({
                    type: 'create_new_chat',
                    workspace_dir: workspace,
                    title: title,
                    model: model,
                    system_prompt: systemPrompt
                }));
            }
            this.close();
        });
        // 初始化模型下拉 (复用 Settings 的逻辑)
        Settings.setupDropdown({
            containerId: 'new-chat-model-select',
            triggerId: 'new-chat-model-trigger',
            dropdownId: 'new-chat-model-dropdown',
            valueDisplayId: 'new-chat-model-value',
            hiddenInputId: 'new-chat-model',
            manualInputId: 'new-chat-model-input',
            addBtnId: 'new-chat-model-add',
            loadingId: 'new-chat-model-loading',
            errorId: 'new-chat-model-error',
            fetchConfig: () => ({
                key: ($('#cfg-api-key')?.value || '').trim(),
                url: ($('#cfg-api-url')?.value || '').trim()
            })
        });
    },
    async open() {
        if (!this.view)
            return;
        // 重置表单
        const workspaceInput = $('#new-chat-workspace');
        const titleInput = $('#new-chat-title');
        const modelInput = $('#new-chat-model');
        const modelDisplay = $('#new-chat-model-value');
        if (workspaceInput) {
            // 默认值优先级：最近使用 > 全局 Home 目录 > ~
            const recents = this.getRecents();
            if (recents.length > 0) {
                workspaceInput.value = recents[0].path;
            }
            else {
                // 尝试从全局配置获取 home_dir
                try {
                    const response = await fetch('/api/config');
                    const result = await response.json();
                    if (result.success && result.config?.system?.home_dir) {
                        workspaceInput.value = result.config.system.home_dir;
                    }
                    else {
                        workspaceInput.value = '~';
                    }
                }
                catch {
                    workspaceInput.value = '~';
                }
            }
        }
        if (titleInput)
            titleInput.value = '';
        if (modelInput)
            modelInput.value = '';
        if (modelDisplay) {
            modelDisplay.textContent = '使用全局默认';
            modelDisplay.classList.add('model-select__value--placeholder');
        }
        // 清空系统提示词
        const systemPromptInput = $('#new-chat-system-prompt');
        if (systemPromptInput)
            systemPromptInput.value = '';
        // 渲染最近列表
        this.renderRecents();
        this.view.classList.add('new-chat-view--visible');
    },
    close() {
        if (this.view) {
            this.view.classList.remove('new-chat-view--visible');
        }
    },
    handleBrowseResult(path) {
        const input = $('#new-chat-workspace');
        if (input) {
            input.value = path;
        }
    },
    // --- 最近工作区管理 ---
    getRecents() {
        try {
            const json = localStorage.getItem('paw_recent_workspaces');
            return json ? JSON.parse(json) : [];
        }
        catch {
            return [];
        }
    },
    addRecentWorkspace(path) {
        let recents = this.getRecents();
        // 移除已存在的同名项
        recents = recents.filter(r => r.path !== path);
        // 添加到头部
        recents.unshift({ path, lastUsed: Date.now() });
        // 限制数量
        if (recents.length > 5)
            recents = recents.slice(0, 5);
        localStorage.setItem('paw_recent_workspaces', JSON.stringify(recents));
    },
    renderRecents() {
        const list = $('#recent-workspaces-list');
        const container = $('#recent-workspaces');
        if (!list || !container)
            return;
        const recents = this.getRecents();
        if (recents.length === 0) {
            container.style.display = 'none';
            return;
        }
        container.style.display = 'block';
        list.innerHTML = '';
        recents.forEach(r => {
            const item = document.createElement('div');
            item.className = 'recent-item';
            item.textContent = r.path;
            item.addEventListener('click', () => {
                const input = $('#new-chat-workspace');
                if (input)
                    input.value = r.path;
            });
            list.appendChild(item);
        });
    }
};
