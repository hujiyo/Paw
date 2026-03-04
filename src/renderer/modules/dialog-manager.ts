// 弹窗管理模块

import { escapeHtml } from './utils.js';

export class DialogManager {
    private modal: HTMLElement;
    private title: HTMLElement;
    private body: HTMLElement;
    private actions: HTMLElement;
    private okBtn: HTMLButtonElement;

    private confirmModal: HTMLElement;
    private confirmTitle: HTMLElement;
    private confirmBody: HTMLElement;
    private confirmCancel: HTMLButtonElement;
    private confirmOk: HTMLButtonElement;
    private confirmCallback: (() => void) | null = null;

    constructor() {
        this.modal = document.getElementById('modal')!;
        this.title = document.getElementById('modal-title')!;
        this.body = document.getElementById('modal-body')!;
        this.actions = document.getElementById('modal-actions')!;
        this.okBtn = document.getElementById('modal-ok') as HTMLButtonElement;

        this.confirmModal = document.getElementById('confirm-modal')!;
        this.confirmTitle = document.getElementById('confirm-title')!;
        this.confirmBody = document.getElementById('confirm-body')!;
        this.confirmCancel = document.getElementById('confirm-cancel') as HTMLButtonElement;
        this.confirmOk = document.getElementById('confirm-ok') as HTMLButtonElement;

        this.setupEventListeners();
    }

    private setupEventListeners(): void {
        this.okBtn.addEventListener('click', () => {
            const input = this.body.querySelector('input') as HTMLInputElement;
            if (input) {
                const value = input.value.trim();
                if (value) {
                    this.emit('input', value);
                    this.hideModal();
                }
            }
        });

        this.modal.addEventListener('click', (e) => {
            if (e.target === this.modal) {
                this.hideModal();
            }
        });

        this.confirmCancel.addEventListener('click', () => {
            this.hideConfirm();
        });

        this.confirmOk.addEventListener('click', () => {
            if (this.confirmCallback) {
                this.confirmCallback();
            }
            this.hideConfirm();
        });

        this.confirmModal.addEventListener('click', (e) => {
            if (e.target === this.confirmModal) {
                this.hideConfirm();
            }
        });
    }

    private eventListeners: Map<string, Set<(data: unknown) => void>> = new Map();

    on(event: string, listener: (data: unknown) => void): void {
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, new Set());
        }
        this.eventListeners.get(event)!.add(listener);
    }

    private emit(event: string, data?: unknown): void {
        const listeners = this.eventListeners.get(event);
        if (listeners) {
            listeners.forEach(listener => listener(data));
        }
    }

    showError(message: string): void {
        this.showModal('错误', `<div style="color:var(--error-color);padding:1rem;text-align:center">${escapeHtml(message)}</div>`);
    }

    showInfo(message: string, autoClose: boolean = true): void {
        this.showModal('提示', `<div style="color:var(--text-primary);padding:1rem;text-align:center">${escapeHtml(message)}</div>`);
        if (autoClose) {
            setTimeout(() => this.hideModal(), 2000);
        }
    }

    showConfirm(title: string, messageHtml: string, onConfirm: () => void): void {
        this.confirmTitle.textContent = title;
        this.confirmBody.innerHTML = messageHtml;
        this.confirmCallback = onConfirm;
        this.confirmModal.classList.add('visible');
    }

    showModelSelect(models: string[], onSelect: (model: string) => void): void {
        const content = models.map(m => `<div class="modal__item" data-model="${m}">${m}</div>`).join('');
        this.showModal('选择模型', content);
        this.actions.style.display = 'none';

        const items = this.body.querySelectorAll('.modal__item');
        items.forEach(item => {
            item.addEventListener('click', () => {
                onSelect((item as HTMLElement).dataset.model || '');
                this.hideModal();
            });
        });
    }

    showInputPrompt(prompt: string): void {
        this.showModal(prompt, '<input type="text" class="modal__input" placeholder="输入...">');
        this.actions.style.display = 'flex';
        setTimeout(() => {
            const input = this.body.querySelector('input') as HTMLInputElement;
            if (input) input.focus();
        }, 30);
    }

    private showModal(title: string, content: string): void {
        this.title.textContent = title;
        this.body.innerHTML = content;
        this.modal.classList.add('visible');
    }

    private hideModal(): void {
        this.modal.classList.remove('visible');
        this.actions.style.display = 'none';
    }

    private hideConfirm(): void {
        this.confirmModal.classList.remove('visible');
        this.confirmCallback = null;
    }
}
