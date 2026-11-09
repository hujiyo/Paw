// 主入口文件 - 重构版
import { $, $$ } from './modules/utils.js';
import { initMarkdown, renderMarkdown } from './modules/markdown.js';
import { ThemeColors } from './modules/theme.js';
import { createMsgEl, addSysMsg, setMessageActions } from './modules/render.js';
import { ChatHistory, DomRefs, SessionChunk } from './modules/chat.js';
import { Memory, Conversation, MemoryDomRefs } from './modules/memory.js';
import { Settings } from './modules/settings.js';
import { NewChatDialog } from './modules/new-chat.js';
import { StatusBar, SessionInfo } from './modules/store.js';
import { RightSidebar } from './modules/right-sidebar.js';
import { Planner } from './modules/planner.js';
import { Browser } from './modules/browser.js';
import { WorkspaceFilesSidebar } from './modules/workspace-files-sidebar.js';
import { Skills } from './modules/skills.js';
import { EditorSettings } from './modules/editor-settings.js';
import { WebSocketManager, installFetchAuth } from './modules/websocket.js';
import { UIStateManager } from './modules/ui-state.js';
import { DialogManager } from './modules/dialog-manager.js';
import { SessionManager } from './modules/session-manager.js';
import { ToolbarManager } from './modules/toolbar-manager.js';
import { ModeSelector } from './modules/mode-selector.js';
import { MessageHandler } from './modules/message-handler.js';
import { MessageEditor } from './modules/message-editor.js';

// ============ DOM 缓存 ============
interface DomElements {
    statusBar: HTMLElement;
    msgWrap: HTMLElement;
    messages: HTMLElement;
    memoryCanvas: HTMLElement;
    memoryEmpty: HTMLElement;
    memoryStats: HTMLElement;
    memorySearchBtn: HTMLElement;
    memoryCleanBtn: HTMLElement;
    sidebar: HTMLElement;
    viewHistory: HTMLElement;
    viewMemory: HTMLElement;
}

const dom: DomElements = {
    statusBar: $<HTMLElement>('#status-bar')!,
    msgWrap: $<HTMLElement>('#messages-wrapper')!,
    messages: $<HTMLElement>('#messages')!,
    memoryCanvas: $<HTMLElement>('#memory-canvas')!,
    memoryEmpty: $<HTMLElement>('#memory-empty')!,
    memoryStats: $<HTMLElement>('#memory-stats')!,
    memorySearchBtn: $<HTMLElement>('#memory-search-btn')!,
    memoryCleanBtn: $<HTMLElement>('#memory-clean-btn')!,
    sidebar: $<HTMLElement>('.sidebar')!,
    viewHistory: $<HTMLElement>('#view-history')!,
    viewMemory: $<HTMLElement>('#view-memory')!
};

// ============ 初始化模块 ============
installFetchAuth();
initMarkdown();

const wsManager = new WebSocketManager(`ws://${location.host}/ws`);
const uiState = new UIStateManager();
const dialogManager = new DialogManager();
const sessionManager = new SessionManager(wsManager, uiState, dialogManager);
const toolbarManager = new ToolbarManager(uiState);
const modeSelector = new ModeSelector(wsManager);
const messageHandler = new MessageHandler(wsManager, uiState, dialogManager);

Settings.init((msg: string) => wsManager.send(msg));
NewChatDialog.init((msg: string) => wsManager.send(msg));
Memory.init(dom as unknown as MemoryDomRefs, (msg: string) => wsManager.send(msg));
ChatHistory.init(dom as unknown as DomRefs);
StatusBar.init(dom.statusBar);
RightSidebar.init(uiState);
Planner.init();
Browser.init();
WorkspaceFilesSidebar.init();
Skills.init();
EditorSettings.init();

// 连接工作区文件侧边栏和右侧边栏
WorkspaceFilesSidebar.onFileOpen((path, name, content) => {
    RightSidebar.openFileTab(path, name, content);
});

