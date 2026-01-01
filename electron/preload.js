const { contextBridge, ipcRenderer } = require('electron');

// 暴露安全的 API 到渲染进程
contextBridge.exposeInMainWorld('electronAPI', {
    // 应用信息
    getAppInfo: () => ipcRenderer.invoke('get-app-info'),

    // 后端控制
    restartBackend: () => ipcRenderer.invoke('restart-backend'),

    // 对话框
    showMessageBox: (options) => ipcRenderer.invoke('show-message-box', options),
    showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options),
    showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),

    // 外部操作
    openExternal: (url) => ipcRenderer.invoke('open-external', url),
    showItemInFolder: (fullPath) => ipcRenderer.invoke('show-item-in-folder', fullPath),

    // Python 日志监听
    onPythonLog: (callback) => {
        const listener = (_event, data) => callback(data);
        ipcRenderer.on('python-log', listener);
        return () => ipcRenderer.removeListener('python-log', listener);
    },
    onPythonError: (callback) => {
        const listener = (_event, data) => callback(data);
        ipcRenderer.on('python-error', listener);
        return () => ipcRenderer.removeListener('python-error', listener);
    },
    onPythonExit: (callback) => {
        const listener = (_event, data) => callback(data);
        ipcRenderer.on('python-exit', listener);
        return () => ipcRenderer.removeListener('python-exit', listener);
    },

    // 启动状态监听（用于 loading 页面）
    onStartupStatus: (callback) => {
        const listener = (_event, status) => callback(status);
        ipcRenderer.on('startup-status', listener);
        return () => ipcRenderer.removeListener('startup-status', listener);
    },
    onStartupError: (callback) => {
        const listener = (_event, error) => callback(error);
        ipcRenderer.on('startup-error', listener);
        return () => ipcRenderer.removeListener('startup-error', listener);
    }
});

// 添加平台信息
contextBridge.exposeInMainWorld('platform', {
    isWindows: process.platform === 'win32',
    isMac: process.platform === 'darwin',
    isLinux: process.platform === 'linux'
});
