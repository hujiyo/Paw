// 渲染相关函数
import { escapeHtml } from './utils.js';

// ============ 类型定义 ============

export interface ToolDisplay {
    abstract: string;
    details: Record<string, string> | null;
}

export interface ToolArgs {
    file_path?: string;
    directory_path?: string;
    pattern?: string;
    query?: string;
    url?: string;
    page_id?: string;
    offset?: number;
    limit?: number;
    [key: string]: unknown;
}

// ============ 消息操作回调 ============

export interface MessageActions {
    onCopy?: (text: string, role: 'user' | 'assistant') => void;
    onDelete?: (msgId: string, role: 'user' | 'assistant') => void;
    onRetry?: (msgId: string) => void;
    onContinue?: (msgId: string) => void;
}

let messageActionsCallbacks: MessageActions = {};

// 设置消息操作回调
export function setMessageActions(actions: MessageActions): void {
    messageActionsCallbacks = actions;
}

// ============ 消息渲染 ============

// 创建消息操作按钮HTML
function buildActionsHtml(role: 'user' | 'assistant'): string {
    let actionsHtml = `
        <div class="msg__actions">
            <button class="msg__action-btn msg__action-btn--copy" title="复制">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                </svg>
            </button>
            <button class="msg__action-btn msg__action-btn--delete" title="删除">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="3 6 5 6 21 6"></polyline>
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                </svg>
            </button>`;
    
    // PAW 消息额外添加重试和继续按钮
    if (role === 'assistant') {
        actionsHtml += `
            <button class="msg__action-btn msg__action-btn--retry" title="重试">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polyline points="1 4 1 10 7 10"></polyline>
                    <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"></path>
                </svg>
            </button>
            <button class="msg__action-btn msg__action-btn--continue" title="继续">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                </svg>
            </button>`;
    }
    actionsHtml += '</div>';
    return actionsHtml;
}

// 创建消息操作按钮元素（用于动态添加）
export function createMessageActions(role: 'user' | 'assistant', msgId: string | null): HTMLDivElement {
    const container = document.createElement('div');
    container.innerHTML = buildActionsHtml(role);
    const actionsEl = container.firstElementChild as HTMLDivElement;
    
    // 绑定事件
    const parentEl = actionsEl;
    const copyBtn = parentEl.querySelector('.msg__action-btn--copy');
    const deleteBtn = parentEl.querySelector('.msg__action-btn--delete');
    const retryBtn = parentEl.querySelector('.msg__action-btn--retry');
    const continueBtn = parentEl.querySelector('.msg__action-btn--continue');
    
    // 复制按钮 - 复制整个消息的所有内容
    copyBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        const msgEl = (e.target as HTMLElement).closest('.msg');
        // 获取所有内容块的文本
        const contentEls = msgEl?.querySelectorAll('.msg__content');
        const textParts: string[] = [];
        contentEls?.forEach(contentEl => {
            const text = contentEl.textContent?.trim();
            if (text) textParts.push(text);
        });
        const textToCopy = textParts.join('\n\n') || '';
        navigator.clipboard.writeText(textToCopy).then(() => {
            const btn = copyBtn as HTMLElement;
            btn.classList.add('msg__action-btn--success');
            setTimeout(() => btn.classList.remove('msg__action-btn--success'), 1500);
        });
        messageActionsCallbacks.onCopy?.(textToCopy, role);
    });
    
    deleteBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (msgId) messageActionsCallbacks.onDelete?.(msgId, role);
    });
    
    retryBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (msgId) messageActionsCallbacks.onRetry?.(msgId);
    });
    
    continueBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (msgId) messageActionsCallbacks.onContinue?.(msgId);
    });
    
    return actionsEl;
}

// 创建消息元素
export function createMsgEl(type: string, author: string, text: string, id: string | null = null): HTMLDivElement {
    const el = document.createElement('div');
    el.className = `msg msg--${type}`;
    const role = type === 'user' ? 'user' : 'assistant';
    
    // 构建操作按钮
    const actionsHtml = buildActionsHtml(role);
    
    // 新结构：body (包含 header + 流式内容) -> actions
    // body 包含所有内容（header、文本块、工具块），按时间顺序排列
    // marked 是全局变量，由 index.html 引入
    el.innerHTML = `<div class="msg__body"><div class="msg__header">${author}</div></div>${actionsHtml}`;
    
    // 如果有初始文本，添加首个内容块
    if (text || id) {
        const body = el.querySelector('.msg__body');
        const contentEl = document.createElement('div');
        contentEl.className = 'msg__content';
        if (id) contentEl.id = id;
        contentEl.innerHTML = marked.parse(text);
        body?.appendChild(contentEl);
    }
    
    // 存储消息ID和角色
    if (id) el.dataset.msgId = id;
    el.dataset.role = role;
    
    // 绑定按钮事件
    bindMessageActions(el, id, role, text);
    
    return el;
}

