// 全局状态管理
// ============ 应用状态 ============
export const AppState = {
    // 左侧边栏状态
    sidebarVisible: true,
    // 右侧边栏状态
    rightSidebarVisible: false,
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
// ============ 状态栏管理器 ============
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
    _order: ['workspace', 'model', 'tokens'], // 字段显示顺序
    /**
     * 初始化状态栏
     * @param el - 状态栏 DOM 元素
     */
    init(el) {
        this._el = el;
        // 默认格式化器
        this._formatters = {
            workspace: (v) => `${v}`,
            model: (v) => `model: ${v}`,
            tokens: (v) => {
                const num = typeof v === 'number' ? v : parseInt(v, 10);
                if (num >= 1000) {
                    return `token: ${(num / 1000).toFixed(1)}K`;
                }
                return `token: ${num}`;
            }
        };
        // 默认顺序：workspace -> model -> tokens
        this._order = ['workspace', 'model', 'tokens'];
    },
    /**
     * 注册自定义格式化器
     * @param key - 字段名
     * @param formatter - 格式化函数 (value) => string
     */
    registerFormatter(key, formatter) {
        this._formatters[key] = formatter;
        if (!this._order.includes(key)) {
            this._order.push(key);
        }
    },
    /**
     * 设置字段显示顺序
     * @param order - 字段名数组
     */
    setOrder(order) {
        this._order = order;
    },
    /**
     * 更新状态栏数据（增量更新）
     * @param data - 要更新的字段
     */
    update(data) {
        Object.assign(this._data, data);
        this._render();
    },
    /**
     * 清除指定字段
     * @param keys - 要清除的字段名
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
        if (!this._el)
            return;
        const parts = [];
        for (const key of this._order) {
            const value = this._data[key];
            if (value === undefined || value === null || value === '')
                continue;
            const formatter = this._formatters[key] || ((v) => `${key}: ${v}`);
            parts.push(formatter(value));
        }
        // 处理不在 _order 中的其他字段
        for (const [key, value] of Object.entries(this._data)) {
            if (this._order.includes(key))
                continue;
            if (value === undefined || value === null || value === '')
                continue;
            const formatter = this._formatters[key] || ((v) => `${key}: ${v}`);
            parts.push(formatter(value));
        }
        this._el.textContent = parts.join(' · ');
    }
};
