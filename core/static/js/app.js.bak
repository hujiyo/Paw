// ========== 配置 ==========
const LOGO = `██████╗    █████╗   ██╗    ██╗
██╔══██╗  ██╔══██╗  ██║ █╗ ██║
██████╔╝  ███████║  ██║███╗██║
██╔═══╝   ██╔══██║  ╚███╔███╔╝
╚═╝       ╚═╝  ╚═╝   ╚══╝╚══╝ `;

// ========== 颜色主题管理 ==========

// 主题预设配置
const THEME_PRESETS = {
    yaoye: {
        name: '耀夜',
        titlebar: '#000000',
        loading: '#000000',
        main: '#000000',
        accent: '#FF9E80'
    },
    shuangbai: {
        name: '霜白',
        titlebar: '#FFFFFF',
        loading: '#FFFFFF',
        main: '#FFFFFF',
        accent: '#ff6b35'
    },
    taoxi: {
        name: '桃汐',
        titlebar: '#FFFFFF',
        loading: '#FFD6E0',
        main: '#FFF0F5',
        accent: '#ff6b35'
    },
    cuimo: {
        name: '翠墨',
        titlebar: '#000000',
        loading: '#000000',
        main: '#000000',
        accent: '#10b981'
    }
};

const ThemeColors = {
    // 深色主题颜色
    dark: {
        bg: '#000000',
        bgSecondary: '#0a0a0a',
        textPrimary: '#EAEAEA',
        textSecondary: '#666666',
        borderColor: '#444444',
        accentUser: '#80D1FF',
        accentAssistant: '#FF9E80',
        accentActive: '#50FA7B',
        toolColor: '#00FFFF',
        errorColor: '#FF5555',
        successColor: '#50FA7B',
        codeBg: '#1a1a1a',
        scrollbarTrack: '#0a0a0a',
        scrollbarThumb: '#444444',
        scrollbarThumbHover: '#555555',
        inputBg: '#0b0b0b',
        headerUserText: '#000000',
        headerAssistantText: '#000000',
        modalBg: '#0d0d0d',
        cardBg: '#0d0d0d',
        buttonText: '#ffffff',
        buttonSecondaryText: '#000000',
        chainItemHover: 'rgba(255,255,255,0.08)',
        historyItemHover: 'rgba(255,255,255,0.08)',
        progressBar: '#ff4444',
        toolBg: '#0d0d0d'
    },

    // 浅色主题颜色
    light: {
        bg: '#FFFFFF',
        bgSecondary: '#f5f5f5',
        textPrimary: '#333333',
        textSecondary: '#666666',
        borderColor: '#999999',
        accentUser: '#0066cc',
        accentAssistant: '#ff6b35',
        accentActive: '#28a745',
        toolColor: '#0088aa',
        errorColor: '#dc3545',
        successColor: '#28a745',
        codeBg: '#f0f0f0',
        scrollbarTrack: '#f0f0f0',
        scrollbarThumb: '#999999',
        scrollbarThumbHover: '#666666',
        inputBg: '#ffffff',
        headerUserText: '#000000',
        headerAssistantText: '#000000',
        modalBg: '#ffffff',
        cardBg: '#f9f9f9',
        buttonText: '#ffffff',
        buttonSecondaryText: '#000000',
        chainItemHover: 'rgba(0,0,0,0.08)',
        historyItemHover: 'rgba(0,0,0,0.08)',
        progressBar: '#dc3545',
        toolBg: '#f0f0f0'
    },

    // 当前主题
    current: 'dark',

    // 用户配置的主背景色
    userBgColor: null,
    // 用户配置的主题色
    userAccentColor: null,

    // 初始化主题
    init(bgColor, accentColor) {
        this.userBgColor = bgColor;
        this.userAccentColor = accentColor;
        const brightness = this.getBrightness(bgColor);
        this.current = brightness > 128 ? 'light' : 'dark';
        this.applyColors();
    },

    // 计算颜色亮度
    getBrightness(color) {
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        return (r * 299 + g * 587 + b * 114) / 1000;
    },

    // 获取当前主题的颜色
    get(key) {
        return this[this.current][key] || this.dark[key];
    },

    // 应用颜色到CSS变量
    applyColors() {
        const colors = this[this.current];
        const root = document.documentElement;

        // 使用用户配置的背景色，而不是预设的颜色
        root.style.setProperty('--bg-color', this.userBgColor);
        root.style.setProperty('--bg-secondary', colors.bgSecondary);
        root.style.setProperty('--text-primary', colors.textPrimary);
        root.style.setProperty('--text-secondary', colors.textSecondary);
        root.style.setProperty('--border-color', colors.borderColor);
        
        // 使用用户配置的主题色，或者预设颜色
        const accent = this.userAccentColor || colors.accentAssistant;
        root.style.setProperty('--accent-user', colors.accentUser);
        root.style.setProperty('--accent-assistant', accent);
        root.style.setProperty('--accent-active', accent);
        
        root.style.setProperty('--tool-color', colors.toolColor);
        root.style.setProperty('--error-color', colors.errorColor);
        root.style.setProperty('--success-color', accent); // 成功色也跟随主题色
        root.style.setProperty('--code-bg', colors.codeBg);
        root.style.setProperty('--modal-bg', colors.modalBg);
        root.style.setProperty('--card-bg', colors.cardBg);
        root.style.setProperty('--input-bg', colors.inputBg);
        root.style.setProperty('--hover-bg', colors.chainItemHover);
        root.style.setProperty('--history-hover-bg', colors.historyItemHover);
        root.style.setProperty('--button-hover-bg', colors.chainItemHover);
        root.style.setProperty('--scrollbar-track', colors.scrollbarTrack);
        root.style.setProperty('--scrollbar-thumb', colors.scrollbarThumb);
        root.style.setProperty('--scrollbar-thumb-hover', colors.scrollbarThumbHover);
    }
};

// ========== Markdown 配置 ==========
marked.setOptions({
    highlight: (code, lang) => {
        if (typeof hljs === 'undefined') return code;
        try {
            if (lang && hljs.getLanguage(lang)) {
                return hljs.highlight(code, { language: lang }).value;
            }
            return hljs.highlightAuto(code).value;
        } catch (e) {
            return code;
        }
    },
    langPrefix: 'hljs language-', gfm: true, breaks: true
});

// ========== DOM ==========
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

// 缓存会话列表，用于前端判断（需要在 newChatBtn 事件之前定义）
let cachedSessions = [];

const dom = {
    statusBar: $('#status-bar'),
    msgWrap: $('#messages-wrapper'),
    messages: $('#messages'),
    form: $('#input-form'),
    input: $('#input'),
    sendBtn: $('#send-btn'),
    modal: $('#modal'),
    modalTitle: $('#modal-title'),
    modalBody: $('#modal-body'),
    modalActions: $('#modal-actions'),
    modalOk: $('#modal-ok'),
    historyList: $('#history-list'),
    historyEmpty: $('#history-empty'),
    newChatBtn: $('#new-chat-btn'),
    viewHistory: $('#view-history'),
    viewChain: $('#view-chain'),
    viewMemory: $('#view-memory'),
    chainList: $('#chain-list'),
    memoryCanvas: $('#memory-canvas'),
    memoryEmpty: $('#memory-empty'),
    memoryStats: $('#memory-stats'),
    memorySearchBtn: $('#memory-search-btn'),
    memoryCleanBtn: $('#memory-clean-btn'),
    sidebar: $('.sidebar'),
    main: $('.main'),
    toggleSidebarBtn: $('#toggle-sidebar'),
    newChatToolbarBtn: $('#new-chat-toolbar')
};

// ========== 工具栏功能 ==========
// 侧边栏状态
let sidebarVisible = true;

