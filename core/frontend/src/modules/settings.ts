// 配置管理
import { $, $$ } from './utils.js';
import { THEME_PRESETS, ThemeColors, ThemePreset } from './theme.js';

// ============ 类型定义 ============

export interface IdentityConfig {
    name?: string;
    username?: string;
    honey?: string;
}

export interface ApiConfig {
    key?: string;
    url?: string;
    model?: string | null;
}

export interface TerminalConfig {
    shell?: string;
    encoding?: string;
    buffer_size?: number;
}

export interface WebConfig {
    search_engine?: string;
    max_results?: number;
    page_size?: number;
    use_jina_reader?: boolean;
}

export interface SystemConfig {
    chunk_size?: number;
}

export interface MemoryConfig {
    enabled?: boolean;
    embedding_url?: string;
    embedding_key?: string;
    embedding_model?: string;
}

export interface RecallConfig {
    enabled?: boolean;
    threshold?: number;
}

export interface ThemeConfig {
    id?: string;
    titlebar?: string;
    loading?: string;
    main?: string;
    accent?: string;
}

export interface AppConfig {
    identity?: IdentityConfig;
    api?: ApiConfig;
    terminal?: TerminalConfig;
    web?: WebConfig;
    system?: SystemConfig;
    memory?: MemoryConfig;
    recall?: RecallConfig;
    theme?: ThemeConfig;
}

interface DropdownOptions {
    containerId: string;
    triggerId: string;
    dropdownId: string;
    valueDisplayId: string;
    hiddenInputId: string;
    manualInputId: string;
    addBtnId: string;
    loadingId: string;
    errorId: string;
    fetchConfig: () => { key: string; url: string };
}

interface ModelFetchData {
    request_id: string;
    models?: string[];
    error?: string;
}

type SendFunction = (msg: string) => void;
type ModelFetchResolver = (data: ModelFetchData) => void;

// ============ Settings 管理器 ============

interface SettingsManager {
    panel: HTMLElement | null;
    overlay: HTMLElement | null;
    toast: HTMLElement | null;
    currentConfig: AppConfig;
    send: SendFunction | null;
    _modelFetchResolvers: Record<string, ModelFetchResolver>;
    init(sendFn: SendFunction): void;
    setupDropdown(opts: DropdownOptions): void;
    selectOption(value: string, opts: Partial<DropdownOptions>): void;
    fetchModelsForDropdown(opts: DropdownOptions): Promise<void>;
    handleModelResponse(data: ModelFetchData): void;
    showDropdownError(opts: DropdownOptions, message: string): void;
    selectModel(value: string): void;
    setupMemoryConfig(): void;
    showCalibrateStatus(type: string, message: string): void;
    hideCalibrateStatus(): void;
    setupThemeSelector(): void;
    selectTheme(theme: string): void;
    open(): Promise<void>;
    close(): void;
    loadConfig(): Promise<void>;
    applyConfigTheme(config: AppConfig): void;
    populateForm(config: AppConfig): void;
    save(): Promise<void>;
    reset(): void;
    showToast(message: string, type?: string): void;
}

