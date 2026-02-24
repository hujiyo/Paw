// 主入口文件
import { $, $$, initMarkdown, scrollToBottom, escapeHtml } from './modules/utils.js';
import { ThemeColors } from './modules/theme.js';
import { createMsgEl, addSysMsg, updateToolElement, renderModalContent, getDefaultDisplay, setMessageActions, getToolIcon } from './modules/render.js';
import { ChatHistory, DomRefs, SessionChunk } from './modules/chat.js';
import { Memory, Conversation, MemoryResult, MemoryDomRefs } from './modules/memory.js';
import { Settings } from './modules/settings.js';
import { NewChatDialog } from './modules/new-chat.js';
import { AppState, StatusBar, SessionInfo } from './modules/store.js';
import { RightSidebar } from './modules/right-sidebar.js';
import { FileExplorer } from './modules/file-explorer.js';
import { Planner } from './modules/planner.js';
import { Browser } from './modules/browser.js';
import { WorkspaceFilesSidebar } from './modules/workspace-files-sidebar.js';
import { Skills } from './modules/skills.js';
import { EditorSettings } from './modules/editor-settings.js';

// ============ 类型定义 ============

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

interface StreamData {
    id: string;
    text?: string;
}

interface StatusData {
    model?: string;
    tokens?: number;
    [key: string]: string | number | undefined;
}

interface SessionListData {
    sessions: SessionInfo[];
    current_id?: string;
}

interface SessionLoadData {
    chunks: SessionChunk[];
    mode?: string;
}

interface SessionLoadedData {
    session_id?: string;
}

interface NewChatData {
    session_id?: string;
}

interface ModelsFetchedData {
    request_id: string;
    models?: string[];
    error?: string;
}

interface InputPromptData {
    prompt?: string;
}

interface WebSocketEvent {
    event: string;
    data: unknown;
}

// ============ 配置 ==========
const LOGO = `██████╗    █████╗   ██╗    ██╗
██╔══██╗  ██╔══██╗  ██║ █╗ ██║
██████╔╝  ███████║  ██║███╗██║
██╔═══╝   ██╔══██║  ╚███╔███╔╝
╚═╝       ╚═╝  ╚═╝   ╚══╝╚══╝ `;

// ============ DOM 缓存 ============
interface DomElements {
    statusBar: HTMLElement;
    msgWrap: HTMLElement;
    messages: HTMLElement;
    form: HTMLFormElement;
    input: HTMLTextAreaElement;
    sendBtn: HTMLButtonElement;
    modal: HTMLElement;
    modalTitle: HTMLElement;
    modalBody: HTMLElement;
    modalActions: HTMLElement;
    modalOk: HTMLButtonElement;
    historyList: HTMLElement;
    historyEmpty: HTMLElement;
    newChatBtn: HTMLButtonElement;
    viewHistory: HTMLElement;
    viewMemory: HTMLElement;
    // Memory
    memoryCanvas: HTMLElement;
    memoryEmpty: HTMLElement;
    memoryStats: HTMLElement;
    memorySearchBtn: HTMLElement;
    memoryCleanBtn: HTMLElement;
    sidebar: HTMLElement;
    sidebarRight: HTMLElement;
    main: HTMLElement;
    toggleSidebarBtn: HTMLElement;
    toggleRightSidebarBtn: HTMLElement;
    toggleWorkspaceFilesSidebarBtn: HTMLElement;
    newChatToolbarBtn: HTMLElement;
    toolbarDivider: HTMLElement;
    // 工作区终端输出
    terminalStatus: HTMLElement;
    terminalContent: HTMLElement;
    terminalOutput: HTMLElement;
    // 确认弹窗
    confirmModal: HTMLElement;
    confirmTitle: HTMLElement;
    confirmBody: HTMLElement;
    confirmCancel: HTMLButtonElement;
    confirmOk: HTMLButtonElement;
}