// 切换侧边栏
function toggleSidebar() {
    sidebarVisible = !sidebarVisible;
    dom.sidebar.classList.toggle('sidebar--hidden', !sidebarVisible);
    dom.main.classList.toggle('main--full-width', !sidebarVisible);
    dom.toggleSidebarBtn.classList.toggle('toolbar__btn--active', sidebarVisible);
    // 保存到 localStorage
    localStorage.setItem('paw-sidebar-visible', sidebarVisible);
}

// 初始化侧边栏状态
function initSidebarState() {
    const saved = localStorage.getItem('paw-sidebar-visible');
    if (saved !== null) {
        sidebarVisible = saved === 'true';
    } else {
        sidebarVisible = true;
    }
    dom.sidebar.classList.toggle('sidebar--hidden', !sidebarVisible);
    dom.main.classList.toggle('main--full-width', !sidebarVisible);
    dom.toggleSidebarBtn.classList.toggle('toolbar__btn--active', sidebarVisible);
}

// 工具栏事件
dom.toggleSidebarBtn.addEventListener('click', toggleSidebar);

dom.newChatToolbarBtn.addEventListener('click', () => {
    dom.newChatBtn.click();
});

// 快捷键: Ctrl+B 切换侧边栏
document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
    }
});

// 初始化侧边栏状态
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
        // 切换到对话链视图时刷新
        if (view === 'chain') ChatHistory.renderChain();
    });
});

// ========== 历史对话管理 ==========
const ChatHistory = {
    messages: [],      // 当前对话的消息列表（仅用于显示，不持久化）
    turns: [],         // 对话轮次列表，每轮包含 {role, msgId, text, parts: [{type, id, name, text}]}
    currentSessionId: null,  // 当前会话ID
    currentTurn: null, // 当前正在进行的助手轮次
    isInAssistantTurn: false, // 是否在助手轮次中（从用户发送到turn_end）

    // 添加用户消息 - 同时开始新的助手轮次
    addUserMessage(text) {
        const msgId = `msg-${Date.now()}`;
        this.messages.push({ id: msgId, role: 'user', text });
        // 添加用户轮次
        this.turns.push({
            role: 'user',
            msgId: msgId,
            text: text,
            parts: []
        });
        dom.messages.appendChild(createMsgEl('user', 'USER', text, msgId));
        scrollToBottom();
        this.renderChain();
        
        // 关键：标记进入助手轮次，创建空的助手轮次对象
        // 这个轮次会在 turn_end 时被提交到 turns 数组
        this.isInAssistantTurn = true;
        this.currentTurn = {
            role: 'assistant',
            msgId: null,  // 第一次 onStreamStart 时设置
            text: '',
            parts: []
        };
        
        return msgId;
    },

    // 记录流式文本开始 - 设置当前轮次的消息ID
    onStreamStart(msgId) {
        if (this.currentTurn && this.isInAssistantTurn) {
            // 只在第一次设置 msgId
            if (!this.currentTurn.msgId) {
                this.currentTurn.msgId = msgId;
            }
        }
    },

    // 记录流式文本结束 - 添加文本到当前轮次的 parts
    onStreamEnd(text) {
        if (this.currentTurn && this.isInAssistantTurn && text) {
            this.currentTurn.parts.push({ type: 'text', text: text });
            // 用第一段文本作为预览
            if (!this.currentTurn.text) {
                this.currentTurn.text = text;
            }
        }
    },

    // 添加工具调用到当前轮次
    addTool(toolId, toolName) {
        if (this.currentTurn && this.isInAssistantTurn) {
            this.currentTurn.parts.push({ type: 'tool', id: toolId, name: toolName });
        }
    },

    // 结束助手轮次（turn_end 时调用）
    // 这是整个轮次的终点，将 currentTurn 提交到 turns 数组
    endAssistantTurn() {
        if (this.currentTurn && this.isInAssistantTurn) {
            // 只有有内容时才添加到 turns
            if (this.currentTurn.parts.length > 0 || this.currentTurn.text) {
                this.turns.push(this.currentTurn);
                this.messages.push({ 
                    id: this.currentTurn.msgId || `msg-${Date.now()}`, 
                    role: 'assistant', 
                    text: this.currentTurn.text 
                });
            }
            // 重置状态
            this.currentTurn = null;
            this.isInAssistantTurn = false;
            this.renderChain();
        }
    },

    // 渲染对话链视图
    renderChain() {
        if (!this.turns.length) {
            dom.chainList.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:2rem 1rem">发送消息开始对话</div>';
            return;
        }
        dom.chainList.innerHTML = '';

        this.turns.forEach((turn, idx) => {
            const el = document.createElement('div');
            el.className = 'chain-item';
            el.dataset.msgId = turn.msgId;
            el.dataset.turnIdx = idx;

            const isAssistant = turn.role === 'assistant';
            const hasParts = isAssistant && turn.parts.length > 0;
            const toolCount = turn.parts.filter(p => p.type === 'tool').length;
            
            // 预览文本
            let preview = '';
            if (turn.role === 'user') {
                preview = turn.text || '';
            } else {
                // 助手：优先显示文本，否则显示工具数量
                const firstText = turn.parts.find(p => p.type === 'text');
                preview = firstText ? firstText.text.slice(0, 40) : (toolCount > 0 ? `${toolCount} 个工具调用` : '');
            }

            // 构建详情HTML（只有助手轮次有）
            let detailsHtml = '';
            if (hasParts) {
                detailsHtml = '<div class="chain-item__details">';
                turn.parts.forEach((part, partIdx) => {
                    if (part.type === 'tool') {
                        detailsHtml += `<div class="chain-item__detail chain-item__detail--tool" data-tool-id="${part.id}">⎿ ⚙ ${part.name}</div>`;
                    } else if (part.type === 'text') {
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

            // 点击头部：展开/折叠 + 滚动
            el.querySelector('.chain-item__header').addEventListener('click', (e) => {
                if (hasParts) {
                    el.classList.toggle('chain-item--expanded');
                }
                // 滚动到对应消息
                if (turn.msgId) {
                    highlightAndScrollTo(turn.msgId);
                }
            });

            // 点击详情项
            el.querySelectorAll('.chain-item__detail').forEach(detail => {
                detail.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const toolId = detail.dataset.toolId;
                    if (toolId) {
                        highlightAndScrollTo(`tool-${toolId}`, true);
                    } else if (turn.msgId) {
                        highlightAndScrollTo(turn.msgId);
                    }
                });
            });

            dom.chainList.appendChild(el);
        });
    },

    // 清空
    clear() {
        this.messages = [];
        this.turns = [];
        this.currentTurn = null;
        this.isInAssistantTurn = false;
        this.renderChain();
    }
};

// 高亮并滚动到指定元素
function highlightAndScrollTo(elementId, isTool = false) {
    const el = document.getElementById(elementId);
    if (!el) return;

    // 移除之前的高亮
    document.querySelectorAll('.msg--highlighted, .tool--highlighted').forEach(e => {
        e.classList.remove('msg--highlighted', 'tool--highlighted');
    });

    // 添加高亮
    el.classList.add(isTool ? 'tool--highlighted' : 'msg--highlighted');

    // 滚动到元素
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // 2秒后移除高亮
    setTimeout(() => {
        el.classList.remove('msg--highlighted', 'tool--highlighted');
    }, 2000);
}

// 历史对话事件(使用 WebSocket 请求后端)
dom.historyList.addEventListener('click', e => {
    const deleteBtn = e.target.closest('[data-delete]');
    if (deleteBtn) {
        e.stopPropagation();
        // 如果正在生成中，阻止删除操作
        if (isGenerating) {
            showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
            return;
        }
        ws.send(`/delete-session ${deleteBtn.dataset.delete}`);
        return;
    }
    const item = e.target.closest('.history-item');
    if (item) {
        // 如果正在生成中，提示用户先中断 - 在发送请求之前就返回
        if (isGenerating) {
            showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
            return;
        }
        requestLoadSession(item.dataset.id);
    }
});

dom.newChatBtn.addEventListener('click', () => {
    // 如果正在生成中，提示用户先中断 - 在任何操作之前就返回
    if (isGenerating) {
        showInfoDialog('我正在回答中，可以先点 Stop 中断当前会话哦~');
        return;
    }
    // 检查当前是否已经是空对话(message_count === 0)
    const currentSession = cachedSessions.find(s => s.session_id === ChatHistory.currentSessionId);
    if (currentSession && currentSession.message_count === 0) {
        // 已经在空对话中，只需确保高亮并清空聊天区
        updateSidebarHighlight(ChatHistory.currentSessionId);
        ChatHistory.clear();
        dom.messages.innerHTML = '';
        dom.chainList.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:2rem 1rem">发送消息开始对话</div>';
        return;
    }
    
    // 检查是否已存在其他空对话(message_count === 0)
    const existingEmptySession = cachedSessions.find(s => s.message_count === 0);
    if (existingEmptySession) {
        // 切换到已存在的空对话
        requestLoadSession(existingEmptySession.session_id);
        return;
    }
    
    // 没有空对话，请求后端创建新对话
    ws.send('/new');
});

// ========== 消息渲染 ==========
function createMsgEl(type, author, text, id = null) {
    const el = document.createElement('div');
    el.className = `msg msg--${type}`;
    if (id) el.id = id;
    // 添加工具容器（用于附加该消息的工具调用）
    el.innerHTML = `<div class="msg__header">${author}</div><div class="msg__content">${marked.parse(text)}</div><div class="msg__tools"></div>`;
    return el;
}

function addSysMsg(text, type = '') {
    const el = document.createElement('div');
    el.className = `sys-msg ${type}`;
    el.textContent = text;
    dom.messages.appendChild(el);
    scrollToBottom();
}

function scrollToBottom() { dom.msgWrap.scrollTop = dom.msgWrap.scrollHeight; }

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ========== WebSocket ==========
const ws = new WebSocket(`ws://${location.host}/ws`);
ws.onopen = () => {
    // WebSocket 连接成功，静默处理
    // 请求会话列表
    ws.send('/sessions');
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
            // 结束助手轮次
            ChatHistory.endAssistantTurn();
            setGeneratingState(false);
        },
        'system_message': () => addSysMsg(data.text, data.type),
        'status_update': () => updateStatus(data),
        'show_model_selection': () => showModelSelect(data.models),
        'request_input': () => showInputPrompt(data),
        'show_memory': () => Memory.show(data.conversations),
        'memory_result': () => Memory.handleResult(data),
        'session_list': () => handleSessionList(data),
        'session_load': () => handleSessionLoad(data),
        'show_error': () => showErrorDialog(data.text),
        'session_loaded': () => {
            // 静默加载会话，不显示消息
            // 更新当前会话ID和侧边栏高亮
            if (data.session_id) {
                ChatHistory.currentSessionId = data.session_id;
                updateSidebarHighlight(data.session_id);
            }
        },
        'new_chat': () => {
            ChatHistory.clear();
            dom.messages.innerHTML = '';
            dom.chainList.innerHTML = '<div style="color:var(--text-secondary);font-size:0.8rem;text-align:center;padding:2rem 1rem">发送消息开始对话</div>';
            // 更新当前会话ID（如果后端返回了）
            if (data.session_id) {
                ChatHistory.currentSessionId = data.session_id;
                // 更新侧边栏高亮
                updateSidebarHighlight(data.session_id);
            }
            // 请求刷新会话列表以确保侧边栏同步
            requestSessionList();
        },
        'models_fetched': () => {
            if (window._modelFetchCallback) {
                window._modelFetchCallback(data);
                window._modelFetchCallback = null;
            }
        }
    };
    h[event]?.();
}

