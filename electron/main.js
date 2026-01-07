const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const yaml = require('js-yaml');

// Python 进程管理
let pythonProcess = null;
let mainWindow = null;
let isServerReady = false;

// 获取项目根目录（开发环境自动检测）
function getAppRoot() {
    // 首先尝试：从 electron 文件夹向上找 paw.py
    const fromElectronDir = path.resolve(path.join(__dirname, '..'));
    if (fs.existsSync(path.join(fromElectronDir, 'paw.py'))) {
        return fromElectronDir;
    }

    // 其次尝试：生产环境 extraResources
    if (process.resourcesPath) {
        const pawCorePath = path.join(process.resourcesPath, 'paw-core');
        if (fs.existsSync(path.join(pawCorePath, 'paw.py'))) {
            return pawCorePath;
        }
    }

    // 最后：使用 userData
    const userDataPath = path.join(app.getPath('userData'), 'paw-core');
    return userDataPath;
}

// 检测是否为开发环境
function isDevMode() {
    // 检查命令行参数
    if (process.argv.includes('--dev')) return true;
    // 检查环境变量
    if (process.env.NODE_ENV === 'development') return true;
    // 检查是否从 electron 文件夹运行
    if (__dirname.includes('electron') && !app.isPackaged) return true;
    return false;
}

// 获取 Python 可执行文件路径
function getPythonPath() {
    const appRoot = getAppRoot();

    // 优先方案1: 生产环境中的打包虚拟环境（最可靠）
    const prodVenvPython = path.join(process.resourcesPath, 'paw_env', 'Scripts', 'python.exe');
    if (fs.existsSync(prodVenvPython)) {
        console.log('[Paw] 使用打包的虚拟环境 Python');
        return prodVenvPython;
    }

    // 优先方案2: 开发模式的本地虚拟环境
    const venvPython = path.join(appRoot, 'paw_env', 'Scripts', 'python.exe');
    if (fs.existsSync(venvPython)) {
        console.log('[Paw] 使用本地虚拟环境 Python');
        return venvPython;
    }

    // 最后回退: 系统 Python（可能缺少依赖！）
    console.warn('[Paw] 警告: 使用系统 Python，可能缺少依赖！');
    return process.platform === 'win32' ? 'python.exe' : 'python3';
}

// 获取 Paw 入口文件路径
function getPawEntryPath() {
    const appRoot = getAppRoot();
    const pawEntry = path.join(appRoot, 'paw.py');
    if (fs.existsSync(pawEntry)) {
        return pawEntry;
    }
    return null;
}

// 发送状态到加载页面
function sendStatus(status) {
    if (mainWindow && mainWindow.webContents) {
        mainWindow.webContents.send('startup-status', status);
    }
}

// 发送错误到加载页面
function sendError(error) {
    if (mainWindow && mainWindow.webContents) {
        mainWindow.webContents.send('startup-error', error);
    }
}

// 启动 Python 后端（异步，不阻塞窗口显示）
async function startPythonBackend() {
    const appRoot = getAppRoot();
    const pythonPath = getPythonPath();
    const pawEntry = getPawEntryPath();

    // 调试信息
    console.log('=== Paw 启动信息 ===');
    console.log(`isDevMode: ${isDevMode()}`);
    console.log(`__dirname: ${__dirname}`);
    console.log(`appRoot: ${appRoot}`);
    console.log(`Python 路径: ${pythonPath}`);
    console.log(`Paw 入口: ${pawEntry}`);
    console.log('=====================');

    if (!pawEntry) {
        const potentialPath = path.join(appRoot, 'paw.py');
        const errorMsg = `Paw 入口文件未找到\n期望路径: ${potentialPath}\nappRoot: ${appRoot}`;
        console.error('[Paw]', errorMsg);
        sendError(errorMsg);
        throw new Error(errorMsg);
    }

    // 设置环境变量
    const env = {
        ...process.env,
        PAW_HOME: appRoot,
        PAW_ELECTRON_MODE: '1',
        PYTHONUNBUFFERED: '1'
    };

    sendStatus('正在启动 Python 后端...');

    // 启动 Python 进程
    pythonProcess = spawn(pythonPath, [pawEntry], {
        cwd: appRoot,
        env: env,
        stdio: ['ignore', 'pipe', 'pipe']
    });

    // 监听 Python 输出
    pythonProcess.stdout.on('data', (data) => {
        const msg = data.toString().trim();
        console.log('[Paw]', msg);
        if (mainWindow && mainWindow.webContents) {
            mainWindow.webContents.send('python-log', { type: 'stdout', message: msg });
        }
        // 检测 Uvicorn 启动成功消息
        if (msg.includes('Uvicorn running') || msg.includes('Application startup complete')) {
            onServerReady();
        }
    });

    pythonProcess.stderr.on('data', (data) => {
        const msg = data.toString().trim();
        console.error('[Paw Error]', msg);
        if (mainWindow && mainWindow.webContents) {
            mainWindow.webContents.send('python-log', { type: 'stderr', message: msg });
        }
    });

    pythonProcess.on('error', (error) => {
        console.error('[Paw] 进程错误:', error);
        sendError(`Python 进程启动失败: ${error.message}`);
        if (mainWindow) {
            mainWindow.webContents.send('python-error', { message: error.message });
        }
    });

    pythonProcess.on('exit', (code, signal) => {
        console.log(`[Paw] 进程退出，代码: ${code}, 信号: ${signal}`);
        pythonProcess = null;
        isServerReady = false;
        if (mainWindow) {
            mainWindow.webContents.send('python-exit', { code, signal });
        }
    });

    // 等待服务器启动（带超时和进度反馈）
    sendStatus('等待服务器就绪...');
    await waitForServer();
}