const dom: DomElements = {
    statusBar: $<HTMLElement>('#status-bar')!,
    msgWrap: $<HTMLElement>('#messages-wrapper')!,
    messages: $<HTMLElement>('#messages')!,
    form: $<HTMLFormElement>('#input-form')!,
    input: $<HTMLTextAreaElement>('#input')!,
    sendBtn: $<HTMLButtonElement>('#send-btn')!,
    // Modal related
    modal: $<HTMLElement>('#modal')!,
    modalTitle: $<HTMLElement>('#modal-title')!,
    modalBody: $<HTMLElement>('#modal-body')!,
    modalActions: $<HTMLElement>('#modal-actions')!,
    modalOk: $<HTMLButtonElement>('#modal-ok')!,
    // Views
    historyList: $<HTMLElement>('#history-list')!,
    historyEmpty: $<HTMLElement>('#history-empty')!,
    newChatBtn: $<HTMLButtonElement>('#new-chat-btn')!,
    viewHistory: $<HTMLElement>('#view-history')!,
    viewMemory: $<HTMLElement>('#view-memory')!,
    // Memory
    memoryCanvas: $<HTMLElement>('#memory-canvas')!,
    memoryEmpty: $<HTMLElement>('#memory-empty')!,
    memoryStats: $<HTMLElement>('#memory-stats')!,
    memorySearchBtn: $<HTMLElement>('#memory-search-btn')!,
    memoryCleanBtn: $<HTMLElement>('#memory-clean-btn')!,
    // Layout
    sidebar: $<HTMLElement>('.sidebar')!,
    sidebarRight: $<HTMLElement>('#sidebar-right')!,
    main: $<HTMLElement>('.main')!,
    toggleSidebarBtn: $<HTMLElement>('#toggle-sidebar')!,
    toggleRightSidebarBtn: $<HTMLElement>('#toggle-right-sidebar')!,
    toggleWorkspaceFilesSidebarBtn: $<HTMLElement>('#toggle-workspace-files-sidebar')!,
    newChatToolbarBtn: $<HTMLElement>('#new-chat-toolbar')!,
    toolbarDivider: $<HTMLElement>('#toolbar-divider')!,
    // 工作区终端输出
    terminalStatus: $<HTMLElement>('#terminal-status')!,
    terminalContent: $<HTMLElement>('#terminal-content')!,
    terminalOutput: $<HTMLElement>('#terminal-output')!,
    // 确认弹窗
    confirmModal: $<HTMLElement>('#confirm-modal')!,
    confirmTitle: $<HTMLElement>('#confirm-title')!,
    confirmBody: $<HTMLElement>('#confirm-body')!,
    confirmCancel: $<HTMLButtonElement>('#confirm-cancel')!,
    confirmOk: $<HTMLButtonElement>('#confirm-ok')!
};

// ============ WebSocket ============
const ws = new WebSocket(`ws://${location.host}/ws`);

function send(msg: string): void {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(msg);
    } else {
        showErrorDialog('未连接到服务器');
    }
}

// ============ 初始化模块 ============
initMarkdown();
Settings.init(send);
NewChatDialog.init(send);
Memory.init(dom as unknown as MemoryDomRefs, send);
ChatHistory.init(dom as unknown as DomRefs);
StatusBar.init(dom.statusBar);
RightSidebar.init();
FileExplorer.init();
Planner.init();
Browser.init();
WorkspaceFilesSidebar.init();
Skills.init();
EditorSettings.init();

// 连接工作区文件侧边栏和右侧边栏：点击文件时在右侧边栏打开标签页
WorkspaceFilesSidebar.onFileOpen((path, name, content) => {
    RightSidebar.openFileTab(path, name, content);
});

// ============ 消息操作回调 ============
// 注意：轮次数据现在由后端统一管理，前端不再维护 turns 列表
setMessageActions({
    onCopy: (text, role) => {
        console.log(`[App] Copied ${role} message`);
    },
    onDelete: (msgId, role) => {
        if (AppState.isGenerating) {
            showInfoDialog('正在生成中，无法删除消息');
            return;
        }
        
        // 从前端状态与 DOM 中移除指定消息（避免清空历史记录）
        const msgIdx = ChatHistory.messages.findIndex(m => m.id === msgId);
        if (msgIdx >= 0) {
            ChatHistory.messages.splice(msgIdx, 1);
        }

        const msgEl = dom.messages.querySelector(`[data-msg-id="${msgId}"]`);
        msgEl?.remove();
        
        // 通知后端删除消息，后端处理完成后会通过 turns_updated 事件刷新对话链
        send(`/delete-message ${msgId} ${role}`);
        // 立即刷新对话链（后端数据）
        ChatHistory.renderChain();
        
        // 刷新 Browser URL 列表 (移除已删除消息中的 URL)
        Browser.refresh();
        // 刷新 Planner 状态
        Planner.refresh();
    },
    onRetry: (msgId) => {
        if (AppState.isGenerating) {
            showInfoDialog('正在生成中，请先停止当前回复');
            return;
        }

        // 从前端状态与 DOM 中移除指定消息（避免清空历史记录）
        const msgIdx = ChatHistory.messages.findIndex(m => m.id === msgId);
        if (msgIdx >= 0) {
            ChatHistory.messages.splice(msgIdx, 1);
        }

        const msgEl = dom.messages.querySelector(`[data-msg-id="${msgId}"]`);
        msgEl?.remove();

        // 发送重试命令，后端会重新生成
        send(`/retry ${msgId}`);
        setGeneratingState(true);
        // 立即刷新对话链（后端数据）
        ChatHistory.renderChain();
        
        // 刷新 Browser URL 列表
        Browser.refresh();
        // 刷新 Planner 状态
        Planner.refresh();
    },
    onContinue: (msgId) => {
        if (AppState.isGenerating) {
            showInfoDialog('正在生成中，请等待完成');
            return;
        }
        // 发送继续命令
        send(`/continue ${msgId}`);
        setGeneratingState(true);
    }
});

