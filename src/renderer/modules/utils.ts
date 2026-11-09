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

export { initMarkdown } from './markdown.js';
