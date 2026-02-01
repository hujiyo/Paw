// 主入口文件
import { $, $$, initMarkdown, scrollToBottom, escapeHtml } from './modules/utils.js';
import { createMsgEl, addSysMsg, updateToolElement, renderModalContent, getToolDisplay, setMessageActions } from './modules/render.js';
import { ChatHistory } from './modules/chat.js';
import { Memory } from './modules/memory.js';
import { Settings } from './modules/settings.js';
import { NewChatDialog } from './modules/new-chat.js';
import { AppState, StatusBar } from './modules/store.js';
import { RightSidebar } from './modules/right-sidebar.js';
import { FileExplorer } from './modules/file-explorer.js';
import { Planner } from './modules/planner.js';
import { Browser } from './modules/browser.js';
import { WorkspaceFilesSidebar } from './modules/workspace-files-sidebar.js';
import { Skills } from './modules/skills.js';
import { EditorSettings } from './modules/editor-settings.js';
// ============ 配置 ==========
const LOGO = `██████╗    █████╗   ██╗    ██╗
██╔══██╗  ██╔══██╗  ██║ █╗ ██║
██████╔╝  ███████║  ██║███╗██║
██╔═══╝   ██╔══██║  ╚███╔███╔╝
╚═╝       ╚═╝  ╚═╝   ╚══╝╚══╝ `;
const dom = {
    statusBar: $('#status-bar'),
    msgWrap: $('#messages-wrapper'),
    messages: $('#messages'),
    form: $('#input-form'),
    input: $('#input'),
    sendBtn: $('#send-btn'),
    // Modal related
    modal: $('#modal'),
    modalTitle: $('#modal-title'),
    modalBody: $('#modal-body'),
    modalActions: $('#modal-actions'),
    modalOk: $('#modal-ok'),
    // Views
    historyList: $('#history-list'),
    historyEmpty: $('#history-empty'),
    newChatBtn: $('#new-chat-btn'),
    viewHistory: $('#view-history'),
    viewMemory: $('#view-memory'),
    viewSkills: $('#view-skills'),
    // Memory
    memoryCanvas: $('#memory-canvas'),
    memoryEmpty: $('#memory-empty'),
    memoryStats: $('#memory-stats'),
    memorySearchBtn: $('#memory-search-btn'),
    memoryCleanBtn: $('#memory-clean-btn'),
    // Layout
    sidebar: $('.sidebar'),
    sidebarRight: $('#sidebar-right'),
    main: $('.main'),
    toggleSidebarBtn: $('#toggle-sidebar'),
    toggleRightSidebarBtn: $('#toggle-right-sidebar'),
    toggleWorkspaceFilesSidebarBtn: $('#toggle-workspace-files-sidebar'),
    newChatToolbarBtn: $('#new-chat-toolbar'),
    toolbarDivider: $('#toolbar-divider'),
    // 工作区终端输出
    terminalStatus: $('#terminal-status'),
    terminalContent: $('#terminal-content'),
    terminalOutput: $('#terminal-output'),
    // 确认弹窗
    confirmModal: $('#confirm-modal'),
    confirmTitle: $('#confirm-title'),
    confirmBody: $('#confirm-body'),
    confirmCancel: $('#confirm-cancel'),
    confirmOk: $('#confirm-ok')
};
// ============ WebSocket ============
const ws = new WebSocket(`ws://${location.host}/ws`);
function send(msg) {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(msg);
    }
    else {
        showErrorDialog('未连接到服务器');
    }
}
// ============ 初始化模块 ============
initMarkdown();
Settings.init(send);
NewChatDialog.init(send);
Memory.init(dom, send);
ChatHistory.init(dom);
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
        // 从前端 messages 中删除（仅用于 UI 显示）
        const msgIdx = ChatHistory.messages.findIndex(m => m.id === msgId);
        if (msgIdx >= 0) {
            ChatHistory.messages.splice(msgIdx, 1);
        }
        // 清空并重新渲染整个消息区域
        dom.messages.innerHTML = '';
        ChatHistory.messages.forEach(msg => {
            const el = createMsgEl(msg.role, msg.role === 'user' ? 'USER' : 'PAW', msg.text, msg.id);
            dom.messages.appendChild(el);
        });
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
        // 从前端 messages 中删除（仅用于 UI 显示）
        const msgIdx = ChatHistory.messages.findIndex(m => m.id === msgId);
        if (msgIdx >= 0) {
            ChatHistory.messages.splice(msgIdx, 1);
        }
        // 清空并重新渲染整个消息区域
        dom.messages.innerHTML = '';
        ChatHistory.messages.forEach(msg => {
            const el = createMsgEl(msg.role, msg.role === 'user' ? 'USER' : 'PAW', msg.text, msg.id);
            dom.messages.appendChild(el);
        });
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
function updateToolbarVisibility() {
    // 左侧边栏打开时，隐藏右侧边栏按钮
    dom.toggleRightSidebarBtn.style.display = AppState.sidebarVisible ? 'none' : '';
    // 右侧边栏打开时，隐藏左侧边栏按钮和新建会话按钮，显示工作区文件目录侧边栏按钮
    dom.toggleSidebarBtn.style.display = AppState.rightSidebarVisible ? 'none' : '';
    dom.newChatToolbarBtn.style.display = AppState.rightSidebarVisible ? 'none' : '';
    dom.toolbarDivider.style.display = AppState.rightSidebarVisible ? 'none' : '';
    // 工作区文件目录侧边栏按钮：只在右侧边栏打开时显示
    dom.toggleWorkspaceFilesSidebarBtn.style.display = AppState.rightSidebarVisible ? '' : 'none';
}
function toggleSidebar() {
    AppState.sidebarVisible = !AppState.sidebarVisible;
    dom.sidebar.classList.toggle('sidebar--hidden', !AppState.sidebarVisible);
    dom.main.classList.toggle('main--full-width', !AppState.sidebarVisible);
    dom.toggleSidebarBtn.classList.toggle('toolbar__btn--active', AppState.sidebarVisible);
    updateToolbarVisibility();
    localStorage.setItem('paw-sidebar-visible', String(AppState.sidebarVisible));
}
function toggleRightSidebar() {
    AppState.rightSidebarVisible = !AppState.rightSidebarVisible;
    dom.sidebarRight.classList.toggle('sidebar-right--visible', AppState.rightSidebarVisible);
    dom.main.classList.toggle('main--with-right-sidebar', AppState.rightSidebarVisible);
    dom.toggleRightSidebarBtn.classList.toggle('toolbar__btn--active', AppState.rightSidebarVisible);
    updateToolbarVisibility();
    localStorage.setItem('paw-right-sidebar-visible', String(AppState.rightSidebarVisible));
}
function initSidebarState() {
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
document.addEventListener('keydown', (e) => {
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
$$('.sidebar__tab').forEach(tab => {
    tab.addEventListener('click', () => {
        $$('.sidebar__tab').forEach(t => t.classList.remove('sidebar__tab--active'));
        tab.classList.add('sidebar__tab--active');
        const view = tab.dataset.view;
        dom.viewHistory.classList.toggle('sidebar__view--active', view === 'history');
        dom.viewMemory.classList.toggle('sidebar__view--active', view === 'memory');
        dom.viewSkills.classList.toggle('sidebar__view--active', view === 'skills');
    });
});
// ============ WebSocket 事件处理 ============
ws.onopen = () => {
    ws.send('/sessions'); // 请求会话列表
};
ws.onclose = () => showErrorDialog('连接已断开');
ws.onerror = () => showErrorDialog('连接错误');
ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
function handleEvent({ event, data }) {
    const handlers = {
        'assistant_stream_start': () => startStream(data.id),
        'assistant_stream_chunk': () => appendStream(data.id, data.text || ''),
        'assistant_stream_end': () => endStream(data.id),
        'tool_start': () => createTool(data),
        'tool_result': () => updateTool(data),
        'turn_end': () => {
            ChatHistory.endAssistantTurn();
            setGeneratingState(false);
        },
        'system_message': () => addSysMsg(dom.messages, data.text, data.type || ''),
        'status_update': () => updateStatus(data),
        'show_model_selection': () => showModelSelect(data.models),
        'request_input': () => showInputPrompt(data),
        'show_memory': () => Memory.show(data.conversations),
        'memory_result': () => Memory.handleResult(data),
        'session_list': () => handleSessionList(data),
        'session_load': () => ChatHistory.loadSessionChunks(data.chunks),
        'show_error': () => showErrorDialog(data.text),
        'session_loaded': () => {
            const loadedData = data;
            if (loadedData.session_id) {
                ChatHistory.currentSessionId = loadedData.session_id;
                updateSidebarHighlight(loadedData.session_id);
            }
        },
        'new_chat': () => {
            ChatHistory.clear();
            dom.messages.innerHTML = '';
            const newChatData = data;
            if (newChatData.session_id) {
                ChatHistory.currentSessionId = newChatData.session_id;
                updateSidebarHighlight(newChatData.session_id);
            }
            requestSessionList();
        },
        'models_fetched': () => Settings.handleModelResponse(data),
        'terminal_output': () => updateTerminalOutput(data),
        'todos_updated': () => handleTodosUpdated(data)
    };
    handlers[event]?.();
}
// ============ 终端输出处理 ============
function updateTerminalOutput({ content, is_open }) {
    // 更新状态标签
    dom.terminalStatus.textContent = is_open ? '运行中' : '未打开';
    dom.terminalStatus.classList.toggle('workspace-header__status--active', is_open);
    // 更新终端内容
    dom.terminalContent.textContent = content;
    // 自动滚动到底部
    dom.terminalOutput.scrollTop = dom.terminalOutput.scrollHeight;
}
// ============ Todo 列表更新处理 ============
function handleTodosUpdated({ todos }) {
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
function startStream(id) {
    AppState.streamId = id;
    AppState.streamBuf = '';
    let existingMsg = dom.messages.querySelector('.msg--assistant:last-child');
    if (ChatHistory.isInAssistantTurn && existingMsg) {
        // 同一轮次中，复用现有消息
        const body = existingMsg.querySelector('.msg__body');
        const actions = existingMsg.querySelector('.msg__actions');
        // 获取最后一个内容块
        const lastContent = body?.querySelector('.msg__content:last-of-type');
        if (lastContent && !lastContent.innerHTML.trim()) {
            // 如果最后的内容块为空，复用它
            if (!lastContent.id)
                lastContent.id = id;
        }
        else {
            // 创建新的内容块，插入在操作按钮之前
            const newContent = document.createElement('div');
            newContent.className = 'msg__content';
            newContent.id = id;
            if (body && actions) {
                body.insertBefore(newContent, actions);
            }
            else if (body) {
                body.appendChild(newContent);
            }
        }
        // 复用消息时也需要通知 ChatHistory（确保对话链正确更新）
        ChatHistory.onStreamStart(id);
    }
    else {
        // 新轮次，创建新消息
        dom.messages.appendChild(createMsgEl('assistant', 'PAW', '', id));
        ChatHistory.onStreamStart(id);
    }
}
function appendStream(id, text) {
    let content = document.getElementById(id);
    if (!content) {
        content = dom.messages.querySelector('.msg--assistant:last-child .msg__content:last-of-type');
    }
    if (!content)
        return;
    AppState.streamBuf += text;
    content.innerHTML = marked.parse(AppState.streamBuf);
    scrollToBottom(dom.msgWrap);
}
function endStream(id) {
    let content = document.getElementById(id);
    if (!content) {
        content = dom.messages.querySelector('.msg--assistant:last-child .msg__content:last-of-type');
    }
    if (content) {
        content.querySelectorAll('pre code').forEach(el => {
            const pre = el.parentElement;
            if (!pre)
                return;
            const btn = document.createElement('button');
            btn.className = 'copy-btn';
            btn.textContent = 'Copy';
            btn.onclick = () => {
                navigator.clipboard.writeText(el.textContent || '');
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = 'Copy', 2000);
            };
            pre.appendChild(btn);
        });
    }
    ChatHistory.onStreamEnd(AppState.streamBuf);
    // 消息结束后刷新 Browser URL 列表
    Browser.refresh();
    AppState.streamId = null;
    AppState.streamBuf = '';
}
// ============ 工具渲染逻辑 ============
function createTool({ id, name, args, raw_request }) {
    // Context-Aware Focus Switching - 只在右侧边栏已经打开时切换标签，不强制打开
    if (AppState.rightSidebarVisible) {
        if (['read_files', 'edit_files', 'create_file', 'file_glob'].includes(name)) {
            RightSidebar.switchView('files');
        }
        else if (['run_shell_command'].includes(name)) {
            RightSidebar.switchView('terminal');
        }
        else if (['create_plan', 'edit_plans', 'create_todo_list', 'add_todos', 'mark_todo_as_done', 'read_todos'].includes(name)) {
            RightSidebar.switchView('plan');
        }
        else if (['search_web', 'load_url_content', 'read_page'].includes(name)) {
            RightSidebar.switchToTab('browser');
            Browser.refresh();
        }
    }
    if (name === 'stay_silent') {
        const msgEl = dom.messages.querySelector('.msg--assistant:last-child');
        if (msgEl)
            msgEl.remove();
        ChatHistory.isInAssistantTurn = false;
        setGeneratingState(false);
        return;
    }
    const el = document.createElement('div');
    el.id = `tool-${id}`;
    el.className = 'tool';
    el.innerHTML = `<div class="tool__header"><div class="tool__spinner"></div><span class="tool__name">${name}</span> <span class="tool__args">${args}</span></div>`;
    // 存储原始请求数据
    if (raw_request) {
        el.dataset.rawRequest = JSON.stringify(raw_request);
    }
    let msgEl = dom.messages.querySelector('.msg--assistant:last-child');
    if (ChatHistory.isInAssistantTurn && msgEl) {
        // 追加到消息体末尾（在操作按钮之前）
        const body = msgEl.querySelector('.msg__body');
        const actions = msgEl.querySelector('.msg__actions');
        if (body && actions) {
            body.insertBefore(el, actions);
        }
        else if (body) {
            body.appendChild(el);
        }
        else {
            // 兼容旧结构（不应该达到这里）
            msgEl.appendChild(el);
        }
    }
    else {
        // 新轮次，创建新消息
        const msgId = `msg-${Date.now()}`;
        const newMsgEl = createMsgEl('assistant', 'PAW', '', msgId);
        dom.messages.appendChild(newMsgEl);
        ChatHistory.onStreamStart(msgId);
        const body = newMsgEl.querySelector('.msg__body');
        body?.appendChild(el);
    }
    ChatHistory.addTool(id, name);
    scrollToBottom(dom.msgWrap);
    // 如果是 Todo 工具，尝试刷新 Planner (从 request 解析)
    if (['create_todo_list', 'add_todos', 'mark_todo_as_done'].includes(name)) {
        Planner.refresh();
    }
}
function updateTool({ id, name, display, success, raw_response }) {
    const el = document.getElementById(`tool-${id}`);
    if (!el)
        return;
    if (name === 'stay_silent') {
        const msgEl = el.closest('.msg--assistant');
        if (msgEl)
            msgEl.remove();
        ChatHistory.isInAssistantTurn = false;
        return;
    }
    // 如果后端没有提供 display 数据（或者数据不完整），则在前端动态计算
    // 这是为了解耦前后端，让前端全权负责渲染逻辑
    let finalDisplay = display;
    if (!finalDisplay || (!finalDisplay.line1 && !finalDisplay.line2)) {
        // 尝试从 raw_response 获取结果文本
        let resultText = '';
        if (raw_response) {
            if (raw_response.result !== undefined)
                resultText = String(raw_response.result);
            else if (raw_response.error !== undefined)
                resultText = String(raw_response.error);
            else if (raw_response.content !== undefined)
                resultText = String(raw_response.content);
        }
        // 尝试从 dataset.rawRequest 获取参数
        let args = {};
        try {
            if (el.dataset.rawRequest) {
                const req = JSON.parse(el.dataset.rawRequest);
                // rawRequest 结构通常是 { function: { arguments: "{...}" } } 或直接是参数对象
                // 这里我们要适配 OpenAI 标准结构
                const rawArgs = req.function?.arguments;
                if (typeof rawArgs === 'string') {
                    args = JSON.parse(rawArgs);
                }
                else if (typeof rawArgs === 'object') {
                    args = rawArgs;
                }
            }
        }
        catch (e) {
            console.warn('Failed to parse args for display generation', e);
        }
        finalDisplay = getToolDisplay(name, resultText, args);
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
function handleSessionList({ sessions, current_id }) {
    AppState.cachedSessions = sessions || [];
    // 确定要使用的 currentSessionId：优先使用后端传来的 current_id，否则保留现有值
    const effectiveCurrentId = current_id || ChatHistory.currentSessionId;
    dom.historyList.innerHTML = '';
    sessions.forEach(s => {
        const el = document.createElement('div');
        el.className = 'history-item';
        el.dataset.id = s.session_id;
        if (s.session_id === effectiveCurrentId)
            el.classList.add('history-item--active');
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
function updateSidebarHighlight(sessionId) {
    dom.historyList.querySelectorAll('.history-item').forEach(item => {
        item.classList.toggle('history-item--active', item.dataset.id === sessionId);
    });
}
function requestSessionList() {
    ws.send('/sessions');
}
function requestLoadSession(sessionId) {
    ws.send(`/load ${sessionId}`);
}
dom.historyList.addEventListener('click', (e) => {
    const deleteBtn = e.target.closest('[data-delete]');
    if (deleteBtn) {
        e.stopPropagation();
        if (AppState.isGenerating) {
            showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
            return;
        }
        const sessionIdToDelete = deleteBtn.dataset.delete;
        // 检查是否为当前会话（也检查侧边栏高亮状态作为后备判断）
        const isCurrentSession = sessionIdToDelete === ChatHistory.currentSessionId ||
            dom.historyList.querySelector(`.history-item--active[data-id="${sessionIdToDelete}"]`);
        if (isCurrentSession) {
            showInfoDialog('无法删除当前会话，请先切换到其它会话');
            return;
        }
        showConfirmDialog('确认删除', `<div style="padding:0.5rem 0;color:var(--text-secondary)">确定要删除这个会话吗？此操作无法撤销。</div>`, () => ws.send(`/delete-session ${sessionIdToDelete}`));
        return;
    }
    const item = e.target.closest('.history-item');
    if (item) {
        if (AppState.isGenerating) {
            showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
            return;
        }
        requestLoadSession(item.dataset.id || '');
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
function setGeneratingState(generating) {
    AppState.isGenerating = generating;
    if (generating) {
        dom.sendBtn.textContent = 'Stop';
        dom.sendBtn.classList.add('button--stop');
    }
    else {
        dom.sendBtn.textContent = 'Send';
        dom.sendBtn.classList.remove('button--stop');
    }
}
function updateStatus(data) {
    StatusBar.update(data);
}
// ============ 输入框 ============
function handleSubmit() {
    if (AppState.isGenerating) {
        send('/stop');
        return;
    }
    const msg = dom.input.value.trim();
    if (!msg)
        return;
    const isCommand = msg.startsWith('/');
    send(msg);
    if (!isCommand) {
        ChatHistory.addUserMessage(msg);
        setGeneratingState(true);
    }
    dom.input.value = '';
    autoResize();
}
function autoResize() {
    dom.input.style.height = 'auto';
    dom.input.style.height = dom.input.scrollHeight + 'px';
}
dom.form.addEventListener('submit', (e) => { e.preventDefault(); handleSubmit(); });
dom.input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSubmit();
} });
dom.input.addEventListener('input', autoResize);
// ============ 弹窗 (模型选择 & 错误提示) ============
function showModelSelect(models) {
    const content = models.map(m => `<div class="modal__item" data-model="${m}">${m}</div>`).join('');
    dom.modalTitle.textContent = '选择模型';
    dom.modalBody.innerHTML = content;
    dom.modalActions.style.display = 'none';
    dom.modal.classList.add('visible');
    // 临时绑定点击事件
    const items = dom.modalBody.querySelectorAll('.modal__item');
    items.forEach(item => {
        item.addEventListener('click', () => {
            send(item.dataset.model || '');
            dom.modal.classList.remove('visible');
        });
    });
}
function showInputPrompt(data) {
    dom.modalTitle.textContent = data?.prompt || '输入';
    dom.modalBody.innerHTML = '<input type="text" class="modal__input" placeholder="输入...">';
    dom.modalActions.style.display = 'flex';
    dom.modal.classList.add('visible');
    setTimeout(() => dom.modalBody.querySelector('input')?.focus(), 30);
}
dom.modalOk.addEventListener('click', () => {
    const input = dom.modalBody.querySelector('input');
    if (input) {
        const v = input.value.trim();
        if (v) {
            send(v);
            dom.modal.classList.remove('visible');
        }
    }
});
// 点击遮罩层关闭弹窗
dom.modal.addEventListener('click', (e) => {
    if (e.target === dom.modal) {
        dom.modal.classList.remove('visible');
    }
});
// ============ 确认弹窗逻辑 ============
let confirmCallback = null;
function showConfirmDialog(title, messageHtml, onConfirm) {
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
    if (confirmCallback)
        confirmCallback();
    dom.confirmModal.classList.remove('visible');
    confirmCallback = null;
});
dom.confirmModal.addEventListener('click', (e) => {
    if (e.target === dom.confirmModal) {
        dom.confirmModal.classList.remove('visible');
        confirmCallback = null;
    }
});
function showErrorDialog(message) {
    renderModalContent('错误', `<div style="color:var(--error-color);padding:1rem;text-align:center">${escapeHtml(message)}</div>`);
}
function showInfoDialog(message) {
    renderModalContent('提示', `<div style="color:var(--text-primary);padding:1rem;text-align:center">${escapeHtml(message)}</div>`);
    setTimeout(() => dom.modal.classList.remove('visible'), 2000);
}
// ============ 工具详情弹窗 ============
const toolDetailModal = document.getElementById('tool-detail-modal');
const toolDetailTitle = document.getElementById('tool-detail-title');
const toolDetailRequestContainer = document.getElementById('tool-detail-request');
const toolDetailResponseContainer = document.getElementById('tool-detail-response');
const toolDetailClose = document.getElementById('tool-detail-close');
function showToolDetail(toolElement) {
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
            }
            catch (e) {
                // 如果解析失败，直接显示原始数据
                toolDetailRequest.textContent = rawRequest;
            }
        }
        else {
            toolDetailRequest.textContent = '暂无请求数据';
        }
    }
    // 显示原始响应数据
    if (toolDetailResponse) {
        if (rawResponse) {
            try {
                const responseData = JSON.parse(rawResponse);
                toolDetailResponse.textContent = JSON.stringify(responseData, null, 2);
            }
            catch (e) {
                toolDetailResponse.textContent = rawResponse;
            }
        }
        else {
            toolDetailResponse.textContent = '暂无响应数据';
        }
    }
    // 显示弹窗
    toolDetailModal.classList.add('tool-detail-modal--visible');
}
function hideToolDetail() {
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
        const copyType = btn.dataset.copy;
        let textToCopy = '';
        const toolDetailRequest = toolDetailRequestContainer?.querySelector('pre');
        const toolDetailResponse = toolDetailResponseContainer?.querySelector('pre');
        if (copyType === 'request' && toolDetailRequest) {
            textToCopy = toolDetailRequest.textContent || '';
        }
        else if (copyType === 'response' && toolDetailResponse) {
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
dom.messages.addEventListener('contextmenu', (e) => {
    const target = e.target;
    const toolElement = target.closest('.tool');
    if (toolElement) {
        e.preventDefault(); // 阻止默认右键菜单
        showToolDetail(toolElement);
    }
});
// 启动初始化
autoResize();