// ============ 工具栏功能 ============

// 更新工具栏按钮可见性（左右侧边栏互斥）
function updateToolbarVisibility(): void {
    // 左侧边栏打开时，隐藏右侧边栏按钮
    dom.toggleRightSidebarBtn.style.display = AppState.sidebarVisible ? 'none' : '';
    // 右侧边栏打开时，隐藏左侧边栏按钮和新建会话按钮，显示工作区文件目录侧边栏按钮
    dom.toggleSidebarBtn.style.display = AppState.rightSidebarVisible ? 'none' : '';
    dom.newChatToolbarBtn.style.display = AppState.rightSidebarVisible ? 'none' : '';
    dom.toolbarDivider.style.display = AppState.rightSidebarVisible ? 'none' : '';
    // 工作区文件目录侧边栏按钮：只在右侧边栏打开时显示
    dom.toggleWorkspaceFilesSidebarBtn.style.display = AppState.rightSidebarVisible ? '' : 'none';
}

function toggleSidebar(): void {
    AppState.sidebarVisible = !AppState.sidebarVisible;
    dom.sidebar.classList.toggle('sidebar--hidden', !AppState.sidebarVisible);
    dom.main.classList.toggle('main--full-width', !AppState.sidebarVisible);
    dom.toggleSidebarBtn.classList.toggle('toolbar__btn--active', AppState.sidebarVisible);
    updateToolbarVisibility();
    localStorage.setItem('paw-sidebar-visible', String(AppState.sidebarVisible));
}

function toggleRightSidebar(): void {
    AppState.rightSidebarVisible = !AppState.rightSidebarVisible;
    dom.sidebarRight.classList.toggle('sidebar-right--visible', AppState.rightSidebarVisible);
    dom.main.classList.toggle('main--with-right-sidebar', AppState.rightSidebarVisible);
    dom.toggleRightSidebarBtn.classList.toggle('toolbar__btn--active', AppState.rightSidebarVisible);
    updateToolbarVisibility();
    localStorage.setItem('paw-right-sidebar-visible', String(AppState.rightSidebarVisible));
}

function initSidebarState(): void {
    AppState.init();
    // 右侧边栏状态
    const savedRightSidebar = localStorage.getItem('paw-right-sidebar-visible');
    AppState.rightSidebarVisible = savedRightSidebar === 'true';
    
    // 左右侧边栏互斥：如果右侧边栏打开，则左侧必须关闭
    if (AppState.rightSidebarVisible) {
        AppState.sidebarVisible = false;
    }
    
    dom.sidebar.classList.toggle('sidebar--hidden', !AppState.sidebarVisible);
    dom.main.classList.toggle('main--full-width', !AppState.sidebarVisible);
    dom.toggleSidebarBtn.classList.toggle('toolbar__btn--active', AppState.sidebarVisible);
    
    dom.sidebarRight.classList.toggle('sidebar-right--visible', AppState.rightSidebarVisible);
    dom.main.classList.toggle('main--with-right-sidebar', AppState.rightSidebarVisible);
    dom.toggleRightSidebarBtn.classList.toggle('toolbar__btn--active', AppState.rightSidebarVisible);
    
    updateToolbarVisibility();
}

dom.toggleSidebarBtn.addEventListener('click', toggleSidebar);
dom.toggleRightSidebarBtn.addEventListener('click', toggleRightSidebar);
dom.newChatToolbarBtn.addEventListener('click', () => dom.newChatBtn.click());

document.addEventListener('keydown', (e: KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
        e.preventDefault();
        toggleRightSidebar();
    }
});

initSidebarState();

// ============ 视图切换 ============

// 侧边栏标签切换（历史/记忆）
$$<HTMLElement>('.sidebar__tab').forEach(tab => {
    tab.addEventListener('click', () => {
        $$<HTMLElement>('.sidebar__tab').forEach(t => t.classList.remove('sidebar__tab--active'));
        tab.classList.add('sidebar__tab--active');
        const view = tab.dataset.view;
        dom.viewHistory.classList.toggle('sidebar__view--active', view === 'history');
        dom.viewMemory.classList.toggle('sidebar__view--active', view === 'memory');
    });
});

// 工具栏按钮切换主内容区视图（消息/Skills）
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
ws.onopen = (): void => {
    ws.send('/sessions'); // 请求会话列表
};
ws.onclose = (): void => showErrorDialog('连接已断开');
ws.onerror = (): void => showErrorDialog('连接错误');
ws.onmessage = (e: MessageEvent): void => handleEvent(JSON.parse(e.data) as WebSocketEvent);

