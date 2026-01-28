import { $ } from './utils.js';

export interface EditorConfig {
    theme: 'vs' | 'vs-dark' | 'hc-black';
    fontSize: number;
    tabSize: number;
    wordWrap: 'on' | 'off' | 'wordWrapColumn' | 'bounded';
    minimap: boolean;
    lineNumbers: 'on' | 'off';
    renderWhitespace: 'none' | 'boundary' | 'selection' | 'trailing' | 'all';
}

const DEFAULT_CONFIG: EditorConfig = {
    theme: 'vs-dark',
    fontSize: 14,
    tabSize: 4,
    wordWrap: 'off',
    minimap: true,
    lineNumbers: 'on',
    renderWhitespace: 'selection'
};

export class EditorSettings {
    private static view: HTMLElement;
    private static closeBtn: HTMLElement;
    private static config: EditorConfig = DEFAULT_CONFIG;
    private static initialized: boolean = false;

    static init() {
        if (this.initialized) return;

        this.view = $('#editor-settings-view')!;
        this.closeBtn = $('#editor-settings-close-btn')!;

        // Load config from localStorage
        this.loadConfig();

        // Bind events
        this.closeBtn?.addEventListener('click', () => this.hide());
        this.bindInputs();

        this.initialized = true;
    }

    static show() {
        // Update inputs to match current config
        this.updateInputs();
        
        // Hide chat view, show settings
        $('#chat-view')?.classList.remove('chat-view--active');
        $('#skills-market-view')?.classList.remove('skills-market-view--active');
        this.view?.classList.add('editor-settings-view--active');
    }

    static hide() {
        this.view?.classList.remove('editor-settings-view--active');
        $('#chat-view')?.classList.add('chat-view--active');
    }

    static getConfig(): EditorConfig {
        if (!this.initialized) {
            this.loadConfig();
        }
        return { ...this.config };
    }

    private static loadConfig() {
        try {
            const saved = localStorage.getItem('paw_editor_config');
            if (saved) {
                const parsed = JSON.parse(saved);
                this.config = { ...DEFAULT_CONFIG, ...parsed };
            }
        } catch (e) {
            console.error('Failed to load editor config', e);
        }
    }

    private static saveConfig() {
        localStorage.setItem('paw_editor_config', JSON.stringify(this.config));
        // Dispatch event for FileEditor to listen
        window.dispatchEvent(new CustomEvent('paw:editor-config-changed', { 
            detail: this.config 
        }));
    }

    private static bindInputs() {
        const bindings = [
            { id: 'es-theme', key: 'theme' },
            { id: 'es-fontSize', key: 'fontSize', type: 'number' },
            { id: 'es-tabSize', key: 'tabSize', type: 'number' },
            { id: 'es-wordWrap', key: 'wordWrap' },
            { id: 'es-renderWhitespace', key: 'renderWhitespace' },
            { id: 'es-lineNumbers', key: 'lineNumbers', type: 'checkbox-on-off' }, // checkbox mapped to 'on'/'off'
            { id: 'es-minimap', key: 'minimap', type: 'checkbox' }
        ];

        bindings.forEach(bind => {
            const el = $(`#${bind.id}`) as HTMLInputElement | HTMLSelectElement;
            if (!el) return;

            el.addEventListener('change', () => {
                let value: any;
                if (bind.type === 'number') {
                    value = parseInt(el.value, 10);
                } else if (bind.type === 'checkbox') {
                    value = (el as HTMLInputElement).checked;
                } else if (bind.type === 'checkbox-on-off') {
                    value = (el as HTMLInputElement).checked ? 'on' : 'off';
                } else {
                    value = el.value;
                }

                (this.config as any)[bind.key] = value;
                this.saveConfig();
            });
        });
    }

    private static updateInputs() {
        const bindings = [
            { id: 'es-theme', key: 'theme' },
            { id: 'es-fontSize', key: 'fontSize' },
            { id: 'es-tabSize', key: 'tabSize' },
            { id: 'es-wordWrap', key: 'wordWrap' },
            { id: 'es-renderWhitespace', key: 'renderWhitespace' },
            { id: 'es-lineNumbers', key: 'lineNumbers', type: 'checkbox-on-off' },
            { id: 'es-minimap', key: 'minimap', type: 'checkbox' }
        ];

        bindings.forEach(bind => {
            const el = $(`#${bind.id}`) as HTMLInputElement | HTMLSelectElement;
            if (!el) return;

            const value = (this.config as any)[bind.key];

            if (bind.type === 'checkbox') {
                (el as HTMLInputElement).checked = value;
            } else if (bind.type === 'checkbox-on-off') {
                (el as HTMLInputElement).checked = value === 'on';
            } else {
                el.value = value;
            }
        });
    }
}