// ============ 消息 → 轮次定位 ============
// 后端按"第几个用户轮次"删除，这里把 DOM 里的消息映射到轮次下标。
// 用户消息本身即一个轮次；助手消息归属于它之前最近的那个用户消息。
function resolveTurnIndex(msgId: string): number | null {
    const all = Array.from(dom.messages.querySelectorAll('[data-msg-id]')) as HTMLElement[];
    const targetIdx = all.findIndex(el => el.dataset.msgId === msgId);
    if (targetIdx < 0) return null;

    let turn = -1;
    for (let i = 0; i <= targetIdx; i++) {
        if (all[i].classList.contains('msg--user')) {
            turn += 1;
        }
    }
    return turn >= 0 ? turn : null;
}

// ============ 消息操作回调 ============
setMessageActions({
    onEdit: () => {
        if (uiState.get('isGenerating')) {
            dialogManager.showInfo('正在生成中，无法编辑对话');
            return;
        }
        MessageEditor.open();
    },
    onCopy: (text, role) => {
        console.log(`[App] Copied ${role} message`);
    },
    onDelete: (msgId, role) => {
        if (uiState.get('isGenerating')) {
            dialogManager.showInfo('正在生成中，无法删除消息');
            return;
        }

        const turnIndex = resolveTurnIndex(msgId);
        if (turnIndex === null) {
            dialogManager.showError('无法定位该消息所属的轮次，请刷新会话');
            return;
        }
        wsManager.send(`/delete-message ${turnIndex} ${role}`);
    },
    onRetry: (msgId) => {
        if (uiState.get('isGenerating')) {
            dialogManager.showInfo('正在生成中，请先停止当前回复');
            return;
        }

        const turnIndex = resolveTurnIndex(msgId);
        if (turnIndex === null) {
            dialogManager.showError('无法定位该消息所属的轮次，请刷新会话');
            return;
        }
        wsManager.send(`/retry ${turnIndex}`);
        uiState.setGenerating(true);
    },
    onContinue: (msgId) => {
        if (uiState.get('isGenerating')) {
            dialogManager.showInfo('正在生成中，请等待完成');
            return;
        }
        wsManager.send(`/continue ${msgId}`);
        uiState.setGenerating(true);
    }
});

// ============ 侧边栏标签切换 ============
$$<HTMLElement>('.sidebar__tab').forEach(tab => {
    tab.addEventListener('click', () => {
        $$<HTMLElement>('.sidebar__tab').forEach(t => t.classList.remove('sidebar__tab--active'));
        tab.classList.add('sidebar__tab--active');
        const view = tab.dataset.view;
        dom.viewHistory.classList.toggle('sidebar__view--active', view === 'history');
        dom.viewMemory.classList.toggle('sidebar__view--active', view === 'memory');
    });
});

// ============ 工具栏按钮切换主内容区视图 ============
const chatViewBtn = $<HTMLElement>('#chat-view-btn');
const skillsMarketBtn = $<HTMLElement>('#skills-market-btn');

if (chatViewBtn) {
    chatViewBtn.addEventListener('click', () => {
        Skills.hide();
        chatViewBtn.classList.add('toolbar__btn--active');
        if (skillsMarketBtn) skillsMarketBtn.classList.remove('toolbar__btn--active');
    });
}
if (skillsMarketBtn) {
    skillsMarketBtn.addEventListener('click', () => {
        Skills.show();
        if (chatViewBtn) chatViewBtn.classList.remove('toolbar__btn--active');
        skillsMarketBtn.classList.add('toolbar__btn--active');
    });
}

// ============ WebSocket 事件处理 ============
wsManager.onConnected(() => {
    wsManager.send('/sessions');
});

wsManager.on('disconnected', () => {
    dialogManager.showError('连接已断开');
});

wsManager.on('error', () => {
    dialogManager.showError('连接错误');
});

wsManager.on('assistant_stream_start', (data) => {
    messageHandler.handleStreamStart(data as { id: string });
});