function handleEvent({ event, data }: WebSocketEvent): void {
    const handlers: Record<string, () => void> = {
        'assistant_stream_start': () => {
            ChatHistory.isInAssistantTurn = true;
            startStream((data as StreamData).id);
        },
        'assistant_stream_chunk': () => appendStream((data as StreamData).id, (data as StreamData).text || ''),
        'assistant_stream_end': () => endStream((data as StreamData).id),
        'tool_start': () => createTool(data as ToolStartData),
        'tool_result': () => updateTool(data as ToolResultData),
        'turn_end': () => {
            ChatHistory.isInAssistantTurn = false;
            ChatHistory.endAssistantTurn();
            setGeneratingState(false);
        },
        'system_message': () => addSysMsg(dom.messages, (data as { text: string; type?: string }).text, (data as { text: string; type?: string }).type || ''),
        'status_update': () => updateStatus(data as StatusData),
        'show_model_selection': () => showModelSelect((data as { models: string[] }).models),
        'request_input': () => showInputPrompt(data as InputPromptData),
        'show_memory': () => Memory.show((data as { conversations: Conversation[] }).conversations),
        'memory_result': () => Memory.handleResult(data as MemoryResult),
        'session_list': () => handleSessionList(data as SessionListData),
        'session_load': () => {
            const loadData = data as SessionLoadData;
            ChatHistory.loadSessionChunks(loadData.chunks);
            if (loadData.mode) updateModeUI(loadData.mode);
        },
        'show_error': () => showErrorDialog((data as { text: string }).text),
        'session_loaded': () => {
            const loadedData = data as SessionLoadedData;
            if (loadedData.session_id) {
                ChatHistory.currentSessionId = loadedData.session_id;
                updateSidebarHighlight(loadedData.session_id);
            }
        },
        'new_chat': () => {
            ChatHistory.clear();
            dom.messages.innerHTML = '';
            const newChatData = data as NewChatData;
            if (newChatData.session_id) {
                ChatHistory.currentSessionId = newChatData.session_id;
                updateSidebarHighlight(newChatData.session_id);
            }
            requestSessionList();
        },
        'models_fetched': () => Settings.handleModelResponse(data as ModelsFetchedData),
        'terminal_output': () => updateTerminalOutput(data as { content: string; is_open: boolean }),
        'todos_updated': () => handleTodosUpdated(data as { todos: Array<{id: string; title: string; details?: string; status: string}> }),
        'mode_changed': () => {
            const modeData = data as { mode: string; success?: boolean };
            updateModeUI(modeData.mode);
        }
    };
    handlers[event]?.();
}

// ============ 终端输出处理 ============
function updateTerminalOutput({ content, is_open }: { content: string; is_open: boolean }): void {
    // 更新状态标签
    dom.terminalStatus.textContent = is_open ? '运行中' : '未打开';
    dom.terminalStatus.classList.toggle('workspace-header__status--active', is_open);
    
    // 更新终端内容
    dom.terminalContent.textContent = content;
    
    // 自动滚动到底部
    dom.terminalOutput.scrollTop = dom.terminalOutput.scrollHeight;
}

// ============ Todo 列表更新处理 ============
function handleTodosUpdated({ todos }: { todos: Array<{id: string; title: string; details?: string; status: string}> }): void {
    // 将后端推送的 todo 列表转换为 Planner 需要的格式
    const items = todos.map(t => ({
        id: t.id,
        text: t.title,
        details: t.details,
        done: t.status === 'completed'
    }));
    
    // 直接设置 Planner 状态（不需要从 DOM 解析）
    Planner.setItems(items);
}

// ============ 流式处理逻辑 ============
//
// 【架构设计 - 强制遵循后端的 turns 定义】
//
// **核心原则：一个 assistant turn = 前端的一个【PAW】消息容器**
//
// 后端 chunk_system.py 中的 get_turns() 定义了消息轮次结构：
// - 一个 assistant turn 从第一个 ASSISTANT chunk 开始
// - 包含所有后续的 TOOL_CALL 和 TOOL_RESULT chunks
// - 直到遇到下一个 USER chunk 为止
//
// 前端必须遵循的渲染规则：
// 1. 消息容器复用：必须复用最后一个 .msg--assistant 元素
// 2. 创建新容器的时机：只有完全不存在时才创建新的【PAW】消息
// 3. 内容块追加：所有文本块、工具都在同一个【PAW】消息的 body 中
// 4. 绝对禁止：因为系统消息、工具调用等原因创建新的 assistant 消息
//
// 验证标准：
// - 用户刷新页面后，看到的消息结构应该和运行时完全一致
// - 一个 assistant turn 只有一个【PAW】标记
// - 所有内容（文本、工具）都在这个【PAW】消息内
//
// =============================================================

