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
