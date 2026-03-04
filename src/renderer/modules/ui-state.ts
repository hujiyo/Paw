// UI 状态管理模块

export interface UIState {
    sidebarVisible: boolean;
    rightSidebarVisible: boolean;
    isGenerating: boolean;
    streamId: string | null;
    streamBuf: string;
    currentContentEl: HTMLElement | null;
    cachedSessions: SessionInfo[];
}

export interface SessionInfo {
    session_id: string;
    title?: string;
    timestamp?: string;
    message_count?: number;
}

export type StateChangeListener = <K extends keyof UIState>(key: K, value: UIState[K]) => void;

export class UIStateManager {
    private state: UIState;
    private listeners: Set<StateChangeListener> = new Set();

    constructor() {
        this.state = this.loadInitialState();
    }

    private loadInitialState(): UIState {
        return {
            sidebarVisible: this.loadBoolean('paw-sidebar-visible', true),
            rightSidebarVisible: this.loadBoolean('paw-right-sidebar-visible', false),
            isGenerating: false,
            streamId: null,
            streamBuf: '',
            currentContentEl: null,
            cachedSessions: []
        };
    }

    private loadBoolean(key: string, defaultValue: boolean): boolean {
        const saved = localStorage.getItem(key);
        return saved !== null ? saved === 'true' : defaultValue;
    }

    get<K extends keyof UIState>(key: K): UIState[K] {
        return this.state[key];
    }

    set<K extends keyof UIState>(key: K, value: UIState[K]): void {
        this.state[key] = value;
        this.notifyListeners(key, value);
        this.persist(key, value);
    }

    private persist<K extends keyof UIState>(key: K, value: UIState[K]): void {
        const storageKey = this.getStorageKey(key);
        if (storageKey) {
            localStorage.setItem(storageKey, String(value));
        }
    }

    private getStorageKey(key: keyof UIState): string | null {
        switch (key) {
        case 'sidebarVisible':
            return 'paw-sidebar-visible';
        case 'rightSidebarVisible':
            return 'paw-right-sidebar-visible';
        default:
            return null;
        }
    }

    subscribe(listener: StateChangeListener): () => void {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    private notifyListeners<K extends keyof UIState>(key: K, value: UIState[K]): void {
        this.listeners.forEach(listener => {
            try {
                listener(key, value);
            } catch (error) {
                console.error('Error in state listener:', error);
            }
        });
    }

    toggleSidebar(): void {
        this.set('sidebarVisible', !this.state.sidebarVisible);
    }

    toggleRightSidebar(): void {
        this.set('rightSidebarVisible', !this.state.rightSidebarVisible);
    }

    setGenerating(generating: boolean): void {
        this.set('isGenerating', generating);
    }

    startStream(streamId: string): void {
        this.set('streamId', streamId);
        this.set('streamBuf', '');
    }

    appendStream(text: string): void {
        this.set('streamBuf', this.state.streamBuf + text);
    }

    endStream(): void {
        this.set('streamId', null);
        this.set('streamBuf', '');
        this.set('currentContentEl', null);
    }

    setCachedSessions(sessions: SessionInfo[]): void {
        this.set('cachedSessions', sessions);
    }
}
