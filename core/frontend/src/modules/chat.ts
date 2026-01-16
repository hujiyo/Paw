// 对话历史管理
import { escapeHtml, scrollToBottom } from './utils.js';
import { createMsgEl, getToolDisplay, updateToolElement, ToolArgs, createMessageActions } from './render.js';
import { Browser } from './browser.js';

// ============ 类型定义 ============

export interface Message {
    id: string;
    role: 'user' | 'assistant';
    text: string;
}

export interface TurnPart {
    type: 'text' | 'tool';
    text?: string;
    id?: string;
    name?: string;
}

export interface Turn {
    role: 'user' | 'assistant';
    msgId: string | null;
    text: string;
    parts: TurnPart[];
}

export interface ToolCall {
    id: string;
    function?: {
        name?: string;
        arguments?: string | Record<string, unknown>;
    };
}

export interface ChunkMetadata {
    tool_calls?: ToolCall[];
    tool_call_id?: string;
    name?: string;
}

export interface SessionChunk {
    type: 'user' | 'assistant' | 'tool_result';
    content?: string;
    metadata?: ChunkMetadata;
}

export interface DomRefs {
    messages: HTMLElement;
    msgWrap: HTMLElement;
    chainList: HTMLElement;
    [key: string]: HTMLElement | null;
}

// ============ ChatHistory 管理器 ============
// 重构说明：轮次数据现在由后端 ChunkManager 统一管理
// 前端仅保留必要的 UI 状态，通过 /api/turns 或 turns_updated 事件获取数据

interface BackendTurn {
    index: number;
    role: 'user' | 'assistant';
    preview: string;
    tool_count: number;
    parts: TurnPart[];
}

interface ChatHistoryManager {
    dom: DomRefs | null;
    messages: Message[];
    currentSessionId: string | null;
    isInAssistantTurn: boolean;
    init(dom: DomRefs): void;
    addUserMessage(text: string): string;
    onStreamStart(msgId: string): void;
    onStreamEnd(text: string): void;
    addTool(toolId: string, toolName: string): void;
    endAssistantTurn(): void;
    renderChain(): void;
    renderChainFromData(turns: BackendTurn[]): void;
    fetchAndRenderChain(): Promise<void>;
    highlightAndScrollTo(elementId: string, isTool?: boolean): void;
    clear(): void;
    loadSessionChunks(chunks: SessionChunk[]): void;
}

