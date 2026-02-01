// 消息操作按钮模块
// 为聊天消息提供复制、删除、重试、继续等操作功能
// ============ SVG 图标常量 ============
const ICONS = {
    copy: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
    </svg>`,
    copySuccess: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="20 6 9 17 4 12"></polyline>
    </svg>`,
    delete: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="3 6 5 6 21 6"></polyline>
        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
    </svg>`,
    retry: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="1 4 1 10 7 10"></polyline>
        <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>
    </svg>`,
    continue: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="5 3 19 12 5 21 5 3"></polygon>
    </svg>`,
    loading: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="msg-action__spinner">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M12 6v6l4 2"></path>
    </svg>`
};
// ============ 按钮配置 ============
const USER_BUTTONS = [
    { id: 'copy', icon: ICONS.copy, tooltip: '复制' },
    { id: 'delete', icon: ICONS.delete, tooltip: '删除' }
];
const ASSISTANT_BUTTONS = [
    { id: 'copy', icon: ICONS.copy, tooltip: '复制' },
    { id: 'delete', icon: ICONS.delete, tooltip: '删除' },
    { id: 'retry', icon: ICONS.retry, tooltip: '重试' },
    { id: 'continue', icon: ICONS.continue, tooltip: '继续' }
];
// ============ 模块状态 ============
let sendFn = null;
const buttonStates = new Map();
// ============ MessageActions 模块 ============
export const MessageActions = {
    /**
     * 初始化模块
     * @param send - 发送消息到后端的函数
     */
    init(send) {
        sendFn = send;
    },
    /**
     * 获取指定消息类型的按钮配置
     * @param type - 消息类型 'user' | 'assistant'
     * @returns 按钮配置数组
     */
    getButtonsForType(type) {
        return type === 'user' ? USER_BUTTONS : ASSISTANT_BUTTONS;
    },
    /**
     * 创建操作按钮HTML
     * @param type - 消息类型 'user' | 'assistant'
     * @returns 按钮容器HTML字符串
     */
    createActionButtons(type) {
        const buttons = this.getButtonsForType(type);
        const buttonsHtml = buttons.map(btn => `<button class="msg-action" data-action="${btn.id}" title="${btn.tooltip}">${btn.icon}</button>`).join('');
        return `<div class="msg__actions">${buttonsHtml}</div>`;
    },
    /**
     * 为消息元素添加操作按钮
     * @param config - 消息配置
     */
    attachActions(config) {
        const { messageId, messageType, messageElement } = config;
        // 检查是否已经有操作按钮
        if (messageElement.querySelector('.msg__actions')) {
            return;
        }
        // 创建按钮容器
        const actionsHtml = this.createActionButtons(messageType);
        messageElement.insertAdjacentHTML('beforeend', actionsHtml);
        // 初始化按钮状态
        buttonStates.set(messageId, {
            messageId,
            isLoading: {},
            isDisabled: {}
        });
        // 绑定事件处理
        const actionsContainer = messageElement.querySelector('.msg__actions');
        if (actionsContainer) {
            actionsContainer.addEventListener('click', (e) => {
                const target = e.target;
                const button = target.closest('.msg-action');
                if (!button)
                    return;
                const action = button.dataset.action;
                if (!action)
                    return;
                e.stopPropagation();
                this.handleAction(action, messageId, messageType, messageElement);
            });
        }
    },
    /**
     * 处理按钮点击事件
     * @param action - 操作类型
     * @param messageId - 消息ID
     * @param messageType - 消息类型
     * @param messageElement - 消息DOM元素
     */
    handleAction(action, messageId, messageType, messageElement) {
        switch (action) {
            case 'copy':
                this.copyMessage(messageId, messageElement);
                break;
            case 'delete':
                this.deleteMessage(messageId, messageType);
                break;
            case 'retry':
                if (messageType === 'assistant') {
                    this.retryMessage(messageId);
                }
                break;
            case 'continue':
                if (messageType === 'assistant') {
                    this.continueMessage(messageId);
                }
                break;
        }
    },
    /**
     * 复制消息内容到剪贴板
     * @param messageId - 消息ID
     * @param messageElement - 消息DOM元素
     * @returns Promise<boolean> 是否成功
     */
    async copyMessage(messageId, messageElement) {
        // 获取消息内容元素
        const contentEl = messageElement.querySelector('.msg__content');
        if (!contentEl)
            return false;
        // 提取纯文本内容
        const text = contentEl.textContent || '';
        try {
            await navigator.clipboard.writeText(text);
            // 显示成功状态
            const copyBtn = messageElement.querySelector('.msg-action[data-action="copy"]');
            if (copyBtn) {
                copyBtn.innerHTML = ICONS.copySuccess;
                copyBtn.classList.add('msg-action--success');
                setTimeout(() => {
                    copyBtn.innerHTML = ICONS.copy;
                    copyBtn.classList.remove('msg-action--success');
                }, 2000);
            }
            return true;
        }
        catch (err) {
            console.error('复制失败:', err);
            // 显示错误状态
            const copyBtn = messageElement.querySelector('.msg-action[data-action="copy"]');
            if (copyBtn) {
                copyBtn.classList.add('msg-action--error');
                setTimeout(() => {
                    copyBtn.classList.remove('msg-action--error');
                }, 2000);
            }
            return false;
        }
    },
    /**
     * 删除消息
     * @param messageId - 消息ID
     * @param messageType - 消息类型
     */
    deleteMessage(messageId, messageType) {
        // TODO: 在后续任务中实现完整的删除逻辑
        console.log('Delete message:', messageId, messageType);
    },
    /**
     * 重试生成（仅assistant消息）
     * @param messageId - 消息ID
     */
    retryMessage(messageId) {
        // TODO: 在后续任务中实现完整的重试逻辑
        console.log('Retry message:', messageId);
    },
    /**
     * 继续生成（仅assistant消息）
     * @param messageId - 消息ID
     */
    continueMessage(messageId) {
        // TODO: 在后续任务中实现完整的继续逻辑
        console.log('Continue message:', messageId);
    },
    /**
     * 设置按钮加载状态
     * @param messageId - 消息ID
     * @param action - 操作类型
     * @param loading - 是否加载中
     */
    setButtonLoading(messageId, action, loading) {
        const state = buttonStates.get(messageId);
        if (state) {
            state.isLoading[action] = loading;
        }
        // 更新UI
        const msgEl = document.getElementById(messageId)?.closest('.msg');
        if (!msgEl)
            return;
        const btn = msgEl.querySelector(`.msg-action[data-action="${action}"]`);
        if (btn) {
            btn.classList.toggle('msg-action--loading', loading);
            if (loading) {
                btn.innerHTML = ICONS.loading;
            }
            else {
                // 恢复原始图标
                const buttons = [...USER_BUTTONS, ...ASSISTANT_BUTTONS];
                const buttonConfig = buttons.find(b => b.id === action);
                if (buttonConfig) {
                    btn.innerHTML = buttonConfig.icon;
                }
            }
        }
    },
    /**
     * 设置按钮禁用状态
     * @param messageId - 消息ID
     * @param action - 操作类型
     * @param disabled - 是否禁用
     */
    setButtonDisabled(messageId, action, disabled) {
        const state = buttonStates.get(messageId);
        if (state) {
            state.isDisabled[action] = disabled;
        }
        // 更新UI
        const msgEl = document.getElementById(messageId)?.closest('.msg');
        if (!msgEl)
            return;
        const btn = msgEl.querySelector(`.msg-action[data-action="${action}"]`);
        if (btn) {
            btn.disabled = disabled;
            btn.classList.toggle('msg-action--disabled', disabled);
        }
    },
    /**
     * 获取发送函数
     * @returns 发送函数或null
     */
    getSendFn() {
        return sendFn;
    }
};
