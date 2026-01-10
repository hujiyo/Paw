// 配置管理
import { $, $$ } from './utils.js';
import { THEME_PRESETS, ThemeColors } from './theme.js';

export const Settings = {
    panel: null,
    overlay: null,
    toast: null,
    currentConfig: {},
    send: null, // 发送函数 WebSocket send
    
    // 回调函数存储
    _modelFetchResolvers: {},

    init(sendFn) {
        this.send = sendFn;
        this.panel = $('#settings-panel');
        this.overlay = $('#settings-overlay');
        this.toast = $('#settings-toast');

        // 绑定事件
        $('#settings-open-btn').addEventListener('click', () => this.open());
        $('#settings-close-btn').addEventListener('click', () => this.close());
        this.overlay.addEventListener('click', () => this.close());
        $('#settings-save-btn').addEventListener('click', () => this.save());
        $('#settings-reset-btn').addEventListener('click', () => this.reset());

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
                key: $('#cfg-api-key').value.trim(),
                url: $('#cfg-api-url').value.trim()
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
                key: $('#cfg-embedding-key').value.trim(),
                url: $('#cfg-embedding-url').value.trim()
            })
        });

        // 主题选择器
        this.setupThemeSelector();

        // 记忆系统配置
        this.setupMemoryConfig();
        
        // 初始加载配置并应用主题
        this.loadConfig();
    },

    setupDropdown(opts) {
        const container = $('#' + opts.containerId);
        const trigger = $('#' + opts.triggerId);
        const dropdown = $('#' + opts.dropdownId);
        const valueDisplay = $('#' + opts.valueDisplayId);
        const hiddenInput = $('#' + opts.hiddenInputId);
        const manualInput = $('#' + opts.manualInputId);
        const addBtn = $('#' + opts.addBtnId);

        // 切换状态管理
        container._isOpen = false;

        // 切换下拉
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            // 关闭其他打开的下拉
            document.querySelectorAll('.model-select--open').forEach(el => {
                if (el !== container) {
                    el.classList.remove('model-select--open');
                    el._isOpen = false;
                }
            });

            container._isOpen = !container._isOpen;
            container.classList.toggle('model-select--open', container._isOpen);
            
            if (container._isOpen) {
                this.fetchModelsForDropdown(opts);
            }
        });

        // 点击外部关闭
        document.addEventListener('click', (e) => {
            if (container._isOpen && !container.contains(e.target)) {
                container._isOpen = false;
                container.classList.remove('model-select--open');
            }
        });

        // 选项点击事件
        dropdown.addEventListener('click', (e) => {
            const option = e.target.closest('.model-select__option');
            if (option) {
                const value = option.dataset.value;
                this.selectOption(value, opts);
                container._isOpen = false;
                container.classList.remove('model-select--open');
            }
        });

        // 手动输入确定
        addBtn.addEventListener('click', () => {
            const value = manualInput.value.trim();
            if (value) {
                this.selectOption(value, opts);
                manualInput.value = '';
                container._isOpen = false;
                container.classList.remove('model-select--open');
            }
        });

        // 手动输入回车
        manualInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                addBtn.click();
            }
        });
    },

    selectOption(value, opts) {
        const hiddenInput = $('#' + opts.hiddenInputId);
        const valueDisplay = $('#' + opts.valueDisplayId);
        const dropdown = $('#' + opts.dropdownId);

        hiddenInput.value = value || '';

        if (!value) {
            valueDisplay.textContent = '留空或选择模型';
            valueDisplay.classList.add('model-select__value--placeholder');
        } else {
            valueDisplay.textContent = value;
            valueDisplay.classList.remove('model-select__value--placeholder');
        }

        // 更新选中状态
        dropdown.querySelectorAll('.model-select__option').forEach(opt => {
            opt.classList.toggle('model-select__option--selected', opt.dataset.value === value);
        });
    },

    async fetchModelsForDropdown(opts) {
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

        const loading = $('#' + opts.loadingId);
        const errorEl = $('#' + opts.errorId);
        const dropdown = $('#' + opts.dropdownId);
        const manualSection = $('#' + opts.manualInputId).parentElement; // model-select__manual div

        // 清除之前的动态选项
        dropdown.querySelectorAll('.model-select__option--dynamic').forEach(el => el.remove());
        errorEl.style.display = 'none';
        loading.style.display = 'block';

        try {
            // 通过 WebSocket 请求模型列表
            const requestId = Date.now().toString();
            const responsePromise = new Promise((resolve, reject) => {
                const timeout = setTimeout(() => {
                    delete this._modelFetchResolvers[requestId];
                    reject(new Error('请求超时'));
                }, 10000);
                
                this._modelFetchResolvers[requestId] = (data) => {
                    clearTimeout(timeout);
                    if (data.error) reject(new Error(data.error));
                    else resolve(data.models);
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
                dropdown.insertBefore(option, manualSection);
            });

            // 更新当前选中状态
            const currentValue = $('#' + opts.hiddenInputId).value;
            dropdown.querySelectorAll('.model-select__option--dynamic').forEach(opt => {
                opt.classList.toggle('model-select__option--selected', opt.dataset.value === currentValue);
            });

        } catch (err) {
            this.showDropdownError(opts, err.message || '获取模型列表失败');
        } finally {
            loading.style.display = 'none';
        }
    },
    
    // 供 app.js 调用处理模型返回数据
    handleModelResponse(data) {
        const resolver = this._modelFetchResolvers[data.request_id];
        if (resolver) {
            resolver(data);
            delete this._modelFetchResolvers[data.request_id];
        }
    },

    showDropdownError(opts, message) {
        const errorEl = $('#' + opts.errorId);
        errorEl.textContent = message;
        errorEl.style.display = 'block';
    },

    selectModel(value) {
        // 兼容旧接口，供 populateForm 使用 (仅更新 LLM 下拉)
        this.selectOption(value, {
            hiddenInputId: 'cfg-model',
            valueDisplayId: 'model-select-value',
            dropdownId: 'model-select-dropdown'
        });
    },

    setupMemoryConfig() {
        const memoryEnabled = $('#cfg-memory-enabled');
        const configFields = $('#memory-config-fields');
        const urlPreset = $('#cfg-embedding-url-preset');
        const urlInput = $('#cfg-embedding-url');

        // 启用/禁用记忆系统时展开/收起配置项
        memoryEnabled.addEventListener('change', () => {
            configFields.style.display = memoryEnabled.checked ? 'block' : 'none';
        });

        // URL 预设选择
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

        // 阈值校准按钮
        const calibrateBtn = $('#btn-calibrate-threshold');
        const thresholdInput = $('#cfg-recall-threshold');

        calibrateBtn.addEventListener('click', async () => {
            const embeddingUrl = urlInput.value.trim();
            const embeddingModel = $('#cfg-embedding-model').value.trim();

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
                const result = await response.json();

                if (result.success) {
                    thresholdInput.value = result.threshold;
                    this.showCalibrateStatus('success', 
                        `推荐阈值: ${result.threshold} (质量: ${result.quality})`);
                    // 3秒后隐藏状态
                    setTimeout(() => this.hideCalibrateStatus(), 3000);
                } else {
                    this.showCalibrateStatus('error', result.error || '校准失败');
                }
            } catch (e) {
                this.showCalibrateStatus('error', '请求失败: ' + e.message);
            } finally {
                calibrateBtn.disabled = false;
            }
        });
    },

    showCalibrateStatus(type, message) {
        const statusEl = $('#calibrate-status');
        statusEl.style.display = 'flex';
        statusEl.className = 'settings__status settings__status--' + type;
        
        if (type === 'loading') {
            statusEl.innerHTML = '<div class="spinner"></div>' + message;
        } else {
            statusEl.textContent = message;
        }
    },

    hideCalibrateStatus() {
        const statusEl = $('#calibrate-status');
        statusEl.style.display = 'none';
    },

    setupThemeSelector() {
        const selector = $('#theme-selector');
        const themeInput = $('#cfg-theme');
        const options = selector.querySelectorAll('.theme-option');

        // 主题选项点击
        options.forEach(option => {
            option.addEventListener('click', () => {
                const theme = option.dataset.theme;
                this.selectTheme(theme);
            });
        });

        // 初始化选中状态
        this.selectTheme(themeInput.value || 'yaoye');
    },

    selectTheme(theme) {
        const selector = $('#theme-selector');
        const themeInput = $('#cfg-theme');
        const options = selector.querySelectorAll('.theme-option');

        // 更新输入框
        themeInput.value = theme;

        // 更新选中状态
        options.forEach(option => {
            option.classList.toggle('theme-option--active',
                option.dataset.theme === theme);
        });
    },


    async open() {
        this.panel.classList.add('settings-panel--visible');
        this.overlay.classList.add('settings-overlay--visible');
        await this.loadConfig();
    },

    close() {
        this.panel.classList.remove('settings-panel--visible');
        this.overlay.classList.remove('settings-overlay--visible');
    },

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            const result = await response.json();
            if (result.success) {
                this.currentConfig = result.config;
                this.populateForm(this.currentConfig);
                
                // 加载时顺便应用主题
                this.applyConfigTheme(result.config);
            } else {
                this.showToast(result.error || '加载配置失败', 'error');
            }
        } catch (e) {
            this.showToast('加载配置失败: ' + e.message, 'error');
        }
    },
    
    applyConfigTheme(config) {
        if (config.theme) {
            const mainColor = config.theme.main || '#000000';
            const accentColor = config.theme.accent || null;
            ThemeColors.init(mainColor, accentColor);
        }
    },

    populateForm(config) {
        // 身份配置
        const identity = config.identity || {};
        $('#cfg-name').value = identity.name || '';
        $('#cfg-username').value = identity.username || '';
        $('#cfg-honey').value = identity.honey || '';

        // API 配置
        const api = config.api || {};
        $('#cfg-api-key').value = api.key || '';
        $('#cfg-api-url').value = api.url || '';
        this.selectModel(api.model || '');

        // 终端配置
        const terminal = config.terminal || {};
        $('#cfg-shell').value = terminal.shell || 'powershell';
        $('#cfg-encoding').value = terminal.encoding || 'utf-8';
        $('#cfg-buffer-size').value = terminal.buffer_size || 24;

        // Web 配置
        const web = config.web || {};
        $('#cfg-search-engine').value = web.search_engine || 'duckduckgo';
        $('#cfg-max-results').value = web.max_results || 5;
        $('#cfg-use-jina').checked = web.use_jina_reader !== false;

        // 系统配置
        const system = config.system || {};
        $('#cfg-chunk-size').value = system.chunk_size || 64000;

        // 记忆系统配置
        const memory = config.memory || {};
        const memoryEnabled = memory.enabled || false;
        $('#cfg-memory-enabled').checked = memoryEnabled;
        $('#memory-config-fields').style.display = memoryEnabled ? 'block' : 'none';
        
        // 设置 Embedding URL
        const embeddingUrl = memory.embedding_url || 'http://localhost:11434/api/embeddings';
        $('#cfg-embedding-url').value = embeddingUrl;
        // 检测预设选项
        if (embeddingUrl === 'http://localhost:11434/api/embeddings') {
            $('#cfg-embedding-url-preset').value = 'ollama';
        } else if (embeddingUrl === 'http://localhost:1234/v1/embeddings') {
            $('#cfg-embedding-url-preset').value = 'lm_studio';
        } else {
            $('#cfg-embedding-url-preset').value = 'custom';
        }
        
        $('#cfg-embedding-key').value = memory.embedding_key || '';
        // 更新 Embedding 下拉
        this.selectOption(memory.embedding_model || 'nomic-embed-text', {
            hiddenInputId: 'cfg-embedding-model',
            valueDisplayId: 'embed-model-select-value',
            dropdownId: 'embed-model-select-dropdown'
        });

        // 回忆阈值配置
        const recall = config.recall || {};
        $('#cfg-recall-threshold').value = recall.threshold || 0.35;

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

    async save() {
        const config = {
            identity: {
                name: $('#cfg-name').value || 'Paw',
                username: $('#cfg-username').value || 'hujiyo',
                honey: $('#cfg-honey').value || '老公'
            },
            api: {
                key: $('#cfg-api-key').value,
                url: $('#cfg-api-url').value,
                model: $('#cfg-model').value || null
            },
            terminal: {
                shell: $('#cfg-shell').value,
                encoding: $('#cfg-encoding').value || 'utf-8',
                buffer_size: Math.max(4, Math.min(64, parseInt($('#cfg-buffer-size').value) || 24))
            },
            web: {
                search_engine: $('#cfg-search-engine').value,
                max_results: parseInt($('#cfg-max-results').value) || 5,
                page_size: 4096,
                use_jina_reader: $('#cfg-use-jina').checked
            },
            system: {
                chunk_size: parseInt($('#cfg-chunk-size').value) || 64000
            },
            memory: {
                enabled: $('#cfg-memory-enabled').checked,
                embedding_url: $('#cfg-embedding-url').value || 'http://localhost:11434/api/embeddings',
                embedding_key: $('#cfg-embedding-key').value || '',
                embedding_model: $('#cfg-embedding-model').value || 'nomic-embed-text'
            },
            recall: {
                enabled: true,
                threshold: parseFloat($('#cfg-recall-threshold').value) || 0.35
            },
            theme: (() => {
                const themeId = $('#cfg-theme').value || 'yaoye';
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
            const result = await response.json();
            if (result.success) {
                this.showToast('配置已保存，请重启应用生效', 'success');
                this.currentConfig = config;
            } else {
                this.showToast(result.error || '保存失败', 'error');
            }
        } catch (e) {
            this.showToast('保存失败: ' + e.message, 'error');
        }
    },

    reset() {
        this.populateForm(this.currentConfig);
        this.showToast('已重置为当前配置', 'success');
    },

    showToast(message, type = 'success') {
        this.toast.textContent = message;
        this.toast.className = 'settings__toast settings__toast--visible';
        if (type === 'error') {
            this.toast.classList.add('settings__toast--error');
        } else {
            this.toast.classList.add('settings__toast--success');
        }
        setTimeout(() => {
            this.toast.classList.remove('settings__toast--visible');
        }, 3000);
    }
};
