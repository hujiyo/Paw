// 记忆管理
import { escapeHtml } from './utils.js';
import { addSysMsg, renderModalContent } from './render.js';

export const Memory = {
    dom: null,
    send: null,
    conversations: [],
    selectedIndex: 0,
    active: false,

    init(dom, sendFn) {
        this.dom = dom;
        this.send = sendFn;

        // 记忆管理快捷键
        // 注意：这里我们绑定在 dom.input 上，这假设 dom.input 已经被正确传入
        if (this.dom.input) {
            this.dom.input.addEventListener('keydown', e => {
                if (!this.active) return;
                if (e.target.tagName === 'TEXTAREA') return;

                if (e.key === 'ArrowUp' || e.key === 'k') {
                    e.preventDefault();
                    this.select(Math.max(0, this.selectedIndex - 1));
                } else if (e.key === 'ArrowDown' || e.key === 'j') {
                    e.preventDefault();
                    this.select(Math.min(this.conversations.length - 1, this.selectedIndex + 1));
                } else if (e.key === 'q' || e.key === 'Q' || e.key === 'Escape') {
                    e.preventDefault();
                    this.hide();
                }
            });
        }

        // 记忆按钮事件
        if (this.dom.memorySearchBtn) {
            this.dom.memorySearchBtn.addEventListener('click', () => {
                const keyword = prompt('输入搜索关键词:');
                if (keyword) this.search(keyword);
            });
        }

        if (this.dom.memoryCleanBtn) {
            this.dom.memoryCleanBtn.addEventListener('click', () => {
                this.clean();
            });
        }
    },

    show(conversations) {
        this.conversations = conversations || [];
        this.selectedIndex = 0;
        this.active = true;
        this.render();
        // 自动切换到记忆视图
        document.querySelectorAll('.sidebar__tab').forEach(t => {
            t.classList.toggle('sidebar__tab--active', t.dataset.view === 'memory');
        });
        document.querySelectorAll('.sidebar__view').forEach(v => v.classList.remove('sidebar__view--active'));
        this.dom.viewMemory.classList.add('sidebar__view--active');
    },

    hide() {
        this.active = false;
        this.dom.memoryCanvas.innerHTML = '<div class="memory-empty">/memory 打开记忆管理</div>';
    },

    render() {
        const count = this.conversations.length;
        this.dom.memoryStats.textContent = `共 ${count} 条记忆`;

        if (!count) {
            this.dom.memoryCanvas.innerHTML = '<div class="memory-empty">暂无记忆</div>';
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

        this.dom.memoryCanvas.innerHTML = html;

        // 绑定点击事件
        this.dom.memoryCanvas.querySelectorAll('.memory-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (e.target.classList.contains('memory-item__delete')) return;
                const idx = parseInt(e.currentTarget.dataset.index);
                this.select(idx);
            });
        });

        // 绑定删除事件
        this.dom.memoryCanvas.querySelectorAll('.memory-item__delete').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const id = e.target.dataset.delete;
                if (confirm('确定删除这条记忆吗？')) {
                    if (this.send) this.send(`MEMORY_DELETE:${id}`);
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
        const content = `
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
        renderModalContent('记忆详情', content, false);
    },

    search(keyword) {
        if (this.send) this.send(`MEMORY_SEARCH:${keyword}`);
    },

    clean() {
        if (confirm('确定清理重复的记忆吗？')) {
            if (this.send) this.send('MEMORY_CLEAN');
        }
    },

    handleResult(data) {
        if (data.success) {
            addSysMsg(this.dom.messages, data.message || '操作成功');
            if (data.conversations) {
                this.conversations = data.conversations;
                this.render();
            }
            // 不隐藏记忆管理，继续编辑模式
        } else {
            addSysMsg(this.dom.messages, data.error || '操作失败', 'error');
        }
    }
};
