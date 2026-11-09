// 消息编辑器 - 全屏页面，左侧轮次列表 + 右侧编辑区

// ============ 类型定义 ============

interface ChunkData {
    chunk_index: number;
    type: string;
    content: string;
    tokens: number;
    metadata: Record<string, unknown>;
    tool_call_parsed?: {
        id: string;
        name: string;
        arguments: string;
    };
}

interface TurnData {
    turn_index: number;
    role: 'user' | 'assistant';
    start_idx: number;
    end_idx: number;
    chunks: ChunkData[];
}

interface EditorCallbacks {
    onSaved?: () => void;
}

// ============ API 请求方法 ============

async function fetchTurnsDetailed(): Promise<TurnData[]> {
    const resp = await fetch('/api/turns/detailed');
    const data = await resp.json();
    if (data.success) return data.turns;
    throw new Error(data.error || 'Failed to fetch turns');
}

async function apiEditChunk(chunkIndex: number, content: string): Promise<boolean> {
    const resp = await fetch('/api/turn/edit-chunk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ chunk_index: chunkIndex, content })
    });
    const data = await resp.json();
    return data.success;
}

async function apiDeleteTurn(turnIndex: number): Promise<boolean> {
    const resp = await fetch('/api/turn/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ turn_index: turnIndex })
    });
    const data = await resp.json();
    return data.success;
}

async function apiInsertTurn(position: number, role: string, content: string): Promise<boolean> {
    const resp = await fetch('/api/turn/insert', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ position, role, content })
    });
    const data = await resp.json();
    return data.success;
}

async function apiAddToolCall(turnIndex: number, toolName: string, args: string, result: string): Promise<string | null> {
    const resp = await fetch('/api/turn/add-tool-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ turn_index: turnIndex, tool_name: toolName, arguments: args, result })
    });
    const data = await resp.json();
    return data.success ? data.tool_call_id : null;
}

async function apiRemoveToolCall(turnIndex: number, toolCallId: string): Promise<boolean> {
    const resp = await fetch('/api/turn/remove-tool-call', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ turn_index: turnIndex, tool_call_id: toolCallId })
    });
    const data = await resp.json();
    return data.success;
}

// ============ 消息编辑器核心 ============

