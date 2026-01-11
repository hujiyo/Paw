// 通用工具函数

export const $ = <T extends Element = Element>(selector: string): T | null => 
    document.querySelector<T>(selector);

export const $$ = <T extends Element = Element>(selector: string): NodeListOf<T> => 
    document.querySelectorAll<T>(selector);

export function escapeHtml(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export function scrollToBottom(element: HTMLElement | null): void {
    if (element) {
        element.scrollTop = element.scrollHeight;
    }
}

// 初始化 Markdown 配置
export function initMarkdown(): void {
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            highlight: (code: string, lang: string): string => {
                if (typeof hljs === 'undefined') return code;
                try {
                    if (lang && hljs.getLanguage(lang)) {
                        return hljs.highlight(code, { language: lang }).value;
                    }
                    return hljs.highlightAuto(code).value;
                } catch (e) {
                    return code;
                }
            },
            langPrefix: 'hljs language-', 
            gfm: true, 
            breaks: true
        });
    }
}
