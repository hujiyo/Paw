const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const yaml = require('js-yaml');

let pythonProcess = null;
let mainWindow = null;
let isServerReady = false;

// ============ 路径管理（核心逻辑，非常简单） ============

function getCoreDir() {
    // 开发环境: electron/../core
    // 生产环境: resources/core
    if (app.isPackaged) {
        return path.join(process.resourcesPath, 'core');
    }
    return path.join(__dirname, '..', 'core');
}

function getPythonPath() {
    const isWin = process.platform === 'win32';
    const pythonExe = isWin ? 'Scripts/python.exe' : 'bin/python3';
    
    // 开发环境: electron/../paw_env
    // 生产环境: resources/paw_env
    let venvDir;
    if (app.isPackaged) {
        venvDir = path.join(process.resourcesPath, 'paw_env');
    } else {
        venvDir = path.join(__dirname, '..', 'paw_env');
    }
    
    const pythonPath = path.join(venvDir, pythonExe);
    if (fs.existsSync(pythonPath)) {
        return pythonPath;
    }
    
    // 兜底：系统 Python
    console.warn('[Paw] 警告: 使用系统 Python');
    return isWin ? 'python.exe' : 'python3';
}

function getConfigPath() {
    return path.join(getCoreDir(), 'config.yaml');
}

function getLoadingPagePath() {
    return path.join(getCoreDir(), 'templates', 'loading.html');
}

function getIconPath() {
    const iconFile = process.platform === 'win32' ? 'icon.ico' :
                     process.platform === 'darwin' ? 'icon.icns' : 'icon.png';
    return path.join(__dirname, 'resources', iconFile);
}

// ============ 配置读取 ============

function getThemeColors() {
    try {
        const configPath = getConfigPath();
        if (fs.existsSync(configPath)) {
            const config = yaml.load(fs.readFileSync(configPath, 'utf8'));
            const theme = config.theme || {};
            return {
                titlebar: theme.titlebar || '#000000',
                loading: theme.loading || '#000000',
                main: theme.main || '#000000'
            };
        }
    } catch (e) {
        console.warn('[Paw] 读取主题配置失败:', e.message);
    }
    return { titlebar: '#000000', loading: '#000000', main: '#000000' };
}

// ============ Python 后端管理 ============

function sendStatus(status) {
    if (mainWindow?.webContents) {
        mainWindow.webContents.send('startup-status', status);
    }
}

function sendError(error) {
    if (mainWindow?.webContents) {
        mainWindow.webContents.send('startup-error', error);
    }
}

async function startPythonBackend() {
    const coreDir = getCoreDir();
    const pythonPath = getPythonPath();
    const pawEntry = path.join(coreDir, 'paw.py');

    console.log('=== Paw 启动信息 ===');
    console.log('isPackaged:', app.isPackaged);
    console.log('coreDir:', coreDir);
    console.log('pythonPath:', pythonPath);
    console.log('pawEntry:', pawEntry);
    console.log('====================');

    // 写入日志（生产环境）
    if (app.isPackaged) {
        const logPath = path.join(app.getPath('userData'), 'paw-startup.log');
        fs.writeFileSync(logPath, `=== Paw 启动日志 ===
时间: ${new Date().toISOString()}
coreDir: ${coreDir}
pythonPath: ${pythonPath}
pawEntry: ${pawEntry}
Python存在: ${fs.existsSync(pythonPath)}
paw.py存在: ${fs.existsSync(pawEntry)}
====================
`);
    }

    if (!fs.existsSync(pawEntry)) {
        const err = `未找到 paw.py: ${pawEntry}`;
        sendError(err);
        throw new Error(err);
    }

    sendStatus('正在启动 Python 后端...');

    const env = {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        PYTHONIOENCODING: 'utf-8'
    };

    pythonProcess = spawn(pythonPath, [pawEntry], {
        cwd: coreDir,
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

    pythonProcess.stdout.on('data', (data) => {
        const msg = data.toString().trim();
        console.log('[Python]', msg);
        if (runtimeLogPath) fs.appendFileSync(runtimeLogPath, `[stdout] ${msg}\n`);
        
        if (msg.includes('Uvicorn running') || msg.includes('Application startup complete')) {
            onServerReady();
        }
    });

    pythonProcess.stderr.on('data', (data) => {
        const msg = data.toString().trim();
        console.error('[Python Error]', msg);
        if (runtimeLogPath) fs.appendFileSync(runtimeLogPath, `[stderr] ${msg}\n`);
        
        // Uvicorn 有时输出到 stderr
        if (msg.includes('Uvicorn running') || msg.includes('Started server process')) {
            onServerReady();
        }
    });

    pythonProcess.on('error', (error) => {
        console.error('[Paw] 进程错误:', error);
        sendError(`Python 启动失败: ${error.message}`);
    });

    pythonProcess.on('exit', (code) => {
        console.log('[Paw] Python 退出, code:', code);
        pythonProcess = null;
        isServerReady = false;
    });

    await waitForServer();
}

function onServerReady() {
    if (isServerReady) return;
    isServerReady = true;
    console.log('[Paw] 服务器就绪');
    sendStatus('正在加载应用...');
    
    setTimeout(() => {
        if (mainWindow) {
            mainWindow.loadURL('http://127.0.0.1:8080');
        }
    }, 300);
}

function waitForServer() {
    return new Promise((resolve) => {
        const check = () => {
            if (isServerReady) { resolve(); return; }
            
            const net = require('net');
            const socket = new net.Socket();
            socket.setTimeout(1000);
            
            socket.connect(8080, '127.0.0.1', () => {
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

function stopPythonBackend() {
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

function createWindow() {
    const themeColors = getThemeColors();
    
    // 根据标题栏颜色亮度设置系统主题（影响 Windows 标题栏颜色）
    const { nativeTheme } = require('electron');
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
        mainWindow.loadURL('http://127.0.0.1:8080');
    }

    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    mainWindow.on('closed', () => { mainWindow = null; });
}

// ============ IPC 处理 ============

function setupIpcHandlers() {
    ipcMain.handle('get-app-info', () => ({
        version: app.getVersion(),
        platform: process.platform,
        isDev: !app.isPackaged,
        coreDir: getCoreDir()
    }));

    ipcMain.handle('get-theme-colors', () => getThemeColors());

    ipcMain.handle('restart-backend', async () => {
        stopPythonBackend();
        const loadingPage = getLoadingPagePath();
        if (mainWindow && fs.existsSync(loadingPage)) {
            mainWindow.loadFile(loadingPage);
        }
        await startPythonBackend();
        return { success: true };
    });

    ipcMain.handle('open-external', (_, url) => shell.openExternal(url));
    ipcMain.handle('show-item-in-folder', (_, p) => shell.showItemInFolder(p));
    ipcMain.handle('open-log-folder', () => {
        shell.openPath(app.getPath('userData'));
        return { success: true };
    });
}

// ============ 应用生命周期 ============

app.whenReady().then(async () => {
    setupIpcHandlers();
    createWindow();
    startPythonBackend().catch(e => {
        console.error('启动失败:', e);
        sendError(e.message);
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});

app.on('before-quit', () => stopPythonBackend());

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
