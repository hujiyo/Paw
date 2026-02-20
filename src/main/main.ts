import { app, BrowserWindow, ipcMain, dialog, shell, nativeTheme } from 'electron';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import * as fs from 'fs';
import * as yaml from 'js-yaml';
import * as net from 'net';

// ============ 类型定义 ============

interface ThemeColors {
    titlebar: string;
    loading: string;
    main: string;
}

interface ThemeConfig {
    titlebar?: string;
    loading?: string;
    main?: string;
}

interface Config {
    theme?: ThemeConfig;
}

interface AppInfo {
    version: string;
    platform: NodeJS.Platform;
    isDev: boolean;
    backendDir: string;
}

// ============ 全局状态 ============

let pythonProcess: ChildProcess | null = null;
let mainWindow: BrowserWindow | null = null;
let isServerReady: boolean = false;

// ============ 路径管理（核心逻辑，非常简单） ============

function getBackendDir(): string {
    // 开发环境: dist/main/../../src/backend
    // 生产环境: resources/backend
    if (app.isPackaged) {
        return path.join(process.resourcesPath, 'backend');
    }
    return path.join(__dirname, '..', '..', 'src', 'backend');
}

function getPythonPath(): string {
    const isWin = process.platform === 'win32';

    let venvDir: string;
    if (app.isPackaged) {
        venvDir = path.join(process.resourcesPath, 'paw_env');
    } else {
        venvDir = path.join(__dirname, '..', '..', 'paw_env');
    }

    // embeddable 包：python.exe 在根目录
    // 传统 venv：python.exe 在 Scripts/（兼容旧环境）
    const candidates = isWin
        ? [path.join(venvDir, 'python.exe'), path.join(venvDir, 'Scripts', 'python.exe')]
        : [path.join(venvDir, 'bin', 'python3'), path.join(venvDir, 'python3')];

    for (const p of candidates) {
        if (fs.existsSync(p)) return p;
    }

    // 返回首选路径，让后续存在性检查捕获错误并上报
    console.error(`[Paw] paw_env 未找到，已尝试: ${candidates.join(', ')}`);
    return candidates[0];
}

function getConfigPath(): string {
    return path.join(getBackendDir(), 'config.yaml');
}

function getLoadingPagePath(): string {
    if (app.isPackaged) {
        return path.join(process.resourcesPath, 'templates', 'loading.html');
    }
    return path.join(__dirname, '..', '..', 'resources', 'templates', 'loading.html');
}

function getIconPath(): string {
    const iconFile = process.platform === 'win32' ? 'icon.ico' :
                     process.platform === 'darwin' ? 'icon.icns' : 'icon.png';
    if (app.isPackaged) {
        return path.join(process.resourcesPath, 'icons', iconFile);
    }
    return path.join(__dirname, '..', '..', 'resources', 'icons', iconFile);
}

// ============ 配置读取 ============

function getThemeColors(): ThemeColors {
    try {
        const configPath = getConfigPath();
        if (fs.existsSync(configPath)) {
            const config = yaml.load(fs.readFileSync(configPath, 'utf8')) as Config;
            const theme = config.theme || {};
            return {
                titlebar: theme.titlebar || '#000000',
                loading: theme.loading || '#000000',
                main: theme.main || '#000000'
            };
        }
    } catch (e) {
        const error = e as Error;
        console.warn('[Paw] 读取主题配置失败:', error.message);
    }
    return { titlebar: '#000000', loading: '#000000', main: '#000000' };
}

// ============ Python 后端管理 ============

function sendStatus(status: string): void {
    if (mainWindow?.webContents) {
        mainWindow.webContents.send('startup-status', status);
    }
}

function sendError(error: string): void {
    if (mainWindow?.webContents) {
        mainWindow.webContents.send('startup-error', error);
    }
}

