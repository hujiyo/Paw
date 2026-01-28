import { $ } from './utils.js';
import { escapeHtml } from './utils.js';
import { EditorSettings, EditorConfig } from './editor-settings.js';

// 声明全局 monaco 变量
declare const monaco: any;
declare const require: any;

interface FileInfo {
    path: string;
    name: string;
    content: string;
}

export class FileEditor {
    private container: HTMLElement;
    private file: FileInfo;
    private editorContainer: HTMLElement | null = null;
    private editor: any = null; // Monaco editor instance
    private saveBtn: HTMLButtonElement | null = null;
    private settingsBtn: HTMLButtonElement | null = null;
    private statusEl: HTMLElement | null = null;
    private isModified: boolean = false;

    constructor(container: HTMLElement, file: FileInfo) {
        this.container = container;
        this.file = file;
        
        // 绑定配置更新事件
        window.addEventListener('paw:editor-config-changed', (e: any) => {
            this.updateConfig(e.detail);
        });
        
        this.render();
    }

    private render() {
        this.container.innerHTML = `
            <div class="file-editor">
                <div class="file-editor__toolbar">
                    <div class="file-editor__info">
                        <span class="file-editor__name">${escapeHtml(this.file.name)}</span>
                        <span class="file-editor__path">${escapeHtml(this.file.path)}</span>
                    </div>
                    <div class="file-editor__actions">
                        <span class="file-editor__status" id="status-${this.hashCode(this.file.path)}"></span>
                        <button class="icon-btn" id="settings-${this.hashCode(this.file.path)}" title="Editor Settings">⚙️</button>
                        <button class="file-editor__btn file-editor__btn--primary" id="save-${this.hashCode(this.file.path)}">Save (Ctrl+S)</button>
                    </div>
                </div>
                <div class="file-editor__content" id="monaco-${this.hashCode(this.file.path)}">
                    <!-- Monaco Editor 挂载点 -->
                </div>
            </div>
        `;

        this.editorContainer = this.container.querySelector('.file-editor__content');
        this.saveBtn = this.container.querySelector('.file-editor__btn');
        this.settingsBtn = this.container.querySelector('.icon-btn');
        this.statusEl = this.container.querySelector('.file-editor__status');

        // 初始化 Monaco Editor
        this.initMonaco();

        if (this.saveBtn) {
            this.saveBtn.addEventListener('click', () => this.save());
        }
        
        if (this.settingsBtn) {
            this.settingsBtn.addEventListener('click', () => {
                EditorSettings.show();
            });
        }
    }

    private initMonaco() {
        if (!this.editorContainer) return;

        // 等待 Monaco 加载完成
        if (typeof monaco === 'undefined') {
            // 如果 monaco 还没加载，尝试通过 require 加载
            if (typeof require !== 'undefined') {
                require(['vs/editor/editor.main'], () => {
                    this.createEditor();
                });
            } else {
                this.editorContainer.innerHTML = '<div style="padding:1rem;color:red">Monaco Editor loader not found.</div>';
            }
        } else {
            this.createEditor();
        }
    }

    private createEditor() {
        if (!this.editorContainer) return;

        // 根据文件名判断语言
        const language = this.getLanguage(this.file.name);
        
        // 获取配置
        const config = EditorSettings.getConfig();

        // 创建编辑器
        this.editor = monaco.editor.create(this.editorContainer, {
            value: this.file.content,
            language: language,
            theme: config.theme,
            automaticLayout: true,
            minimap: { enabled: config.minimap },
            scrollBeyondLastLine: false,
            fontSize: config.fontSize,
            fontFamily: "'Consolas', 'Monaco', 'Courier New', monospace",
            renderWhitespace: config.renderWhitespace,
            tabSize: config.tabSize,
            wordWrap: config.wordWrap,
            lineNumbers: config.lineNumbers
        });

        // 绑定变化事件
        this.editor.onDidChangeModelContent(() => {
            this.onInput();
        });

        // 绑定保存快捷键 (Ctrl+S / Cmd+S)
        this.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
            this.save();
        });
        
        // 监听容器大小变化（虽然 automaticLayout: true 很有用，但在某些 flex 布局下可能需要手动触发）
        const observer = new ResizeObserver(() => {
            this.editor.layout();
        });
        observer.observe(this.editorContainer);
    }
    
    private updateConfig(config: EditorConfig) {
        if (!this.editor) return;
        
        // 更新主题 (全局设置)
        monaco.editor.setTheme(config.theme);
        
        // 更新选项
        this.editor.updateOptions({
            fontSize: config.fontSize,
            tabSize: config.tabSize,
            wordWrap: config.wordWrap,
            minimap: { enabled: config.minimap },
            lineNumbers: config.lineNumbers,
            renderWhitespace: config.renderWhitespace
        });
    }

    private getLanguage(filename: string): string {
        const ext = filename.split('.').pop()?.toLowerCase();
        const map: Record<string, string> = {
            'js': 'javascript', 'ts': 'typescript', 'py': 'python',
            'html': 'html', 'css': 'css', 'json': 'json',
            'md': 'markdown', 'yml': 'yaml', 'yaml': 'yaml',
            'xml': 'xml', 'sh': 'shell', 'bash': 'shell',
            'sql': 'sql', 'java': 'java', 'c': 'c', 'cpp': 'cpp',
            'go': 'go', 'rs': 'rust', 'php': 'php'
        };
        return map[ext || ''] || 'plaintext';
    }

    private onInput() {
        if (!this.isModified) {
            this.isModified = true;
            if (this.statusEl) this.statusEl.textContent = 'Unsaved';
        }
    }

    private async save() {
        if (!this.editor) return;
        
        const content = this.editor.getValue();
        const btn = this.saveBtn;
        
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Saving...';
        }
        
        try {
            const res = await fetch('/api/fs/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    path: this.file.path,
                    content: content
                })
            });
            
            const data = await res.json();
            
            if (data.success) {
                this.isModified = false;
                // Update internal content
                this.file.content = content;
                
                if (this.statusEl) {
                    this.statusEl.textContent = 'Saved';
                    setTimeout(() => {
                        if (this.statusEl && this.statusEl.textContent === 'Saved') {
                            this.statusEl.textContent = '';
                        }
                    }, 2000);
                }
            } else {
                alert('Failed to save: ' + data.error);
            }
        } catch (e) {
            alert('Error saving file: ' + e);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Save (Ctrl+S)';
            }
        }
    }

    private hashCode(str: string): string {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return Math.abs(hash).toString(36);
    }
}
