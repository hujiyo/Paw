// 把前端的第三方运行库从 node_modules 复制到 resources/static/vendor。
//
// 这些文件不提交到仓库：体积大、内容完全由 package.json 锁定版本决定。
// 每次 compile 前自动执行，保证本地与打包产物引用的是同一份。

const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const outDir = path.join(root, 'resources', 'static', 'vendor');

/** @type {Array<{from: string, to: string}>} */
const assets = [
    { from: 'node_modules/marked/marked.min.js', to: 'marked.min.js' },
    { from: 'node_modules/dompurify/dist/purify.min.js', to: 'purify.min.js' },
    { from: 'node_modules/highlight.js/lib/common.js', to: 'highlight-common.js' },
    { from: 'node_modules/highlight.js/styles/atom-one-dark.min.css', to: 'hljs-atom-one-dark.css' },
    { from: 'node_modules/monaco-editor/min/vs', to: 'monaco/vs' },
];

function copy(relFrom, relTo) {
    const src = path.join(root, relFrom);
    const dest = path.join(outDir, relTo);
    if (!fs.existsSync(src)) {
        throw new Error(`缺少依赖文件: ${relFrom}（请先执行 npm install）`);
    }
    fs.mkdirSync(path.dirname(dest), { recursive: true });
    fs.cpSync(src, dest, { recursive: true });
}

fs.mkdirSync(outDir, { recursive: true });
for (const asset of assets) {
    copy(asset.from, asset.to);
}
console.log(`[vendor] 已复制 ${assets.length} 项到 resources/static/vendor`);