async function startPythonBackend(): Promise<void> {
    const backendDir = getBackendDir();
    const pythonPath = getPythonPath();
    const pawEntry = path.join(backendDir, 'paw.py');

    const pythonExists = fs.existsSync(pythonPath);
    const pawExists = fs.existsSync(pawEntry);

    console.log('=== Paw 启动信息 ===');
    console.log('isPackaged:', app.isPackaged);
    console.log('backendDir:', backendDir);
    console.log('pythonPath:', pythonPath);
    console.log('pawEntry:', pawEntry);
    console.log('Python存在:', pythonExists);
    console.log('paw.py存在:', pawExists);
    console.log('====================');

    // 写入日志（生产环境）
    if (app.isPackaged) {
        const logPath = path.join(app.getPath('userData'), 'paw-startup.log');
        fs.writeFileSync(logPath, `=== Paw 启动日志 ===
时间: ${new Date().toISOString()}
backendDir: ${backendDir}
pythonPath: ${pythonPath}
pawEntry: ${pawEntry}
Python存在: ${pythonExists}
paw.py存在: ${pawExists}
====================
`);
    }

    if (!pythonExists) {
        const err = `Python 环境未找到: ${pythonPath}\n\n请确认安装包中包含完整的 paw_env 目录`;
        sendError(err);
        throw new Error(err);
    }

    if (!pawExists) {
        const err = `未找到 paw.py: ${pawEntry}`;
        sendError(err);
        throw new Error(err);
    }

    sendStatus('正在启动 Python 后端...');

    // 计算静态资源路径
    const rendererDir = app.isPackaged
        ? path.join(process.resourcesPath, 'renderer')
        : path.join(__dirname, '..', 'renderer');

    const staticDir = app.isPackaged
        ? path.join(process.resourcesPath, 'static')
        : path.join(__dirname, '..', '..', 'resources', 'static');

    const env = {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8',
        PAW_RENDERER_DIR: rendererDir,
        PAW_STATIC_DIR: staticDir
    };

    // 用 -c 注入 sys.path，兼容 embeddable Python（不读 PYTHONPATH）
    // 同时设置 __file__ 和 __spec__，让 exec 里的代码行为与直接运行脚本一致
    const bootstrap = `import sys; sys.path.insert(0, r'${backendDir}'); __file__ = r'${pawEntry}'; __spec__ = None; exec(open(r'${pawEntry}', encoding='utf-8').read())`;
    pythonProcess = spawn(pythonPath, ['-c', bootstrap], {
        cwd: backendDir,
        env: env,
        stdio: ['ignore', 'pipe', 'pipe']
    });

    // 日志文件（生产环境）
    const runtimeLogPath = app.isPackaged 
        ? path.join(app.getPath('userData'), 'paw-runtime.log')
        : null;
    
    if (runtimeLogPath) {
        fs.writeFileSync(runtimeLogPath, `=== 运行日志 ${new Date().toISOString()} ===\n`);
    }

    pythonProcess.stdout?.on('data', (data: Buffer) => {
        const msg = data.toString().trim();
        console.log('[Python]', msg);
        if (runtimeLogPath) fs.appendFileSync(runtimeLogPath, `[stdout] ${msg}\n`);
        
        if (msg.includes('Uvicorn running') || msg.includes('Application startup complete')) {
            onServerReady();
        }
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
        const msg = data.toString().trim();
        console.error('[Python Error]', msg);
        if (runtimeLogPath) fs.appendFileSync(runtimeLogPath, `[stderr] ${msg}\n`);
        
        // Uvicorn 有时输出到 stderr
        if (msg.includes('Uvicorn running') || msg.includes('Started server process')) {
            onServerReady();
        }
    });

    pythonProcess.on('error', (error: Error) => {
        console.error('[Paw] 进程错误:', error);
        sendError(`Python 启动失败: ${error.message}`);
    });

    pythonProcess.on('exit', (code: number | null) => {
        console.log('[Paw] Python 退出, code:', code);
        pythonProcess = null;
        if (!isServerReady && code !== 0) {
            const err = `Python 后端异常退出（退出码: ${code}），请检查日志文件获取详细信息`;
            sendError(err);
        }
        isServerReady = false;
    });

    await waitForServer();
}

function onServerReady(): void {
    if (isServerReady) return;
    isServerReady = true;
    console.log('[Paw] 服务器就绪');
    sendStatus('正在加载应用...');
    
    setTimeout(() => {
        if (mainWindow) {
            mainWindow.loadURL('http://127.0.0.1:8081');
        }
    }, 300);
}

