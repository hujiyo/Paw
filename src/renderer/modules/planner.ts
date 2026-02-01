
import { $ } from './utils.js';
import { escapeHtml } from './utils.js';

interface PlanItem {
    id: string;
    text: string;
    details?: string;
    done: boolean;
}

export class Planner {
    private static container: HTMLElement;
    private static items: PlanItem[] = [];

    static getItemCount(): number {
        return this.items.length;
    }

    static init() {
        this.container = $('#plan-list')!;
        this.render();
    }

    static setItems(items: PlanItem[]) {
        this.items = items;
        this.render();
    }
    
    /**
     * 从对话历史中重新提取计划状态
     * 逻辑：正向遍历所有相关工具调用，重放操作以构建最终状态
     */
    static refresh() {
        // 从消息容器中提取所有相关工具
        const messagesEl = document.getElementById('messages');
        if (!messagesEl) return;

        // 重置状态
        this.items = [];
        
        // 收集所有工具元素
        const toolEls = messagesEl.querySelectorAll('.tool');
        
        toolEls.forEach(el => {
            const toolEl = el as HTMLElement;
            const name = toolEl.querySelector('.tool__name')?.textContent || '';
            const rawRequest = toolEl.dataset.rawRequest;
            const rawResponse = toolEl.dataset.rawResponse; // 优先使用响应数据
            
            if (!['create_todo_list', 'add_todos', 'mark_todo_as_done'].includes(name)) {
                return;
            }

            try {
                // 1. 尝试从响应中获取全量状态 (create/add/read 都会返回全量 todos)
                if (rawResponse) {
                    const resp = JSON.parse(rawResponse);
                    if (resp.success && resp.todos && Array.isArray(resp.todos)) {
                        // 如果有全量数据，直接覆盖（针对 create/add）
                        // 注意：add_todos 返回的全量数据包含了之前的，所以可以直接覆盖
                        // 但为了保险（防止后端逻辑变动），我们还是根据工具类型处理
                        
                        if (name === 'create_todo_list' || name === 'add_todos') {
                            this.items = resp.todos.map((t: any, i: number) => ({
                                id: String(t.id || i),
                                text: t.title,
                                details: t.details,
                                done: t.status === 'completed'
                            }));
                            return; // 处理完这个工具，继续下一个
                        }
                    }
                    
                    // mark_todo_as_done 的响应只包含更新项
                    if (name === 'mark_todo_as_done' && resp.updated) {
                        resp.updated.forEach((u: any) => {
                            const item = this.items.find(i => i.id === String(u.id));
                            if (item) item.done = true;
                        });
                        return;
                    }
                }

                // 2. 如果没有响应（正在生成）或响应不包含全量数据，回退到请求参数
                if (rawRequest) {
                    const req = JSON.parse(rawRequest);
                    
                    if (name === 'create_todo_list' && req.todos) {
                        this.items = req.todos.map((t: any, i: number) => ({
                            id: String(i), // 初始 ID，可能不准，但在单次生成中够用
                            text: t.title,
                            details: t.details,
                            done: false
                        }));
                    } else if (name === 'add_todos' && req.todos) {
                        const startId = this.items.length;
                        req.todos.forEach((t: any, i: number) => {
                            this.items.push({
                                id: String(startId + i),
                                text: t.title,
                                details: t.details,
                                done: false
                            });
                        });
                    } else if (name === 'mark_todo_as_done' && req.todo_ids) {
                        req.todo_ids.forEach((id: string) => {
                            const item = this.items.find(i => i.id === id);
                            if (item) item.done = true;
                        });
                    }
                }
            } catch (e) {
                console.warn('[Planner] Failed to parse tool data', e);
            }
        });

        this.render();
    }
    
    static render() {
        if (this.items.length === 0) {
            this.container.innerHTML = '<div class="plan-empty">No active plan</div>';
            return;
        }

        let html = '';
        this.items.forEach(item => {
            const statusClass = item.done ? 'plan-item--done' : '';
            const detailsHtml = item.details ? `<div class="plan-item__details">${escapeHtml(item.details)}</div>` : '';
            html += `
                <div class="plan-item ${statusClass}" data-id="${item.id}">
                    <div class="plan-item__checkbox"></div>
                    <div class="plan-item__content">
                        <div class="plan-item__text">${escapeHtml(item.text)}</div>
                        ${detailsHtml}
                        <div class="plan-item__status">${item.done ? 'Completed' : 'Pending'}</div>
                    </div>
                </div>
            `;
        });
        
        this.container.innerHTML = html;
        
        // Planner is read-only for now, state is managed by conversation history
    }
}
