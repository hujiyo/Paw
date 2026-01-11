// ============ 第三方库类型定义 ============

/**
 * marked 库类型定义
 */
interface MarkedOptions {
    highlight?: (code: string, lang: string) => string;
    langPrefix?: string;
    gfm?: boolean;
    breaks?: boolean;
}

interface MarkedLib {
    parse(text: string): string;
    setOptions(options: MarkedOptions): void;
}

/**
 * highlight.js 类型定义
 */
interface HighlightResult {
    value: string;
    language?: string;
    relevance: number;
}

interface HljsLib {
    highlight(code: string, options: { language: string }): HighlightResult;
    highlightAuto(code: string): HighlightResult;
    getLanguage(name: string): object | undefined;
}

// ============ Electron API 类型定义 ============

interface ElectronAppInfo {
    version: string;
    platform: string;
    isDev: boolean;
    coreDir: string;
}

interface ElectronThemeColors {
    titlebar: string;
    loading: string;
    main: string;
}

interface ElectronRestartResult {
    success: boolean;
}

interface ElectronPythonLogData {
    type: string;
    message: string;
}

type ElectronUnsubscribeFunction = () => void;

interface ElectronAPI {
    getAppInfo(): Promise<ElectronAppInfo>;
    getThemeColors(): Promise<ElectronThemeColors>;
    restartBackend(): Promise<ElectronRestartResult>;
    openExternal(url: string): Promise<void>;
    showItemInFolder(path: string): Promise<void>;
    openLogFolder(): Promise<ElectronRestartResult>;
    selectFolder(): Promise<string | null>;
    onStartupStatus(callback: (status: string) => void): ElectronUnsubscribeFunction;
    onStartupError(callback: (error: string) => void): ElectronUnsubscribeFunction;
    onPythonLog(callback: (data: ElectronPythonLogData) => void): ElectronUnsubscribeFunction;
}

interface PlatformInfo {
    isWindows: boolean;
    isMac: boolean;
    isLinux: boolean;
}

declare global {
    interface Window {
        electronAPI?: ElectronAPI;
        platform?: PlatformInfo;
    }
    const marked: MarkedLib;
    const hljs: HljsLib;
}

export {};
