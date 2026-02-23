// 对话历史管理
import { escapeHtml, scrollToBottom } from './utils.js';
import { createMsgEl, getDefaultDisplay, updateToolElement, getToolIcon, ToolArgs, createMessageActions } from './render.js';
import { Browser } from './browser.js';
import { Planner } from './planner.js';

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
    display?: ToolDisplay;
    success?: boolean;
}

export interface ToolDisplay {
    abstract: string;
    details: Record<string, string> | null;
}

export interface SessionChunk {
    type: 'user' | 'assistant' | 'tool_call' | 'tool_result' | 'system' | 'memory' | 'shell' | 'thought';
    content?: string;
    metadata?: ChunkMetadata;
}

export interface DomRefs {
    messages: HTMLElement;
    msgWrap: HTMLElement;
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
    //
    // 【架构设计 - 会话恢复必须和流式输出使用相同的渲染逻辑】
    //
    // **核心原则：刷新后的显示必须和运行时完全一致**
    //
    // 后端的 chunks 数据结构定义：
    // - chunks 按时间顺序排列，包含所有类型的消息
    // - 一个 assistant turn 包含多个 chunks（文本、工具调用、工具结果）
    // - 直到遇到下一个 user chunk，assistant turn 结束
    //
    // 前端必须遵循的重建规则：
    // 1. 使用 currentAssistantMsgEl 跟踪当前 assistant 消息容器
    // 2. 遇到 user chunk 时：重置 currentAssistantMsgEl = null（结束当前 turn）
    // 3. 遇到 assistant chunk 时：
    //    - 如果存在 currentAssistantMsgEl：追加内容到现有消息
    //    - 否则：创建新的【PAW】消息（新的 assistant turn 开始）
    // 4. 工具调用和结果：作为内容块插入到 currentAssistantMsgEl 的 body 中
    //
    // 验证标准：
    // - 运行时显示 == 刷新后显示
    // - 一个 assistant turn = 一个【PAW】消息容器
    // - 所有内容（文本、工具）都在同一个容器内
    //
    // ==========================================================

    loadSessionChunks(chunks: SessionChunk[]): void {
        this.messages = [];
        this.isInAssistantTurn = false;
        if (!this.dom) return;
        
        this.dom.messages.innerHTML = '';

        const toolResults: Array<{
            toolCallId: string | undefined;
            toolName: string;
            content: string;
            display?: ToolDisplay;
            success: boolean;
        }> = [];
        const toolArgsMap = new Map<string, ToolArgs>();
        
        let currentAssistantMsgId: string | null = null;
        let currentAssistantMsgEl: HTMLElement | null = null;

        chunks.forEach(chunk => {
            const type = chunk.type;

            // 跳过内部 chunk 类型
            if (type === 'system' || type === 'memory' || type === 'shell' || type === 'thought') {
                return;
            }

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
                        // 追加新的文本块到 msg__body
                        const body = currentAssistantMsgEl.querySelector('.msg__body');

                        if (body) {
                            const newContent = document.createElement('div');
                            newContent.className = 'msg__content';
                            newContent.innerHTML = marked.parse(chunk.content);
                            body.appendChild(newContent);
                        }
                    }
                } else {
                    // 创建新的 assistant 消息容器（即使 content 为空也要创建）
                    const msgId = `msg-${Date.now()}-${Math.random()}`;
                    currentAssistantMsgId = msgId;

                    // 即使内容为空，也要记录这个 chunk（可能有 tool_calls）
                    this.messages.push({ id: msgId, role: 'assistant', text: chunk.content || '' });

                    currentAssistantMsgEl = createMsgEl('assistant', 'PAW', chunk.content || '', msgId);
                    this.dom!.messages.appendChild(currentAssistantMsgEl);
                }

                // tool_call 卡片由独立的 tool_call chunk 负责渲染，此处不重复处理
                // 仅将 metadata.tool_calls 的 id→args 映射预存，供 tool_result 查找
                if (chunk.metadata?.tool_calls) {
                    chunk.metadata.tool_calls.forEach(tc => {
                        const func = tc.function || {};
                        const args = func.arguments || '{}';
                        let parsedArgs: ToolArgs;
                        if (typeof args === 'string') {
                            try { parsedArgs = JSON.parse(args) as ToolArgs; }
                            catch { parsedArgs = {}; }
                        } else {
                            parsedArgs = args as ToolArgs;
                        }
                        toolArgsMap.set(tc.id, parsedArgs);
                    });
                }

            } else if (type === 'tool_call') {
                const body = currentAssistantMsgEl?.querySelector('.msg__body');
                
                if (chunk.content) {
                    try {
                        const tc = JSON.parse(chunk.content) as ToolCall;
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
                        toolEl.className = 'tool tool--running';
                        const toolIcon = getToolIcon(func.name || '');
                        const argsStr = typeof args === 'string' ? args : JSON.stringify(args);
                        toolEl.innerHTML = `<div class="tool__header"><span class="tool__icon-wrap">${toolIcon}</span><span class="tool__name">${func.name || ''}</span>${argsStr ? `<span class="tool__args">${argsStr}</span>` : ''}<span class="tool__meta"><span class="tool__spinner"></span></span></div>`;
                        toolEl.dataset.rawRequest = JSON.stringify(tc);

                        if (body) {
                            body.appendChild(toolEl);
                        }
                    } catch {
                        // 解析失败，跳过
                    }
                }

            } else if (type === 'tool_result') {
                toolResults.push({
                    toolCallId: chunk.metadata?.tool_call_id,
                    toolName: chunk.metadata?.name || 'unknown',
                    content: chunk.content || '',
                    display: chunk.metadata?.display,
                    success: chunk.metadata?.success ?? true
                });
            }
        });

        toolResults.forEach(result => {
            const args = toolArgsMap.get(result.toolCallId || '') || {};
            const display = result.display || getDefaultDisplay(result.content);
            const el = document.getElementById(`tool-${result.toolCallId}`);
            updateToolElement(el, result.toolName, display, result.success);
            
            // 保存原始响应数据
            if (el) {
                el.dataset.rawResponse = JSON.stringify({
                    success: result.success,
                    result: result.content
                });
            }
        });

        scrollToBottom(this.dom!.msgWrap);
        
        // 从后端获取轮次数据并渲染对话链
        this.renderChain();
        
        // 刷新 Browser URL 列表
        Browser.refresh();
        // 刷新 Planner 状态
        Planner.refresh();
    }
};