// ========== 会话管理 ==========
function handleSessionList({ sessions, current_id }) {
    // 缓存会话列表
    cachedSessions = sessions || [];
    // 更新侧边栏的会话列表
    dom.historyList.innerHTML = '';
    sessions.forEach(s => {
        const el = document.createElement('div');
        el.className = 'history-item';
        el.dataset.id = s.session_id;
        if (s.session_id === current_id) el.classList.add('history-item--active');
        el.innerHTML = `
            <div class="history-item__title">${escapeHtml(s.title || '新对话')}</div>
            <div class="history-item__meta">${s.timestamp || ''} · ${s.message_count || 0} 消息</div>
            <span class="history-item__delete" data-delete="${s.session_id}">×</span>
        `;
        dom.historyList.appendChild(el);
    });
    // 更新当前会话ID
    ChatHistory.currentSessionId = current_id;
}

// 更新侧边栏高亮状态
function updateSidebarHighlight(sessionId) {
    dom.historyList.querySelectorAll('.history-item').forEach(item => {
        item.classList.toggle('history-item--active', item.dataset.id === sessionId);
    });
}

function handleSessionLoad({ chunks }) {
    // 清空当前消息
    ChatHistory.clear();
    dom.messages.innerHTML = '';

    // 先收集工具结果（稍后更新）
    const toolResults = [];
    // 建立 tool_call_id → args 的映射
    const toolArgsMap = new Map();
    
    // 当前助手轮次的 parts 和消息元素
    let currentAssistantParts = [];
    let currentAssistantMsgId = null;
    let currentAssistantMsgEl = null;  // 当前助手消息的 DOM 元素

    // 从 chunks 重建消息和工具调用
    // 关键：连续的 assistant chunks（在同一个 user 之后）应该合并为一个轮次
    chunks.forEach(chunk => {
        const type = chunk.type;

        if (type === 'user') {
            // 遇到用户消息，先保存之前的助手轮次
            if (currentAssistantParts.length > 0) {
                ChatHistory.turns.push({
                    role: 'assistant',
                    msgId: currentAssistantMsgId,
                    text: currentAssistantParts.find(p => p.type === 'text')?.text || '',
                    parts: currentAssistantParts
                });
                currentAssistantParts = [];
                currentAssistantMsgId = null;
                currentAssistantMsgEl = null;
            }
            
            // 用户消息
            const msgId = `msg-${Date.now()}-${Math.random()}`;
            ChatHistory.messages.push({ id: msgId, role: 'user', text: chunk.content });
            ChatHistory.turns.push({
                role: 'user',
                msgId: msgId,
                text: chunk.content,
                parts: []
            });
            dom.messages.appendChild(createMsgEl('user', 'USER', chunk.content, msgId));

        } else if (type === 'assistant') {
            // 助手消息 - 检查是否应该合并到现有轮次
            // 如果已有助手消息元素且没有遇到新的用户消息，则合并
            if (currentAssistantMsgEl) {
                // 合并到现有消息：在工具后添加新内容块
                if (chunk.content) {
                    const newContent = document.createElement('div');
                    newContent.className = 'msg__content msg__content--continued';
                    newContent.innerHTML = marked.parse(chunk.content);
                    currentAssistantMsgEl.appendChild(newContent);
                    currentAssistantParts.push({ type: 'text', text: chunk.content });
                }
            } else {
                // 创建新的助手消息
                const msgId = `msg-${Date.now()}-${Math.random()}`;
                currentAssistantMsgId = msgId;
                ChatHistory.messages.push({ id: msgId, role: 'assistant', text: chunk.content || '' });
                
                currentAssistantMsgEl = createMsgEl('assistant', 'PAW', chunk.content || '', msgId);
                dom.messages.appendChild(currentAssistantMsgEl);
                
                // 记录文本内容
                if (chunk.content) {
                    currentAssistantParts.push({ type: 'text', text: chunk.content });
                }
            }

            // 如果有 tool_calls，渲染工具调用
            if (chunk.metadata?.tool_calls) {
                chunk.metadata.tool_calls.forEach(tc => {
                    const func = tc.function || {};
                    const args = func.arguments || '{}';
                    const parsedArgs = typeof args === 'string' ? JSON.parse(args) : args;
                    toolArgsMap.set(tc.id, parsedArgs);
                    
                    // 创建工具元素
                    const toolEl = document.createElement('div');
                    toolEl.id = `tool-${tc.id}`;
                    toolEl.className = 'tool';
                    toolEl.innerHTML = `<div class="tool__header"><div class="tool__spinner"></div><span class="tool__name">${func.name}</span> <span class="tool__args">${typeof args === 'string' ? args : JSON.stringify(args)}</span></div>`;
                    
                    const toolsContainer = currentAssistantMsgEl.querySelector('.msg__tools');
                    if (toolsContainer) {
                        toolsContainer.appendChild(toolEl);
                    }
                    
                    // 记录工具
                    currentAssistantParts.push({ type: 'tool', id: tc.id, name: func.name });
                });
            }

        } else if (type === 'tool_result') {
            // 收集工具结果，稍后更新
            toolResults.push({
                toolCallId: chunk.metadata?.tool_call_id,
                toolName: chunk.metadata?.name || 'unknown',
                content: chunk.content
            });
        }
    });
    
    // 保存最后一个助手轮次
    if (currentAssistantParts.length > 0) {
        ChatHistory.turns.push({
            role: 'assistant',
            msgId: currentAssistantMsgId,
            text: currentAssistantParts.find(p => p.type === 'text')?.text || '',
            parts: currentAssistantParts
        });
    }

    // 更新所有工具结果状态
    toolResults.forEach(result => {
        const args = toolArgsMap.get(result.toolCallId) || {};
        const display = getToolDisplay(result.toolName, result.content, args);
        updateTool({
            id: result.toolCallId,
            name: result.toolName,
            display: display,
            success: true
        });
    });

    scrollToBottom();
    ChatHistory.renderChain();
}

