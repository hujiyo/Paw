// 模式选择器模块

import { WebSocketManager } from './websocket.js';

interface ModeInfo {
    name: string;
    label: string;
    desc: string;
}

export class ModeSelector {
    private wsManager: WebSocketManager;
    private modeTrigger: HTMLButtonElement | null;
    private modeDropdown: HTMLElement | null;
    private modeLabelEl: HTMLElement | null;
    private modeLabels: Record<string, string> = {};

    constructor(wsManager: WebSocketManager) {
        this.wsManager = wsManager;
        this.modeTrigger = document.getElementById('mode-trigger') as HTMLButtonElement | null;
        this.modeDropdown = document.getElementById('mode-dropdown') as HTMLElement | null;
        this.modeLabelEl = document.getElementById('mode-label') as HTMLElement | null;
    }

    async init(): Promise<void> {
        if (!this.modeDropdown) return;

        try {
            const res = await fetch('/api/modes');
            const data = await res.json() as { modes: ModeInfo[] };
            const dropdown = this.modeDropdown;
            dropdown.innerHTML = '';
            data.modes.forEach((m, i) => {
                this.modeLabels[m.name] = m.label;
                const el = document.createElement('div');
                el.className = 'mode-selector__option' + (i === 0 ? ' mode-selector__option--active' : '');
                el.dataset.mode = m.name;
                el.innerHTML = `<span class="mode-selector__option-name">${m.label}</span><span class="mode-selector__option-desc">${m.desc}</span>`;
                dropdown.appendChild(el);
            });
            this.bindEvents();
        } catch {
            this.modeLabels['default'] = 'Default';
            this.bindEvents();
        }
    }

    private bindEvents(): void {
        if (!this.modeTrigger || !this.modeDropdown) return;

        this.modeTrigger.addEventListener('click', (e: MouseEvent) => {
            e.stopPropagation();
            this.modeDropdown!.classList.toggle('mode-selector__dropdown--open');
        });

        this.modeDropdown.querySelectorAll<HTMLElement>('.mode-selector__option').forEach(opt => {
            opt.addEventListener('click', () => {
                const mode = opt.dataset.mode || 'default';
                this.wsManager.send(JSON.stringify({ type: 'set_mode', mode }));
                this.updateUI(mode);
                this.modeDropdown!.classList.remove('mode-selector__dropdown--open');
            });
        });

        document.addEventListener('click', (e: MouseEvent) => {
            if (!this.modeDropdown || !this.modeDropdown.classList.contains('mode-selector__dropdown--open')) {
                return;
            }
            const selector = document.getElementById('mode-selector');
            if (selector && !selector.contains(e.target as Node)) {
                this.modeDropdown.classList.remove('mode-selector__dropdown--open');
            }
        });
    }

    updateUI(mode: string): void {
        if (this.modeLabelEl) {
            this.modeLabelEl.textContent = this.modeLabels[mode] || mode;
        }
        if (this.modeDropdown) {
            this.modeDropdown.querySelectorAll<HTMLElement>('.mode-selector__option').forEach(opt => {
                opt.classList.toggle('mode-selector__option--active', opt.dataset.mode === mode);
            });
        }
        if (this.modeTrigger) {
            this.modeTrigger.classList.toggle('mode-selector__trigger--active', mode !== 'default');
        }
    }
}
