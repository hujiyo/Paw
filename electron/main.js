const { app, BrowserWindow, ipcMain, dialog, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// Python 进程管理
let pythonProcess = null;
let mainWindow = null;

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

    // 优先使用项目本地虚拟环境
    const venvPython = path.join(appRoot, 'paw_env', 'Scripts', 'python.exe');
    if (fs.existsSync(venvPython)) {
        return venvPython;
    }

    // Windows: python.exe, Unix: python3
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

// 启动 Python 后端
async function startPythonBackend() {
    const appRoot = getAppRoot();
    const pythonPath = getPythonPath();
    const pawEntry = getPawEntryPath();

    // 调试信息
    console.log('=== Paw 启动信息 ===');
    console.log(`isDevMode: ${isDevMode()}`);
    console.log(`__dirname: ${__dirname}`);
    console.log(`appRoot: ${appRoot}`);
    console.log(`paw.py 存在: ${fs.existsSync(path.join(appRoot, 'paw.py'))}`);
    console.log(`Python 路径: ${pythonPath}`);
    console.log(`Paw 入口: ${pawEntry}`);
    console.log('=====================');

    if (!pawEntry) {
        const potentialPath = path.join(appRoot, 'paw.py');
        throw new Error(`Paw 入口文件未找到\n期望路径: ${potentialPath}\nappRoot: ${appRoot}`);
    }

    // 设置环境变量
    const env = {
        ...process.env,
        PAW_HOME: appRoot,
        PAW_ELECTRON_MODE: '1',
        PYTHONUNBUFFERED: '1'
    };

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
        if (mainWindow) {
            mainWindow.webContents.send('python-error', { message: error.message });
        }
    });

    pythonProcess.on('exit', (code, signal) => {
        console.log(`[Paw] 进程退出，代码: ${code}, 信号: ${signal}`);
        pythonProcess = null;
        if (mainWindow) {
            mainWindow.webContents.send('python-exit', { code, signal });
        }
    });

    // 等待服务器启动
    await waitForServer();
}

// 等待 Web 服务器就绪
function waitForServer() {
    return new Promise((resolve) => {
        const maxAttempts = 60;
        let attempts = 0;

        const checkServer = () => {
            attempts++;
            if (attempts >= maxAttempts) {
                console.error('[Paw] 服务器启动超时');
                resolve(false);
                return;
            }

            const net = require('net');
            const socket = new net.Socket();

            socket.connect(8080, '127.0.0.1', () => {
                socket.destroy();
                console.log('[Paw] 服务器已就绪');
                resolve(true);
            });

            socket.on('error', () => {
                setTimeout(checkServer, 1000);
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

// 创建主窗口
function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1200,
        height: 800,
        minWidth: 800,
        minHeight: 600,
        title: 'Paw - AI Terminal Agent',
        icon: getIconPath(),  // 设置图标
        backgroundColor: '#000000',
        show: false,
        autoHideMenuBar: true,  // 隐藏菜单栏（按 Alt 可临时显示）
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false,
            webSecurity: true
        }
    });

    mainWindow.once('ready-to-show', () => {
        mainWindow.show();
        if (isDevMode()) {
            mainWindow.webContents.openDevTools();
        }
    });

    mainWindow.loadURL('http://127.0.0.1:8080');

    mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
        if (errorCode === -102) {
            console.log('[Electron] 等待 Paw 服务器启动...');
            setTimeout(() => {
                mainWindow.loadURL('http://127.0.0.1:8080');
            }, 3000);
        }
    });

    mainWindow.webContents.setWindowOpenHandler(({ url }) => {
        shell.openExternal(url);
        return { action: 'deny' };
    });

    mainWindow.on('closed', () => {
        mainWindow = null;
    });
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

    ipcMain.handle('restart-backend', async () => {
        stopPythonBackend();
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

    try {
        await startPythonBackend();
        createWindow();
    } catch (error) {
        console.error('启动失败:', error);
        dialog.showErrorBox('启动失败', `无法启动 Paw 后端: ${error.message}`);
        app.quit();
    }
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
