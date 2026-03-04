// 会话管理模块

import { WebSocketManager } from './websocket.js';
import { UIStateManager, SessionInfo } from './ui-state.js';
import { DialogManager } from './dialog-manager.js';
import { ChatHistory } from './chat.js';
import { escapeHtml } from './utils.js';

export class SessionManager {
    private wsManager: WebSocketManager;
    private uiState: UIStateManager;
    private dialogManager: DialogManager;
    private historyList: HTMLElement;
    private newChatBtn: HTMLButtonElement;

    constructor(
        wsManager: WebSocketManager,
        uiState: UIStateManager,
        dialogManager: DialogManager
    ) {
        this.wsManager = wsManager;
        this.uiState = uiState;
        this.dialogManager = dialogManager;
        this.historyList = document.getElementById('history-list')!;
        this.newChatBtn = document.getElementById('new-chat-btn') as HTMLButtonElement;
    }

    init(): void {
        this.setupEventListeners();
    }

    private setupEventListeners(): void {
        this.historyList.addEventListener('click', (e: MouseEvent) => {
            const deleteBtn = (e.target as HTMLElement).closest('[data-delete]');
            if (deleteBtn) {
                e.stopPropagation();
                const sessionIdToDelete = (deleteBtn as HTMLElement).dataset.delete;
                if (!sessionIdToDelete) {
                    return;
                }

                if (sessionIdToDelete === ChatHistory.currentSessionId) {
                    this.dialogManager.showInfo('无法删除当前会话，请先切换到其它会话');
                    return;
                }

                this.dialogManager.showConfirm(
                    '确认删除',
                    '<div style="padding:0.5rem 0;color:var(--text-secondary)">确定要删除这个会话吗？此操作无法撤销。</div>',
                    () => {
                        this.wsManager.send(`/delete-session ${sessionIdToDelete}`);
                    }
                );
                return;
            }

            const item = (e.target as HTMLElement).closest('.history-item');
            if (item) {
                if (this.uiState.get('isGenerating')) {
                    this.dialogManager.showInfo('我正在回答中，可以先点 Stop 中断当前会话哦~');
                    return;
                }
                this.requestLoadSession((item as HTMLElement).dataset.id || '');
            }
        });

        this.newChatBtn.addEventListener('click', () => {
            if (this.uiState.get('isGenerating')) {
                this.dialogManager.showInfo('我正在回答中，可以先点 Stop 中断当前会话哦~');
                return;
            }
            this.wsManager.send(JSON.stringify({ type: 'create_new_chat' }));
        });
    }

    handleSessionList(data: { sessions: SessionInfo[]; current_id?: string }): void {
        const { sessions, current_id } = data;
        this.uiState.setCachedSessions(sessions || []);

        const effectiveCurrentId = current_id || ChatHistory.currentSessionId;

        this.historyList.innerHTML = '';
        sessions.forEach(s => {
            const el = document.createElement('div');
            el.className = 'history-item';
            el.dataset.id = s.session_id;
            if (s.session_id === effectiveCurrentId) {
                el.classList.add('history-item--active');
            }
            el.innerHTML = `
                <div class="history-item__title">${escapeHtml(s.title || '新对话')}</div>
                <div class="history-item__meta">${s.timestamp || ''} · ${s.message_count || 0} 消息</div>
                <span class="history-item__delete" data-delete="${s.session_id}">×</span>
            `;
            this.historyList.appendChild(el);
        });

        if (current_id) {
            ChatHistory.currentSessionId = current_id;
        }
    }

    updateSidebarHighlight(sessionId: string): void {
        this.historyList.querySelectorAll('.history-item').forEach(item => {
            item.classList.toggle('history-item--active', (item as HTMLElement).dataset.id === sessionId);
        });
    }

    requestSessionList(): void {
        this.wsManager.send('/sessions');
    }

    requestLoadSession(sessionId: string): void {
        this.wsManager.send(`/load ${sessionId}`);
    }
}