export const MessageEditor = {
    _page: null as HTMLElement | null,
    _turnList: null as HTMLElement | null,
    _editorContent: null as HTMLElement | null,
    _editorEmpty: null as HTMLElement | null,
    _turnCount: null as HTMLElement | null,
    _turns: [] as TurnData[],
    _selectedTurnIndex: null as number | null,
    _callbacks: {} as EditorCallbacks,
    _dirty: false,
    _refreshing: false,
    _currentToolDialogCleanup: null as (() => void) | null,

    init(callbacks?: EditorCallbacks): void {
        this._page = document.getElementById('message-editor-page');
        this._turnList = document.getElementById('me-turn-list');
        this._editorContent = document.getElementById('me-editor-content');
        this._editorEmpty = document.getElementById('me-editor-empty');
        this._turnCount = document.getElementById('me-turn-count');
        this._callbacks = callbacks || {};

        // 返回按钮
        const backBtn = document.getElementById('me-back-btn');
        backBtn?.addEventListener('click', () => this.close());

        // 添加轮次按钮
        const addUserBtn = document.getElementById('me-add-user-btn');
        const addAssistantBtn = document.getElementById('me-add-assistant-btn');
        addUserBtn?.addEventListener('click', () => this._addNewTurn('user'));
        addAssistantBtn?.addEventListener('click', () => this._addNewTurn('assistant'));
    },

    async open(): Promise<void> {
        if (!this._page) return;
        this._dirty = false;
        this._selectedTurnIndex = null;

        try {
            this._turns = await fetchTurnsDetailed();
            this._renderTurnList();
            this._showEmptyState();
            this._page.classList.add('me-page--visible');
        } catch (e) {
            console.error('[MessageEditor] Failed to open:', e);
        }
    },

    close(): void {
        if (!this._page) return;
        this._page.classList.remove('me-page--visible');
        this._selectedTurnIndex = null;
        
        if (this._currentToolDialogCleanup) {
            this._currentToolDialogCleanup();
            this._currentToolDialogCleanup = null;
        }
        
        if (this._dirty && this._callbacks.onSaved) {
            this._callbacks.onSaved();
        }
    },

    _renderTurnList(): void {
        if (!this._turnList || !this._turnCount) return;
        const turnList = this._turnList;
        turnList.innerHTML = '';
        this._turnCount.textContent = String(this._turns.length);

        if (this._turns.length === 0) {
            turnList.innerHTML = '<div class="me-empty">暂无对话轮次</div>';
            return;
        }

        this._turns.forEach((turn, index) => {
            const item = this._createTurnListItem(turn, index);
            turnList.appendChild(item);
        });
    },

    _createTurnListItem(turn: TurnData, index: number): HTMLElement {
        const item = document.createElement('div');
        item.className = 'me-turn-item';
        if (this._selectedTurnIndex === index) {
            item.classList.add('me-turn-item--active');
        }

        const header = document.createElement('div');
        header.className = 'me-turn-item__header';

        const roleLabel = document.createElement('span');
        roleLabel.className = `me-turn-item__role me-turn-item__role--${turn.role}`;
        roleLabel.textContent = turn.role === 'user' ? 'USER' : 'PAW';

        const tokenInfo = document.createElement('span');
        tokenInfo.className = 'me-turn-item__tokens';
        const totalTokens = turn.chunks.reduce((sum, c) => sum + c.tokens, 0);
        tokenInfo.textContent = `${totalTokens}t`;

        header.appendChild(roleLabel);
        header.appendChild(tokenInfo);

        const preview = document.createElement('div');
        preview.className = 'me-turn-item__preview';
        const firstChunk = turn.chunks.find(c => c.type === 'user' || c.type === 'assistant');
        preview.textContent = firstChunk?.content?.slice(0, 50) || '(空消息)';

        item.appendChild(header);
        item.appendChild(preview);

        item.addEventListener('click', () => {
            this._selectTurn(index);
        });

        return item;
    },

    _selectTurn(index: number): void {
        if (index < 0 || index >= this._turns.length) return;
        this._selectedTurnIndex = index;
        this._renderTurnList();
        this._renderEditor(this._turns[index]);
    },

    _showEmptyState(): void {
        if (!this._editorEmpty || !this._editorContent) return;
        this._editorEmpty.style.display = 'flex';
        this._editorContent.classList.remove('me-editor__content--visible');
    },

    _renderEditor(turn: TurnData): void {
        if (!this._editorContent || !this._editorEmpty) return;

        this._editorEmpty.style.display = 'none';
        this._editorContent.classList.add('me-editor__content--visible');
        this._editorContent.innerHTML = '';

        const header = document.createElement('div');
        header.className = 'me-editor__header';

        const headerLeft = document.createElement('div');
        headerLeft.className = 'me-editor__header-left';

        const roleBadge = document.createElement('div');
        roleBadge.className = `me-editor__role-badge me-editor__role-badge--${turn.role}`;
        roleBadge.textContent = turn.role === 'user' ? 'USER' : 'PAW';

        const turnInfo = document.createElement('div');
        turnInfo.className = 'me-editor__turn-info';
        const totalTokens = turn.chunks.reduce((sum, c) => sum + c.tokens, 0);
        turnInfo.textContent = `轮次 #${turn.turn_index + 1} · ${turn.chunks.length} 块 · ${totalTokens} tokens`;

        headerLeft.appendChild(roleBadge);
        headerLeft.appendChild(turnInfo);

        const headerActions = document.createElement('div');
        headerActions.className = 'me-editor__header-actions';

        if (turn.role === 'assistant') {
            const addToolBtn = document.createElement('button');
            addToolBtn.className = 'me-btn me-btn--tool';
            addToolBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg> 添加工具调用';
            addToolBtn.addEventListener('click', () => this._showAddToolDialog(turn.turn_index));
            headerActions.appendChild(addToolBtn);
        }

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'me-btn me-btn--danger';
        deleteBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg> 删除轮次';
        deleteBtn.addEventListener('click', () => this._deleteTurn(turn.turn_index));
        headerActions.appendChild(deleteBtn);

        header.appendChild(headerLeft);
        header.appendChild(headerActions);

        const chunksContainer = document.createElement('div');
        chunksContainer.className = 'me-editor__chunks';

        turn.chunks.forEach((chunk) => {
            const chunkEl = this._createEditorChunk(chunk, turn);
            chunksContainer.appendChild(chunkEl);
        });

        this._editorContent.appendChild(header);
        this._editorContent.appendChild(chunksContainer);
    },

    _createEditorChunk(chunk: ChunkData, turn: TurnData): HTMLElement {
        const el = document.createElement('div');
        el.className = `me-editor-chunk me-editor-chunk--${chunk.type}`;

        const header = document.createElement('div');
        header.className = 'me-editor-chunk__header';

        const typeLabel = document.createElement('div');
        typeLabel.className = 'me-editor-chunk__type';

        if (chunk.type === 'user') {
            typeLabel.textContent = '用户消息';
        } else if (chunk.type === 'assistant') {
            typeLabel.textContent = '助手回复';
        } else if (chunk.type === 'tool_call') {
            const parsed = chunk.tool_call_parsed;
            typeLabel.textContent = `工具调用: ${parsed?.name || '未知'}`;
        } else if (chunk.type === 'tool_result') {
            const toolName = (chunk.metadata?.name as string) || '工具';
            typeLabel.textContent = `工具结果: ${toolName}`;
        } else {
            typeLabel.textContent = chunk.type;
        }

        header.appendChild(typeLabel);

        const actions = document.createElement('div');
        actions.className = 'me-editor-chunk__actions';

        if (chunk.type === 'user' || chunk.type === 'assistant') {
            const textarea = document.createElement('textarea');
            textarea.className = 'me-chunk__textarea';
            textarea.value = chunk.content || '';
            textarea.rows = Math.max(3, Math.min(20, (chunk.content || '').split('\n').length));

            const footer = document.createElement('div');
            footer.className = 'me-chunk__footer';

            const tokenSpan = document.createElement('span');
            tokenSpan.className = 'me-chunk__token-count';
            tokenSpan.textContent = `~${chunk.tokens} tokens`;

            const saveBtn = document.createElement('button');
            saveBtn.className = 'me-btn me-btn--save';
            saveBtn.textContent = '保存';
            saveBtn.addEventListener('click', async () => {
                if (this._refreshing) return;
                const newContent = textarea.value;
                const ok = await apiEditChunk(chunk.chunk_index, newContent);
                if (ok) {
                    this._dirty = true;
                    saveBtn.textContent = '已保存';
                    saveBtn.classList.add('me-btn--saved');
                    setTimeout(() => {
                        saveBtn.textContent = '保存';
                        saveBtn.classList.remove('me-btn--saved');
                    }, 1500);
                } else {
                    saveBtn.textContent = '失败';
                    setTimeout(() => { saveBtn.textContent = '保存'; }, 1500);
                }
            });

            footer.appendChild(tokenSpan);
            footer.appendChild(saveBtn);

            el.appendChild(header);
            el.appendChild(textarea);
            el.appendChild(footer);

        } else if (chunk.type === 'tool_call') {
            const parsed = chunk.tool_call_parsed;
            const toolId = parsed?.id || '';

            const removeBtn = document.createElement('button');
            removeBtn.className = 'me-btn me-btn--danger me-btn--sm';
            removeBtn.textContent = '移除';
            removeBtn.addEventListener('click', async () => {
                if (toolId && !this._refreshing) {
                    this._refreshing = true;
                    const ok = await apiRemoveToolCall(turn.turn_index, toolId);
                    if (ok) {
                        this._dirty = true;
                        await this._refresh();
                    }
                    this._refreshing = false;
                }
            });
            actions.appendChild(removeBtn);
            header.appendChild(actions);

            let argsText = parsed?.arguments || '{}';
            try {
                const argsObj = typeof argsText === 'string' ? JSON.parse(argsText) : argsText;
                argsText = JSON.stringify(argsObj, null, 2);
            } catch { /* keep original */ }

            const argsTextarea = document.createElement('textarea');
            argsTextarea.className = 'me-chunk__textarea me-chunk__textarea--args';
            argsTextarea.value = argsText;
            argsTextarea.rows = Math.max(2, Math.min(10, argsText.split('\n').length));
            argsTextarea.readOnly = true;

            el.appendChild(header);
            el.appendChild(argsTextarea);

        } else if (chunk.type === 'tool_result') {
            const contentPre = document.createElement('pre');
            contentPre.className = 'me-chunk__tool-result';
            const contentText = chunk.content || '';
            contentPre.textContent = contentText.length > 500 ? contentText.slice(0, 500) + '...' : contentText;

            el.appendChild(header);
            el.appendChild(contentPre);

        } else {
            const content = document.createElement('pre');
            content.className = 'me-chunk__content-pre';
            content.textContent = chunk.content || '';

            el.appendChild(header);
            el.appendChild(content);
        }

        return el;
    },

    async _deleteTurn(turnIndex: number): Promise<void> {
        if (!confirm('确定删除此轮次？此操作不可撤销。')) return;
        if (this._refreshing) return;

        this._refreshing = true;
        const ok = await apiDeleteTurn(turnIndex);
        if (ok) {
            this._dirty = true;
            this._selectedTurnIndex = null;
            await this._refresh();
        }
        this._refreshing = false;
    },

    async _addNewTurn(role: 'user' | 'assistant'): Promise<void> {
        if (this._refreshing) return;

        this._refreshing = true;
        const position = this._turns.length;
        const ok = await apiInsertTurn(position, role, '');
        if (ok) {
            this._dirty = true;
            await this._refresh();
            this._selectTurn(this._turns.length - 1);
        }
        this._refreshing = false;
    },

    _showAddToolDialog(turnIndex: number): void {
        const dialog = document.getElementById('me-tool-dialog');
        const nameInput = document.getElementById('me-tool-name') as HTMLInputElement;
        const argsInput = document.getElementById('me-tool-args') as HTMLTextAreaElement;
        const resultInput = document.getElementById('me-tool-result') as HTMLTextAreaElement;
        const confirmBtn = document.getElementById('me-tool-confirm');
        const cancelBtn = document.getElementById('me-tool-cancel');

        if (!dialog || !nameInput || !argsInput || !resultInput || !confirmBtn || !cancelBtn) return;

        if (this._currentToolDialogCleanup) {
            this._currentToolDialogCleanup();
        }

        nameInput.value = '';
        argsInput.value = '{}';
        resultInput.value = '';
        dialog.classList.add('me-tool-dialog--visible');

        const onConfirm = async (): Promise<void> => {
            const toolName = nameInput.value.trim();
            if (!toolName) {
                nameInput.focus();
                return;
            }

            // 参数必须是合法 JSON 对象，否则后续发给 API 的 tool_calls 会被拒收
            const argsText = argsInput.value.trim() || '{}';
            try {
                const parsed = JSON.parse(argsText);
                if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
                    throw new Error('not an object');
                }
            } catch {
                argsInput.value = argsText;
                argsInput.focus();
                argsInput.style.borderColor = 'var(--error-color)';
                setTimeout(() => { argsInput.style.borderColor = ''; }, 1500);
                return;
            }

            this._refreshing = true;
            const tcId = await apiAddToolCall(turnIndex, toolName, argsText, resultInput.value);
            if (tcId) {
                this._dirty = true;
                await this._refresh();
            }
            this._refreshing = false;
            dialog.classList.remove('me-tool-dialog--visible');
            cleanup();
        };

        const onCancel = (): void => {
            dialog.classList.remove('me-tool-dialog--visible');
            cleanup();
        };

        const cleanup = (): void => {
            confirmBtn.removeEventListener('click', onConfirm);
            cancelBtn.removeEventListener('click', onCancel);
            this._currentToolDialogCleanup = null;
        };

        confirmBtn.addEventListener('click', onConfirm);
        cancelBtn.addEventListener('click', onCancel);
        this._currentToolDialogCleanup = cleanup;
    },

    async _refresh(): Promise<void> {
        try {
            const currentIndex = this._selectedTurnIndex;
            this._turns = await fetchTurnsDetailed();
            this._renderTurnList();
            
            if (currentIndex !== null && currentIndex < this._turns.length) {
                this._selectTurn(currentIndex);
            } else {
                this._showEmptyState();
            }
        } catch (e) {
            console.error('[MessageEditor] Refresh failed:', e);
        }
    }
};
