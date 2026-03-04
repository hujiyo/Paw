// 消息处理模块

import { WebSocketManager } from './websocket.js';
import { UIStateManager } from './ui-state.js';
import { DialogManager } from './dialog-manager.js';
import { ChatHistory } from './chat.js';
import { createMsgEl, getDefaultDisplay, updateToolElement, getToolIcon } from './render.js';
import { scrollToBottom, escapeHtml } from './utils.js';
import { StatusBar } from './store.js';
import { RightSidebar } from './right-sidebar.js';
import { Browser } from './browser.js';
import { Planner } from './planner.js';
import { Memory, Conversation, MemoryResult } from './memory.js';

const renderMarkdown = (text: string): string => {
    if (typeof marked !== 'undefined' && typeof marked.parse === 'function') {
        try {
            return marked.parse(text);
        } catch (err) {
            console.error('[MessageHandler] Failed to parse markdown chunk:', err);
        }
    }
    return text.replace(/\n/g, '<br>');
};

interface StreamData {
    id: string;
    text?: string;
}

interface ToolStartData {
    id: string;
    name: string;
    args: string;
    raw_request?: Record<string, unknown>;
}

interface ToolResultData {
    id: string;
    name: string;
    display: {
        abstract: string;
        details: Record<string, string> | null;
    };
    success: boolean;
    raw_response?: Record<string, unknown>;
}

interface StatusData {
    model?: string;
    tokens?: number;
    [key: string]: string | number | undefined;
}

export class MessageHandler {
    private wsManager: WebSocketManager;
    private uiState: UIStateManager;
    private dialogManager: DialogManager;
    private messages: HTMLElement;
    private msgWrap: HTMLElement;
    private input: HTMLTextAreaElement;
    private sendBtn: HTMLButtonElement;
    private terminalStatus: HTMLElement;
    private terminalContent: HTMLElement;
    private terminalOutput: HTMLElement;

    constructor(
        wsManager: WebSocketManager,
        uiState: UIStateManager,
        dialogManager: DialogManager
    ) {
        this.wsManager = wsManager;
        this.uiState = uiState;
        this.dialogManager = dialogManager;
        this.messages = document.getElementById('messages')!;
        this.msgWrap = document.getElementById('messages-wrapper')!;
        this.input = document.getElementById('input') as HTMLTextAreaElement;
        this.sendBtn = document.getElementById('send-btn') as HTMLButtonElement;
        this.terminalStatus = document.getElementById('terminal-status')!;
        this.terminalContent = document.getElementById('terminal-content')!;
        this.terminalOutput = document.getElementById('terminal-output')!;
    }

    init(): void {
        this.setupEventListeners();
    }

