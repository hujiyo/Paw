import { $ } from './utils.js';
const DEFAULT_CONFIG = {
    theme: 'vs-dark',
    fontSize: 14,
    tabSize: 4,
    wordWrap: 'off',
    minimap: true,
    lineNumbers: 'on',
    renderWhitespace: 'selection'
};
export class EditorSettings {
    static init() {
        if (this.initialized)
            return;
        this.view = $('#editor-settings-view');
        this.closeBtn = $('#editor-settings-close-btn');
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
    static getConfig() {
        if (!this.initialized) {
            this.loadConfig();
        }
        return { ...this.config };
    }
    static loadConfig() {
        try {
            const saved = localStorage.getItem('paw_editor_config');
            if (saved) {
                const parsed = JSON.parse(saved);
                this.config = { ...DEFAULT_CONFIG, ...parsed };
            }
        }
        catch (e) {
            console.error('Failed to load editor config', e);
        }
    }
    static saveConfig() {
        localStorage.setItem('paw_editor_config', JSON.stringify(this.config));
        // Dispatch event for FileEditor to listen
        window.dispatchEvent(new CustomEvent('paw:editor-config-changed', {
            detail: this.config
        }));
    }
    static bindInputs() {
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
            const el = $(`#${bind.id}`);
            if (!el)
                return;
            el.addEventListener('change', () => {
                let value;
                if (bind.type === 'number') {
                    value = parseInt(el.value, 10);
                }
                else if (bind.type === 'checkbox') {
                    value = el.checked;
                }
                else if (bind.type === 'checkbox-on-off') {
                    value = el.checked ? 'on' : 'off';
                }
                else {
                    value = el.value;
                }
                this.config[bind.key] = value;
                this.saveConfig();
            });
        });
    }
    static updateInputs() {
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
            const el = $(`#${bind.id}`);
            if (!el)
                return;
            const value = this.config[bind.key];
            if (bind.type === 'checkbox') {
                el.checked = value;
            }
            else if (bind.type === 'checkbox-on-off') {
                el.checked = value === 'on';
            }
            else {
                el.value = value;
            }
        });
    }
}
EditorSettings.config = DEFAULT_CONFIG;
EditorSettings.initialized = false;
