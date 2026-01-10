// 主入口文件
import { $, $$, initMarkdown, scrollToBottom, escapeHtml } from './modules/utils.js';
import { ThemeColors } from './modules/theme.js';
import { createMsgEl, addSysMsg, updateToolElement, renderModalContent, getToolDisplay } from './modules/render.js';
import { ChatHistory } from './modules/chat.js';
import { Memory } from './modules/memory.js';
import { Settings } from './modules/settings.js';
import { AppState, StatusBar } from './modules/store.js';

// ========== 配置 ==========
const LOGO = `██████╗    █████╗   ██╗    ██╗
██╔══██╗  ██╔══██╗  ██║ █╗ ██║
██████╔╝  ███████║  ██║███╗██║
██╔═══╝   ██╔══██║  ╚███╔███╔╝
╚═╝       ╚═╝  ╚═╝   ╚══╝╚══╝ `;

// ========== DOM 缓存 ==========
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
    viewChain: $('#view-chain'),
    viewMemory: $('#view-memory'),
    chainList: $('#chain-list'),
    // Memory
    memoryCanvas: $('#memory-canvas'),
    memoryEmpty: $('#memory-empty'),
    memoryStats: $('#memory-stats'),
    memorySearchBtn: $('#memory-search-btn'),
    memoryCleanBtn: $('#memory-clean-btn'),
    // Layout
    sidebar: $('.sidebar'),
    main: $('.main'),
    toggleSidebarBtn: $('#toggle-sidebar'),
    newChatToolbarBtn: $('#new-chat-toolbar')
};

// ========== WebSocket ==========
const ws = new WebSocket(`ws://${location.host}/ws`);

function send(msg) {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(msg);
    } else {
        showErrorDialog('未连接到服务器');
    }
}

// ========== 初始化模块 ==========
initMarkdown();
Settings.init(send);
Memory.init(dom, send);
ChatHistory.init(dom);
StatusBar.init(dom.statusBar);

// ========== 工具栏功能 ==========
function toggleSidebar() {
    AppState.sidebarVisible = !AppState.sidebarVisible;
    dom.sidebar.classList.toggle('sidebar--hidden', !AppState.sidebarVisible);
    dom.main.classList.toggle('main--full-width', !AppState.sidebarVisible);
    dom.toggleSidebarBtn.classList.toggle('toolbar__btn--active', AppState.sidebarVisible);
    localStorage.setItem('paw-sidebar-visible', AppState.sidebarVisible);
}

function initSidebarState() {
    AppState.init();
    dom.sidebar.classList.toggle('sidebar--hidden', !AppState.sidebarVisible);
    dom.main.classList.toggle('main--full-width', !AppState.sidebarVisible);
    dom.toggleSidebarBtn.classList.toggle('toolbar__btn--active', AppState.sidebarVisible);
}

dom.toggleSidebarBtn.addEventListener('click', toggleSidebar);
dom.newChatToolbarBtn.addEventListener('click', () => dom.newChatBtn.click());

document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
    }
});

initSidebarState();

// ========== 视图切换 ==========
$$('.sidebar__tab').forEach(tab => {
    tab.addEventListener('click', () => {
        $$('.sidebar__tab').forEach(t => t.classList.remove('sidebar__tab--active'));
        tab.classList.add('sidebar__tab--active');
        const view = tab.dataset.view;
        dom.viewHistory.classList.toggle('sidebar__view--active', view === 'history');
        dom.viewChain.classList.toggle('sidebar__view--active', view === 'chain');
        dom.viewMemory.classList.toggle('sidebar__view--active', view === 'memory');
        if (view === 'chain') ChatHistory.renderChain();
    });
});

// ========== WebSocket 事件处理 ==========
ws.onopen = () => {
    ws.send('/sessions'); // 请求会话列表
};
ws.onclose = () => showErrorDialog('连接已断开');
ws.onerror = () => showErrorDialog('连接错误');
ws.onmessage = e => handleEvent(JSON.parse(e.data));

