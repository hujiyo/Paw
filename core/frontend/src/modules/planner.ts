
import { $ } from './utils.js';
import { escapeHtml } from './utils.js';

interface PlanItem {
    id: string;
    text: string;
    done: boolean;
}

export class Planner {
    private static container: HTMLElement;
    private static items: PlanItem[] = [];

    static init() {
        this.container = $('#plan-list')!;
        this.render();
    }

    static setItems(items: PlanItem[]) {
        this.items = items;
        this.render();
    }
    
    static addItem(text: string) {
        this.items.push({
            id: Date.now().toString(),
            text,
            done: false
        });
        this.render();
    }

    static toggleItem(id: string) {
        const item = this.items.find(i => i.id === id);
        if (item) {
            item.done = !item.done;
            this.render();
        }
    }

    static render() {
        if (this.items.length === 0) {
            this.container.innerHTML = '<div class="plan-empty">No active plan</div>';
            return;
        }

        let html = '';
        this.items.forEach(item => {
            const statusClass = item.done ? 'plan-item--done' : '';
            html += `
                <div class="plan-item ${statusClass}" data-id="${item.id}">
                    <div class="plan-item__checkbox"></div>
                    <div class="plan-item__content">
                        <div class="plan-item__text">${escapeHtml(item.text)}</div>
                        <div class="plan-item__status">${item.done ? 'Completed' : 'Pending'}</div>
                    </div>
                </div>
            `;
        });
        
        this.container.innerHTML = html;
        
        // Bind events
        this.container.querySelectorAll('.plan-item').forEach(el => {
            el.addEventListener('click', () => {
                const id = (el as HTMLElement).dataset.id;
                if (id) this.toggleItem(id);
            });
        });
    }
}