// 重新生成工具显示信息（与后端 _get_tool_display 逻辑一致）
function getToolDisplay(toolName, resultText, args) {
    const content = resultText || '';

    // read_file
    if (toolName === 'read_file') {
        const path = args.file_path || '';
        const filename = path.split('/').pop().split('\\').pop();
        const totalLines = content.split('\n').length;
        const offset = args.offset;
        const limit = args.limit;
        let rangeStr = `(all ${totalLines}行)`;
        if (offset && limit) {
            const end = offset + limit - 1;
            rangeStr = `(${offset}-${end}/${totalLines}行)`;
        } else if (offset) {
            rangeStr = `(${offset}-end/${totalLines}行)`;
        }
        return {
            line1: `${filename} ${rangeStr}`,
            line2: '',
            has_line2: false
        };
    }

    // write_to_file / delete_file / edit / multi_edit
    if (['write_to_file', 'delete_file', 'edit', 'multi_edit'].includes(toolName)) {
        const path = args.file_path || '';
        const filename = path.split('/').pop().split('\\').pop();
        return { line1: filename, line2: '', has_line2: false };
    }

    // list_dir
    if (toolName === 'list_dir') {
        const path = args.directory_path || '.';
        const lines = content.split('\n').filter(l => l.startsWith('['));
        const count = lines.length;
        const preview = lines.slice(0, 3).map(l => {
            const match = l.match(/\] (.+?)(?: \(|$)/);
            return match ? match[1] : '';
        }).filter(Boolean).join(', ');
        return {
            line1: path,
            line2: preview + (count > 3 ? `... (+${count-3})` : ''),
            has_line2: count > 0
        };
    }

    // find_by_name
    if (toolName === 'find_by_name') {
        const pattern = args.pattern || '';
        const items = content.split('\n').filter(Boolean);
        const count = items.length;
        if (count === 0) {
            return { line1: `"${pattern}" 无匹配`, line2: '', has_line2: false };
        }
        const names = items.slice(0, 3).map(i => i.split('/').pop().split('\\').pop());
        const preview = names.join(', ');
        return {
            line1: `"${pattern}" ${count}匹配`,
            line2: preview + (count > 3 ? `... (+${count-3})` : ''),
            has_line2: true
        };
    }

    // grep_search
    if (toolName === 'grep_search') {
        const query = args.query || '';
        const resultText = content.trim();
        if (!resultText || resultText.toLowerCase().includes('no matches')) {
            return { line1: `"${query}" 无匹配`, line2: '', has_line2: false };
        }
        const lines = resultText.split('\n');
        const summary = lines[0]?.slice(0, 60) + (lines[0].length > 60 ? '...' : '');
        return {
            line1: `"${query}"`,
            line2: summary + (lines.length > 1 ? ` (+${lines.length-1})` : ''),
            has_line2: true
        };
    }

    // search_web
    if (toolName === 'search_web') {
        const query = args.query || '';
        try {
            const jsonMatch = content.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const data = JSON.parse(jsonMatch[0]);
                const results = data.results || [];
                return {
                    line1: `${results.length}条 "${query}"`,
                    line2: results.map(r => `[${r.id}] ${r.title}`).join('\n'),
                    has_line2: results.length > 0
                };
            }
        } catch (e) {}
        return { line1: `"${query}"`, line2: '', has_line2: false };
    }

    // load_url_content
    if (toolName === 'load_url_content') {
        try {
            const jsonMatch = content.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const data = JSON.parse(jsonMatch[0]);
                const title = (data.title || '无标题').slice(0, 40);
                const urlId = data.url_id || '';
                const pages = data.pages || [];
                return {
                    line1: urlId ? `[${urlId}] ${title}` : title,
                    line2: pages.map(p => `[${p.page_id}] ${p.summary}`).join('\n'),
                    has_line2: pages.length > 0
                };
            }
        } catch (e) {}
        return { line1: args.url?.slice(0, 40) || '', line2: '', has_line2: false };
    }

    // read_page
    if (toolName === 'read_page') {
        const pageId = args.page_id || '';
        try {
            const jsonMatch = content.match(/\{[\s\S]*\}/);
            if (jsonMatch) {
                const data = JSON.parse(jsonMatch[0]);
                const pageNum = data.page_num || '?';
                const total = data.total_pages || '?';
                const size = data.size || 0;
                return {
                    line1: `[${pageId}] 第${pageNum}/${total}页 (${size}字节)`,
                    line2: '',
                    has_line2: false
                };
            }
        } catch (e) {}
        return { line1: `[${pageId}]`, line2: '', has_line2: false };
    }

    // 默认：多行内容显示
    if (content.includes('\n')) {
        const lines = content.split('\n');
        return {
            line1: lines[0]?.slice(0, 60) || '',
            line2: lines.slice(1, 10).join('\n'),
            has_line2: true
        };
    }

    return { line1: content.slice(0, 60), line2: '', has_line2: false };
}

// 请求会话列表
function requestSessionList() {
    ws.send('/sessions');
}

// 请求加载会话
function requestLoadSession(sessionId) {
    ws.send(`/load ${sessionId}`);
}

function send(msg) {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(msg);
    } else {
        showErrorDialog('未连接到服务器');
    }
}

// ========== 消息处理 ==========
let streamId = null, streamBuf = '';
let isGenerating = false;  // 是否正在生成

function addUserMessage(text) {
    return ChatHistory.addUserMessage(text);
}

function setGeneratingState(generating) {
    isGenerating = generating;
    if (generating) {
        dom.sendBtn.textContent = 'Stop';
        dom.sendBtn.classList.add('button--stop');
    } else {
        dom.sendBtn.textContent = 'Send';
        dom.sendBtn.classList.remove('button--stop');
    }
}