function startStream(id: string): void {
    AppState.streamId = id;
    AppState.streamBuf = '';

    // 后端每次 print_assistant 都发送 assistant_stream_start
    // 前端逻辑：必须复用最后一个 assistant 消息容器
    let msgEl = dom.messages.querySelector('.msg--assistant:last-child');

    if (!msgEl) {
        // 只有在完全不存在时才创建新的【PAW】消息
        // 这是新的 assistant turn 的开始
        msgEl = createMsgEl('assistant', 'PAW', '', id);
        dom.messages.appendChild(msgEl);
    }
    // 否则必须复用现有的【PAW】消息，追加内容到其中

    // 为这次流式输出创建新的内容块（每次都有独立容器）
    // 注意：内容块（.msg__content）和消息容器（.msg--assistant）是不同层级
    const body = msgEl.querySelector('.msg__body');
    const uniqueId = `stream-${id}`;
    const content = document.createElement('div');
    content.className = 'msg__content';
    content.id = uniqueId;

    // 直接追加到 body 末尾
    if (body) {
        body.appendChild(content);
    }

    // 保存当前内容块引用，供 appendStream 使用
    AppState.currentContentEl = content;
    ChatHistory.onStreamStart(id);
}

function appendStream(id: string, text: string): void {
    // 追加到 startStream 中创建的内容块
    const content = AppState.currentContentEl;

    if (!content) {
        // 理论上不应该到达这里（startStream 会先被调用）
        console.warn('[appendStream] No current content element, ignoring chunk');
        return;
    }

    AppState.streamBuf += text;
    content.innerHTML = marked.parse(AppState.streamBuf);
    scrollToBottom(dom.msgWrap);
}

function endStream(id: string): void {
    // 使用 startStream 中保存的内容块引用
    const content = AppState.currentContentEl;

    if (!content) {
        console.warn('[endStream] No current content element');
        return;
    }

    // 添加代码复制按钮
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

    ChatHistory.onStreamEnd(AppState.streamBuf);

    // 消息结束后刷新 Browser URL 列表
    Browser.refresh();
    AppState.streamId = null;
    AppState.streamBuf = '';
    AppState.currentContentEl = null; // 清理引用
}

// ============ 工具渲染逻辑 ============
//
// 【架构设计 - 工具调用属于同一个 assistant turn】
//
// **核心原则：工具调用和结果必须追加到当前 assistant 消息中**
//
// 根据后端的 turns 定义，一个 assistant turn 包含：
// - ASSISTANT chunks（文本内容）
// - TOOL_CALL chunks（工具调用）
// - TOOL_RESULT chunks（工具结果）
//
// 前端渲染规则：
// 1. 工具元素必须追加到最后一个 .msg--assistant 消息的 body 中
// 2. 只有在完全不存在 assistant 消息时才创建新的【PAW】消息
// 3. 工具和文本内容在同一个消息容器内，只是不同的内容块
// 4. 绝对禁止：为工具调用创建独立的【PAW】消息
//
// =============================================================

function createTool({ id, name, args, raw_request }: ToolStartData): void {
    // Context-Aware Focus Switching - 只在右侧边栏已经打开时切换标签，不强制打开
    if (AppState.rightSidebarVisible) {
        if (['read_files', 'edit_files', 'create_file', 'file_glob'].includes(name)) {
            RightSidebar.switchView('files');
        } else if (['run_shell_command'].includes(name)) {
            RightSidebar.switchView('terminal');
        } else if (['create_plan', 'edit_plans', 'create_todo_list', 'add_todos', 'mark_todo_as_done', 'read_todos'].includes(name)) {
            RightSidebar.switchView('plan');
        } else if (['search_web', 'load_url_content', 'read_page'].includes(name)) {
            RightSidebar.switchToTab('browser');
            Browser.refresh();
        }
    }

    if (name === 'stay_silent') {
        const msgEl = dom.messages.querySelector('.msg--assistant:last-child');
        if (msgEl) msgEl.remove();
        ChatHistory.isInAssistantTurn = false;
        setGeneratingState(false);
        return;
    }

    const el = document.createElement('div');
    el.id = `tool-${id}`;
    el.className = 'tool tool--running';
    el.dataset.startTime = String(Date.now());
    const icon = getToolIcon(name);
    el.innerHTML = `<div class="tool__header"><span class="tool__icon-wrap">${icon}</span><span class="tool__name">${escapeHtml(name)}</span>${args ? `<span class="tool__args">${escapeHtml(args)}</span>` : ''}<span class="tool__meta"><span class="tool__spinner"></span></span></div>`;

    // 存储原始请求数据
    if (raw_request) {
        el.dataset.rawRequest = JSON.stringify(raw_request);
    }

    // 前端逻辑：有 assistant 消息就追加，没有就创建（不猜测）
    let msgEl = dom.messages.querySelector('.msg--assistant:last-child');

    if (!msgEl) {
        // 没有 assistant 消息，创建新的
        msgEl = createMsgEl('assistant', 'PAW', '', `msg-${Date.now()}`);
        dom.messages.appendChild(msgEl);
    }

    // 追加工具到消息体（在操作按钮之前）
    const body = msgEl.querySelector('.msg__body');
    if (body) {
        body.appendChild(el);
    } else {
        // 兼容旧结构（不应该到达这里）
        msgEl.appendChild(el);
    }

    ChatHistory.addTool(id, name);
    scrollToBottom(dom.msgWrap);
    
    // 如果是 Todo 工具，尝试刷新 Planner (从 request 解析)
    if (['create_todo_list', 'add_todos', 'mark_todo_as_done'].includes(name)) {
        Planner.refresh();
    }
}

