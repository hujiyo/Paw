// 通用工具函数

export const $ = s => document.querySelector(s);
export const $$ = s => document.querySelectorAll(s);

export function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

export function scrollToBottom(element) {
    if (element) {
        element.scrollTop = element.scrollHeight;
    }
}

// 初始化 Markdown 配置
export function initMarkdown() {
    if (typeof marked !== 'undefined') {
        marked.setOptions({
            highlight: (code, lang) => {
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
