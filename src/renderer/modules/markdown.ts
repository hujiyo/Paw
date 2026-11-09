// Markdown 渲染：唯一的解析入口。
//
// 模型输出、网页内容、技能文档都可能进入这里，必须消毒后再写入 DOM，
// 否则模型（或被读取的网页）可以注入脚本/事件处理器。

declare const marked: { parse(text: string): string } | undefined;
declare const DOMPurify: { sanitize(html: string, options?: Record<string, unknown>): string } | undefined;

let configured = false;

/** 只允许标记与链接，禁止脚本、表单、事件属性与 iframe。 */
const SANITIZE_OPTIONS = {
    ALLOWED_TAGS: [
        'a', 'b', 'blockquote', 'br', 'code', 'del', 'details', 'div', 'em', 'h1',
        'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'li', 'ol', 'p', 'pre', 's',
        'span', 'strong', 'summary', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul',
    ],
    ALLOWED_ATTR: ['href', 'title', 'class', 'target', 'rel'],
    FORBID_ATTR: ['style', 'onerror', 'onclick', 'onload'],
};

export function initMarkdown(): void {
    if (configured) return;
    configured = true;

    if (typeof marked !== 'undefined') {
        (marked as unknown as { setOptions(o: Record<string, unknown>): void }).setOptions({
            gfm: true,
            breaks: true,
        });
    }
}

/** 把 Markdown 渲染成可安全插入 DOM 的 HTML。 */
export function renderMarkdown(text: string): string {
    if (typeof marked === 'undefined') {
        return escapeAndWrap(text);
    }

    let html: string;
    try {
        html = marked.parse(text);
    } catch {
        return escapeAndWrap(text);
    }

    if (typeof DOMPurify !== 'undefined') {
        return DOMPurify.sanitize(html, SANITIZE_OPTIONS);
    }

    // 消毒库缺失时不做降级渲染，明确退化为纯文本，避免注入
    console.warn('[markdown] DOMPurify 不可用，退化为纯文本渲染');
    return escapeAndWrap(text);
}

function escapeAndWrap(text: string): string {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, '<br>');
}

/** 渲染完成后再做代码高亮（在已消毒的 DOM 上操作）。 */
export function highlightCode(root: HTMLElement): void {
    if (typeof hljs === 'undefined') return;
    root.querySelectorAll('code').forEach((el) => {
        const code = el as HTMLElement;
        if (code.dataset.highlighted) return;
        try {
            hljs.highlightElement(code);
            code.dataset.highlighted = '1';
        } catch {
            // 高亮失败不影响内容
        }
    });
}