// 服务器就绪回调
function onServerReady() {
    if (isServerReady) return; // 避免重复触发

    isServerReady = true;
    console.log('[Paw] 服务器已就绪');

    sendStatus('正在加载应用...');

    // 切换到实际应用
    if (mainWindow && mainWindow.webContents) {
        setTimeout(() => {
            mainWindow.loadURL('http://127.0.0.1:8080');
        }, 500);
    }
}

// 等待 Web 服务器就绪
function waitForServer() {
    return new Promise((resolve) => {
        let attempts = 0;

        const checkServer = () => {
            // 如果已经就绪，直接返回
            if (isServerReady) {
                resolve(true);
                return;
            }

            attempts++;

            // 更新进度（但不发送错误，让 loading 页面自己处理超时）
            if (attempts <= 60) { // 最多显示 60 次进度
                sendStatus(`正在启动... ${attempts}`);
            }

            const net = require('net');
            const socket = new net.Socket();

            socket.setTimeout(2000);

            socket.connect(8080, '127.0.0.1', () => {
                socket.destroy();
                onServerReady();
                resolve(true);
            });

            socket.on('timeout', () => {
                socket.destroy();
                setTimeout(checkServer, 500);
            });

            socket.on('error', () => {
                setTimeout(checkServer, 500);
            });
        };

        checkServer();
    });
}

// 停止 Python 后端
function stopPythonBackend() {
    if (pythonProcess) {
        console.log('[Paw] 正在停止后端...');
        pythonProcess.kill('SIGTERM');
        setTimeout(() => {
            if (pythonProcess && !pythonProcess.killed) {
                pythonProcess.kill('SIGKILL');
            }
        }, 5000);
        pythonProcess = null;
    }
    isServerReady = false;
}

// 获取图标路径
function getIconPath() {
    const iconFile = process.platform === 'win32' ? 'icon.ico' :
                     process.platform === 'darwin' ? 'icon.icns' : 'icon.png';

    // 开发环境：从 electron/resources 加载
    const devIcon = path.join(__dirname, 'resources', iconFile);
    if (fs.existsSync(devIcon)) {
        return devIcon;
    }

    // 生产环境：从 resources 加载
    const prodIcon = path.join(process.resourcesPath, 'resources', iconFile);
    if (fs.existsSync(prodIcon)) {
        return prodIcon;
    }

    return undefined;
}

