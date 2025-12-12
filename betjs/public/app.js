const socket = io();

// Elements
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const consoleOutput = document.getElementById('console-output');
const matricesContainer = document.getElementById('matrices-container');
const dateSelect = document.getElementById('date-select');

// Inputs
const inpUser = document.getElementById('cfg-username');
const inpPass = document.getElementById('cfg-password');
const inpLookback = document.getElementById('cfg-lookback');
const inpHour = document.getElementById('anchor-hour');

// State
let currentData = [];
let selectedDate = '';

// --- SOCKET EVENTS ---
socket.on('status', (data) => {
    updateStatus(data.running);
});

socket.on('log', (msg) => {
    const div = document.createElement('div');
    div.textContent = `> ${msg}`;
    consoleOutput.appendChild(div);
    consoleOutput.scrollTop = consoleOutput.scrollHeight;
});

// --- FUNCTIONS ---
function updateStatus(running) {
    if (running) {
        statusDot.className = 'status-dot running';
        statusText.textContent = 'Rodando';
        statusText.style.color = 'var(--primary-color)';
    } else {
        statusDot.className = 'status-dot stopped';
        statusText.textContent = 'Parado';
        statusText.style.color = 'var(--danger-color)';
    }
}

async function loadConfig() {
    const res = await fetch('/api/config');
    const cfg = await res.json();
    inpUser.value = cfg.USERNAME || '';
    inpPass.value = cfg.PASSWORD || '';
    inpLookback.value = cfg.LOOKBACK_HOURS || 5;
}

async function saveConfig() {
    const cfg = {
        USERNAME: inpUser.value,
        PASSWORD: inpPass.value,
        LOOKBACK_HOURS: parseInt(inpLookback.value)
    };
    await fetch('/api/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(cfg)
    });
    alert('Configurações salvas!');
}

async function loadDates() {
    const res = await fetch('/api/dates');
    const dates = await res.json();
    dateSelect.innerHTML = '';
    dates.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d.filename;
        opt.textContent = d.label;
        dateSelect.appendChild(opt);
    });
    if (dates.length > 0) {
        selectedDate = dates[0].filename;
        loadData();
    }
}

async function loadData() {
    if (!dateSelect.value) return;
    const res = await fetch(`/api/data?filename=${dateSelect.value}`);
    currentData = await res.json();
    renderMatrices();
}

function renderMatrices() {
    matricesContainer.innerHTML = '';
    if (currentData.length === 0) {
        matricesContainer.innerHTML = '<div class="card">Sem dados para exibir</div>';
        return;
    }

    const selectedPattern = document.getElementById('pattern-select').value;
    const filterLastHours = parseInt(document.getElementById('filter-last-hours').value);

    // Group by Competition
    const comps = [...new Set(currentData.map(d => d['Competição']))];
    
    comps.forEach(comp => {
        const compData = currentData.filter(d => d['Competição'] === comp);
        
        // --- TABLE 1: RESULTADOS ---
        createTableCard(comp, compData, 'Ambos Marcam', 'Resultado', filterLastHours);
        
        // --- TABLE 2: PADRÃO ---
        let pat = selectedPattern;
        if (pat === 'Ambos Marcam') pat = '1x'; 
        
        createTableCard(comp, compData, pat, `Padrão ${pat}`, filterLastHours);
    });

    // --- RUN ANALYSIS ---
    analyzePatterns(currentData, selectedPattern);
}

