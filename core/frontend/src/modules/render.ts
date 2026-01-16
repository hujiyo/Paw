// 渲染相关函数
import { escapeHtml } from './utils.js';

// ============ 类型定义 ============

export interface ToolDisplay {
    line1: string;
    line2: string;
    has_line2: boolean;
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
    
    // 添加工具容器（用于附加该消息的工具调用）
    // marked 是全局变量，由 index.html 引入
    // 注意：id 设置在 msg__content 上，方便 appendStream 直接定位
    // 操作按钮放在消息最末尾（工具容器之后）
    el.innerHTML = `<div class="msg__header">${author}</div><div class="msg__content"${id ? ` id="${id}"` : ''}>${marked.parse(text)}</div><div class="msg__tools"></div>${actionsHtml}`;
    
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

// ============ 工具显示格式化 ============

// 工具显示格式化 (核心逻辑，与后端对齐)
export function getToolDisplay(toolName: string, resultText: string, args: ToolArgs): ToolDisplay {
    const content = resultText || '';

    // read_file
    if (toolName === 'read_file') {
        const path = args.file_path || '';
        const filename = path.split('/').pop()?.split('\\').pop() || '';
        const totalLines = content.split('\n').length;
        const offset = args.offset;
        const limit = args.limit;
        let rangeStr = `(all ${totalLines}行)`;
        if (offset && limit) {
            const end = offset + limit - 1;
            rangeStr = `(${offset}-${end}/${totalLines}行)`;
        } else if (offset) {
            rangeStr = `(${offset}-end/${totalLines}行)`;
        }
        return {
            line1: `${filename} ${rangeStr}`,
            line2: '',
            has_line2: false
        };
    }

    // write_to_file / delete_file / edit / multi_edit
    if (['write_to_file', 'delete_file', 'edit', 'multi_edit'].includes(toolName)) {
        const path = args.file_path || '';
        const filename = path.split('/').pop()?.split('\\').pop() || '';
        return { line1: filename, line2: '', has_line2: false };
    }

    // list_dir
    if (toolName === 'list_dir') {
        const path = args.directory_path || '.';
        const lines = content.split('\n').filter(l => l.startsWith('['));
        const count = lines.length;
        const preview = lines.slice(0, 3).map(l => {
            const match = l.match(/\] (.+?)(?: \(|$)/);
            return match ? match[1] : '';
        }).filter(Boolean).join(', ');
        return {
            line1: path,
            line2: preview + (count > 3 ? `... (+${count-3})` : ''),
            has_line2: count > 0
        };
    }

    // find_by_name
    if (toolName === 'find_by_name') {
        const pattern = args.pattern || '';
        const items = content.split('\n').filter(Boolean);
        const count = items.length;
        if (count === 0) {
            return { line1: `"${pattern}" 无匹配`, line2: '', has_line2: false };
        }
        const names = items.slice(0, 3).map(i => i.split('/').pop()?.split('\\').pop() || '');
        const preview = names.join(', ');
        return {
            line1: `"${pattern}" ${count}匹配`,
            line2: preview + (count > 3 ? `... (+${count-3})` : ''),
            has_line2: true
        };
    }

    // grep_search
    if (toolName === 'grep_search') {
        const query = args.query || '';
        const resultTextTrimmed = content.trim();
        if (!resultTextTrimmed || resultTextTrimmed.toLowerCase().includes('no matches')) {
            return { line1: `"${query}" 无匹配`, line2: '', has_line2: false };
        }
        const lines = resultTextTrimmed.split('\n');
        const summary = (lines[0]?.slice(0, 100) || '') + (lines[0]?.length > 100 ? '...' : '');
        return {
            line1: `"${query}"`,
            line2: summary + (lines.length > 1 ? ` (+${lines.length-1})` : ''),
            has_line2: true
        };
    }

    // search_web
    if (toolName === 'search_web') {
        const query = args.query || '';
        try {
            const jsonMatch = content.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const data = JSON.parse(jsonMatch[0]) as { results?: Array<{ id: string; title: string }> };
                const results = data.results || [];
                return {
                    line1: `${results.length}条 "${query}"`,
                    line2: results.map(r => `[${r.id}] ${r.title}`).join('\n'),
                    has_line2: results.length > 0
                };
            }
        } catch (e) { /* ignore */ }
        return { line1: `"${query}"`, line2: '', has_line2: false };
    }

    // load_url_content
    if (toolName === 'load_url_content') {
        try {
            const jsonMatch = content.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const data = JSON.parse(jsonMatch[0]) as { 
                    title?: string; 
                    url_id?: string; 
                    pages?: Array<{ page_id: string; summary: string }> 
                };
                const title = (data.title || '无标题').slice(0, 100);
                const urlId = data.url_id || '';
                const pages = data.pages || [];
                return {
                    line1: urlId ? `[${urlId}] ${title}` : title,
                    line2: pages.map(p => `[${p.page_id}] ${p.summary}`).join('\n'),
                    has_line2: pages.length > 0
                };
            }
        } catch (e) { /* ignore */ }
        return { line1: args.url?.slice(0, 100) || '', line2: '', has_line2: false };
    }

    // read_page
    if (toolName === 'read_page') {
        const pageId = args.page_id || '';
        try {
            const jsonMatch = content.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const data = JSON.parse(jsonMatch[0]) as { 
                    page_num?: string | number; 
                    total_pages?: string | number; 
                    size?: number 
                };
                const pageNum = data.page_num || '?';
                const total = data.total_pages || '?';
                const size = data.size || 0;
                return {
                    line1: `[${pageId}] 第${pageNum}/${total}页 (${size}字节)`,
                    line2: '',
                    has_line2: false
                };
            }
        } catch (e) { /* ignore */ }
        return { line1: `[${pageId}]`, line2: '', has_line2: false };
    }

    // 默认：多行内容显示
    if (content.includes('\n')) {
        const lines = content.split('\n');
        return {
            line1: lines[0]?.slice(0, 100) || '',
            line2: lines.slice(1, 10).join('\n'),
            has_line2: true
        };
    }

    return { line1: content.slice(0, 100), line2: '', has_line2: false };
}

// ============ 工具UI更新 ============

// 更新工具UI
export function updateToolElement(el: HTMLElement | null, name: string, display: ToolDisplay, success: boolean): void {
    if (!el) return;

    el.className = `tool ${success ? 'tool--success' : 'tool--error'}`;

    const line1 = display.line1 || '';
    const line2 = display.line2 || '';
    const hasLine2 = display.has_line2 || false;

    // Header: ● tool_name line1
    let headerHtml = `<span class="tool__icon">●</span><span class="tool__name">${name}</span> <span class="tool__args">${line1}</span>`;

    // Body: 每行前面加 ⎿
    let bodyHtml = '';
    if (hasLine2 && line2) {
        const lines = line2.split('\n');
        let firstLine = true;
        lines.forEach(line => {
            // 如果行以 │ 开头（连接线），保留原样
            if (line.startsWith('│')) {
                bodyHtml += `<div class="tool__body-line">${escapeHtml(line)}</div>`;
            } else {
                // 使用 Flex 布局结构：左侧是固定宽度的分支符号，右侧是内容
                const branch = firstLine ? '⎿ ' : '';
                bodyHtml += `<div class="tool__body-line">
                    <span class="tool__branch">${branch}</span>
                    <span class="tool__content">${escapeHtml(line)}</span>
                </div>`;
                firstLine = false;
            }
        });
    }

    el.innerHTML = `<div class="tool__header">${headerHtml}</div>${bodyHtml ? `<div class="tool__body">${bodyHtml}</div>` : ''}`;
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