function handleEvent({ event, data }) {
    const h = {
        'assistant_stream_start': () => startStream(data.id),
        'assistant_stream_chunk': () => appendStream(data.id, data.text),
        'assistant_stream_end': () => endStream(data.id),
        'tool_start': () => createTool(data),
        'tool_result': () => updateTool(data),
        'turn_end': () => {
            ChatHistory.endAssistantTurn();
            setGeneratingState(false);
        },
        'system_message': () => addSysMsg(dom.messages, data.text, data.type),
        'status_update': () => updateStatus(data),
        'show_model_selection': () => showModelSelect(data.models),
        'request_input': () => showInputPrompt(data),
        'show_memory': () => Memory.show(data.conversations),
        'memory_result': () => Memory.handleResult(data),
        'session_list': () => handleSessionList(data),
        'session_load': () => ChatHistory.loadSessionChunks(data.chunks), // 使用 ChatHistory 的新方法
        'show_error': () => showErrorDialog(data.text),
        'session_loaded': () => {
            if (data.session_id) {
                ChatHistory.currentSessionId = data.session_id;
                updateSidebarHighlight(data.session_id);
            }
        },
        'new_chat': () => {
            ChatHistory.clear();
            dom.messages.innerHTML = '';
            dom.chainList.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:2rem 1rem">发送消息开始对话</div>';
            if (data.session_id) {
                ChatHistory.currentSessionId = data.session_id;
                updateSidebarHighlight(data.session_id);
            }
            requestSessionList();
        },
        'models_fetched': () => Settings.handleModelResponse(data)
    };
    h[event]?.();
}

// ========== 流式处理逻辑 ==========
function startStream(id) {
    AppState.streamId = id;
    AppState.streamBuf = '';
    
    let existingMsg = dom.messages.querySelector('.msg--assistant:last-child');
    
    if (ChatHistory.isInAssistantTurn && existingMsg) {
        // 同一轮次中，复用现有消息
        const toolsContainer = existingMsg.querySelector('.msg__tools');
        if (toolsContainer && toolsContainer.children.length > 0) {
            // 有工具调用，在消息末尾添加新内容块
            const newContent = document.createElement('div');
            newContent.className = 'msg__content msg__content--continued';
            newContent.id = id;
            existingMsg.appendChild(newContent);
        } else {
            // 没有工具调用，直接使用现有内容区域
            const existingContent = existingMsg.querySelector('.msg__content');
            if (existingContent && existingContent.innerHTML.trim()) {
                const newContent = document.createElement('div');
                newContent.className = 'msg__content msg__content--continued';
                newContent.id = id;
                existingMsg.appendChild(newContent);
            }
        }
    } else {
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
    if (!content) return;
    
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
            const btn = document.createElement('button');
            btn.className = 'copy-btn';
            btn.textContent = 'Copy';
            btn.onclick = () => { 
                navigator.clipboard.writeText(el.textContent); 
                btn.textContent = 'Copied!'; 
                setTimeout(() => btn.textContent = 'Copy', 2000); 
            };
            pre.appendChild(btn);
        });
    }

    ChatHistory.onStreamEnd(AppState.streamBuf);
    AppState.streamId = null;
    AppState.streamBuf = '';
}

// ========== 工具渲染逻辑 ==========
function createTool({ id, name, args }) {
    if (name === 'stay_silent') {
        const msgEl = dom.messages.querySelector('.msg--assistant:last-child');
        if (msgEl) msgEl.remove();
        
        if (ChatHistory.currentTurn) {
            ChatHistory.currentTurn = null;
            ChatHistory.isInAssistantTurn = false;
        }
        setGeneratingState(false);
        return;
    }

    const el = document.createElement('div');
    el.id = `tool-${id}`;
    el.className = 'tool';
    el.innerHTML = `<div class="tool__header"><div class="tool__spinner"></div><span class="tool__name">${name}</span> <span class="tool__args">${args}</span></div>`;

    let msgEl = dom.messages.querySelector('.msg--assistant:last-child');
    
    if (ChatHistory.isInAssistantTurn && msgEl) {
        const toolsContainer = msgEl.querySelector('.msg__tools');
        if (toolsContainer) {
            toolsContainer.appendChild(el);
        } else {
            msgEl.appendChild(el);
        }
    } else {
        const msgId = `msg-${Date.now()}`;
        msgEl = createMsgEl('assistant', 'PAW', '', msgId);
        dom.messages.appendChild(msgEl);
        ChatHistory.onStreamStart(msgId);
        
        const toolsContainer = msgEl.querySelector('.msg__tools');
        if (toolsContainer) {
            toolsContainer.appendChild(el);
        } else {
            msgEl.appendChild(el);
        }
    }
    
    ChatHistory.addTool(id, name);
    scrollToBottom(dom.msgWrap);
}