export const Settings: SettingsManager = {
    panel: null,
    overlay: null,
    toast: null,
    currentConfig: {},
    send: null,
    
    // 回调函数存储
    _modelFetchResolvers: {},

    init(sendFn: SendFunction): void {
        this.send = sendFn;
        this.panel = $<HTMLElement>('#settings-panel');
        this.overlay = $<HTMLElement>('#settings-overlay');
        this.toast = $<HTMLElement>('#settings-toast');

        // 绑定事件
        $<HTMLElement>('#settings-open-btn')?.addEventListener('click', () => this.open());
        $<HTMLElement>('#settings-close-btn')?.addEventListener('click', () => this.close());
        this.overlay?.addEventListener('click', () => this.close());
        $<HTMLElement>('#settings-save-btn')?.addEventListener('click', () => this.save());
        $<HTMLElement>('#settings-reset-btn')?.addEventListener('click', () => this.reset());

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
                key: ($<HTMLInputElement>('#cfg-api-key')?.value || '').trim(),
                url: ($<HTMLInputElement>('#cfg-api-url')?.value || '').trim()
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
                key: ($<HTMLInputElement>('#cfg-embedding-key')?.value || '').trim(),
                url: ($<HTMLInputElement>('#cfg-embedding-url')?.value || '').trim()
            })
        });

        // 主题选择器
        this.setupThemeSelector();

        // 记忆系统配置
        this.setupMemoryConfig();
        
        // 初始加载配置并应用主题
        this.loadConfig();
    },

    setupDropdown(opts: DropdownOptions): void {
        const container = $<HTMLElement>('#' + opts.containerId);
        const trigger = $<HTMLElement>('#' + opts.triggerId);
        const dropdown = $<HTMLElement>('#' + opts.dropdownId);
        const manualInput = $<HTMLInputElement>('#' + opts.manualInputId);
        const addBtn = $<HTMLElement>('#' + opts.addBtnId);

        if (!container || !trigger || !dropdown) return;

        // 切换状态管理
        (container as any)._isOpen = false;

        // 切换下拉
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            // 关闭其他打开的下拉
            document.querySelectorAll('.model-select--open').forEach(el => {
                if (el !== container) {
                    el.classList.remove('model-select--open');
                    (el as any)._isOpen = false;
                }
            });

            (container as any)._isOpen = !(container as any)._isOpen;
            container.classList.toggle('model-select--open', (container as any)._isOpen);
            
            if ((container as any)._isOpen) {
                this.fetchModelsForDropdown(opts);
            }
        });

        // 点击外部关闭
        document.addEventListener('click', (e) => {
            if ((container as any)._isOpen && !container.contains(e.target as Node)) {
                (container as any)._isOpen = false;
                container.classList.remove('model-select--open');
            }
        });

        // 选项点击事件
        dropdown.addEventListener('click', (e) => {
            const option = (e.target as HTMLElement).closest('.model-select__option');
            if (option) {
                const value = (option as HTMLElement).dataset.value || '';
                this.selectOption(value, opts);
                (container as any)._isOpen = false;
                container.classList.remove('model-select--open');
            }
        });

        // 手动输入确定
        if (addBtn && manualInput) {
            addBtn.addEventListener('click', () => {
                const value = manualInput.value.trim();
                if (value) {
                    this.selectOption(value, opts);
                    manualInput.value = '';
                    (container as any)._isOpen = false;
                    container.classList.remove('model-select--open');
                }
            });

            // 手动输入回车
            manualInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    addBtn.click();
                }
            });
        }
    },

    selectOption(value: string, opts: Partial<DropdownOptions>): void {
        if (!opts.hiddenInputId || !opts.valueDisplayId || !opts.dropdownId) return;
        
        const hiddenInput = $<HTMLInputElement>('#' + opts.hiddenInputId);
        const valueDisplay = $<HTMLElement>('#' + opts.valueDisplayId);
        const dropdown = $<HTMLElement>('#' + opts.dropdownId);

        if (hiddenInput) hiddenInput.value = value || '';

        if (valueDisplay) {
            if (!value) {
                valueDisplay.textContent = '留空或选择模型';
                valueDisplay.classList.add('model-select__value--placeholder');
            } else {
                valueDisplay.textContent = value;
                valueDisplay.classList.remove('model-select__value--placeholder');
            }
        }

        // 更新选中状态
        if (dropdown) {
            dropdown.querySelectorAll('.model-select__option').forEach(opt => {
                opt.classList.toggle('model-select__option--selected', (opt as HTMLElement).dataset.value === value);
            });
        }
    },

    async fetchModelsForDropdown(opts: DropdownOptions): Promise<void> {
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

        const loading = $<HTMLElement>('#' + opts.loadingId);
        const errorEl = $<HTMLElement>('#' + opts.errorId);
        const dropdown = $<HTMLElement>('#' + opts.dropdownId);
        const manualInput = $<HTMLInputElement>('#' + opts.manualInputId);
        const manualSection = manualInput?.parentElement;

        if (!dropdown) return;

        // 清除之前的动态选项
        dropdown.querySelectorAll('.model-select__option--dynamic').forEach(el => el.remove());
        if (errorEl) errorEl.style.display = 'none';
        if (loading) loading.style.display = 'block';

        try {
            // 通过 WebSocket 请求模型列表
            const requestId = Date.now().toString();
            const responsePromise = new Promise<string[]>((resolve, reject) => {
                const timeout = setTimeout(() => {
                    delete this._modelFetchResolvers[requestId];
                    reject(new Error('请求超时'));
                }, 10000);
                
                this._modelFetchResolvers[requestId] = (data: ModelFetchData) => {
                    clearTimeout(timeout);
                    if (data.error) reject(new Error(data.error));
                    else resolve(data.models || []);
                };
            });

            if (this.send) {
                this.send(JSON.stringify({
                    type: 'fetch_models',
                    request_id: requestId,
                    api_key: config.key,
                    api_url: config.url
                }));
            } else {
                throw new Error("WebSocket未连接");
            }

            const models = await responsePromise;
            
            // 插入模型选项
            models.forEach(model => {
                const option = document.createElement('div');
                option.className = 'model-select__option model-select__option--dynamic';
                option.dataset.value = model;
                option.textContent = model;
                // 插入到 manual section 之前
                if (manualSection) {
                    dropdown.insertBefore(option, manualSection);
                } else {
                    dropdown.appendChild(option);
                }
            });

            // 更新当前选中状态
            const currentValue = $<HTMLInputElement>('#' + opts.hiddenInputId)?.value || '';
            dropdown.querySelectorAll('.model-select__option--dynamic').forEach(opt => {
                opt.classList.toggle('model-select__option--selected', (opt as HTMLElement).dataset.value === currentValue);
            });

        } catch (err) {
            this.showDropdownError(opts, (err as Error).message || '获取模型列表失败');
        } finally {
            if (loading) loading.style.display = 'none';
        }
    },
    
    // 供 app.js 调用处理模型返回数据
    handleModelResponse(data: ModelFetchData): void {
        const resolver = this._modelFetchResolvers[data.request_id];
        if (resolver) {
            resolver(data);
            delete this._modelFetchResolvers[data.request_id];
        }
    },

    showDropdownError(opts: DropdownOptions, message: string): void {
        const errorEl = $<HTMLElement>('#' + opts.errorId);
        if (errorEl) {
            errorEl.textContent = message;
            errorEl.style.display = 'block';
        }
    },

    selectModel(value: string): void {
        // 兼容旧接口，供 populateForm 使用 (仅更新 LLM 下拉)
        this.selectOption(value, {
            hiddenInputId: 'cfg-model',
            valueDisplayId: 'model-select-value',
            dropdownId: 'model-select-dropdown'
        });
    },

    setupMemoryConfig(): void {
        const memoryEnabled = $<HTMLInputElement>('#cfg-memory-enabled');
        const configFields = $<HTMLElement>('#memory-config-fields');
        const urlPreset = $<HTMLSelectElement>('#cfg-embedding-url-preset');
        const urlInput = $<HTMLInputElement>('#cfg-embedding-url');

        // 启用/禁用记忆系统时展开/收起配置项
        if (memoryEnabled && configFields) {
            memoryEnabled.addEventListener('change', () => {
                configFields.style.display = memoryEnabled.checked ? 'block' : 'none';
            });
        }

        // URL 预设选择
        if (urlPreset && urlInput) {
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
        }

        // 阈值校准按钮
        const calibrateBtn = $<HTMLButtonElement>('#btn-calibrate-threshold');
        const thresholdInput = $<HTMLInputElement>('#cfg-recall-threshold');

        if (calibrateBtn && urlInput) {
            calibrateBtn.addEventListener('click', async () => {
                const embeddingUrl = urlInput.value.trim();
                const embeddingModel = ($<HTMLInputElement>('#cfg-embedding-model')?.value || '').trim();

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
                    const result = await response.json() as { 
                        success: boolean; 
                        threshold?: number; 
                        quality?: string; 
                        error?: string 
                    };

                    if (result.success && thresholdInput) {
                        thresholdInput.value = String(result.threshold);
                        this.showCalibrateStatus('success', 
                            `推荐阈值: ${result.threshold} (质量: ${result.quality})`);
                        // 3秒后隐藏状态
                        setTimeout(() => this.hideCalibrateStatus(), 3000);
                    } else {
                        this.showCalibrateStatus('error', result.error || '校准失败');
                    }
                } catch (e) {
                    this.showCalibrateStatus('error', '请求失败: ' + (e as Error).message);
                } finally {
                    calibrateBtn.disabled = false;
                }
            });
        }
    },

    showCalibrateStatus(type: string, message: string): void {
        const statusEl = $<HTMLElement>('#calibrate-status');
        if (!statusEl) return;
        
        statusEl.style.display = 'flex';
        statusEl.className = 'settings__status settings__status--' + type;
        
        if (type === 'loading') {
            statusEl.innerHTML = '<div class="spinner"></div>' + message;
        } else {
            statusEl.textContent = message;
        }
    },

    hideCalibrateStatus(): void {
        const statusEl = $<HTMLElement>('#calibrate-status');
        if (statusEl) {
            statusEl.style.display = 'none';
        }
    },

    setupThemeSelector(): void {
        const selector = $<HTMLElement>('#theme-selector');
        const themeInput = $<HTMLInputElement>('#cfg-theme');
        
        if (!selector) return;
        
        const options = selector.querySelectorAll('.theme-option');

        // 主题选项点击
        options.forEach(option => {
            option.addEventListener('click', () => {
                const theme = (option as HTMLElement).dataset.theme || 'yaoye';
                this.selectTheme(theme);
            });
        });

        // 初始化选中状态
        this.selectTheme(themeInput?.value || 'yaoye');
    },

    selectTheme(theme: string): void {
        const selector = $<HTMLElement>('#theme-selector');
        const themeInput = $<HTMLInputElement>('#cfg-theme');
        
        if (!selector) return;
        
        const options = selector.querySelectorAll('.theme-option');

        // 更新输入框
        if (themeInput) themeInput.value = theme;

        // 更新选中状态
        options.forEach(option => {
            option.classList.toggle('theme-option--active',
                (option as HTMLElement).dataset.theme === theme);
        });
    },


    async open(): Promise<void> {
        if (this.panel) this.panel.classList.add('settings-panel--visible');
        if (this.overlay) this.overlay.classList.add('settings-overlay--visible');
        await this.loadConfig();
    },

    close(): void {
        if (this.panel) this.panel.classList.remove('settings-panel--visible');
        if (this.overlay) this.overlay.classList.remove('settings-overlay--visible');
    },

    async loadConfig(): Promise<void> {
        try {
            const response = await fetch('/api/config');
            const result = await response.json() as { success: boolean; config?: AppConfig; error?: string };
            if (result.success && result.config) {
                this.currentConfig = result.config;
                this.populateForm(this.currentConfig);
                
                // 加载时顺便应用主题
                this.applyConfigTheme(result.config);
            } else {
                this.showToast(result.error || '加载配置失败', 'error');
            }
        } catch (e) {
            this.showToast('加载配置失败: ' + (e as Error).message, 'error');
        }
    },
    
    applyConfigTheme(config: AppConfig): void {
        if (config.theme) {
            const mainColor = config.theme.main || '#000000';
            const accentColor = config.theme.accent || null;
            ThemeColors.init(mainColor, accentColor);
        }
    },

    populateForm(config: AppConfig): void {
        // 身份配置
        const identity = config.identity || {};
        const cfgName = $<HTMLInputElement>('#cfg-name');
        const cfgUsername = $<HTMLInputElement>('#cfg-username');
        const cfgHoney = $<HTMLInputElement>('#cfg-honey');
        if (cfgName) cfgName.value = identity.name || '';
        if (cfgUsername) cfgUsername.value = identity.username || '';
        if (cfgHoney) cfgHoney.value = identity.honey || '';

        // API 配置
        const api = config.api || {};
        const cfgApiKey = $<HTMLInputElement>('#cfg-api-key');
        const cfgApiUrl = $<HTMLInputElement>('#cfg-api-url');
        if (cfgApiKey) cfgApiKey.value = api.key || '';
        if (cfgApiUrl) cfgApiUrl.value = api.url || '';
        this.selectModel(api.model || '');

        // 终端配置
        const terminal = config.terminal || {};
        const cfgShell = $<HTMLSelectElement>('#cfg-shell');
        const cfgEncoding = $<HTMLInputElement>('#cfg-encoding');
        const cfgBufferSize = $<HTMLInputElement>('#cfg-buffer-size');
        if (cfgShell) cfgShell.value = terminal.shell || 'powershell';
        if (cfgEncoding) cfgEncoding.value = terminal.encoding || 'utf-8';
        if (cfgBufferSize) cfgBufferSize.value = String(terminal.buffer_size || 24);

        // Web 配置
        const web = config.web || {};
        const cfgSearchEngine = $<HTMLSelectElement>('#cfg-search-engine');
        const cfgMaxResults = $<HTMLInputElement>('#cfg-max-results');
        const cfgUseJina = $<HTMLInputElement>('#cfg-use-jina');
        if (cfgSearchEngine) cfgSearchEngine.value = web.search_engine || 'duckduckgo';
        if (cfgMaxResults) cfgMaxResults.value = String(web.max_results || 5);
        if (cfgUseJina) cfgUseJina.checked = web.use_jina_reader !== false;

        // 系统配置
        const system = config.system || {};
        const cfgChunkSize = $<HTMLInputElement>('#cfg-chunk-size');
        if (cfgChunkSize) cfgChunkSize.value = String(system.chunk_size || 64000);

        // 记忆系统配置
        const memory = config.memory || {};
        const memoryEnabled = memory.enabled || false;
        const cfgMemoryEnabled = $<HTMLInputElement>('#cfg-memory-enabled');
        const memoryConfigFields = $<HTMLElement>('#memory-config-fields');
        if (cfgMemoryEnabled) cfgMemoryEnabled.checked = memoryEnabled;
        if (memoryConfigFields) memoryConfigFields.style.display = memoryEnabled ? 'block' : 'none';
        
        // 设置 Embedding URL
        const embeddingUrl = memory.embedding_url || 'http://localhost:11434/api/embeddings';
        const cfgEmbeddingUrl = $<HTMLInputElement>('#cfg-embedding-url');
        const cfgEmbeddingUrlPreset = $<HTMLSelectElement>('#cfg-embedding-url-preset');
        if (cfgEmbeddingUrl) cfgEmbeddingUrl.value = embeddingUrl;
        
        // 检测预设选项
        if (cfgEmbeddingUrlPreset) {
            if (embeddingUrl === 'http://localhost:11434/api/embeddings') {
                cfgEmbeddingUrlPreset.value = 'ollama';
            } else if (embeddingUrl === 'http://localhost:1234/v1/embeddings') {
                cfgEmbeddingUrlPreset.value = 'lm_studio';
            } else {
                cfgEmbeddingUrlPreset.value = 'custom';
            }
        }
        
        const cfgEmbeddingKey = $<HTMLInputElement>('#cfg-embedding-key');
        if (cfgEmbeddingKey) cfgEmbeddingKey.value = memory.embedding_key || '';
        
        // 更新 Embedding 下拉
        this.selectOption(memory.embedding_model || 'nomic-embed-text', {
            hiddenInputId: 'cfg-embedding-model',
            valueDisplayId: 'embed-model-select-value',
            dropdownId: 'embed-model-select-dropdown'
        });

        // 回忆阈值配置
        const recall = config.recall || {};
        const cfgRecallThreshold = $<HTMLInputElement>('#cfg-recall-threshold');
        if (cfgRecallThreshold) cfgRecallThreshold.value = String(recall.threshold || 0.35);

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

    async save(): Promise<void> {
        const cfgName = $<HTMLInputElement>('#cfg-name');
        const cfgUsername = $<HTMLInputElement>('#cfg-username');
        const cfgHoney = $<HTMLInputElement>('#cfg-honey');
        const cfgApiKey = $<HTMLInputElement>('#cfg-api-key');
        const cfgApiUrl = $<HTMLInputElement>('#cfg-api-url');
        const cfgModel = $<HTMLInputElement>('#cfg-model');
        const cfgShell = $<HTMLSelectElement>('#cfg-shell');
        const cfgEncoding = $<HTMLInputElement>('#cfg-encoding');
        const cfgBufferSize = $<HTMLInputElement>('#cfg-buffer-size');
        const cfgSearchEngine = $<HTMLSelectElement>('#cfg-search-engine');
        const cfgMaxResults = $<HTMLInputElement>('#cfg-max-results');
        const cfgUseJina = $<HTMLInputElement>('#cfg-use-jina');
        const cfgChunkSize = $<HTMLInputElement>('#cfg-chunk-size');
        const cfgMemoryEnabled = $<HTMLInputElement>('#cfg-memory-enabled');
        const cfgEmbeddingUrl = $<HTMLInputElement>('#cfg-embedding-url');
        const cfgEmbeddingKey = $<HTMLInputElement>('#cfg-embedding-key');
        const cfgEmbeddingModel = $<HTMLInputElement>('#cfg-embedding-model');
        const cfgRecallThreshold = $<HTMLInputElement>('#cfg-recall-threshold');
        const cfgTheme = $<HTMLInputElement>('#cfg-theme');
        
        const config: AppConfig = {
            identity: {
                name: cfgName?.value || 'Paw',
                username: cfgUsername?.value || 'hujiyo',
                honey: cfgHoney?.value || '老公'
            },
            api: {
                key: cfgApiKey?.value || '',
                url: cfgApiUrl?.value || '',
                model: cfgModel?.value || null
            },
            terminal: {
                shell: cfgShell?.value || 'powershell',
                encoding: cfgEncoding?.value || 'utf-8',
                buffer_size: Math.max(4, Math.min(64, parseInt(cfgBufferSize?.value || '24', 10) || 24))
            },
            web: {
                search_engine: cfgSearchEngine?.value || 'duckduckgo',
                max_results: parseInt(cfgMaxResults?.value || '5', 10) || 5,
                page_size: 4096,
                use_jina_reader: cfgUseJina?.checked ?? true
            },
            system: {
                chunk_size: parseInt(cfgChunkSize?.value || '64000', 10) || 64000
            },
            memory: {
                enabled: cfgMemoryEnabled?.checked ?? false,
                embedding_url: cfgEmbeddingUrl?.value || 'http://localhost:11434/api/embeddings',
                embedding_key: cfgEmbeddingKey?.value || '',
                embedding_model: cfgEmbeddingModel?.value || 'nomic-embed-text'
            },
            recall: {
                enabled: true,
                threshold: parseFloat(cfgRecallThreshold?.value || '0.35') || 0.35
            },
            theme: (() => {
                const themeId = cfgTheme?.value || 'yaoye';
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
            const result = await response.json() as { success: boolean; error?: string };
            if (result.success) {
                this.showToast('配置已保存，请重启应用生效', 'success');
                this.currentConfig = config;
            } else {
                this.showToast(result.error || '保存失败', 'error');
            }
        } catch (e) {
            this.showToast('保存失败: ' + (e as Error).message, 'error');
        }
    },

    reset(): void {
        this.populateForm(this.currentConfig);
        this.showToast('已重置为当前配置', 'success');
    },

    showToast(message: string, type: string = 'success'): void {
        if (!this.toast) return;
        
        this.toast.textContent = message;
        this.toast.className = 'settings__toast settings__toast--visible';
        if (type === 'error') {
            this.toast.classList.add('settings__toast--error');
        } else {
            this.toast.classList.add('settings__toast--success');
        }
        setTimeout(() => {
            if (this.toast) this.toast.classList.remove('settings__toast--visible');
        }, 3000);
    }
};
