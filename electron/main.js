import { app, BrowserWindow } from 'electron';
import path from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow;
let workerProcess;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // In development, load from Vite dev server
  if (process.env.NODE_ENV !== 'production') {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    // In production, load the built files
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function startWorker() {
  const backendPath = path.join(__dirname, '../backend');
  const workerScript = path.join(backendPath, 'worker.py');
  const venvPython = path.join(backendPath, 'venv', 'Scripts', 'python.exe');
  
  console.log('Starting worker process...');
  console.log('Worker script:', workerScript);
  console.log('Python executable:', venvPython);
  
  // Start the worker process
  workerProcess = spawn(venvPython, [workerScript], {
    cwd: backendPath,
    stdio: ['ignore', 'pipe', 'pipe']
  });
  
  // Log worker output
  workerProcess.stdout.on('data', (data) => {
    console.log(`[Worker] ${data.toString().trim()}`);
  });
  
  workerProcess.stderr.on('data', (data) => {
    console.error(`[Worker Error] ${data.toString().trim()}`);
  });
  
  workerProcess.on('close', (code) => {
    console.log(`Worker process exited with code ${code}`);
    workerProcess = null;
  });
  
  workerProcess.on('error', (err) => {
    console.error('Failed to start worker process:', err);
  });
}

function stopWorker() {
  if (workerProcess) {
    console.log('Stopping worker process...');
    workerProcess.kill('SIGTERM');
    workerProcess = null;
  }
}

app.whenReady().then(() => {
  createWindow();
  startWorker();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  stopWorker();
});

app.on('will-quit', () => {
  stopWorker();
});