function updateTool({ id, name, display, success }) {
    const el = document.getElementById(`tool-${id}`);
    if (!el) return;
    
    if (name === 'stay_silent') {
        const msgEl = el.closest('.msg--assistant');
        if (msgEl) msgEl.remove();
        if (ChatHistory.currentTurn) {
            ChatHistory.currentTurn = null;
            ChatHistory.isInAssistantTurn = false;
        }
        return;
    }
    
    updateToolElement(el, name, display, success);
}

// ========== 会话管理 ==========
function handleSessionList({ sessions, current_id }) {
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

dom.historyList.addEventListener('click', e => {
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
        ws.send(`/delete-session ${sessionIdToDelete}`);
        return;
    }
    const item = e.target.closest('.history-item');
    if (item) {
        if (AppState.isGenerating) {
            showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
            return;
        }
        requestLoadSession(item.dataset.id);
    }
});

dom.newChatBtn.addEventListener('click', () => {
    if (AppState.isGenerating) {
        showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
        return;
    }
    
    const currentSession = AppState.cachedSessions.find(s => s.session_id === ChatHistory.currentSessionId);
    if (currentSession && currentSession.message_count === 0) {
        updateSidebarHighlight(ChatHistory.currentSessionId);
        ChatHistory.clear();
        dom.messages.innerHTML = '';
        dom.chainList.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:2rem 1rem">发送消息开始对话</div>';
        return;
    }
    
    const existingEmptySession = AppState.cachedSessions.find(s => s.message_count === 0);
    if (existingEmptySession) {
        requestLoadSession(existingEmptySession.session_id);
        return;
    }
    
    ws.send('/new');
});

// ========== UI 状态 ==========
function setGeneratingState(generating) {
    AppState.isGenerating = generating;
    if (generating) {
        dom.sendBtn.textContent = 'Stop';
        dom.sendBtn.classList.add('button--stop');
    } else {
        dom.sendBtn.textContent = 'Send';
        dom.sendBtn.classList.remove('button--stop');
    }
}

function updateStatus(data) {
    StatusBar.update(data);
}

// ========== 输入框 ==========
function handleSubmit() {
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

function autoResize() {
    dom.input.style.height = 'auto';
    dom.input.style.height = dom.input.scrollHeight + 'px';
}

dom.form.addEventListener('submit', e => { e.preventDefault(); handleSubmit(); });
dom.input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(); } });
dom.input.addEventListener('input', autoResize);

// ========== 弹窗 (模型选择 & 错误提示) ==========
function showModelSelect(models) {
    const content = models.map(m => `<div class="modal__item" data-model="${m}">${m}</div>`).join('');
    dom.modalTitle.textContent = '选择模型';
    dom.modalBody.innerHTML = content;
    dom.modalActions.style.display = 'none';
    dom.modal.classList.add('visible');
    
    // 临时绑定点击事件 (TODO: 优化为代理或 Settings 管理)
    const items = dom.modalBody.querySelectorAll('.modal__item');
    items.forEach(item => {
        item.addEventListener('click', () => {
            send(item.dataset.model);
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
        if (v) { send(v); dom.modal.classList.remove('visible'); }
    }
});

// 点击遮罩层关闭弹窗
dom.modal.addEventListener('click', e => {
    if (e.target === dom.modal) {
        dom.modal.classList.remove('visible');
    }
});

function showErrorDialog(message) {
    renderModalContent('错误', `<div style="color:var(--error-color);padding:1rem;text-align:center">${escapeHtml(message)}</div>`);
}

function showInfoDialog(message) {
    renderModalContent('提示', `<div style="color:var(--text-primary);padding:1rem;text-align:center">${escapeHtml(message)}</div>`);
    setTimeout(() => dom.modal.classList.remove('visible'), 2000);
}

// 启动初始化
autoResize();