function startStream(id) {
    streamId = id;
    streamBuf = '';
    
    // 核心逻辑：在同一轮次中（isInAssistantTurn=true），复用同一个消息元素
    // 只有新轮次才创建新消息
    let existingMsg = dom.messages.querySelector('.msg--assistant:last-child');
    
    if (ChatHistory.isInAssistantTurn && existingMsg) {
        // 同一轮次中，复用现有消息
        // 检查是否有工具调用，如果有则在工具后添加新内容块
        const toolsContainer = existingMsg.querySelector('.msg__tools');
        if (toolsContainer && toolsContainer.children.length > 0) {
            // 有工具调用，在消息末尾添加新内容块（工具后的继续输出）
            const newContent = document.createElement('div');
            newContent.className = 'msg__content msg__content--continued';
            newContent.id = id;
            existingMsg.appendChild(newContent);
        } else {
            // 没有工具调用，直接使用现有内容区域
            // 如果内容区域已有内容，添加新内容块
            const existingContent = existingMsg.querySelector('.msg__content');
            if (existingContent && existingContent.innerHTML.trim()) {
                const newContent = document.createElement('div');
                newContent.className = 'msg__content msg__content--continued';
                newContent.id = id;
                existingMsg.appendChild(newContent);
            }
        }
        // 不需要调用 onStreamStart，因为 msgId 已经设置
    } else {
        // 新轮次，创建新消息
        dom.messages.appendChild(createMsgEl('assistant', 'PAW', '', id));
        ChatHistory.onStreamStart(id);
    }
}

function appendStream(id, text) {
    // 优先查找专门的内容块，否则查找消息内容
    let content = document.getElementById(id);
    if (!content) {
        content = dom.messages.querySelector('.msg--assistant:last-child .msg__content:last-of-type');
    }
    if (!content) return;
    
    streamBuf += text;
    content.innerHTML = marked.parse(streamBuf);
    scrollToBottom();
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
            btn.onclick = () => { navigator.clipboard.writeText(el.textContent); btn.textContent = 'Copied!'; setTimeout(() => btn.textContent = 'Copy', 2000); };
            pre.appendChild(btn);
        });
    }

    // 记录流式结束（添加到当前轮次的 parts）
    ChatHistory.onStreamEnd(streamBuf);

    streamId = null;
    streamBuf = '';
}

function createTool({ id, name, args }) {
    // stay_silent 核心修正：在工具开始时立即执行清理
    if (name === 'stay_silent') {
        // 查找当前助手消息
        const msgEl = dom.messages.querySelector('.msg--assistant:last-child');
        if (msgEl) {
            msgEl.remove();
        }
        
        // 立即重置 ChatHistory 状态
        if (ChatHistory.currentTurn) {
            ChatHistory.currentTurn = null;
            ChatHistory.isInAssistantTurn = false;
        }
        
        // 核心修正：检测到 stay_silent 后，强制立即结束生成状态，恢复 Send 按钮
        setGeneratingState(false);
        
        // 不需要继续创建工具 UI
        return;
    }

    const el = document.createElement('div');
    el.id = `tool-${id}`;
    el.className = 'tool';
    el.innerHTML = `<div class="tool__header"><div class="tool__spinner"></div><span class="tool__name">${name}</span> <span class="tool__args">${args}</span></div>`;

    // 核心逻辑：在同一轮次中，工具调用附加到当前助手消息
    let msgEl = dom.messages.querySelector('.msg--assistant:last-child');
    
    if (ChatHistory.isInAssistantTurn && msgEl) {
        // 同一轮次，附加到现有消息
        const toolsContainer = msgEl.querySelector('.msg__tools');
        if (toolsContainer) {
            toolsContainer.appendChild(el);
        } else {
            msgEl.appendChild(el);
        }
    } else {
        // 新轮次（理论上不应该发生，因为工具调用前应该有流式输出）
        // 但为了健壮性，创建新消息
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
    
    // 记录工具调用到当前轮次
    ChatHistory.addTool(id, name);
    
    scrollToBottom();
}

function updateTool({ id, name, display, success }) {
    const el = document.getElementById(`tool-${id}`);
    if (!el) return;
    
    // stay_silent 特殊处理：移除整个助手消息，就像 Paw 完全没有回复
    if (name === 'stay_silent') {
        const msgEl = el.closest('.msg--assistant');
        if (msgEl) {
            msgEl.remove();
        }
        // 重置 ChatHistory，不记录这个轮次
        if (ChatHistory.currentTurn) {
            ChatHistory.currentTurn = null;
            ChatHistory.isInAssistantTurn = false;
        }
        return;
    }
    
    el.className = `tool ${success ? 'tool--success' : 'tool--error'}`;

    const line1 = display.line1 || '';
    const line2 = display.line2 || '';
    const hasLine2 = display.has_line2 || false;

    // Header: ● tool_name line1
    let headerHtml = `<span class="tool__icon">●</span><span class="tool__name">${name}</span> <span class="tool__args">${line1}</span>`;

    // Body: 每行前面加 ⎿
    let bodyHtml = '';
    if (hasLine2 && line2) {
        const lines = line2.split('\n');
        let firstLine = true;
        lines.forEach(line => {
            // 如果行以 │ 开头（连接线），保留原样
            if (line.startsWith('│')) {
                bodyHtml += `<div class="tool__body-line">${escapeHtml(line)}</div>`;
            } else {
                // 第一行用 ⎿，后续行用空格对齐
                const prefix = firstLine ? '⎿ ' : '  ';
                bodyHtml += `<div class="tool__body-line">${prefix}${escapeHtml(line)}</div>`;
                firstLine = false;
            }
        });
    }

    el.innerHTML = `<div class="tool__header">${headerHtml}</div>${bodyHtml ? `<div class="tool__body">${bodyHtml}</div>` : ''}`;
}

function updateStatus(data) {
    const parts = [];
    if (data.time) parts.push(`time: ${data.time}`);
    if (data.model) parts.push(`model: ${data.model}`);
    if (data.mode) parts.push(`mode: ${data.mode}`);
    dom.statusBar.textContent = parts.join(' · ');
}

// ========== 弹窗 ==========
function showModelSelect(models) {
    dom.modalTitle.textContent = '选择模型';
    dom.modalBody.innerHTML = models.map(m => `<div class="modal__item" data-model="${m}">${m}</div>`).join('');
    dom.modalActions.style.display = 'none';
    dom.modal.classList.add('visible');
}

function showInputPrompt(data) {
    dom.modalTitle.textContent = data?.prompt || '输入';
    dom.modalBody.innerHTML = '<input type="text" class="modal__input" placeholder="输入...">';
    dom.modalActions.style.display = 'flex';
    dom.modal.classList.add('visible');
    setTimeout(() => dom.modalBody.querySelector('input')?.focus(), 30);
}

dom.modalBody.addEventListener('click', e => {
    const item = e.target.closest('.modal__item');
    if (item) { send(item.dataset.model); dom.modal.classList.remove('visible'); }
});

dom.modalOk.addEventListener('click', () => {
    const v = dom.modalBody.querySelector('input')?.value.trim();
    if (v) { send(v); dom.modal.classList.remove('visible'); }
});

// 点击遮罩层关闭弹窗
dom.modal.addEventListener('click', e => {
    // 只有点击遮罩层本身才关闭，点击弹窗内容不关闭
    if (e.target === dom.modal) {
        dom.modal.classList.remove('visible');
    }
});

// ========== 输入 ==========
function handleSubmit() {
    // 如果正在生成/处理中，点击按钮则是停止
    if (isGenerating) {
        send('/stop');
        // 不改变状态，等待 turn_end 事件
        return;
    }

    // 发送消息
    const msg = dom.input.value.trim();
    if (!msg) return;
    
    // 检查是否是命令（以 / 开头）
    const isCommand = msg.startsWith('/');
    
    send(msg);
    
    // 只有非命令消息才显示在聊天区并进入生成状态
    if (!isCommand) {
        addUserMessage(msg);
        setGeneratingState(true);  // 立即变成 Stop 状态
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

// ========== 记忆管理 ==========
const Memory = {
    conversations: [],
    selectedIndex: 0,
    active: false,

    show(conversations) {
        this.conversations = conversations || [];
        this.selectedIndex = 0;
        this.active = true;
        this.render();
        // 自动切换到记忆视图
        $$('.sidebar__tab').forEach(t => {
            t.classList.toggle('sidebar__tab--active', t.dataset.view === 'memory');
        });
        $$('.sidebar__view').forEach(v => v.classList.remove('sidebar__view--active'));
        dom.viewMemory.classList.add('sidebar__view--active');
    },

    hide() {
        this.active = false;
        dom.memoryCanvas.innerHTML = '<div class="memory-empty">/memory 打开记忆管理</div>';
    },

    render() {
        const count = this.conversations.length;
        dom.memoryStats.textContent = `共 ${count} 条记忆`;

        if (!count) {
            dom.memoryCanvas.innerHTML = '<div class="memory-empty">暂无记忆</div>';
            return;
        }

        let html = '';
        this.conversations.forEach((conv, idx) => {
            const meta = conv.metadata || {};
            const userMsg = meta.user_message || '';
            const preview = userMsg.substring(0, 40);
            const timestamp = meta.timestamp || '';
            const isActive = idx === this.selectedIndex;
            html += `
                <div class="memory-item ${isActive ? 'memory-item--active' : ''}" data-index="${idx}" data-id="${conv.id}">
                    <div class="memory-item__msg">${escapeHtml(preview)}</div>
                    <div class="memory-item__meta">${timestamp.substring(0, 16)}</div>
                    <button class="memory-item__delete" data-delete="${conv.id}">×</button>
                </div>
            `;
        });

        dom.memoryCanvas.innerHTML = html;

        // 绑定点击事件
        dom.memoryCanvas.querySelectorAll('.memory-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('memory-item__delete')) return;
                const idx = parseInt(e.currentTarget.dataset.index);
                this.select(idx);
            });
        });

        // 绑定删除事件
        dom.memoryCanvas.querySelectorAll('.memory-item__delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = e.target.dataset.delete;
                if (confirm('确定删除这条记忆吗？')) {
                    send(`MEMORY_DELETE:${id}`);
                }
            });
        });
    },

    select(idx) {
        this.selectedIndex = idx;
        this.render();

        // 显示详情弹窗
        const conv = this.conversations[idx];
        if (conv) {
            this.showDetail(conv);
        }
    },

    showDetail(conv) {
        const meta = conv.metadata || {};
        dom.modalTitle.textContent = '记忆详情';
        dom.modalBody.innerHTML = `
            <div style="font-size:0.8rem;color:var(--text-secondary);margin-bottom:0.5rem">
                ID: ${conv.id}<br>
                项目: ${meta.project || '(无)'}<br>
                时间: ${meta.timestamp || '(未知)'}
            </div>
            <div style="margin-bottom:0.5rem;color:var(--accent-user)">用户:</div>
            <div style="background:var(--card-bg);padding:0.5rem;border-radius:4px;margin-bottom:0.5rem;max-height:120px;overflow:auto">${escapeHtml(meta.user_message || '(无)')}</div>
            <div style="margin-bottom:0.5rem;color:var(--accent-assistant)">AI:</div>
            <div style="background:var(--card-bg);padding:0.5rem;border-radius:4px;max-height:120px;overflow:auto">${escapeHtml(meta.assistant_message || '(无)')}</div>
        `;
        dom.modalActions.style.display = 'none';
        dom.modal.classList.add('visible');
    },

    search(keyword) {
        send(`MEMORY_SEARCH:${keyword}`);
    },

    clean() {
        if (confirm('确定清理重复的记忆吗？')) {
            send('MEMORY_CLEAN');
        }
    },

    handleResult(data) {
        if (data.success) {
            addSysMsg(data.message || '操作成功');
            if (data.conversations) {
                this.conversations = data.conversations;
                this.render();
            }
            // 不隐藏记忆管理，继续编辑模式
        } else {
            addSysMsg(data.error || '操作失败', 'error');
        }
    }
};

