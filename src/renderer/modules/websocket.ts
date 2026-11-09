// WebSocket 通信管理模块

export type EventHandler = (data?: unknown) => void;

function readToken(): string {
    const meta = document.querySelector('meta[name="paw-token"]');
    return meta?.getAttribute('content') || '';
}

/**
 * 本机接口的鉴权：包装全局 fetch，让所有同源请求自动带上令牌。
 * 在 app.ts 启动时调用一次即可，调用点无需关心鉴权。
 */
export function installFetchAuth(): void {
    const original = window.fetch.bind(window);
    window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
        const url = typeof input === 'string' ? input : (input as Request).url ?? String(input);
        // 只对本站路径加头，外部链接保持原样
        if (url.startsWith('/') || url.startsWith(window.location.origin)) {
            const headers = new Headers(init?.headers || {});
            headers.set('X-Paw-Token', readToken());
            return original(input, { ...(init || {}), headers });
        }
        return original(input, init);
    };
}

export class WebSocketManager {
    private ws: WebSocket | null = null;
    private eventHandlers: Map<string, Set<EventHandler>> = new Map();
    private connectionHandlers: Set<() => void> = new Set();
    private readonly url: string;
    private reconnectAttempts = 0;
    private reconnectTimer: number | null = null;
    private manualClose = false;
    private messageQueue: string[] = [];
    private static readonly MAX_QUEUE_SIZE = 50;

    constructor(url: string) {
        // 令牌来自页面 meta，随 URL 一起传给后端校验
        const token = readToken();
        this.url = token ? `${url}?token=${encodeURIComponent(token)}` : url;
        this.connect();
    }

    private connect(): void {
        // 令牌在构造时已附加到 URL；重连沿用同一个带令牌地址
        this.ws = new WebSocket(this.url);
        this.setupEventListeners();
    }

    private setupEventListeners(): void {
        if (!this.ws) return;

        this.ws.onopen = () => {
            this.reconnectAttempts = 0;
            if (this.reconnectTimer) {
                clearTimeout(this.reconnectTimer);
                this.reconnectTimer = null;
            }
            this.connectionHandlers.forEach(handler => handler());
            this.flushQueue();
        };

        this.ws.onclose = () => {
            this.emit('disconnected');
            this.scheduleReconnect();
        };

        this.ws.onerror = () => {
            this.emit('error');
        };

        this.ws.onmessage = (e: MessageEvent) => {
            try {
                const event = JSON.parse(e.data) as { event: string; data: unknown };
                this.emit(event.event, event.data);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error);
            }
        };
    }

    private scheduleReconnect(): void {
        if (this.manualClose) return;
        if (this.reconnectTimer !== null) return;

        const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 15000);
        this.reconnectTimer = window.setTimeout(() => {
            this.reconnectAttempts += 1;
            this.reconnectTimer = null;
            this.connect();
        }, delay);
    }

    private flushQueue(): void {
        if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
        while (this.messageQueue.length > 0) {
            const message = this.messageQueue.shift();
            if (message) {
                this.ws.send(message);
            }
        }
    }

    send(message: string): void {
        if (!this.ws) {
            this.queueMessage(message);
            this.scheduleReconnect();
            return;
        }

        if (this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(message);
        } else if (this.ws.readyState === WebSocket.CONNECTING) {
            this.queueMessage(message);
        } else {
            this.queueMessage(message);
            this.scheduleReconnect();
        }
    }

    private queueMessage(message: string): void {
        this.messageQueue.push(message);
        if (this.messageQueue.length > WebSocketManager.MAX_QUEUE_SIZE) {
            this.messageQueue.shift();
        }
    }

    on(event: string, handler: EventHandler): void {
        if (!this.eventHandlers.has(event)) {
            this.eventHandlers.set(event, new Set());
        }
        this.eventHandlers.get(event)!.add(handler);
    }

    off(event: string, handler: EventHandler): void {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            handlers.delete(handler);
        }
    }

    onConnected(handler: () => void): void {
        this.connectionHandlers.add(handler);
    }

    private emit(event: string, data?: unknown): void {
        const handlers = this.eventHandlers.get(event);
        if (handlers) {
            handlers.forEach(handler => {
                try {
                    handler(data);
                } catch (error) {
                    console.error(`Error in event handler for "${event}":`, error);
                }
            });
        }
    }

    getReadyState(): number {
        return this.ws?.readyState ?? WebSocket.CLOSED;
    }

    close(): void {
        this.manualClose = true;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        this.ws?.close();
    }
}
