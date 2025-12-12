const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs-extra');
const cors = require('cors');

const app = express();
const server = http.createServer(app);
const io = new Server(server);

const PORT = 3000;
const ROOT = __dirname;
const CONFIG_PATH = path.join(ROOT, 'config.json');
const ANCHOR_DIR = path.join(ROOT, 'anchor_time');
const HISTORY_DIR = path.join(ROOT, 'historico');

app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// Ensure dirs
fs.ensureDirSync(ANCHOR_DIR);
fs.ensureDirSync(HISTORY_DIR);

// Global State
let scraperProcess = null;

// --- API ENDPOINTS ---

app.get('/api/status', (req, res) => {
    res.json({ running: !!scraperProcess, pid: scraperProcess?.pid });
});

app.post('/api/start', (req, res) => {
    if (scraperProcess) {
        return res.status(400).json({ message: 'Scraper already running' });
    }

    console.log('Starting scraper...');
    scraperProcess = spawn('node', ['scraper.js'], { cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe'] });

    scraperProcess.stdout.on('data', (data) => {
        const line = data.toString().trim();
        console.log(`[SCRAPER] ${line}`);
        io.emit('log', line);
    });

    scraperProcess.stderr.on('data', (data) => {
        const line = data.toString().trim();
        console.error(`[SCRAPER ERR] ${line}`);
        io.emit('log', `ERROR: ${line}`);
    });

    scraperProcess.on('close', (code) => {
        console.log(`Scraper exited with code ${code}`);
        io.emit('log', `Scraper exited with code ${code}`);
        io.emit('status', { running: false });
        scraperProcess = null;
    });

    io.emit('status', { running: true, pid: scraperProcess.pid });
    res.json({ message: 'Started', pid: scraperProcess.pid });
});

app.post('/api/stop', (req, res) => {
    if (scraperProcess) {
        scraperProcess.kill();
        scraperProcess = null;
        io.emit('status', { running: false });
        res.json({ message: 'Stopped' });
    } else {
        res.status(400).json({ message: 'Not running' });
    }
});

app.get('/api/config', (req, res) => {
    if (fs.existsSync(CONFIG_PATH)) {
        res.json(fs.readJsonSync(CONFIG_PATH));
    } else {
        res.json({});
    }
});

app.post('/api/config', (req, res) => {
    const newConfig = req.body;
    let current = {};
    if (fs.existsSync(CONFIG_PATH)) {
        current = fs.readJsonSync(CONFIG_PATH);
    }
    const updated = { ...current, ...newConfig };
    fs.writeJsonSync(CONFIG_PATH, updated, { spaces: 4 });
    res.json({ message: 'Saved', config: updated });
});

app.get('/api/dates', (req, res) => {
    try {
        const files = fs.readdirSync(HISTORY_DIR)
            .filter(f => f.startsWith('matches_') && f.endsWith('.csv'))
            .map(f => {
                const datePart = f.replace('matches_', '').replace('.csv', '');
                // DD-MM-YYYY -> YYYY-MM-DD for sorting
                const [d, m, y] = datePart.split('-');
                return {
                    filename: f,
                    label: datePart,
                    value: `${y}-${m}-${d}`
                };
            })
            .sort((a, b) => b.value.localeCompare(a.value));
        res.json(files);
    } catch (e) {
        res.json([]);
    }
});

app.get('/api/data', (req, res) => {
    const { filename } = req.query;
    if (!filename) return res.status(400).json({ error: 'Filename required' });
    
    const filePath = path.join(HISTORY_DIR, filename);
    if (!fs.existsSync(filePath)) return res.json([]);

    try {
        const content = fs.readFileSync(filePath, 'utf8');
        const lines = content.split('\n').filter(l => l.trim());
        if (lines.length < 2) return res.json([]);

        const headers = lines[0].split(',').map(h => h.trim());
        const data = [];

        for (let i = 1; i < lines.length; i++) {
            const vals = lines[i].split(',');
            if (vals.length === headers.length) {
                let obj = {};
                headers.forEach((h, idx) => obj[h] = vals[idx].trim());
                data.push(obj);
            }
        }
        res.json(data);
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.post('/api/anchor', (req, res) => {
    const { hour } = req.body;
    if (hour === undefined) return res.status(400).json({ error: 'Hour required' });

    try {
        const h = parseInt(hour);
        const todayStr = new Date().toISOString().split('T')[0]; // YYYY-MM-DD
        const anchorFile = path.join(ANCHOR_DIR, `anchor_time_${todayStr}.json`);
        
        // Load config to get competitions
        let comps = ["Euro Cup", "Premier League", "Sul Americano", "Copa do Mundo"];
        if (fs.existsSync(CONFIG_PATH)) {
            const cfg = fs.readJsonSync(CONFIG_PATH);
            if (cfg.COMPETITIONS) comps = cfg.COMPETITIONS;
        }

        const timeStr = `${String(h).padStart(2, '0')}.00`;
        const anchorData = {};
        comps.forEach(c => anchorData[c] = timeStr);

        fs.writeJsonSync(anchorFile, anchorData, { spaces: 4 });
        res.json({ message: `Anchor set to ${timeStr} for ${todayStr}` });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

io.on('connection', (socket) => {
    console.log('Client connected');
    socket.emit('status', { running: !!scraperProcess, pid: scraperProcess?.pid });
});

server.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
});
