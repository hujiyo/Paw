// 对话历史管理
import { escapeHtml, scrollToBottom } from './utils.js';
import { createMsgEl, getToolDisplay, updateToolElement } from './render.js';
import { Browser } from './browser.js';
import { Planner } from './planner.js';
export const ChatHistory = {
    dom: null,
    messages: [], // 当前对话的消息列表（仅用于显示）
    currentSessionId: null, // 当前会话ID
    isInAssistantTurn: false, // 是否在助手轮次中（用于 UI 状态）
    // 初始化 DOM 引用
    init(dom) {
        this.dom = dom;
    },
    // 添加用户消息
    addUserMessage(text) {
        const msgId = `msg-${Date.now()}`;
        this.messages.push({ id: msgId, role: 'user', text });
        if (this.dom) {
            this.dom.messages.appendChild(createMsgEl('user', 'USER', text, msgId));
            scrollToBottom(this.dom.msgWrap);
        }
        // 标记进入助手轮次
        this.isInAssistantTurn = true;
        return msgId;
    },
    // 记录流式文本开始（UI 状态管理）
    onStreamStart(msgId) {
        // 保留用于 UI 状态跟踪
    },
    // 记录流式文本结束
    onStreamEnd(text) {
        // 保留用于 UI 状态跟踪
    },
    // 添加工具调用（UI 状态管理）
    addTool(toolId, toolName) {
        // 保留用于 UI 状态跟踪
    },
    // 结束助手轮次 - 从后端获取最新轮次数据并渲染
    endAssistantTurn() {
        this.isInAssistantTurn = false;
        // 从后端获取最新轮次数据
        this.fetchAndRenderChain();
    },
    // 从后端获取轮次数据并渲染
    async fetchAndRenderChain() {
        try {
            const response = await fetch('/api/turns');
            const data = await response.json();
            if (data.success && data.turns) {
                this.renderChainFromData(data.turns);
            }
        }
        catch (e) {
            console.warn('Failed to fetch turns:', e);
        }
    },
    // 渲染对话链视图（从后端数据）
    renderChainFromData(turns) {
        if (!this.dom)
            return;
        // 当前对话视图已移除，此方法不再需要
        return;
        turns.forEach((turn) => {
            const el = document.createElement('div');
            el.className = 'chain-item';
            el.dataset.turnIdx = String(turn.index);
            const isAssistant = turn.role === 'assistant';
            const hasParts = isAssistant && turn.parts && turn.parts.length > 0;
            const toolCount = turn.tool_count || 0;
            const preview = turn.preview || '';
            let detailsHtml = '';
            if (hasParts && turn.parts) {
                detailsHtml = '<div class="chain-item__details">';
                turn.parts.forEach((part) => {
                    if (part.type === 'tool') {
                        detailsHtml += `<div class="chain-item__detail chain-item__detail--tool" data-tool-id="${part.id}">⎿ ⚙ ${part.name}</div>`;
                    }
                    else if (part.type === 'text' && part.text) {
                        const textPreview = part.text.slice(0, 50) + (part.text.length > 50 ? '…' : '');
                        detailsHtml += `<div class="chain-item__detail chain-item__detail--text">⎿ 💬 ${escapeHtml(textPreview)}</div>`;
                    }
                });
                detailsHtml += '</div>';
            }
            el.innerHTML = `
                <div class="chain-item__header">
                    ${hasParts ? '<span class="chain-item__toggle">▶</span>' : ''}
                    <span class="chain-item__role chain-item__role--${turn.role}">${turn.role === 'user' ? 'USER' : 'PAW'}</span>
                    <span class="chain-item__text">${escapeHtml(preview.slice(0, 45))}${preview.length > 45 ? '…' : ''}</span>
                    ${toolCount > 0 ? `<span class="chain-item__meta">${toolCount}⚙</span>` : ''}
                </div>
                ${detailsHtml}
            `;
            const header = el.querySelector('.chain-item__header');
            if (header) {
                header.addEventListener('click', () => {
                    if (hasParts) {
                        el.classList.toggle('chain-item--expanded');
                    }
                });
            }
            el.querySelectorAll('.chain-item__detail').forEach(detail => {
                detail.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const toolId = detail.dataset.toolId;
                    if (toolId) {
                        this.highlightAndScrollTo(`tool-${toolId}`, true);
                    }
                });
            });
        });
    },
    // 兼容方法：立即调用后端获取并渲染
    renderChain() {
        this.fetchAndRenderChain();
    },
    highlightAndScrollTo(elementId, isTool = false) {
        const el = document.getElementById(elementId);
        if (!el)
            return;
        document.querySelectorAll('.msg--highlighted, .tool--highlighted').forEach(e => {
            e.classList.remove('msg--highlighted', 'tool--highlighted');
        });
        el.classList.add(isTool ? 'tool--highlighted' : 'msg--highlighted');
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => {
            el.classList.remove('msg--highlighted', 'tool--highlighted');
        }, 2000);
    },
    clear() {
        this.messages = [];
        this.isInAssistantTurn = false;
        this.renderChain();
    },
    // 加载历史会话 (包含 chunks 解析逻辑)
    // 注意：轮次数据不再在前端维护，而是通过 renderChain() 从后端获取
    loadSessionChunks(chunks) {
        this.messages = [];
        this.isInAssistantTurn = false;
        if (!this.dom)
            return;
        this.dom.messages.innerHTML = '';
        const toolResults = [];
        const toolArgsMap = new Map();
        let currentAssistantMsgId = null;
        let currentAssistantMsgEl = null;
        chunks.forEach(chunk => {
            const type = chunk.type;
            if (type === 'user') {
                // 重置 assistant 状态
                currentAssistantMsgId = null;
                currentAssistantMsgEl = null;
                const msgId = `msg-${Date.now()}-${Math.random()}`;
                this.messages.push({ id: msgId, role: 'user', text: chunk.content || '' });
                this.dom.messages.appendChild(createMsgEl('user', 'USER', chunk.content || '', msgId));
            }
            else if (type === 'assistant') {
                if (currentAssistantMsgEl) {
                    if (chunk.content) {
                        // 追加新的文本块到 msg__body
                        const body = currentAssistantMsgEl.querySelector('.msg__body');
                        const actions = currentAssistantMsgEl.querySelector('.msg__actions');
                        const newContent = document.createElement('div');
                        newContent.className = 'msg__content';
                        newContent.innerHTML = marked.parse(chunk.content);
                        if (body && actions) {
                            body.insertBefore(newContent, actions);
                        }
                        else if (body) {
                            body.appendChild(newContent);
                        }
                    }
                }
                else {
                    const msgId = `msg-${Date.now()}-${Math.random()}`;
                    currentAssistantMsgId = msgId;
                    this.messages.push({ id: msgId, role: 'assistant', text: chunk.content || '' });
                    currentAssistantMsgEl = createMsgEl('assistant', 'PAW', chunk.content || '', msgId);
                    this.dom.messages.appendChild(currentAssistantMsgEl);
                }
                if (chunk.metadata?.tool_calls) {
                    const body = currentAssistantMsgEl?.querySelector('.msg__body');
                    const actions = currentAssistantMsgEl?.querySelector('.msg__actions');
                    chunk.metadata.tool_calls.forEach(tc => {
                        const func = tc.function || {};
                        const args = func.arguments || '{}';
                        let parsedArgs;
                        if (typeof args === 'string') {
                            try {
                                parsedArgs = JSON.parse(args);
                            }
                            catch {
                                parsedArgs = {};
                            }
                        }
                        else {
                            parsedArgs = args;
                        }
                        toolArgsMap.set(tc.id, parsedArgs);
                        const toolEl = document.createElement('div');
                        toolEl.id = `tool-${tc.id}`;
                        toolEl.className = 'tool';
                        toolEl.innerHTML = `<div class="tool__header"><div class="tool__spinner"></div><span class="tool__name">${func.name || ''}</span> <span class="tool__args">${typeof args === 'string' ? args : JSON.stringify(args)}</span></div>`;
                        toolEl.dataset.rawRequest = JSON.stringify(tc);
                        // 追加到 body（在 actions 之前）
                        if (body && actions) {
                            body.insertBefore(toolEl, actions);
                        }
                        else if (body) {
                            body.appendChild(toolEl);
                        }
                    });
                }
            }
            else if (type === 'tool_result') {
                toolResults.push({
                    toolCallId: chunk.metadata?.tool_call_id,
                    toolName: chunk.metadata?.name || 'unknown',
                    content: chunk.content || ''
                });
            }
        });
        toolResults.forEach(result => {
            const args = toolArgsMap.get(result.toolCallId || '') || {};
            const display = getToolDisplay(result.toolName, result.content, args);
            const el = document.getElementById(`tool-${result.toolCallId}`);
            updateToolElement(el, result.toolName, display, true);
            // 保存原始响应数据
            if (el) {
                el.dataset.rawResponse = JSON.stringify({
                    success: true,
                    result: result.content
                });
            }
        });
        scrollToBottom(this.dom.msgWrap);
        // 从后端获取轮次数据并渲染对话链
        this.renderChain();
        // 刷新 Browser URL 列表
        Browser.refresh();
        // 刷新 Planner 状态
        Planner.refresh();
    }
};