function updateTool({ id, name, display, success, raw_response }: ToolResultData): void {
    const el = document.getElementById(`tool-${id}`);
    if (!el) return;

    if (name === 'stay_silent') {
        const msgEl = el.closest('.msg--assistant');
        if (msgEl) msgEl.remove();
        ChatHistory.isInAssistantTurn = false;
        return;
    }

    // 后端已计算好 display，直接使用
    // 如果后端没有提供 display，使用默认降级处理
    console.log('[updateTool] name:', name, 'display:', JSON.stringify(display));
    let finalDisplay = display;
    if (!finalDisplay || !finalDisplay.abstract) {
        let resultText = '';
        if (raw_response) {
            if (raw_response.result !== undefined) resultText = String(raw_response.result);
            else if (raw_response.error !== undefined) resultText = String(raw_response.error);
            else if (raw_response.content !== undefined) resultText = String(raw_response.content);
        }
        finalDisplay = getDefaultDisplay(resultText);
    }

    updateToolElement(el, name, finalDisplay, success);

    // 存储原始响应数据
    if (raw_response) {
        el.dataset.rawResponse = JSON.stringify(raw_response);
    }
    
    // 如果是 Todo 工具，刷新 Planner 视图
    if (['create_todo_list', 'add_todos', 'read_todos', 'mark_todo_as_done'].includes(name)) {
        Planner.refresh();
    }

    // 工具结果收到后，刷新 Browser URL 列表
    if (['search_web', 'load_url_content', 'read_page'].includes(name) && success) {
        console.log(`[App] Tool ${name} finished, refreshing Browser...`);
        Browser.refresh();
    }
}

// ============ 会话管理 ============
function handleSessionList({ sessions, current_id }: SessionListData): void {
    AppState.cachedSessions = sessions || [];
    
    // 确定要使用的 currentSessionId：优先使用后端传来的 current_id，否则保留现有值
    const effectiveCurrentId = current_id || ChatHistory.currentSessionId;
    
    dom.historyList.innerHTML = '';
    sessions.forEach(s => {
        const el = document.createElement('div');
        el.className = 'history-item';
        el.dataset.id = s.session_id;
        if (s.session_id === effectiveCurrentId) el.classList.add('history-item--active');
        el.innerHTML = `
            <div class="history-item__title">${escapeHtml(s.title || '新对话')}</div>
            <div class="history-item__meta">${s.timestamp || ''} · ${s.message_count || 0} 消息</div>
            <span class="history-item__delete" data-delete="${s.session_id}">×</span>
        `;
        dom.historyList.appendChild(el);
    });
    
    // 只有当 current_id 有效时才更新 ChatHistory.currentSessionId
    if (current_id) {
        ChatHistory.currentSessionId = current_id;
    }
}

function updateSidebarHighlight(sessionId: string): void {
    dom.historyList.querySelectorAll('.history-item').forEach(item => {
        item.classList.toggle('history-item--active', (item as HTMLElement).dataset.id === sessionId);
    });
}

function requestSessionList(): void {
    ws.send('/sessions');
}

function requestLoadSession(sessionId: string): void {
    ws.send(`/load ${sessionId}`);
}

dom.historyList.addEventListener('click', (e: MouseEvent) => {
    const deleteBtn = (e.target as HTMLElement).closest('[data-delete]');
    if (deleteBtn) {
        e.stopPropagation();
        const sessionIdToDelete = (deleteBtn as HTMLElement).dataset.delete;
        const isCurrentSession = sessionIdToDelete === ChatHistory.currentSessionId || 
            dom.historyList.querySelector(`.history-item--active[data-id="${sessionIdToDelete}"]`);
        if (isCurrentSession) {
            showInfoDialog('无法删除当前会话，请先切换到其它会话');
            return;
        }
        
        showConfirmDialog(
            '确认删除',
            `<div style="padding:0.5rem 0;color:var(--text-secondary)">确定要删除这个会话吗？此操作无法撤销。</div>`,
            () => ws.send(`/delete-session ${sessionIdToDelete}`)
        );
        return;
    }
    const item = (e.target as HTMLElement).closest('.history-item');
    if (item) {
        if (AppState.isGenerating) {
            showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
            return;
        }
        requestLoadSession((item as HTMLElement).dataset.id || '');
    }
});