function waitForServer(timeoutMs: number = 60000): Promise<void> {
    return new Promise((resolve, reject) => {
        const deadline = Date.now() + timeoutMs;

        const check = (): void => {
            if (isServerReady) { resolve(); return; }

            if (Date.now() > deadline) {
                const err = `后端启动超时（${timeoutMs / 1000}秒内未就绪），请检查 Python 环境是否完整`;
                sendError(err);
                reject(new Error(err));
                return;
            }

            const socket = new net.Socket();
            socket.setTimeout(1000);

            socket.connect(8081, '127.0.0.1', () => {
                socket.destroy();
                onServerReady();
                resolve();
            });

            socket.on('error', () => setTimeout(check, 500));
            socket.on('timeout', () => { socket.destroy(); setTimeout(check, 500); });
        };
        check();
    });
}

function stopPythonBackend(): void {
    if (pythonProcess) {
        pythonProcess.kill('SIGTERM');
        setTimeout(() => {
            if (pythonProcess && !pythonProcess.killed) {
                pythonProcess.kill('SIGKILL');
            }
        }, 3000);
        pythonProcess = null;
    }
    isServerReady = false;
}

// ============ 窗口创建 ============

function createWindow(): void {
    const themeColors = getThemeColors();
    
    // 根据标题栏颜色亮度设置系统主题（影响 Windows 标题栏颜色）
    const titlebarColor = themeColors.titlebar;
    const r = parseInt(titlebarColor.slice(1, 3), 16);
    const g = parseInt(titlebarColor.slice(3, 5), 16);
    const b = parseInt(titlebarColor.slice(5, 7), 16);
    const brightness = (r * 299 + g * 587 + b * 114) / 1000;
    nativeTheme.themeSource = brightness > 128 ? 'light' : 'dark';

    mainWindow = new BrowserWindow({
        width: 1400,
        height: 800,
        minWidth: 1000,
        minHeight: 600,
        title: 'Paw',
        icon: getIconPath(),
        backgroundColor: themeColors.titlebar,
        show: true,
        autoHideMenuBar: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });

    const loadingPage = getLoadingPagePath();
    if (fs.existsSync(loadingPage)) {
        mainWindow.loadFile(loadingPage);
    } else {
        mainWindow.loadURL('http://127.0.0.1:8081');
    }

    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    // F12 打开 DevTools
    mainWindow.webContents.on('before-input-event', (event, input) => {
        if (input.key === 'F12') {
            mainWindow?.webContents.toggleDevTools();
        }
    });

    mainWindow.on('closed', () => { mainWindow = null; });
}

// ============ IPC 处理 ============

function setupIpcHandlers(): void {
    ipcMain.handle('get-app-info', (): AppInfo => ({
        version: app.getVersion(),
        platform: process.platform,
        isDev: !app.isPackaged,
        backendDir: getBackendDir()
    }));

    ipcMain.handle('get-theme-colors', (): ThemeColors => getThemeColors());

    ipcMain.handle('restart-backend', async (): Promise<{ success: boolean }> => {
        stopPythonBackend();
        const loadingPage = getLoadingPagePath();
        if (mainWindow && fs.existsSync(loadingPage)) {
            mainWindow.loadFile(loadingPage);
        }
        await startPythonBackend();
        return { success: true };
    });

    ipcMain.handle('open-external', (_, url: string): Promise<void> => shell.openExternal(url));
    ipcMain.handle('show-item-in-folder', (_, p: string): void => shell.showItemInFolder(p));
    ipcMain.handle('open-log-folder', (): { success: boolean } => {
        shell.openPath(app.getPath('userData'));
        return { success: true };
    });
    
    // 文件夹选择对话框
    ipcMain.handle('select-folder', async (): Promise<string | null> => {
        if (!mainWindow) return null;
        
        const result = await dialog.showOpenDialog(mainWindow, {
            properties: ['openDirectory', 'createDirectory'],
            title: '选择工作目录',
            buttonLabel: '选择',
            defaultPath: app.getPath('home')
        });
        
        if (result.canceled || result.filePaths.length === 0) {
            return null;
        }
        
        return result.filePaths[0];
    });
}

// ============ 应用生命周期 ============

app.whenReady().then(async () => {
    setupIpcHandlers();
    createWindow();
    startPythonBackend().catch(e => {
        console.error('启动失败:', e);
        sendError((e as Error).message);
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => stopPythonBackend());

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