// 获取主题颜色配置
function getThemeColors() {
    const appRoot = getAppRoot();
    const configPath = path.join(appRoot, 'config.yaml');

    try {
        if (fs.existsSync(configPath)) {
            const configContent = fs.readFileSync(configPath, 'utf8');
            const config = yaml.load(configContent);
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

    // 默认颜色
    return {
        titlebar: '#000000',
        loading: '#000000',
        main: '#000000'
    };
}

// 获取加载页面路径
function getLoadingPagePath() {
    const appRoot = getAppRoot();

    // 开发环境：从项目 templates 目录加载
    const devLoading = path.join(appRoot, 'templates', 'loading.html');
    if (fs.existsSync(devLoading)) {
        return devLoading;
    }

    // 生产环境：从 paw-core/templates 加载
    const prodLoading = path.join(appRoot, 'templates', 'loading.html');
    if (fs.existsSync(prodLoading)) {
        return prodLoading;
    }

    return null;
}

// 创建主窗口
function createWindow() {
    const themeColors = getThemeColors();

    mainWindow = new BrowserWindow({
        width: 1400,
        height: 800,
        minWidth: 1000,
        minHeight: 600,
        title: 'Paw - AI Desktop Agent',
        icon: getIconPath(),
        backgroundColor: themeColors.titlebar,
        frame: true, // 保留系统标题栏
        titleBarStyle: 'default', // Windows 使用默认样式
        show: true,
        autoHideMenuBar: true,
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            webSecurity: true
        }
    });

    // 先加载加载页面
    const loadingPage = getLoadingPagePath();
    if (loadingPage) {
        mainWindow.loadFile(loadingPage);
    } else {
        // 如果没有加载页面，直接加载应用
        mainWindow.loadURL('http://127.0.0.1:8080');
    }

    // 开发模式按 F12 打开 DevTools
    // mainWindow.webContents.openDevTools();

    // 处理页面加载失败（用于重试连接）
    mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
        if (errorCode === -102 || errorCode === -2) { // 连接被拒绝或未找到
            console.log('[Electron] 等待 Paw 服务器启动...');
            // 不做任何事，等待 onServerReady 切换 URL
        }
    });

    // 处理新窗口打开
    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });

    // Windows: 尝试设置标题栏颜色
    if (process.platform === 'win32') {
        mainWindow.setBackgroundColor(themeColors.titlebar);
        // 尝试使用 Windows 11 的 DWM 属性
        const { nativeTheme } = require('electron');

        // 根据标题栏颜色亮度决定主题
        const r = parseInt(themeColors.titlebar.slice(1, 3), 16);
        const g = parseInt(themeColors.titlebar.slice(3, 5), 16);
        const b = parseInt(themeColors.titlebar.slice(5, 7), 16);
        const brightness = (r * 299 + g * 587 + b * 114) / 1000;

        nativeTheme.themeSource = brightness > 128 ? 'light' : 'dark';
    }
}

// IPC 处理程序
function setupIpcHandlers() {
    ipcMain.handle('get-app-info', () => {
        return {
            version: app.getVersion(),
            platform: process.platform,
            arch: process.arch,
            isDev: isDevMode(),
            appRoot: getAppRoot(),
            pythonPath: getPythonPath()
        };
    });

    ipcMain.handle('get-theme-colors', () => {
        return getThemeColors();
    });

    ipcMain.handle('restart-backend', async () => {
        stopPythonBackend();
        isServerReady = false;
        // 重新显示加载页面
        const loadingPage = getLoadingPagePath();
        if (loadingPage && mainWindow) {
            mainWindow.loadFile(loadingPage);
        }
        await startPythonBackend();
        return { success: true };
    });

    ipcMain.handle('show-message-box', async (event, options) => {
        return await dialog.showMessageBox(mainWindow, options);
    });

    ipcMain.handle('show-open-dialog', async (event, options) => {
        return await dialog.showOpenDialog(mainWindow, options);
    });

    ipcMain.handle('show-save-dialog', async (event, options) => {
        return await dialog.showSaveDialog(mainWindow, options);
    });

    ipcMain.handle('open-external', async (event, url) => {
        await shell.openExternal(url);
        return { success: true };
    });

    ipcMain.handle('show-item-in-folder', async (event, fullPath) => {
        shell.showItemInFolder(fullPath);
        return { success: true };
    });
}

// 应用生命周期
app.whenReady().then(async () => {
    setupIpcHandlers();

    // 立即创建窗口（不等待 Python）
    createWindow();

    // 在后台启动 Python（不设超时，让 loading 页面自己处理）
    startPythonBackend().catch(error => {
        console.error('启动失败:', error);
        // 只有真正的错误才发送，超时不发送
        if (!error.message.includes('超时')) {
            sendError(error.message);
        }
    });
});

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

app.on('before-quit', () => {
    stopPythonBackend();
});

app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
    }
});

process.on('uncaughtException', (error) => {
    console.error('未捕获的异常:', error);
});