dom.newChatBtn.addEventListener('click', () => {
    if (AppState.isGenerating) {
        showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
        return;
    }
    
    // 打开新建对话弹窗
    NewChatDialog.open();
});

// ============ UI 状态 ============
function setGeneratingState(generating: boolean): void {
    AppState.isGenerating = generating;
    if (generating) {
        dom.sendBtn.textContent = 'Stop';
        dom.sendBtn.classList.add('button--stop');
    } else {
        dom.sendBtn.textContent = 'Send';
        dom.sendBtn.classList.remove('button--stop');
    }
}

function updateStatus(data: StatusData): void {
    StatusBar.update(data as Record<string, string | number>);
}

// ============ 输入框 ============
function handleSubmit(): void {
    if (AppState.isGenerating) {
        send('/stop');
        return;
    }

    const msg = dom.input.value.trim();
    if (!msg) return;
    
    const isCommand = msg.startsWith('/');
    send(msg);
    
    if (!isCommand) {
        ChatHistory.addUserMessage(msg);
        setGeneratingState(true);
    }
    
    dom.input.value = '';
    autoResize();
}

function autoResize(): void {
    dom.input.style.height = 'auto';
    dom.input.style.height = dom.input.scrollHeight + 'px';
}

dom.form.addEventListener('submit', (e: Event) => { e.preventDefault(); handleSubmit(); });
dom.input.addEventListener('keydown', (e: KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); } });
dom.input.addEventListener('input', autoResize);

// ============ 弹窗 (模型选择 & 错误提示) ============
function showModelSelect(models: string[]): void {
    const content = models.map(m => `<div class="modal__item" data-model="${m}">${m}</div>`).join('');
    dom.modalTitle.textContent = '选择模型';
    dom.modalBody.innerHTML = content;
    dom.modalActions.style.display = 'none';
    dom.modal.classList.add('visible');
    
    // 临时绑定点击事件
    const items = dom.modalBody.querySelectorAll('.modal__item');
    items.forEach(item => {
        item.addEventListener('click', () => {
            send((item as HTMLElement).dataset.model || '');
            dom.modal.classList.remove('visible');
        });
    });
}

function showInputPrompt(data: InputPromptData): void {
    dom.modalTitle.textContent = data?.prompt || '输入';
    dom.modalBody.innerHTML = '<input type="text" class="modal__input" placeholder="输入...">';
    dom.modalActions.style.display = 'flex';
    dom.modal.classList.add('visible');
    setTimeout(() => (dom.modalBody.querySelector('input') as HTMLInputElement)?.focus(), 30);
}

dom.modalOk.addEventListener('click', () => {
    const input = dom.modalBody.querySelector('input') as HTMLInputElement;
    if (input) {
        const v = input.value.trim();
        if (v) { send(v); dom.modal.classList.remove('visible'); }
    }
});

// 点击遮罩层关闭弹窗
dom.modal.addEventListener('click', (e: MouseEvent) => {
    if (e.target === dom.modal) {
        dom.modal.classList.remove('visible');
    }
});

// ============ 确认弹窗逻辑 ============
let confirmCallback: (() => void) | null = null;

function showConfirmDialog(title: string, messageHtml: string, onConfirm: () => void): void {
    dom.confirmTitle.textContent = title;
    dom.confirmBody.innerHTML = messageHtml;
    confirmCallback = onConfirm;
    dom.confirmModal.classList.add('visible');
}

dom.confirmCancel.addEventListener('click', () => {
    dom.confirmModal.classList.remove('visible');
    confirmCallback = null;
});

dom.confirmOk.addEventListener('click', () => {
    if (confirmCallback) confirmCallback();
    dom.confirmModal.classList.remove('visible');
    confirmCallback = null;
});

dom.confirmModal.addEventListener('click', (e) => {
    if (e.target === dom.confirmModal) {
        dom.confirmModal.classList.remove('visible');
        confirmCallback = null;
    }
});

function showErrorDialog(message: string): void {
    renderModalContent('错误', `<div style="color:var(--error-color);padding:1rem;text-align:center">${escapeHtml(message)}</div>`);
}

