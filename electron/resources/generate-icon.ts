/**
 * Paw 图标生成器
 * 需要先安装: npm install sharp png-to-ico
 */

import * as fs from 'fs';
import * as path from 'path';

// 简单的 SVG 图标（爪印形状）
const pawSVG: string = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" fill="#1a1a2e"/>
  <g fill="#ff9e80">
    <!-- 掌心 -->
    <ellipse cx="256" cy="320" rx="80" ry="70"/>
    <!-- 上方三个趾印 -->
    <ellipse cx="256" cy="180" rx="40" ry="50"/>
    <ellipse cx="170" cy="210" rx="35" ry="45"/>
    <ellipse cx="342" cy="210" rx="35" ry="45"/>
    <!-- 下方两个小趾印 -->
    <ellipse cx="190" cy="280" rx="25" ry="35"/>
    <ellipse cx="322" cy="280" rx="25" ry="35"/>
  </g>
  <!-- 终端风格装饰 -->
  <rect x="50" y="50" width="412" height="412" fill="none" stroke="#ff9e80" stroke-width="4" rx="20"/>
  <text x="256" y="450" font-family="monospace" font-size="48" fill="#80d1ff" text-anchor="middle">PAW</text>
</svg>`;

// 如果用户提供了 PNG 文件，使用它；否则生成默认图标
const inputIcon: string | undefined = process.argv[2];

if (inputIcon) {
    console.log(`使用输入图标: ${inputIcon}`);
    console.log('请手动使用在线工具转换:');
    console.log('  - ICO: https://convertio.co/zh/png-ico/');
    console.log('  - ICNS: https://cloudconvert.com/png-to-icns');
} else {
    console.log('生成默认 Paw SVG 图标...');
    fs.writeFileSync(path.join(__dirname, 'paw-icon.svg'), pawSVG);
    console.log('已生成: electron/resources/paw-icon.svg');
    console.log('\n推荐在线转换工具:');
    console.log('  - SVG to PNG: https://cloudconvert.com/svg-to-png');
    console.log('  - PNG to ICO: https://convertio.co/zh/png-ico/');
    console.log('  - PNG to ICNS: https://cloudconvert.com/png-to-icns');
    console.log('\n或使用本地工具:');
    console.log('  npm install -g @electron/fuses');
    console.log('  electron-builder --icon');
}