wsManager.on('assistant_stream_chunk', (data) => {
    messageHandler.handleStreamChunk(data as { id: string; text?: string });
});

wsManager.on('assistant_stream_end', (data) => {
    messageHandler.handleStreamEnd(data as { id: string });
});

wsManager.on('reasoning_start', () => {
    messageHandler.handleReasoningStart();
});

wsManager.on('reasoning_chunk', (data) => {
    messageHandler.handleReasoningChunk(data as { id: string; text?: string });
});

wsManager.on('reasoning_end', () => {
    messageHandler.handleReasoningEnd();
});

wsManager.on('tool_start', (data) => {
    messageHandler.handleToolStart(data as { id: string; name: string; args: string; raw_request?: Record<string, unknown> });
});

wsManager.on('tool_result', (data) => {
    messageHandler.handleToolResult(data as { id: string; name: string; display: { abstract: string; details: Record<string, string> | null }; success: boolean; raw_response?: Record<string, unknown> });
});

wsManager.on('turn_end', () => {
    messageHandler.handleTurnEnd();
});

wsManager.on('system_message', (data) => {
    addSysMsg(dom.messages, (data as { text: string; type?: string }).text, (data as { text: string; type?: string }).type || '');
});

wsManager.on('status_update', (data) => {
    messageHandler.handleStatusUpdate(data as { model?: string; tokens?: number; [key: string]: string | number | undefined });
});

wsManager.on('show_model_selection', (data) => {
    dialogManager.showModelSelect((data as { models: string[] }).models, (model: string) => {
        wsManager.send(model);
    });
});

// 控制输入的回调只注册一次，否则每次请求都会叠加监听器导致重复发送
let controlInputHandler: ((data: unknown) => void) | null = null;
dialogManager.on('input', (value) => {
    controlInputHandler?.(value);
});

wsManager.on('request_input', (data) => {
    controlInputHandler = (value: unknown): void => {
        wsManager.send(String(value));
    };
    dialogManager.showInputPrompt((data as { prompt?: string }).prompt || '输入');
});

wsManager.on('show_memory', (data) => {
    messageHandler.handleMemoryShow(data as { conversations: Conversation[] });
});

wsManager.on('memory_result', (data) => {
    messageHandler.handleMemoryResult(data as { success: boolean; message?: string });
});

wsManager.on('session_list', (data) => {
    sessionManager.handleSessionList(data as { sessions: SessionInfo[]; current_id?: string });
});

wsManager.on('session_load', (data) => {
    messageHandler.resetTurnState();
    const loadData = data as { chunks: SessionChunk[]; mode?: string };
    ChatHistory.loadSessionChunks(loadData.chunks);
    if (loadData.mode) modeSelector.updateUI(loadData.mode);
});

wsManager.on('show_error', (data) => {
    dialogManager.showError((data as { text: string }).text);
});

wsManager.on('session_loaded', (data) => {
    const loadedData = data as { session_id?: string };
    if (loadedData.session_id) {
        ChatHistory.currentSessionId = loadedData.session_id;
        sessionManager.updateSidebarHighlight(loadedData.session_id);
    }
});

wsManager.on('new_chat', (data) => {
    messageHandler.resetTurnState();
    ChatHistory.clear();
    dom.messages.innerHTML = '';
    const newChatData = data as { session_id?: string };
    if (newChatData.session_id) {
        ChatHistory.currentSessionId = newChatData.session_id;
        sessionManager.updateSidebarHighlight(newChatData.session_id);
    }
    sessionManager.requestSessionList();
});

wsManager.on('models_fetched', (data) => {
    Settings.handleModelResponse(data as { request_id: string; models?: string[]; error?: string });
});

wsManager.on('terminal_output', (data) => {
    messageHandler.handleTerminalOutput(data as { content: string; is_open: boolean });
});

wsManager.on('todos_updated', (data) => {
    messageHandler.handleTodosUpdated(data as { todos: Array<{id: string; title: string; details?: string; status: string}> });
});