// 记忆管理快捷键
dom.input.addEventListener('keydown', e => {
    if (!Memory.active) return;
    if (e.target.tagName === 'TEXTAREA') return;

    if (e.key === 'ArrowUp' || e.key === 'k') {
        e.preventDefault();
        Memory.select(Math.max(0, Memory.selectedIndex - 1));
    } else if (e.key === 'ArrowDown' || e.key === 'j') {
        e.preventDefault();
        Memory.select(Math.min(Memory.conversations.length - 1, Memory.selectedIndex + 1));
    } else if (e.key === 'q' || e.key === 'Q' || e.key === 'Escape') {
        e.preventDefault();
        Memory.hide();
    }
});

// 记忆按钮事件
dom.memorySearchBtn.addEventListener('click', () => {
    const keyword = prompt('输入搜索关键词:');
    if (keyword) Memory.search(keyword);
});

dom.memoryCleanBtn.addEventListener('click', () => {
    Memory.clean();
});

// ========== 配置管理 ==========
const Settings = {
    panel: null,
    overlay: null,
    toast: null,
    currentConfig: {},
    modelSelectOpen: false,
    fetchedModels: [],

    init() {
        this.panel = $('#settings-panel');
        this.overlay = $('#settings-overlay');
        this.toast = $('#settings-toast');

        // 绑定事件
        $('#settings-open-btn').addEventListener('click', () => this.open());
        $('#settings-close-btn').addEventListener('click', () => this.close());
        this.overlay.addEventListener('click', () => this.close());
        $('#settings-save-btn').addEventListener('click', () => this.save());
        $('#settings-reset-btn').addEventListener('click', () => this.reset());

        // 模型选择下拉 (LLM)
        this.setupDropdown({
            containerId: 'model-select',
            triggerId: 'model-select-trigger',
            dropdownId: 'model-select-dropdown',
            valueDisplayId: 'model-select-value',
            hiddenInputId: 'cfg-model',
            manualInputId: 'model-select-input',
            addBtnId: 'model-select-add',
            loadingId: 'model-select-loading',
            errorId: 'model-select-error',
            fetchConfig: () => ({
                key: $('#cfg-api-key').value.trim(),
                url: $('#cfg-api-url').value.trim()
            })
        });

        // 模型选择下拉 (Embedding)
        this.setupDropdown({
            containerId: 'embed-model-select',
            triggerId: 'embed-model-select-trigger',
            dropdownId: 'embed-model-select-dropdown',
            valueDisplayId: 'embed-model-select-value',
            hiddenInputId: 'cfg-embedding-model',
            manualInputId: 'embed-model-select-input',
            addBtnId: 'embed-model-select-add',
            loadingId: 'embed-model-select-loading',
            errorId: 'embed-model-select-error',
            fetchConfig: () => ({
                key: $('#cfg-embedding-key').value.trim(),
                url: $('#cfg-embedding-url').value.trim()
            })
        });

        // 主题选择器
        this.setupThemeSelector();

        // 记忆系统配置
        this.setupMemoryConfig();
    },

    setupDropdown(opts) {
        const container = $('#' + opts.containerId);
        const trigger = $('#' + opts.triggerId);
        const dropdown = $('#' + opts.dropdownId);
        const valueDisplay = $('#' + opts.valueDisplayId);
        const hiddenInput = $('#' + opts.hiddenInputId);
        const manualInput = $('#' + opts.manualInputId);
        const addBtn = $('#' + opts.addBtnId);

        // 切换状态管理
        container._isOpen = false;

        // 切换下拉
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            // 关闭其他打开的下拉
            document.querySelectorAll('.model-select--open').forEach(el => {
                if (el !== container) {
                    el.classList.remove('model-select--open');
                    el._isOpen = false;
                }
            });

            container._isOpen = !container._isOpen;
            container.classList.toggle('model-select--open', container._isOpen);
            
            if (container._isOpen) {
                this.fetchModelsForDropdown(opts);
            }
        });

        // 点击外部关闭
        document.addEventListener('click', (e) => {
            if (container._isOpen && !container.contains(e.target)) {
                container._isOpen = false;
                container.classList.remove('model-select--open');
            }
        });

        // 选项点击事件
        dropdown.addEventListener('click', (e) => {
            const option = e.target.closest('.model-select__option');
            if (option) {
                const value = option.dataset.value;
                this.selectOption(value, opts);
                container._isOpen = false;
                container.classList.remove('model-select--open');
            }
        });

        // 手动输入确定
        addBtn.addEventListener('click', () => {
            const value = manualInput.value.trim();
            if (value) {
                this.selectOption(value, opts);
                manualInput.value = '';
                container._isOpen = false;
                container.classList.remove('model-select--open');
            }
        });

        // 手动输入回车
        manualInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                addBtn.click();
            }
        });
    },

    selectOption(value, opts) {
        const hiddenInput = $('#' + opts.hiddenInputId);
        const valueDisplay = $('#' + opts.valueDisplayId);
        const dropdown = $('#' + opts.dropdownId);

        hiddenInput.value = value || '';

        if (!value) {
            valueDisplay.textContent = '留空或选择模型';
            valueDisplay.classList.add('model-select__value--placeholder');
        } else {
            valueDisplay.textContent = value;
            valueDisplay.classList.remove('model-select__value--placeholder');
        }

        // 更新选中状态
        dropdown.querySelectorAll('.model-select__option').forEach(opt => {
            opt.classList.toggle('model-select__option--selected', opt.dataset.value === value);
        });
    },

    async fetchModelsForDropdown(opts) {
        const config = opts.fetchConfig();
        if (!config.key && !config.url && opts.hiddenInputId === 'cfg-model') {
             // LLM 必须有 URL (Key 可选)
             this.showDropdownError(opts, '请先配置 API 地址');
             return;
        }
        if (!config.url && opts.hiddenInputId === 'cfg-embedding-model') {
             // Embedding 必须有 URL
             this.showDropdownError(opts, '请先配置 Embedding URL');
             return;
        }

        const loading = $('#' + opts.loadingId);
        const errorEl = $('#' + opts.errorId);
        const dropdown = $('#' + opts.dropdownId);
        const manualSection = $('#' + opts.manualInputId).parentElement; // model-select__manual div

        // 清除之前的动态选项
        dropdown.querySelectorAll('.model-select__option--dynamic').forEach(el => el.remove());
        errorEl.style.display = 'none';
        loading.style.display = 'block';

        try {
            // 通过 WebSocket 请求模型列表
            const requestId = Date.now().toString();
            const responsePromise = new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('请求超时')), 10000);
                // 挂载一个临时的 callback 处理器
                const originalCallback = window._modelFetchCallback;
                window._modelFetchCallback = (data) => {
                    if (data.request_id === requestId) {
                        clearTimeout(timeout);
                        if (data.error) reject(new Error(data.error));
                        else resolve(data.models);
                    } else if (originalCallback) {
                        originalCallback(data);
                    }
                };
            });

            ws.send(JSON.stringify({
                type: 'fetch_models',
                request_id: requestId,
                api_key: config.key,
                api_url: config.url
            }));

            const models = await responsePromise;
            
            // 插入模型选项
            models.forEach(model => {
                const option = document.createElement('div');
                option.className = 'model-select__option model-select__option--dynamic';
                option.dataset.value = model;
                option.textContent = model;
                // 插入到 manual section 之前
                dropdown.insertBefore(option, manualSection);
            });

            // 更新当前选中状态
            const currentValue = $('#' + opts.hiddenInputId).value;
            dropdown.querySelectorAll('.model-select__option--dynamic').forEach(opt => {
                opt.classList.toggle('model-select__option--selected', opt.dataset.value === currentValue);
            });

        } catch (err) {
            this.showDropdownError(opts, err.message || '获取模型列表失败');
        } finally {
            loading.style.display = 'none';
        }
    },

    showDropdownError(opts, message) {
        const errorEl = $('#' + opts.errorId);
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    },

    selectModel(value) {
        // 兼容旧接口，供 populateForm 使用 (仅更新 LLM 下拉)
        this.selectOption(value, {
            hiddenInputId: 'cfg-model',
            valueDisplayId: 'model-select-value',
            dropdownId: 'model-select-dropdown'
        });
    },

    setupMemoryConfig() {
        const memoryEnabled = $('#cfg-memory-enabled');
        const configFields = $('#memory-config-fields');
        const urlPreset = $('#cfg-embedding-url-preset');
        const urlInput = $('#cfg-embedding-url');

        // 启用/禁用记忆系统时展开/收起配置项
        memoryEnabled.addEventListener('change', () => {
            configFields.style.display = memoryEnabled.checked ? 'block' : 'none';
        });

        // URL 预设选择
        urlPreset.addEventListener('change', () => {
            const preset = urlPreset.value;
            if (preset === 'ollama') {
                urlInput.value = 'http://localhost:11434/api/embeddings';
            } else if (preset === 'lm_studio') {
                urlInput.value = 'http://localhost:1234/v1/embeddings';
            }
            // custom 时不改变，用户自己输入
        });

        // URL 输入框变化时自动检测预设
        urlInput.addEventListener('input', () => {
            const url = urlInput.value;
            if (url === 'http://localhost:11434/api/embeddings') {
                urlPreset.value = 'ollama';
            } else if (url === 'http://localhost:1234/v1/embeddings') {
                urlPreset.value = 'lm_studio';
            } else {
                urlPreset.value = 'custom';
            }
        });

        // 阈值校准按钮
        const calibrateBtn = $('#btn-calibrate-threshold');
        const thresholdInput = $('#cfg-recall-threshold');
        const statusEl = $('#calibrate-status');

        calibrateBtn.addEventListener('click', async () => {
            const embeddingUrl = urlInput.value.trim();
            const embeddingModel = $('#cfg-embedding-model').value.trim();

            if (!embeddingUrl || !embeddingModel) {
                this.showCalibrateStatus('error', '请先配置 Embedding URL 和模型');
                return;
            }

            // 显示加载状态
            calibrateBtn.disabled = true;
            this.showCalibrateStatus('loading', '正在计算推荐阈值...(这可能需要几分钟)');

            try {
                const response = await fetch('/api/calibrate-threshold', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        embedding_url: embeddingUrl,
                        embedding_model: embeddingModel
                    })
                });
                const result = await response.json();

                if (result.success) {
                    thresholdInput.value = result.threshold;
                    this.showCalibrateStatus('success', 
                        `推荐阈值: ${result.threshold} (质量: ${result.quality})`);
                    // 3秒后隐藏状态
                    setTimeout(() => this.hideCalibrateStatus(), 3000);
                } else {
                    this.showCalibrateStatus('error', result.error || '校准失败');
                }
            } catch (e) {
                this.showCalibrateStatus('error', '请求失败: ' + e.message);
            } finally {
                calibrateBtn.disabled = false;
            }
        });
    },

    showCalibrateStatus(type, message) {
        const statusEl = $('#calibrate-status');
        statusEl.style.display = 'flex';
        statusEl.className = 'settings__status settings__status--' + type;
        
        if (type === 'loading') {
            statusEl.innerHTML = '<div class="spinner"></div>' + message;
        } else {
            statusEl.textContent = message;
        }
    },

    hideCalibrateStatus() {
        const statusEl = $('#calibrate-status');
        statusEl.style.display = 'none';
    },

    setupThemeSelector() {
        const selector = $('#theme-selector');
        const themeInput = $('#cfg-theme');
        const options = selector.querySelectorAll('.theme-option');

        // 主题选项点击
        options.forEach(option => {
            option.addEventListener('click', () => {
                const theme = option.dataset.theme;
                this.selectTheme(theme);
            });
        });

        // 初始化选中状态
        this.selectTheme(themeInput.value || 'yaoye');
    },

    selectTheme(theme) {
        const selector = $('#theme-selector');
        const themeInput = $('#cfg-theme');
        const options = selector.querySelectorAll('.theme-option');

        // 更新输入框
        themeInput.value = theme;

        // 更新选中状态
        options.forEach(option => {
            option.classList.toggle('theme-option--active',
                option.dataset.theme === theme);
        });
    },


    async open() {
        this.panel.classList.add('settings-panel--visible');
        this.overlay.classList.add('settings-overlay--visible');
        await this.loadConfig();
    },

    close() {
        this.panel.classList.remove('settings-panel--visible');
        this.overlay.classList.remove('settings-overlay--visible');
    },

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const result = await response.json();
            if (result.success) {
                this.currentConfig = result.config;
                this.populateForm(this.currentConfig);
            } else {
                this.showToast(result.error || '加载配置失败', 'error');
            }
        } catch (e) {
            this.showToast('加载配置失败: ' + e.message, 'error');
        }
    },

    populateForm(config) {
        // 身份配置
        const identity = config.identity || {};
        $('#cfg-name').value = identity.name || '';
        $('#cfg-username').value = identity.username || '';
        $('#cfg-honey').value = identity.honey || '';

        // API 配置
        const api = config.api || {};
        $('#cfg-api-key').value = api.key || '';
        $('#cfg-api-url').value = api.url || '';
        this.selectModel(api.model || '');

        // 终端配置
        const terminal = config.terminal || {};
        $('#cfg-shell').value = terminal.shell || 'powershell';
        $('#cfg-encoding').value = terminal.encoding || 'utf-8';
        $('#cfg-buffer-size').value = terminal.buffer_size || 24;

        // Web 配置
        const web = config.web || {};
        $('#cfg-search-engine').value = web.search_engine || 'duckduckgo';
        $('#cfg-max-results').value = web.max_results || 5;
        $('#cfg-use-jina').checked = web.use_jina_reader !== false;

        // 系统配置
        const system = config.system || {};
        $('#cfg-chunk-size').value = system.chunk_size || 64000;

        // 记忆系统配置
        const memory = config.memory || {};
        const memoryEnabled = memory.enabled || false;
        $('#cfg-memory-enabled').checked = memoryEnabled;
        $('#memory-config-fields').style.display = memoryEnabled ? 'block' : 'none';
        
        // 设置 Embedding URL
        const embeddingUrl = memory.embedding_url || 'http://localhost:11434/api/embeddings';
        $('#cfg-embedding-url').value = embeddingUrl;
        // 检测预设选项
        if (embeddingUrl === 'http://localhost:11434/api/embeddings') {
            $('#cfg-embedding-url-preset').value = 'ollama';
        } else if (embeddingUrl === 'http://localhost:1234/v1/embeddings') {
            $('#cfg-embedding-url-preset').value = 'lm_studio';
        } else {
            $('#cfg-embedding-url-preset').value = 'custom';
        }
        
        $('#cfg-embedding-key').value = memory.embedding_key || '';
        // 更新 Embedding 下拉
        this.selectOption(memory.embedding_model || 'nomic-embed-text', {
            hiddenInputId: 'cfg-embedding-model',
            valueDisplayId: 'embed-model-select-value',
            dropdownId: 'embed-model-select-dropdown'
        });

        // 回忆阈值配置
        const recall = config.recall || {};
        $('#cfg-recall-threshold').value = recall.threshold || 0.35;

        // 颜色主题配置 - 根据颜色值匹配主题预设
        const theme = config.theme || {};
        const themeId = theme.id || null;
        const themeTitlebar = theme.titlebar || '#000000';
        const themeLoading = theme.loading || '#000000';
        const themeMain = theme.main || '#000000';

        // 根据 ID 或 颜色值匹配主题预设
        let matchedTheme = 'yaoye'; // 默认
        
        if (themeId && THEME_PRESETS[themeId]) {
            matchedTheme = themeId;
        } else {
            for (const [id, preset] of Object.entries(THEME_PRESETS)) {
                if (preset.titlebar === themeTitlebar &&
                    preset.loading === themeLoading &&
                    preset.main === themeMain) {
                    matchedTheme = id;
                    // 如果找到了颜色匹配的，但因为 Hacker 和 Yaoye 颜色一样，优先检查 accent
                    if (theme.accent && preset.accent !== theme.accent) {
                        continue;
                    }
                    break;
                }
            }
        }
        this.selectTheme(matchedTheme);
    },

    async save() {
        const config = {
            identity: {
                name: $('#cfg-name').value || 'Paw',
                username: $('#cfg-username').value || 'hujiyo',
                honey: $('#cfg-honey').value || '老公'
            },
            api: {
                key: $('#cfg-api-key').value,
                url: $('#cfg-api-url').value,
                model: $('#cfg-model').value || null
            },
            terminal: {
                shell: $('#cfg-shell').value,
                encoding: $('#cfg-encoding').value || 'utf-8',
                buffer_size: Math.max(4, Math.min(64, parseInt($('#cfg-buffer-size').value) || 24))
            },
            web: {
                search_engine: $('#cfg-search-engine').value,
                max_results: parseInt($('#cfg-max-results').value) || 5,
                page_size: 4096,
                use_jina_reader: $('#cfg-use-jina').checked
            },
            system: {
                chunk_size: parseInt($('#cfg-chunk-size').value) || 64000
            },
            memory: {
                enabled: $('#cfg-memory-enabled').checked,
                embedding_url: $('#cfg-embedding-url').value || 'http://localhost:11434/api/embeddings',
                embedding_key: $('#cfg-embedding-key').value || '',
                embedding_model: $('#cfg-embedding-model').value || 'nomic-embed-text'
            },
            recall: {
                enabled: true,
                threshold: parseFloat($('#cfg-recall-threshold').value) || 0.35
            },
            theme: (() => {
                const themeId = $('#cfg-theme').value || 'yaoye';
                const preset = THEME_PRESETS[themeId] || THEME_PRESETS.yaoye;
                return {
                    id: themeId,
                    titlebar: preset.titlebar,
                    loading: preset.loading,
                    main: preset.main,
                    accent: preset.accent
                };
            })()
        };

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ config })
            });
            const result = await response.json();
            if (result.success) {
                this.showToast('配置已保存，请重启应用生效', 'success');
                this.currentConfig = config;
            } else {
                this.showToast(result.error || '保存失败', 'error');
            }
        } catch (e) {
            this.showToast('保存失败: ' + e.message, 'error');
        }
    },

    reset() {
        this.populateForm(this.currentConfig);
        this.showToast('已重置为当前配置', 'success');
    },

    showToast(message, type = 'success') {
        this.toast.textContent = message;
        this.toast.className = 'settings__toast settings__toast--visible';
        if (type === 'error') {
            this.toast.classList.add('settings__toast--error');
        } else {
            this.toast.classList.add('settings__toast--success');
        }
        setTimeout(() => {
            this.toast.classList.remove('settings__toast--visible');
        }, 3000);
    }
};