// 绑定消息操作按钮事件
function bindMessageActions(el: HTMLElement, msgId: string | null, role: 'user' | 'assistant', originalText: string): void {
    const copyBtn = el.querySelector('.msg__action-btn--copy');
    const deleteBtn = el.querySelector('.msg__action-btn--delete');
    const retryBtn = el.querySelector('.msg__action-btn--retry');
    const continueBtn = el.querySelector('.msg__action-btn--continue');
    
    // 复制按钮 - 复制整个消息的所有内容
    copyBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        // 获取所有内容块的文本（一个消息可能有多个 .msg__content）
        const contentEls = el.querySelectorAll('.msg__content');
        const textParts: string[] = [];
        contentEls.forEach(contentEl => {
            const text = contentEl.textContent?.trim();
            if (text) textParts.push(text);
        });
        const textToCopy = textParts.join('\n\n') || originalText;
        
        navigator.clipboard.writeText(textToCopy).then(() => {
            // 显示复制成功反馈
            const btn = copyBtn as HTMLElement;
            btn.classList.add('msg__action-btn--success');
            setTimeout(() => btn.classList.remove('msg__action-btn--success'), 1500);
        });
        
        messageActionsCallbacks.onCopy?.(textToCopy, role);
    });
    
    // 删除按钮
    deleteBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (msgId) {
            messageActionsCallbacks.onDelete?.(msgId, role);
        }
    });
    
    // 重试按钮（仅PAW消息）
    retryBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (msgId) {
            messageActionsCallbacks.onRetry?.(msgId);
        }
    });
    
    // 继续按钮（仅PAW消息）
    continueBtn?.addEventListener('click', (e) => {
        e.stopPropagation();
        if (msgId) {
            messageActionsCallbacks.onContinue?.(msgId);
        }
    });
}

// 系统消息
export function addSysMsg(container: HTMLElement, text: string, type: string = ''): void {
    const el = document.createElement('div');
    el.className = `sys-msg ${type}`;
    el.textContent = text;
    container.appendChild(el);
}

// ============ 工具图标映射 ============

const TOOL_ICONS: Record<string, string> = {
    read_files:        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
    edit_files:        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    create_file:       '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>',
    file_glob:         '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
    run_shell_command: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
    search_web:        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    load_url_content:  '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    read_page:         '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>',
    create_plan:       '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
    edit_plans:        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
    create_todo_list:  '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    add_todos:         '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    mark_todo_as_done: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
    read_todos:        '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    memory_search:     '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
    memory_write:      '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>',
};

const DEFAULT_TOOL_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/></svg>';

export function getToolIcon(name: string): string {
    return TOOL_ICONS[name] ?? DEFAULT_TOOL_ICON;
}

// ============ 工具显示格式化 ============

// 默认显示格式化（降级处理，后端已计算好 display）
export function getDefaultDisplay(resultText: string): ToolDisplay {
    const content = resultText?.trim() || '';
    if (!content) return { abstract: '已完成', details: null };

    const lines = content.split('\n').filter(l => l.trim());
    if (lines.length <= 1) {
        return { abstract: content.slice(0, 80), details: null };
    }
    return {
        abstract: lines[0].slice(0, 80) + (lines[0].length > 80 ? '…' : ''),
        details: { '输出': lines.join('\n') }
    };
}

// ============ 工具UI更新 ============

// 构建 details 字段的展开体 HTML
function buildDetailsHtml(details: Record<string, string>): string {
    const rows = Object.entries(details).map(([key, val]) => {
        const isMultiline = val.includes('\n');
        const valHtml = isMultiline
            ? `<pre class="tool__detail-pre">${escapeHtml(val)}</pre>`
            : `<span class="tool__detail-val">${escapeHtml(val)}</span>`;
        return `<div class="tool__detail-row"><span class="tool__detail-key">${escapeHtml(key)}</span>${valHtml}</div>`;
    }).join('');
    return `<div class="tool__body">${rows}</div>`;
}

// 绑定卡片折叠展开事件
function bindToolToggle(el: HTMLElement): void {
    const header = el.querySelector('.tool__header');
    if (!header) return;
    header.addEventListener('click', () => {
        el.classList.toggle('tool--expanded');
    });
}

// 更新工具UI（完成态）
export function updateToolElement(el: HTMLElement | null, name: string, display: ToolDisplay, success: boolean): void {
    if (!el) return;

    const startTime = el.dataset.startTime ? parseInt(el.dataset.startTime) : 0;
    const elapsed = startTime ? ((Date.now() - startTime) / 1000).toFixed(1) + 's' : '';

    const hasDetails = !!display.details && Object.keys(display.details).length > 0;
    el.className = `tool tool--done ${success ? 'tool--success' : 'tool--error'}`;

    const icon = getToolIcon(name);
    const statusIcon = success
        ? '<svg class="tool__status-icon tool__status-icon--ok" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>'
        : '<svg class="tool__status-icon tool__status-icon--err" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';

    const chevronHtml = hasDetails
        ? '<svg class="tool__chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>'
        : '';

    const elapsedHtml = elapsed ? `<span class="tool__elapsed">${elapsed}</span>` : '';
    const abstract = display.abstract || '';
    const bodyHtml = hasDetails ? buildDetailsHtml(display.details!) : '';

    el.innerHTML = `
        <div class="tool__header">
            <span class="tool__icon-wrap">${icon}</span>
            <span class="tool__name">${escapeHtml(name)}</span>
            ${abstract ? `<span class="tool__args">${escapeHtml(abstract)}</span>` : ''}
            <span class="tool__meta">
                ${elapsedHtml}
                ${statusIcon}
                ${chevronHtml}
            </span>
        </div>
        ${bodyHtml}
    `;

    if (hasDetails) bindToolToggle(el);
}

// ============ 弹窗渲染 ============

// 弹窗相关渲染
export function renderModalContent(title: string, contentHtml: string, showActions: boolean = false): void {
    const modalTitle = document.getElementById('modal-title');
    const modalBody = document.getElementById('modal-body');
    const modalActions = document.getElementById('modal-actions');
    const modal = document.getElementById('modal');

    if (modalTitle) modalTitle.textContent = title;
    if (modalBody) modalBody.innerHTML = contentHtml;
    if (modalActions) modalActions.style.display = showActions ? 'flex' : 'none';
    if (modal) modal.classList.add('visible');
}
