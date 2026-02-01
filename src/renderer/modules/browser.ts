import { $, escapeHtml } from './utils.js';

export interface SearchResult {
    id: string;
    title: string;
    url: string;
    snippet: string;
}

/** URL条目（从对话中提取） */
interface UrlEntry {
    url: string;
    title: string;
}

export class Browser {
    private static mainView: HTMLElement;
    private static detailView: HTMLElement;
    private static urlListContainer: HTMLElement;
    private static emptyState: HTMLElement;
    private static iframe: HTMLIFrameElement;
    private static input: HTMLInputElement;
    private static goBtn: HTMLButtonElement;
    private static backBtn: HTMLElement;
    private static externalBtn: HTMLElement;
    private static detailTitle: HTMLElement;
    private static urlCountEl: HTMLElement;

    static init() {
        this.mainView = $('#browser-main-view')!;
        this.detailView = $('#browser-detail-view')!;
        this.urlListContainer = $('#browser-results')!;
        this.emptyState = this.urlListContainer?.querySelector('.browser-empty')!;
        this.iframe = $('#browser-frame') as HTMLIFrameElement;
        this.input = $('#browser-url') as HTMLInputElement;
        this.goBtn = $('#browser-go') as HTMLButtonElement;
        this.backBtn = $('#browser-back-btn')!;
        this.externalBtn = $('#browser-external-btn')!;
        this.detailTitle = $('#browser-detail-title')!;
        this.urlCountEl = $('#browser-url-count')!;

        this.goBtn?.addEventListener('click', () => this.navigate());
        this.input?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this.navigate();
        });
        this.backBtn?.addEventListener('click', () => this.showMainView());
        this.externalBtn?.addEventListener('click', () => this.openInExternalBrowser());
    }

    /**
     * 从对话历史中提取并渲染所有URL
     * 直接遍历DOM获取最新状态
     */
    static refresh() {
        if (!this.urlListContainer) return;

        // 从消息容器中提取所有URL
        const messagesEl = document.getElementById('messages');
        if (!messagesEl) return;

        const urls: UrlEntry[] = [];
        const seenUrls = new Set<string>();

        console.log('[Browser] Refreshing URLs from DOM...');

        // 遍历所有消息，按顺序提取URL
        messagesEl.querySelectorAll('.msg').forEach((msgEl, msgIndex) => {
            // 1. 从消息文本中提取（markdown渲染后的<a>标签）
            msgEl.querySelectorAll('.msg__content a[href]').forEach(a => {
                const href = (a as HTMLAnchorElement).href;
                const text = a.textContent || href;
                if (href.startsWith('http') && !seenUrls.has(href)) {
                    seenUrls.add(href);
                    urls.push({ url: href, title: text });
                }
            });

            // 2. 从工具结果中提取（search_web等）
            msgEl.querySelectorAll('.tool').forEach((toolEl, toolIndex) => {
                const rawResponse = (toolEl as HTMLElement).dataset.rawResponse;
                const toolName = (toolEl as HTMLElement).querySelector('.tool__name')?.textContent;
                
                if (!rawResponse) {
                    console.log(`[Browser] Msg ${msgIndex} Tool ${toolIndex} (${toolName}): No rawResponse`);
                    return;
                }

                try {
                    const resp = JSON.parse(rawResponse);
                    // 解析 search_web 结果
                    let data = resp;
                    // 如果 result 是字符串（可能是二次序列化的JSON），尝试解析它
                    if (typeof resp.result === 'string') {
                        try {
                            data = JSON.parse(resp.result);
                        } catch (e) {
                            // 如果 result 只是普通字符串而不是JSON，就保留原样
                            // console.log('[Browser] result is string but not JSON');
                        }
                    }
                    
                    if (data.results && Array.isArray(data.results)) {
                        console.log(`[Browser] Found search results in tool ${toolName}:`, data.results.length);
                        data.results.forEach((r: any) => {
                            if (r.url && !seenUrls.has(r.url)) {
                                seenUrls.add(r.url);
                                urls.push({ url: r.url, title: r.title || r.url });
                            }
                        });
                    } else if (data.url) {
                        // 解析 load_url_content 结果
                        console.log(`[Browser] Found single URL in tool ${toolName}:`, data.url);
                        if (!seenUrls.has(data.url)) {
                            seenUrls.add(data.url);
                            urls.push({ url: data.url, title: data.title || data.url });
                        }
                    } else {
                         // 尝试直接在 resp 中查找 (防止结构差异)
                         if (resp.results && Array.isArray(resp.results)) {
                            console.log(`[Browser] Found search results in root resp:`, resp.results.length);
                             resp.results.forEach((r: any) => {
                                if (r.url && !seenUrls.has(r.url)) {
                                    seenUrls.add(r.url);
                                    urls.push({ url: r.url, title: r.title || r.url });
                                }
                            });
                         }
                    }
                } catch (e) {
                    console.warn('[Browser] Error parsing rawResponse:', e);
                }
            });
        });

        console.log(`[Browser] Total URLs found: ${urls.length}`);
        urls.reverse(); // 倒序显示，最新的在上面
        this.renderUrlList(urls);
    }

    /**
     * 渲染URL列表
     */
    private static renderUrlList(urls: UrlEntry[]) {
        this.urlListContainer.innerHTML = '';

        if (this.urlCountEl) {
            this.urlCountEl.textContent = `${urls.length}`;
        }

        if (urls.length === 0) {
            if (this.emptyState) {
                this.urlListContainer.appendChild(this.emptyState.cloneNode(true));
            }
            return;
        }

        urls.forEach((entry, index) => {
            const el = this.createUrlElement(entry, index + 1);
            this.urlListContainer.appendChild(el);
        });
    }

    /**
     * 创建单个URL条目元素
     */
    private static createUrlElement(entry: UrlEntry, index: number): HTMLElement {
        const el = document.createElement('div');
        el.className = 'browser-result';
        el.dataset.url = entry.url;

        el.innerHTML = `
            <div class="browser-result__content">
                <span class="browser-result__index">${index}</span>
                <span class="browser-result__separator">-</span>
                <div class="browser-result__text">
                    <div class="browser-result__title">${escapeHtml(entry.title)}</div>
                    <div class="browser-result__url">${escapeHtml(entry.url)}</div>
                </div>
                <button class="browser-result__copy-btn" title="复制链接">CP</button>
            </div>
        `;

        // 点击整个区域打开URL
        el.addEventListener('click', (e) => {
            // 如果点击的是复制按钮，不触发打开URL
            if ((e.target as HTMLElement).classList.contains('browser-result__copy-btn')) {
                return;
            }
            this.openUrl(entry);
        });

        // 复制按钮点击事件
        const copyBtn = el.querySelector('.browser-result__copy-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', (e) => {
                e.stopPropagation(); // 阻止事件冒泡，不触发打开URL
                navigator.clipboard.writeText(entry.url).then(() => {
                    const originalText = copyBtn.textContent;
                    copyBtn.textContent = 'OK';
                    setTimeout(() => {
                        copyBtn.textContent = originalText;
                    }, 1500);
                }).catch(err => {
                    console.error('复制失败:', err);
                });
            });
        }

        return el;
    }

    private static openUrl(entry: UrlEntry) {
        if (this.detailTitle) {
            this.detailTitle.textContent = entry.title;
        }
        this.navigate(entry.url);
        if (this.mainView) this.mainView.style.display = 'none';
        if (this.detailView) this.detailView.style.display = 'flex';
    }

    private static showMainView() {
        if (this.detailView) this.detailView.style.display = 'none';
        if (this.mainView) this.mainView.style.display = 'flex';
    }

    private static navigate(url?: string) {
        let target = url || this.input?.value.trim();
        if (!target) return;

        if (!target.startsWith('http://') && !target.startsWith('https://')) {
            target = 'https://' + target;
        }

        if (this.input) this.input.value = target;
        if (this.iframe) this.iframe.src = target;
    }

    private static openInExternalBrowser() {
        const url = this.input?.value.trim();
        if (!url) return;
        window.open(url, '_blank');
    }
}