export const ChatHistory: ChatHistoryManager = {
    dom: null,
    messages: [],      // 当前对话的消息列表（仅用于显示）
    currentSessionId: null,  // 当前会话ID
    isInAssistantTurn: false, // 是否在助手轮次中（用于 UI 状态）
    
    // 初始化 DOM 引用
    init(dom: DomRefs): void {
        this.dom = dom;
    },

    // 添加用户消息
    addUserMessage(text: string): string {
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
    onStreamStart(msgId: string): void {
        // 保留用于 UI 状态跟踪
    },

    // 记录流式文本结束
    onStreamEnd(text: string): void {
        // 保留用于 UI 状态跟踪
    },

    // 添加工具调用（UI 状态管理）
    addTool(toolId: string, toolName: string): void {
        // 保留用于 UI 状态跟踪
    },

    // 结束助手轮次 - 从后端获取最新轮次数据并渲染
    endAssistantTurn(): void {
        this.isInAssistantTurn = false;
        // 从后端获取最新轮次数据
        this.fetchAndRenderChain();
    },

    // 从后端获取轮次数据并渲染
    async fetchAndRenderChain(): Promise<void> {
        try {
            const response = await fetch('/api/turns');
            const data = await response.json();
            if (data.success && data.turns) {
                this.renderChainFromData(data.turns);
            }
        } catch (e) {
            console.warn('Failed to fetch turns:', e);
        }
    },

    // 渲染对话链视图（从后端数据）
    renderChainFromData(turns: BackendTurn[]): void {
        if (!this.dom) return;
        
        if (!turns.length) {
            this.dom.chainList.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:2rem 1rem">发送消息开始对话</div>';
            return;
        }
        this.dom.chainList.innerHTML = '';

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
                    } else if (part.type === 'text' && part.text) {
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
                    const toolId = (detail as HTMLElement).dataset.toolId;
                    if (toolId) {
                        this.highlightAndScrollTo(`tool-${toolId}`, true);
                    }
                });
            });

            this.dom!.chainList.appendChild(el);
        });
    },

    // 兼容方法：立即调用后端获取并渲染
    renderChain(): void {
        this.fetchAndRenderChain();
    },

    highlightAndScrollTo(elementId: string, isTool: boolean = false): void {
        const el = document.getElementById(elementId);
        if (!el) return;

        document.querySelectorAll('.msg--highlighted, .tool--highlighted').forEach(e => {
            e.classList.remove('msg--highlighted', 'tool--highlighted');
        });

        el.classList.add(isTool ? 'tool--highlighted' : 'msg--highlighted');
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });

        setTimeout(() => {
            el.classList.remove('msg--highlighted', 'tool--highlighted');
        }, 2000);
    },

    clear(): void {
        this.messages = [];
        this.isInAssistantTurn = false;
        this.renderChain();
    },

    // 加载历史会话 (包含 chunks 解析逻辑)
    // 注意：轮次数据不再在前端维护，而是通过 renderChain() 从后端获取
    loadSessionChunks(chunks: SessionChunk[]): void {
        this.messages = [];
        this.isInAssistantTurn = false;
        if (!this.dom) return;
        
        this.dom.messages.innerHTML = '';

        const toolResults: Array<{
            toolCallId: string | undefined;
            toolName: string;
            content: string;
        }> = [];
        const toolArgsMap = new Map<string, ToolArgs>();
        
        let currentAssistantMsgId: string | null = null;
        let currentAssistantMsgEl: HTMLElement | null = null;

        chunks.forEach(chunk => {
            const type = chunk.type;

            if (type === 'user') {
                // 重置 assistant 状态
                currentAssistantMsgId = null;
                currentAssistantMsgEl = null;
                
                const msgId = `msg-${Date.now()}-${Math.random()}`;
                this.messages.push({ id: msgId, role: 'user', text: chunk.content || '' });
                this.dom!.messages.appendChild(createMsgEl('user', 'USER', chunk.content || '', msgId));

            } else if (type === 'assistant') {
                if (currentAssistantMsgEl) {
                    if (chunk.content) {
                        // 在添加新内容前，先移除操作按钮
                        const actionsEl = currentAssistantMsgEl.querySelector('.msg__actions');
                        if (actionsEl) actionsEl.remove();
                        
                        const newContent = document.createElement('div');
                        newContent.className = 'msg__content msg__content--continued';
                        newContent.innerHTML = marked.parse(chunk.content);
                        currentAssistantMsgEl.appendChild(newContent);
                        
                        // 重新添加操作按钮到末尾
                        currentAssistantMsgEl.appendChild(createMessageActions('assistant', currentAssistantMsgId));
                    }
                } else {
                    const msgId = `msg-${Date.now()}-${Math.random()}`;
                    currentAssistantMsgId = msgId;
                    this.messages.push({ id: msgId, role: 'assistant', text: chunk.content || '' });
                    
                    currentAssistantMsgEl = createMsgEl('assistant', 'PAW', chunk.content || '', msgId);
                    this.dom!.messages.appendChild(currentAssistantMsgEl);
                }

                if (chunk.metadata?.tool_calls) {
                    chunk.metadata.tool_calls.forEach(tc => {
                        const func = tc.function || {};
                        const args = func.arguments || '{}';
                        let parsedArgs: ToolArgs;
                        if (typeof args === 'string') {
                            try {
                                parsedArgs = JSON.parse(args) as ToolArgs;
                            } catch {
                                parsedArgs = {};
                            }
                        } else {
                            parsedArgs = args as ToolArgs;
                        }
                        toolArgsMap.set(tc.id, parsedArgs);
                        
                        const toolEl = document.createElement('div');
                        toolEl.id = `tool-${tc.id}`;
                        toolEl.className = 'tool';
                        toolEl.innerHTML = `<div class="tool__header"><div class="tool__spinner"></div><span class="tool__name">${func.name || ''}</span> <span class="tool__args">${typeof args === 'string' ? args : JSON.stringify(args)}</span></div>`;
                        
                        // 保存原始请求数据
                        toolEl.dataset.rawRequest = JSON.stringify(tc);
                        
                        const toolsContainer = currentAssistantMsgEl?.querySelector('.msg__tools');
                        if (toolsContainer) {
                            toolsContainer.appendChild(toolEl);
                        }
                    });
                }

            } else if (type === 'tool_result') {
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

        scrollToBottom(this.dom!.msgWrap);
        
        // 从后端获取轮次数据并渲染对话链
        this.renderChain();
        
        // 刷新 Browser URL 列表
        Browser.refresh();
    }
};
