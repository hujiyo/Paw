// 对话历史管理
import { escapeHtml, scrollToBottom } from './utils.js';
import { createMsgEl, getToolDisplay, updateToolElement, ToolArgs } from './render.js';

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

interface ChatHistoryManager {
    dom: DomRefs | null;
    messages: Message[];
    turns: Turn[];
    currentSessionId: string | null;
    currentTurn: Turn | null;
    isInAssistantTurn: boolean;
    init(dom: DomRefs): void;
    addUserMessage(text: string): string;
    onStreamStart(msgId: string): void;
    onStreamEnd(text: string): void;
    addTool(toolId: string, toolName: string): void;
    endAssistantTurn(): void;
    renderChain(): void;
    highlightAndScrollTo(elementId: string, isTool?: boolean): void;
    clear(): void;
    loadSessionChunks(chunks: SessionChunk[]): void;
}

export const ChatHistory: ChatHistoryManager = {
    dom: null,
    messages: [],      // 当前对话的消息列表（仅用于显示，不持久化）
    turns: [],         // 对话轮次列表
    currentSessionId: null,  // 当前会话ID
    currentTurn: null, // 当前正在进行的助手轮次
    isInAssistantTurn: false, // 是否在助手轮次中
    
    // 初始化 DOM 引用
    init(dom: DomRefs): void {
        this.dom = dom;
    },

    // 添加用户消息
    addUserMessage(text: string): string {
        const msgId = `msg-${Date.now()}`;
        this.messages.push({ id: msgId, role: 'user', text });
        
        this.turns.push({
            role: 'user',
            msgId: msgId,
            text: text,
            parts: []
        });
        
        if (this.dom) {
            this.dom.messages.appendChild(createMsgEl('user', 'USER', text, msgId));
            scrollToBottom(this.dom.msgWrap);
        }
        this.renderChain();
        
        // 标记进入助手轮次
        this.isInAssistantTurn = true;
        this.currentTurn = {
            role: 'assistant',
            msgId: null,  // 第一次 onStreamStart 时设置
            text: '',
            parts: []
        };
        
        return msgId;
    },

    // 记录流式文本开始
    onStreamStart(msgId: string): void {
        if (this.currentTurn && this.isInAssistantTurn) {
            if (!this.currentTurn.msgId) {
                this.currentTurn.msgId = msgId;
            }
        }
    },

    // 记录流式文本结束
    onStreamEnd(text: string): void {
        if (this.currentTurn && this.isInAssistantTurn && text) {
            this.currentTurn.parts.push({ type: 'text', text: text });
            if (!this.currentTurn.text) {
                this.currentTurn.text = text;
            }
        }
    },

    // 添加工具调用到当前轮次
    addTool(toolId: string, toolName: string): void {
        if (this.currentTurn && this.isInAssistantTurn) {
            this.currentTurn.parts.push({ type: 'tool', id: toolId, name: toolName });
        }
    },

    // 结束助手轮次
    endAssistantTurn(): void {
        if (this.currentTurn && this.isInAssistantTurn) {
            if (this.currentTurn.parts.length > 0 || this.currentTurn.text) {
                this.turns.push(this.currentTurn);
                this.messages.push({ 
                    id: this.currentTurn.msgId || `msg-${Date.now()}`, 
                    role: 'assistant', 
                    text: this.currentTurn.text 
                });
            }
            this.currentTurn = null;
            this.isInAssistantTurn = false;
            this.renderChain();
        }
    },

    // 渲染对话链视图
    renderChain(): void {
        if (!this.dom) return;
        
        if (!this.turns.length) {
            this.dom.chainList.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:2rem 1rem">发送消息开始对话</div>';
            return;
        }
        this.dom.chainList.innerHTML = '';

        this.turns.forEach((turn, idx) => {
            const el = document.createElement('div');
            el.className = 'chain-item';
            el.dataset.msgId = turn.msgId || '';
            el.dataset.turnIdx = String(idx);

            const isAssistant = turn.role === 'assistant';
            const hasParts = isAssistant && turn.parts.length > 0;
            const toolCount = turn.parts.filter(p => p.type === 'tool').length;
            
            let preview = '';
            if (turn.role === 'user') {
                preview = turn.text || '';
            } else {
                const firstText = turn.parts.find(p => p.type === 'text');
                preview = firstText?.text ? firstText.text.slice(0, 40) : (toolCount > 0 ? `${toolCount} 个工具调用` : '');
            }

            let detailsHtml = '';
            if (hasParts) {
                detailsHtml = '<div class="chain-item__details">';
                turn.parts.forEach((part, partIdx) => {
                    if (part.type === 'tool') {
                        detailsHtml += `<div class="chain-item__detail chain-item__detail--tool" data-tool-id="${part.id}">⎿ ⚙ ${part.name}</div>`;
                    } else if (part.type === 'text' && part.text) {
                        const textPreview = part.text.slice(0, 50) + (part.text.length > 50 ? '…' : '');
                        detailsHtml += `<div class="chain-item__detail chain-item__detail--text" data-part-idx="${partIdx}">⎿ 💬 ${escapeHtml(textPreview)}</div>`;
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
                    if (turn.msgId) {
                        this.highlightAndScrollTo(turn.msgId);
                    }
                });
            }

            el.querySelectorAll('.chain-item__detail').forEach(detail => {
                detail.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const toolId = (detail as HTMLElement).dataset.toolId;
                    if (toolId) {
                        this.highlightAndScrollTo(`tool-${toolId}`, true);
                    } else if (turn.msgId) {
                        this.highlightAndScrollTo(turn.msgId);
                    }
                });
            });

            this.dom!.chainList.appendChild(el);
        });
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
        this.turns = [];
        this.currentTurn = null;
        this.isInAssistantTurn = false;
        this.renderChain();
    },

    // 加载历史会话 (包含 chunks 解析逻辑)
    loadSessionChunks(chunks: SessionChunk[]): void {
        this.clear();
        if (!this.dom) return;
        
        this.dom.messages.innerHTML = '';

        const toolResults: Array<{
            toolCallId: string | undefined;
            toolName: string;
            content: string;
        }> = [];
        const toolArgsMap = new Map<string, ToolArgs>();
        
        let currentAssistantParts: TurnPart[] = [];
        let currentAssistantMsgId: string | null = null;
        let currentAssistantMsgEl: HTMLElement | null = null;

        chunks.forEach(chunk => {
            const type = chunk.type;

            if (type === 'user') {
                if (currentAssistantParts.length > 0) {
                    this.turns.push({
                        role: 'assistant',
                        msgId: currentAssistantMsgId,
                        text: currentAssistantParts.find(p => p.type === 'text')?.text || '',
                        parts: currentAssistantParts
                    });
                    currentAssistantParts = [];
                    currentAssistantMsgId = null;
                    currentAssistantMsgEl = null;
                }
                
                const msgId = `msg-${Date.now()}-${Math.random()}`;
                this.messages.push({ id: msgId, role: 'user', text: chunk.content || '' });
                this.turns.push({
                    role: 'user',
                    msgId: msgId,
                    text: chunk.content || '',
                    parts: []
                });
                this.dom!.messages.appendChild(createMsgEl('user', 'USER', chunk.content || '', msgId));

            } else if (type === 'assistant') {
                if (currentAssistantMsgEl) {
                    if (chunk.content) {
                        const newContent = document.createElement('div');
                        newContent.className = 'msg__content msg__content--continued';
                        newContent.innerHTML = marked.parse(chunk.content);
                        currentAssistantMsgEl.appendChild(newContent);
                        currentAssistantParts.push({ type: 'text', text: chunk.content });
                    }
                } else {
                    const msgId = `msg-${Date.now()}-${Math.random()}`;
                    currentAssistantMsgId = msgId;
                    this.messages.push({ id: msgId, role: 'assistant', text: chunk.content || '' });
                    
                    currentAssistantMsgEl = createMsgEl('assistant', 'PAW', chunk.content || '', msgId);
                    this.dom!.messages.appendChild(currentAssistantMsgEl);
                    
                    if (chunk.content) {
                        currentAssistantParts.push({ type: 'text', text: chunk.content });
                    }
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
                        
                        const toolsContainer = currentAssistantMsgEl?.querySelector('.msg__tools');
                        if (toolsContainer) {
                            toolsContainer.appendChild(toolEl);
                        }
                        
                        currentAssistantParts.push({ type: 'tool', id: tc.id, name: func.name });
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
        
        if (currentAssistantParts.length > 0) {
            this.turns.push({
                role: 'assistant',
                msgId: currentAssistantMsgId,
                text: currentAssistantParts.find(p => p.type === 'text')?.text || '',
                parts: currentAssistantParts
            });
        }

        toolResults.forEach(result => {
            const args = toolArgsMap.get(result.toolCallId || '') || {};
            const display = getToolDisplay(result.toolName, result.content, args);
            const el = document.getElementById(`tool-${result.toolCallId}`);
            updateToolElement(el, result.toolName, display, true);
        });

        scrollToBottom(this.dom!.msgWrap);
        this.renderChain();
    }
};