wsManager.on('mode_changed', (data) => {
    const modeData = data as { mode: string; success?: boolean };
    modeSelector.updateUI(modeData.mode);
});

// ============ 工具详情弹窗 ============
const toolDetailModal = document.getElementById('tool-detail-modal') as HTMLElement;
const toolDetailTitle = document.getElementById('tool-detail-title') as HTMLElement;
const toolDetailRequestContainer = document.getElementById('tool-detail-request') as HTMLElement;
const toolDetailResponseContainer = document.getElementById('tool-detail-response') as HTMLElement;
const toolDetailClose = document.getElementById('tool-detail-close') as HTMLElement;

function showToolDetail(toolElement: HTMLElement): void {
    if (!toolDetailModal) {
        console.error('toolDetailModal not found');
        return;
    }

    const toolName = toolElement.querySelector('.tool__name')?.textContent || '未知工具';
    const rawRequest = toolElement.dataset.rawRequest;
    const rawResponse = toolElement.dataset.rawResponse;

    if (toolDetailTitle) {
        toolDetailTitle.textContent = `工具底层详情: ${toolName}`;
    }

    const toolDetailRequest = toolDetailRequestContainer?.querySelector('pre');
    const toolDetailResponse = toolDetailResponseContainer?.querySelector('pre');

    if (toolDetailRequest) {
        if (rawRequest) {
            try {
                const requestData = JSON.parse(rawRequest);
                toolDetailRequest.textContent = JSON.stringify(requestData, null, 2);
            } catch (e) {
                toolDetailRequest.textContent = rawRequest;
            }
        } else {
            toolDetailRequest.textContent = '暂无请求数据';
        }
    }

    if (toolDetailResponse) {
        if (rawResponse) {
            try {
                const responseData = JSON.parse(rawResponse);
                toolDetailResponse.textContent = JSON.stringify(responseData, null, 2);
            } catch (e) {
                toolDetailResponse.textContent = rawResponse;
            }
        } else {
            toolDetailResponse.textContent = '暂无响应数据';
        }
    }

    toolDetailModal.classList.add('tool-detail-modal--visible');
}

function hideToolDetail(): void {
    toolDetailModal.classList.remove('tool-detail-modal--visible');
}

if (toolDetailClose) {
    toolDetailClose.addEventListener('click', hideToolDetail);
}

if (toolDetailModal) {
    toolDetailModal.addEventListener('click', (e) => {
        if (e.target === toolDetailModal) {
            hideToolDetail();
        }
    });
}

document.querySelectorAll('.tool-detail-copy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const copyType = (btn as HTMLElement).dataset.copy;
        let textToCopy = '';

        const toolDetailRequest = toolDetailRequestContainer?.querySelector('pre');
        const toolDetailResponse = toolDetailResponseContainer?.querySelector('pre');

        if (copyType === 'request' && toolDetailRequest) {
            textToCopy = toolDetailRequest.textContent || '';
        } else if (copyType === 'response' && toolDetailResponse) {
            textToCopy = toolDetailResponse.textContent || '';
        }

        if (textToCopy) {
            navigator.clipboard.writeText(textToCopy).then(() => {
                const originalText = btn.textContent;
                btn.textContent = 'Copied!';
                setTimeout(() => {
                    btn.textContent = originalText;
                }, 1500);
            });
        }
    });
});

dom.messages.addEventListener('contextmenu', (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    const toolElement = target.closest('.tool') as HTMLElement;

    if (toolElement) {
        e.preventDefault();
        showToolDetail(toolElement);
    }
});

// ============ 启动初始化 ============
toolbarManager.init();
sessionManager.init();
messageHandler.init();
modeSelector.init();

// 初始化消息编辑器
MessageEditor.init({
    onSaved: () => {
        // 编辑器保存后重新加载会话，刷新显示
        wsManager.send('/reload-session');
    }
});

// 自动调整输入框高度
const input = document.getElementById('input') as HTMLTextAreaElement;
if (input) {
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';
}