// 初始化配置管理
Settings.init();

// ========== 主题颜色应用 ==========
async function applyThemeColors() {
    try {
        const response = await fetch('/api/config');
        const result = await response.json();
        if (result.success && result.config.theme) {
            const mainColor = result.config.theme.main || '#000000';
            const accentColor = result.config.theme.accent || null;
            // 使用ThemeColors类初始化并应用主题
            ThemeColors.init(mainColor, accentColor);
        }
    } catch (e) {
        console.warn('Failed to apply theme colors:', e);
    }
}

// 页面加载时应用主题颜色
applyThemeColors();

// ========== 错误弹窗 ==========
function showErrorDialog(message) {
    dom.modalTitle.textContent = '错误';
    dom.modalBody.innerHTML = `<div style="color:var(--error-color);padding:1rem;text-align:center">${escapeHtml(message)}</div>`;
    dom.modalActions.style.display = 'none';
    dom.modal.classList.add('visible');
}

// ========== 提示弹窗 ==========
function showInfoDialog(message) {
    dom.modalTitle.textContent = '提示';
    dom.modalBody.innerHTML = `<div style="color:var(--text-primary);padding:1rem;text-align:center">${escapeHtml(message)}</div>`;
    dom.modalActions.style.display = 'none';
    dom.modal.classList.add('visible');
    // 2秒后自动关闭
    setTimeout(() => dom.modal.classList.remove('visible'), 2000);
}

// ========== 启动 ==========
autoResize();