function showInfoDialog(message: string): void {
    renderModalContent('提示', `<div style="color:var(--text-primary);padding:1rem;text-align:center">${escapeHtml(message)}</div>`);
    setTimeout(() => dom.modal.classList.remove('visible'), 2000);
}

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
    
    // 设置标题
    if (toolDetailTitle) {
        toolDetailTitle.textContent = `工具底层详情: ${toolName}`;
    }
    
    // 获取 pre 元素
    const toolDetailRequest = toolDetailRequestContainer?.querySelector('pre');
    const toolDetailResponse = toolDetailResponseContainer?.querySelector('pre');
    
    // 显示原始 JSON 数据（就像 LLM 实际看到的那样）
    if (toolDetailRequest) {
        if (rawRequest) {
            try {
                // 解析后重新格式化，保持 2 空格缩进
                const requestData = JSON.parse(rawRequest);
                toolDetailRequest.textContent = JSON.stringify(requestData, null, 2);
            } catch (e) {
                // 如果解析失败，直接显示原始数据
                toolDetailRequest.textContent = rawRequest;
            }
        } else {
            toolDetailRequest.textContent = '暂无请求数据';
        }
    }
    
    // 显示原始响应数据
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
    
    // 显示弹窗
    toolDetailModal.classList.add('tool-detail-modal--visible');
}

function hideToolDetail(): void {
    toolDetailModal.classList.remove('tool-detail-modal--visible');
}

// 绑定关闭按钮
if (toolDetailClose) {
    toolDetailClose.addEventListener('click', hideToolDetail);
}

// 点击遮罩层关闭
if (toolDetailModal) {
    toolDetailModal.addEventListener('click', (e) => {
        if (e.target === toolDetailModal) {
            hideToolDetail();
        }
    });
}

// 绑定复制按钮
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

// 使用事件委托，监听所有工具元素的右键点击
dom.messages.addEventListener('contextmenu', (e: MouseEvent) => {
    const target = e.target as HTMLElement;
    const toolElement = target.closest('.tool') as HTMLElement;
    
    if (toolElement) {
        e.preventDefault(); // 阻止默认右键菜单
        showToolDetail(toolElement);
    }
});

// ============ 模式选择器 ============
interface ModeInfo { name: string; label: string; desc: string; }

const modeLabels: Record<string, string> = {};

const modeTrigger = document.getElementById('mode-trigger') as HTMLButtonElement | null;
const modeDropdown = document.getElementById('mode-dropdown') as HTMLElement | null;
const modeLabelEl = document.getElementById('mode-label') as HTMLElement | null;

function updateModeUI(mode: string): void {
    if (modeLabelEl) {
        modeLabelEl.textContent = modeLabels[mode] || mode;
    }
    if (modeDropdown) {
        modeDropdown.querySelectorAll<HTMLElement>('.mode-selector__option').forEach(opt => {
            opt.classList.toggle('mode-selector__option--active', opt.dataset.mode === mode);
        });
    }
    if (modeTrigger) {
        modeTrigger.classList.toggle('mode-selector__trigger--active', mode !== 'default');
    }
}

function bindModeDropdownEvents(): void {
    if (!modeTrigger || !modeDropdown) return;

    modeTrigger.addEventListener('click', (e: MouseEvent) => {
        e.stopPropagation();
        modeDropdown.classList.toggle('mode-selector__dropdown--open');
    });

    modeDropdown.querySelectorAll<HTMLElement>('.mode-selector__option').forEach(opt => {
        opt.addEventListener('click', () => {
            const mode = opt.dataset.mode || 'default';
            send(JSON.stringify({ type: 'set_mode', mode }));
            updateModeUI(mode);
            modeDropdown.classList.remove('mode-selector__dropdown--open');
        });
    });
}

async function initModeSelector(): Promise<void> {
    if (!modeDropdown) return;
    try {
        const res = await fetch('/api/modes');
        const data = await res.json() as { modes: ModeInfo[] };
        modeDropdown.innerHTML = '';
        data.modes.forEach((m, i) => {
            modeLabels[m.name] = m.label;
            const el = document.createElement('div');
            el.className = 'mode-selector__option' + (i === 0 ? ' mode-selector__option--active' : '');
            el.dataset.mode = m.name;
            el.innerHTML = `<span class="mode-selector__option-name">${m.label}</span><span class="mode-selector__option-desc">${m.desc}</span>`;
            modeDropdown.appendChild(el);
        });
        bindModeDropdownEvents();
    } catch {
        modeLabels['default'] = 'Default';
        bindModeDropdownEvents();
    }
}

document.addEventListener('click', (e: MouseEvent) => {
    if (!modeDropdown || !modeDropdown.classList.contains('mode-selector__dropdown--open')) return;
    const selector = document.getElementById('mode-selector');
    if (selector && !selector.contains(e.target as Node)) {
        modeDropdown.classList.remove('mode-selector__dropdown--open');
    }
});

// 启动初始化
autoResize();
initModeSelector();
