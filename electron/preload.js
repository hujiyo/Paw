const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    // 应用信息
    getAppInfo: () => ipcRenderer.invoke('get-app-info'),
    getThemeColors: () => ipcRenderer.invoke('get-theme-colors'),

    // 后端控制
    restartBackend: () => ipcRenderer.invoke('restart-backend'),

    // 外部操作
    openExternal: (url) => ipcRenderer.invoke('open-external', url),
    showItemInFolder: (path) => ipcRenderer.invoke('show-item-in-folder', path),
    openLogFolder: () => ipcRenderer.invoke('open-log-folder'),

    // 启动状态监听
    onStartupStatus: (callback) => {
        const listener = (_, status) => callback(status);
        ipcRenderer.on('startup-status', listener);
        return () => ipcRenderer.removeListener('startup-status', listener);
    },
    onStartupError: (callback) => {
        const listener = (_, error) => callback(error);
        ipcRenderer.on('startup-error', listener);
        return () => ipcRenderer.removeListener('startup-error', listener);
    },
    onPythonLog: (callback) => {
        const listener = (_, data) => callback(data);
        ipcRenderer.on('python-log', listener);
        return () => ipcRenderer.removeListener('python-log', listener);
    }
});

contextBridge.exposeInMainWorld('platform', {
    isWindows: process.platform === 'win32',
    isMac: process.platform === 'darwin',
    isLinux: process.platform === 'linux'
});