function createTableCard(comp, data, key, labelSuffix, limit) {
    const card = document.createElement('div');
    card.className = 'card';
    
    const header = document.createElement('div');
    header.className = 'card-header';
    header.textContent = `🏆 ${comp} - ${labelSuffix}`;
    card.appendChild(header);

    let hours = [...new Set(data.map(d => parseInt(d['Hora'])))].sort((a,b) => b-a);
    
    // Apply Filter
    if (limit && limit > 0) {
        hours = hours.slice(0, limit);
    }

    const minutes = [...new Set(data.map(d => parseInt(d['Minuto'])))].sort((a,b) => a-b);

    const table = document.createElement('table');
    
    const thead = document.createElement('thead');
    const trHead = document.createElement('tr');
    trHead.innerHTML = '<th>H</th>' + minutes.map(m => `<th>${m}</th>`).join('');
    thead.appendChild(trHead);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    hours.forEach(h => {
        const tr = document.createElement('tr');
        let html = `<td><b>${h}</b></td>`;
        minutes.forEach(m => {
            const match = data.find(d => parseInt(d['Hora']) === h && parseInt(d['Minuto']) === m);
            let val = 'X';
            let cls = 'res-empty';
            
            if (match) {
                const rawVal = match[key];
                if (rawVal === 'Sim') {
                    val = 'S';
                    cls = 'res-sim';
                } else if (rawVal === 'Não') {
                    val = 'N';
                    cls = 'res-nao';
                }
            }
            html += `<td class="${cls}">${val}</td>`;
        });
        tr.innerHTML = html;
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    card.appendChild(table);
    matricesContainer.appendChild(card);
}

// --- ANALYSIS LOGIC ---
function analyzePatterns(allData, patternKey) {
    const container = document.getElementById('analysis-output');
    container.innerHTML = '';
    
    if (patternKey === 'Ambos Marcam') patternKey = '1x'; // Default fallback

    // 1. Determine "Last 3 Hours" window relative to the *latest* data point
    // We need 3 full hours: H, H-1, H-2.
    // Let's find max hour in dataset
    const maxHour = Math.max(...allData.map(d => parseInt(d['Hora'])));
    const hourList = [maxHour, maxHour - 1, maxHour - 2];
    
    // Filter data for these 3 hours
    const relevantData = allData.filter(d => hourList.includes(parseInt(d['Hora'])));
    
    // We need to look up data by (Comp, Hour, Minute) easily
    // Map: Comp|Min -> { h0: val, h1: val, h2: val }
    // Where h0 is maxHour, h1 is maxHour-1...
    
    const comps = [...new Set(relevantData.map(d => d['Competição']))];
    let candidates = [];

    comps.forEach(comp => {
        // Build a mini-grid for this comp (0-59 mins)
        // Rows: 0 (H-2), 1 (H-1), 2 (H)
        // Values: 'S' or 'N' (or null)
        
        // Helper to get value
        const getVal = (hOffset, m) => {
            const h = hourList[2 - hOffset]; // list is [H, H-1, H-2]. hOffset 0->H-2, 1->H-1, 2->H
            // Wait, let's stick to H, H-1, H-2 logic from user text
            // User: "Hora Atual (20), Hora-1 (19), Hora-2 (18)"
            // Vertical Match means: Col M has same result at H, H-1, H-2.
            
            const match = relevantData.find(d => 
                d['Competição'] === comp && 
                parseInt(d['Hora']) === h && 
                parseInt(d['Minuto']) === m
            );
            if (!match) return null;
            
            // Map raw to S/N
            const raw = match[patternKey];
            if (raw === 'Sim') return 'S';
            if (raw === 'Não') return 'N';
            return null;
        };

        // 1. FIND BASES (3 consecutive vertical)
        let baseMinutes = [];
        for (let m = 0; m < 60; m++) {
            const v2 = getVal(0, m); // H-2
            const v1 = getVal(1, m); // H-1
            const v0 = getVal(2, m); // H (Atual)
            
            if (v2 && v1 && v0 && v2 === v1 && v1 === v0) {
                // Found BASE
                baseMinutes.push({ m, val: v0 });
            }
        }

        // 2. FIND TARGETS (Next minute with 2 consecutive vertical)
        // User: "procurar o próximo minuto subsequente que contenha no mínimo 2 resultados idênticos"
        // Interpretation: Look at m+1, m+2... find first one with 2 vertical matches (H, H-1 ? Or any 2?)
        // "no mínimo 2 resultados idênticos consecutivos nas últimas 3 horas" -> Likely H and H-1, or H-1 and H-2.
        // Usually "vertical pattern" implies consistency. Let's assume ANY 2 consecutive slots (H/H-1 or H-1/H-2) or just 2 same values?
        // "2 Reds ou 2 Greens".
        // Let's assume strict vertical index 1&2 (H-1, H) or 0&1 (H-2, H-1) matching.
        // Actually simplest interpretation: checking the COLUMN. If col has >= 2 identicals.
        
        baseMinutes.forEach(base => {
            // Search forward from base.m + 1
            for (let t = base.m + 1; t < 60; t++) {
                const v2 = getVal(0, t);
                const v1 = getVal(1, t);
                const v0 = getVal(2, t); // This is the PREDICTION/RESULT usually, but historical analysis checks consistency.
                
                // We need 2 identicals.
                // Case A: v0 == v1
                // Case B: v1 == v2
                // Case C: v0 == v2 (not consecutive, but maybe valid?)
                // User said "consecutivos". So v0==v1 OR v1==v2.
                
                let isTarget = false;
                if (v0 && v1 && v0 === v1) isTarget = true;
                if (v1 && v2 && v1 === v2) isTarget = true;
                
                if (isTarget) {
                    // Start of target found.
                    // We need to pick THIS minute.
                    candidates.push({
                        comp,
                        minute: t,
                        baseM: base.m,
                        h2: v2 || '-',
                        h1: v1 || '-',
                        h0: v0 || '-', // This is the "result"
                        eliminated: false,
                        reason: ''
                    });
                    break; // Only first valid target per base? Or multiple? Usually one entry per signal. Let's break.
                }
            }
        });
    });

    // 3. CONSOLIDATE & SORT
    // Sort by Minute ASC
    candidates.sort((a, b) => a.minute - b.minute);
    
    // Remove exact duplicates (same comp/minute triggered by different bases?)
    // If minute 13 is target for base 10, and also base 9... keep one.
    candidates = candidates.filter((v,i,a) => a.findIndex(t => t.comp === v.comp && t.minute === v.minute) === i);


    // 4. APPLY RULES (Elimination)
    let lastValidMinute = -100;
    let lastValidComp = '';

    candidates.forEach(cand => {
        // Rule 1: Min 3 mins gap from LAST VALID
        const diff = cand.minute - lastValidMinute;
        
        // Rule 2: Different League from LAST VALID
        const sameComp = (cand.comp === lastValidComp);

        if (diff >= 3 && !sameComp) {
            // Valid
            cand.eliminated = false;
            lastValidMinute = cand.minute;
            lastValidComp = cand.comp;
        } else {
            // Eliminated
            cand.eliminated = true;
            if (diff < 3) cand.reason = 'Tempo < 3';
            else if (sameComp) cand.reason = 'Mesma Liga';
        }
    });

    // 5. RENDER
    if (candidates.length === 0) {
        container.innerHTML = '<div>Nenhuma oportunidade encontrada nas últimas 3h.</div>';
        return;
    }

    const table = document.createElement('table');
    table.style.width = '100%';
    table.innerHTML = `
        <thead>
            <tr>
                <th>Liga</th>
                <th>Minuto</th>
                <th>${hourList[2]}h</th>
                <th>${hourList[1]}h</th>
                <th>${hourList[0]}h</th>
                <th>Status</th>
            </tr>
        </thead>
    `;
    const tbody = document.createElement('tbody');
    
    candidates.forEach(c => {
        const tr = document.createElement('tr');
        if (c.eliminated) {
            tr.style.opacity = '0.5';
            tr.style.textDecoration = 'line-through';
            tr.style.backgroundColor = '#3e1a1a'; // Dark Red tint
        } else {
            tr.style.backgroundColor = '#1a3e1a'; // Dark Green tint
        }
        
        const getCls = (v) => v === 'S' ? 'res-sim' : (v === 'N' ? 'res-nao' : '');
        
        tr.innerHTML = `
            <td>${c.comp}</td>
            <td>${c.minute}</td>
            <td class="${getCls(c.h2)}">${c.h2}</td>
            <td class="${getCls(c.h1)}">${c.h1}</td>
            <td class="${getCls(c.h0)}">${c.h0}</td>
            <td>${c.eliminated ? c.reason : 'OK'}</td>
        `;
        tbody.appendChild(tr);
    });
    
    table.appendChild(tbody);
    container.appendChild(table);
}

// --- EVENT LISTENERS ---
document.getElementById('btn-start').onclick = async () => {
    await saveConfig(); // Save before start
    const res = await fetch('/api/start', { method: 'POST' });
    if (!res.ok) alert('Erro ao iniciar');
};

document.getElementById('btn-stop').onclick = async () => {
    await fetch('/api/stop', { method: 'POST' });
};

document.getElementById('btn-save-config').onclick = saveConfig;

document.getElementById('btn-set-anchor').onclick = async () => {
    const h = inpHour.value;
    if (!h) return alert('Digite a hora');
    const res = await fetch('/api/anchor', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ hour: h })
    });
    if (res.ok) alert('Anchor definido!');
    else alert('Erro ao definir anchor');
};

dateSelect.onchange = () => {
    loadData();
};

// Auto refresh data every 5s
setInterval(loadData, 5000);

// Init
loadConfig();
loadDates();
fetch('/api/status').then(r => r.json()).then(d => updateStatus(d.running));
