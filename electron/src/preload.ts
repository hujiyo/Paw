import { contextBridge, ipcRenderer, IpcRendererEvent } from 'electron';

// ============ 类型定义 ============

interface AppInfo {
    version: string;
    platform: NodeJS.Platform;
    isDev: boolean;
    coreDir: string;
}

interface ThemeColors {
    titlebar: string;
    loading: string;
    main: string;
}

interface RestartResult {
    success: boolean;
}

interface PythonLogData {
    type: string;
    message: string;
}

type UnsubscribeFunction = () => void;

// ============ API 定义 ============

const electronAPI = {
    // 应用信息
    getAppInfo: (): Promise<AppInfo> => ipcRenderer.invoke('get-app-info'),
    getThemeColors: (): Promise<ThemeColors> => ipcRenderer.invoke('get-theme-colors'),

    // 后端控制
    restartBackend: (): Promise<RestartResult> => ipcRenderer.invoke('restart-backend'),

    // 外部操作
    openExternal: (url: string): Promise<void> => ipcRenderer.invoke('open-external', url),
    showItemInFolder: (path: string): Promise<void> => ipcRenderer.invoke('show-item-in-folder', path),
    openLogFolder: (): Promise<RestartResult> => ipcRenderer.invoke('open-log-folder'),
    selectFolder: (): Promise<string | null> => ipcRenderer.invoke('select-folder'),

    // 启动状态监听
    onStartupStatus: (callback: (status: string) => void): UnsubscribeFunction => {
        const listener = (_: IpcRendererEvent, status: string): void => callback(status);
        ipcRenderer.on('startup-status', listener);
        return () => ipcRenderer.removeListener('startup-status', listener);
    },
    onStartupError: (callback: (error: string) => void): UnsubscribeFunction => {
        const listener = (_: IpcRendererEvent, error: string): void => callback(error);
        ipcRenderer.on('startup-error', listener);
        return () => ipcRenderer.removeListener('startup-error', listener);
    },
    onPythonLog: (callback: (data: PythonLogData) => void): UnsubscribeFunction => {
        const listener = (_: IpcRendererEvent, data: PythonLogData): void => callback(data);
        ipcRenderer.on('python-log', listener);
        return () => ipcRenderer.removeListener('python-log', listener);
    }
};

const platformInfo = {
    isWindows: process.platform === 'win32',
    isMac: process.platform === 'darwin',
    isLinux: process.platform === 'linux'
};

// ============ 暴露 API ============

contextBridge.exposeInMainWorld('electronAPI', electronAPI);
contextBridge.exposeInMainWorld('platform', platformInfo);
