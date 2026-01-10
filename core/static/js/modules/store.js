// 全局状态管理
export const AppState = {
    // 侧边栏状态
    sidebarVisible: true,
    
    // 生成状态
    isGenerating: false,
    
    // 流式输出相关
    streamId: null,
    streamBuf: '',
    
    // 会话列表缓存
    cachedSessions: [],

    // 初始化状态 (可以包含从 localStorage 读取的逻辑)
    init() {
        const savedSidebar = localStorage.getItem('paw-sidebar-visible');
        this.sidebarVisible = savedSidebar !== null ? savedSidebar === 'true' : true;
    }
};

/**
 * 可扩展的状态栏管理器
 * 
 * 使用方式:
 *   StatusBar.init(domElement);
 *   StatusBar.update({ model: 'gpt-4', tokens: 12500 });
 *   StatusBar.registerFormatter('tokens', (v) => `token: ${(v/1000).toFixed(1)}K`);
 */
export const StatusBar = {
    _el: null,
    _data: {},
    _formatters: {},
    _order: ['model', 'tokens'],  // 字段显示顺序

    /**
     * 初始化状态栏
     * @param {HTMLElement} el - 状态栏 DOM 元素
     */
    init(el) {
        this._el = el;
        // 默认格式化器
        this._formatters = {
            model: v => `model: ${v}`,
            tokens: v => {
                if (v >= 1000) {
                    return `token: ${(v / 1000).toFixed(1)}K`;
                }
                return `token: ${v}`;
            }
        };
    },

    /**
     * 注册自定义格式化器
     * @param {string} key - 字段名
     * @param {Function} formatter - 格式化函数 (value) => string
     */
    registerFormatter(key, formatter) {
        this._formatters[key] = formatter;
        if (!this._order.includes(key)) {
            this._order.push(key);
        }
    },

    /**
     * 设置字段显示顺序
     * @param {string[]} order - 字段名数组
     */
    setOrder(order) {
        this._order = order;
    },

    /**
     * 更新状态栏数据（增量更新）
     * @param {Object} data - 要更新的字段
     */
    update(data) {
        Object.assign(this._data, data);
        this._render();
    },

    /**
     * 清除指定字段
     * @param {...string} keys - 要清除的字段名
     */
    clear(...keys) {
        keys.forEach(k => delete this._data[k]);
        this._render();
    },

    /**
     * 重置所有数据
     */
    reset() {
        this._data = {};
        this._render();
    },

    /**
     * 渲染状态栏
     */
    _render() {
        if (!this._el) return;
        
        const parts = [];
        for (const key of this._order) {
            const value = this._data[key];
            if (value === undefined || value === null || value === '') continue;
            
            const formatter = this._formatters[key] || (v => `${key}: ${v}`);
            parts.push(formatter(value));
        }
        
        // 处理不在 _order 中的其他字段
        for (const [key, value] of Object.entries(this._data)) {
            if (this._order.includes(key)) continue;
            if (value === undefined || value === null || value === '') continue;
            
            const formatter = this._formatters[key] || (v => `${key}: ${v}`);
            parts.push(formatter(value));
        }
        
        this._el.textContent = parts.join(' · ');
    }
};