    private setupEventListeners(): void {
        const form = document.getElementById('input-form') as HTMLFormElement;

        form.addEventListener('submit', (e: Event) => {
            e.preventDefault();
            this.handleSubmit();
        });

        this.input.addEventListener('keydown', (e: KeyboardEvent) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSubmit();
            }
        });

        this.input.addEventListener('input', () => {
            this.autoResize();
        });
    }

    private handleSubmit(): void {
        if (this.uiState.get('isGenerating')) {
            this.wsManager.send('/stop');
            return;
        }

        const msg = this.input.value.trim();
        if (!msg) return;

        const isCommand = msg.startsWith('/');
        this.wsManager.send(msg);

        if (!isCommand) {
            ChatHistory.addUserMessage(msg);
            this.setGeneratingState(true);
        }

        this.input.value = '';
        this.autoResize();
    }

    private autoResize(): void {
        this.input.style.height = 'auto';
        this.input.style.height = this.input.scrollHeight + 'px';
    }

    private setGeneratingState(generating: boolean): void {
        this.uiState.setGenerating(generating);
        if (generating) {
            this.sendBtn.textContent = 'Stop';
            this.sendBtn.classList.add('button--stop');
        } else {
            this.sendBtn.textContent = 'Send';
            this.sendBtn.classList.remove('button--stop');
        }
    }

    handleStreamStart(data: StreamData): void {
        ChatHistory.isInAssistantTurn = true;
        this.startStream(data.id);
    }

    handleStreamChunk(data: StreamData): void {
        this.appendStream(data.id, data.text || '');
    }

    handleStreamEnd(data: StreamData): void {
        this.endStream(data.id);
    }

    private startStream(id: string): void {
        this.uiState.startStream(id);

        let msgEl = this.messages.querySelector('.msg--assistant:last-child');

        if (!msgEl) {
            msgEl = createMsgEl('assistant', 'PAW', '', id);
            this.messages.appendChild(msgEl);
        }

        const body = msgEl.querySelector('.msg__body');
        const uniqueId = `stream-${id}`;
        const content = document.createElement('div');
        content.className = 'msg__content';
        content.id = uniqueId;

        if (body) {
            body.appendChild(content);
        }

        this.uiState.set('currentContentEl', content);
        ChatHistory.onStreamStart(id);
    }

    private appendStream(id: string, text: string): void {
        const content = this.uiState.get('currentContentEl');

        if (!content) {
            console.warn('[appendStream] No current content element, ignoring chunk');
            return;
        }

        this.uiState.appendStream(text);
        const streamBuf = this.uiState.get('streamBuf');
        content.innerHTML = renderMarkdown(streamBuf);
        scrollToBottom(this.msgWrap);
    }

    private endStream(id: string): void {
        const content = this.uiState.get('currentContentEl');

        if (!content) {
            console.warn('[endStream] No current content element');
            return;
        }

        content.querySelectorAll('pre code').forEach(el => {
            const pre = el.parentElement;
            if (!pre) return;
            const btn = document.createElement('button');
            btn.className = 'copy-btn';
            btn.textContent = 'Copy';
            btn.onclick = (): void => {
                navigator.clipboard.writeText(el.textContent || '');
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy', 2000);
            };
            pre.appendChild(btn);
        });

        const streamBuf = this.uiState.get('streamBuf');
        ChatHistory.onStreamEnd(streamBuf);

        Browser.refresh();
        this.uiState.endStream();
    }

    handleToolStart(data: ToolStartData): void {
        if (this.uiState.get('rightSidebarVisible')) {
            if (['read_files', 'edit_files', 'create_file', 'file_glob'].includes(data.name)) {
                RightSidebar.switchView('files');
            } else if (['run_shell_command'].includes(data.name)) {
                RightSidebar.switchView('terminal');
            } else if (['create_plan', 'edit_plans', 'create_todo_list', 'add_todos', 'mark_todo_as_done', 'read_todos'].includes(data.name)) {
                RightSidebar.switchView('plan');
            } else if (['search_web', 'load_url_content', 'read_page'].includes(data.name)) {
                RightSidebar.switchToTab('browser');
                Browser.refresh();
            }
        }

        if (data.name === 'stay_silent') {
            const msgEl = this.messages.querySelector('.msg--assistant:last-child');
            if (msgEl) msgEl.remove();
            ChatHistory.isInAssistantTurn = false;
            this.setGeneratingState(false);
            return;
        }

        const el = document.createElement('div');
        el.id = `tool-${data.id}`;
        el.className = 'tool tool--running';
        el.dataset.startTime = String(Date.now());
        const icon = getToolIcon(data.name);
        el.innerHTML = `<div class="tool__header"><span class="tool__icon-wrap">${icon}</span><span class="tool__name">${escapeHtml(data.name)}</span>${data.args ? `<span class="tool__args">${escapeHtml(data.args)}</span>` : ''}<span class="tool__meta"><span class="tool__spinner"></span></span></div>`;

        if (data.raw_request) {
            el.dataset.rawRequest = JSON.stringify(data.raw_request);
        }

        let msgEl = this.messages.querySelector('.msg--assistant:last-child');

        if (!msgEl) {
            msgEl = createMsgEl('assistant', 'PAW', '', `msg-${Date.now()}`);
            this.messages.appendChild(msgEl);
        }

        const body = msgEl.querySelector('.msg__body');
        if (body) {
            body.appendChild(el);
        } else {
            msgEl.appendChild(el);
        }

        ChatHistory.addTool(data.id, data.name);
        scrollToBottom(this.msgWrap);

        if (['create_todo_list', 'add_todos', 'mark_todo_as_done'].includes(data.name)) {
            Planner.refresh();
        }
    }

    handleToolResult(data: ToolResultData): void {
        const el = document.getElementById(`tool-${data.id}`);
        if (!el) return;

        if (data.name === 'stay_silent') {
            const msgEl = el.closest('.msg--assistant');
            if (msgEl) msgEl.remove();
            ChatHistory.isInAssistantTurn = false;
            return;
        }

        console.log('[updateTool] name:', data.name, 'display:', JSON.stringify(data.display));
        let finalDisplay = data.display;
        if (!finalDisplay || !finalDisplay.abstract) {
            let resultText = '';
            if (data.raw_response) {
                if (data.raw_response.result !== undefined) resultText = String(data.raw_response.result);
                else if (data.raw_response.error !== undefined) resultText = String(data.raw_response.error);
                else if (data.raw_response.content !== undefined) resultText = String(data.raw_response.content);
            }
            finalDisplay = getDefaultDisplay(resultText);
        }

        updateToolElement(el, data.name, finalDisplay, data.success);

        if (data.raw_response) {
            el.dataset.rawResponse = JSON.stringify(data.raw_response);
        }

        if (['create_todo_list', 'add_todos', 'read_todos', 'mark_todo_as_done'].includes(data.name)) {
            Planner.refresh();
        }

        if (['search_web', 'load_url_content', 'read_page'].includes(data.name) && data.success) {
            console.log(`[App] Tool ${data.name} finished, refreshing Browser...`);
            Browser.refresh();
        }
    }

    handleTurnEnd(): void {
        ChatHistory.isInAssistantTurn = false;
        ChatHistory.endAssistantTurn();
        this.setGeneratingState(false);
    }

    handleStatusUpdate(data: StatusData): void {
        StatusBar.update(data as Record<string, string | number>);
    }

    handleTerminalOutput(data: { content: string; is_open: boolean }): void {
        this.terminalStatus.textContent = data.is_open ? '运行中' : '未打开';
        this.terminalStatus.classList.toggle('workspace-header__status--active', data.is_open);

        this.terminalContent.textContent = data.content;

        this.terminalOutput.scrollTop = this.terminalOutput.scrollHeight;
    }

    handleTodosUpdated(data: { todos: Array<{id: string; title: string; details?: string; status: string}> }): void {
        const items = data.todos.map(t => ({
            id: t.id,
            text: t.title,
            details: t.details,
            done: t.status === 'completed'
        }));

        Planner.setItems(items);
    }

    handleMemoryShow(data: { conversations: Conversation[] }): void {
        Memory.show(data.conversations);
    }

    handleMemoryResult(data: MemoryResult): void {
        Memory.handleResult(data);
    }
}
