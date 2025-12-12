const { chromium } = require('playwright');
const fs = require('fs-extra');
const path = require('path');
const { createObjectCsvWriter } = require('csv-writer');
const dayjs = require('dayjs');
const customParseFormat = require('dayjs/plugin/customParseFormat');
const { Mutex } = require('async-mutex');

dayjs.extend(customParseFormat);

// --- CONFIGURATION ---
const ROOT = __dirname;
const CONFIG_PATH = path.join(ROOT, 'config.json');
const ANCHOR_DIR = path.join(ROOT, 'anchor_time');
const HISTORY_DIR = path.join(ROOT, 'historico');

fs.ensureDirSync(ANCHOR_DIR);
fs.ensureDirSync(HISTORY_DIR);

let config = {
    TARGET_URL: "https://extra.bet365.bet.br/results/br?li=1",
    BROWSER_CHANNEL: "chrome",
    COMPETITIONS: ["Euro Cup", "Premier League", "Sul Americano", "Copa do Mundo"],
    DELAY_MIN: 0.5,
    DELAY_MAX: 1.5,
    POLLING_INTERVAL: 30,
    LOOKBACK_HOURS: 1,
    USERNAME: "",
    PASSWORD: ""
};

if (fs.existsSync(CONFIG_PATH)) {
    try {
        const loaded = fs.readJsonSync(CONFIG_PATH);
        Object.assign(config, loaded);
        console.log("✅ Configuração carregada do arquivo config.json");
    } catch (e) {
        console.error(`⚠️ Erro ao carregar config.json: ${e}`);
    }
}

// Normalização
config.COMPETITIONS = config.COMPETITIONS.map(c => c.replace("Premiere League", "Premier League"));

const COMPETITIONS_MAP = {
    "Euro Cup": "#CompetitionList > div:nth-child(3) > button > div",
    "Premier League": "#CompetitionList > div:nth-child(5) > button > div",
    "Sul Americano": "#CompetitionList > div:nth-child(6) > button > div",
    "Copa do Mundo": "#CompetitionList > div:nth-child(8) > button > div"
};

const csvMutex = new Mutex();

// --- HELPERS ---

function getAnchorFilename() {
    return path.join(ANCHOR_DIR, `anchor_time_${dayjs().format('YYYY-MM-DD')}.json`);
}

function loadAnchorTime(compName) {
    const f = getAnchorFilename();
    if (fs.existsSync(f)) {
        try {
            const data = fs.readJsonSync(f);
            return data[compName] || null;
        } catch (e) { return null; }
    }
    return null;
}

function saveAnchorTime(compName, timeStr) {
    const f = getAnchorFilename();
    let data = {};
    if (fs.existsSync(f)) {
        try { data = fs.readJsonSync(f); } catch (e) {}
    }
    data[compName] = timeStr;
    fs.writeJsonSync(f, data, { spaces: 4 });
}

function timeStrToMinutes(tStr) {
    try {
        const clean = tStr.replace(':', '.');
        const [h, m] = clean.split('.').map(Number);
        return h * 60 + m;
    } catch (e) { return -1; }
}

function minutesToTimeStr(minutes) {
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return `${String(h).padStart(2, '0')}.${String(m).padStart(2, '0')}`;
}

async function waitRandom() {
    const delay = Math.random() * (config.DELAY_MAX - config.DELAY_MIN) + config.DELAY_MIN;
    await new Promise(r => setTimeout(r, delay * 1000));
}

async function saveMatchData(compName, dateStr, hour, minute, ambosMarcam, csvPath) {
    await csvMutex.runExclusive(async () => {
        try {
            let records = [];
            if (fs.existsSync(csvPath)) {
                const content = fs.readFileSync(csvPath, 'utf8');
                const lines = content.split('\n').filter(l => l.trim());
                if (lines.length > 1) {
                    const headers = lines[0].split(',');
                    for (let i = 1; i < lines.length; i++) {
                        const vals = lines[i].split(',');
                        if (vals.length >= 5) {
                            records.push({
                                Data: vals[0],
                                Competição: vals[1],
                                Hora: vals[2],
                                Minuto: vals[3],
                                'Ambos Marcam': vals[4]
                            });
                        }
                    }
                }
            }

            const existingIndex = records.findIndex(r => 
                r['Competição'] === compName && 
                parseInt(r['Hora']) === hour && 
                parseInt(r['Minuto']) === minute
            );

            if (existingIndex !== -1) {
                if (ambosMarcam) {
                    records[existingIndex]['Ambos Marcam'] = ambosMarcam;
                }
            } else {
                records.push({
                    Data: dateStr,
                    Competição: compName,
                    Hora: hour,
                    Minuto: minute,
                    'Ambos Marcam': ambosMarcam || ''
                });
                if (ambosMarcam) {
                    console.log(`     [${compName}] 💾 Salvo no CSV: ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')} - ${ambosMarcam}`);
                }
            }

            const csvWriter = createObjectCsvWriter({
                path: csvPath,
                header: [
                    {id: 'Data', title: 'Data'},
                    {id: 'Competição', title: 'Competição'},
                    {id: 'Hora', title: 'Hora'},
                    {id: 'Minuto', title: 'Minuto'},
                    {id: 'Ambos Marcam', title: 'Ambos Marcam'}
                ]
            });

            await csvWriter.writeRecords(records);

        } catch (e) {
            console.error(`     [${compName}] ❌ Erro ao salvar CSV: ${e}`);
        }
    });
}

async function extractAmbosMarcamLogic(page) {
    let ambosMarcam = "";
    let clickedAmbos = false;

    const ambosBtnSelector = '#ResultsComponent > div:nth-child(4) > div > div.market-search > div.market-search__link-wrapper > div:nth-child(21) > button';

    if (await page.isVisible(ambosBtnSelector)) {
        try {
            await page.click(ambosBtnSelector);
            await new Promise(r => setTimeout(r, 1000));
            clickedAmbos = true;
        } catch (e) {}
    }

    if (!clickedAmbos) {
        try {
            const wrapper = page.locator(".market-search__link-wrapper");
            let btn = wrapper.getByText("Ambos Marcam", { exact: true });
            if (await btn.count() === 0) {
                btn = wrapper.locator("button").filter({ hasText: "Ambos Marcam" }).first();
            }
            if (await btn.isVisible()) {
                await btn.click();
                await new Promise(r => setTimeout(r, 1000));
                clickedAmbos = true;
            }
        } catch (e) {}
    }

    if (clickedAmbos) {
        await new Promise(r => setTimeout(r, 1000));
        
        // Strategy 1
        try {
            const varsSelector = '#ResultsComponent > div:nth-child(4) > div > div.market-search > div.market-search__link-wrapper > div:nth-child(21) > div > div.market-search__link-variables';
            if (await page.isVisible(varsSelector)) {
                const rows = page.locator(`${varsSelector} > div.market-search__link-variables-row`);
                const count = await rows.count();
                for (let i = 0; i < count; i++) {
                    const row = rows.nth(i);
                    const name = (await row.locator(".market-search__link-variables-name").innerText()).trim();
                    const value = (await row.locator(".market-search__link-variables-value").innerText()).trim();
                    if (value === "Won") {
                        if (name === "Sim") return "Sim";
                        if (name === "Não") return "Não";
                    }
                }
            }
        } catch (e) {}

        // Strategy 2
        try {
            const candidates = page.getByText("Ambos Marcam", { exact: true });
            const count = await candidates.count();
            for (let i = 0; i < count; i++) {
                const cand = candidates.nth(i);
                const tag = await cand.evaluate(el => el.tagName);
                if (tag === "BUTTON") continue;

                let parent = cand.locator("..");
                let varsContainer = parent.locator(".market-search__link-variables");
                if (await varsContainer.count() === 0) {
                    parent = parent.locator("..");
                    varsContainer = parent.locator(".market-search__link-variables");
                }

                if (await varsContainer.count() > 0) {
                    const rows = varsContainer.first().locator(".market-search__link-variables-row");
                    const rCount = await rows.count();
                    for (let r = 0; r < rCount; r++) {
                        const row = rows.nth(r);
                        const name = (await row.locator(".market-search__link-variables-name").innerText()).trim();
                        const value = (await row.locator(".market-search__link-variables-value").innerText()).trim();
                        if (value === "Won") {
                            if (name === "Sim") return "Sim";
                            if (name === "Não") return "Não";
                        }
                    }
                }
            }
        } catch (e) {}
    }
    return "";
}

async function navigateToCompetition(page, compName) {
    try {
        await page.goto(config.TARGET_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
        await waitRandom();

        // 1. Encontrar Resultado
        const findResultSelector = '#ResultsComponent > div.home-page__inner > button > div';
        if (await page.isVisible(findResultSelector)) {
            await page.click(findResultSelector);
        } else {
            const foundBtn = page.getByText("Encontrar um Resultado").first();
            if (await foundBtn.isVisible()) await foundBtn.click();
        }
        await waitRandom();

        // 2. Futebol Virtual
        const fvSelector = '#ResultsSportsList > div:nth-child(43) > button > div';
        if (await page.isVisible(fvSelector)) {
            await page.click(fvSelector);
        } else {
            const fvBtn = page.locator("#ResultsSportsList").getByText("Futebol Virtual").first();
            if (await fvBtn.isVisible()) await fvBtn.click();
        }
        await waitRandom();

        // 3. Data
        try {
            const currentDay = dayjs().date();
            const datesContainer = page.locator('#ResultsDatePicker > div > div.date-picker__selector-wrapper > div.date-picker__selector > div.date-picker__dates');
            const dayLocator = datesContainer.getByText(String(currentDay), { exact: true });
            if (await dayLocator.isVisible()) {
                await dayLocator.click({ force: true });
                await dayLocator.click();
            }
            await page.click('#ResultsDatePicker > div > button');
            await waitRandom();
        } catch (e) {
            console.log(`⚠️ [${compName}] Erro ao setar data.`);
        }

        // 4. Selecionar Competição
        const compSelector = COMPETITIONS_MAP[compName];
        if (compSelector && await page.isVisible(compSelector)) {
            await page.click(compSelector);
        } else {
            let searchName = compName;
            if (compName === "Sul Americano") searchName = "Super Liga Sul-Americana";
            const cBtn = page.locator("#CompetitionList").getByText(searchName).first();
            if (await cBtn.isVisible()) await cBtn.click();
        }

        console.log(`✅ [${compName}] Navegação inicial concluída.`);
        await waitRandom();

    } catch (e) {
        console.error(`❌ [${compName}] Erro na navegação: ${e}`);
        throw e;
    }
}

async function workerCompetition(context, compName, csvPath) {
    console.log(`🚀 [${compName}] Iniciando worker...`);
    const page = await context.newPage();

    try {
        await navigateToCompetition(page, compName);

        let anchorMinutes = -1;
        const savedAnchor = loadAnchorTime(compName);
        if (savedAnchor) {
            anchorMinutes = timeStrToMinutes(savedAnchor);
            console.log(`   [${compName}] ⚓ Anchor carregado: ${savedAnchor}`);
        }

        let needCalibration = (anchorMinutes === -1);

        while (true) {
            try {
                const matchesContainerSelector = "#ResultsComponent > div:nth-child(3) > div";
                if (!await page.isVisible(matchesContainerSelector)) {
                    console.log(`⚠️ [${compName}] Container não visível. Reiniciando...`);
                    await page.goto(config.TARGET_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
                    console.log(`⏳ [${compName}] Aguardando 30s...`);
                    await new Promise(r => setTimeout(r, 30000));
                    await navigateToCompetition(page, compName);
                    continue;
                }

                const dateStr = dayjs().format('DD/MM/YYYY');
                const allButtons = page.locator(`${matchesContainerSelector} > button`);
                const count = await allButtons.count();

                if (count === 0) {
                    console.log(`   [${compName}] 0 partidas. Aguardando...`);
                    await new Promise(r => setTimeout(r, config.POLLING_INTERVAL * 1000));
                    continue;
                }

                let scrapedMatches = [];
                for (let i = 0; i < count; i++) {
                    const btn = allButtons.nth(i);
                    const text = await btn.innerText();
                    const lines = text.split('\n').map(l => l.trim()).filter(l => l);
                    if (!lines.length) continue;

                    let h = 0, m = 0;
                    const timeStr = lines[0].split(' ')[0];
                    if (timeStr) {
                        try {
                            const clean = timeStr.replace(/:/g, '.');
                            const parts = clean.split('.');
                            if (parts.length >= 2) {
                                h = parseInt(parts[0]);
                                m = parseInt(parts[1]);
                            }
                        } catch (e) {}
                    }
                    scrapedMatches.push({ h, m, index: i, timeStr });
                }

                // Sort DESC
                scrapedMatches.sort((a, b) => (b.h * 60 + b.m) - (a.h * 60 + a.m));

                // 1. Calibração
                if (needCalibration) {
                    console.log(`   [${compName}] 🔍 Iniciando Calibração...`);
                    for (const match of scrapedMatches) {
                        const targetTime = `${String(match.h).padStart(2,'0')}:${String(match.m).padStart(2,'0')}`;
                        const targetTimeDot = `${String(match.h).padStart(2,'0')}.${String(match.m).padStart(2,'0')}`;
                        
                        let btnLocator = page.locator(`${matchesContainerSelector} > button`).filter({ hasText: targetTime }).first();
                        if (await btnLocator.count() === 0) {
                            btnLocator = page.locator(`${matchesContainerSelector} > button`).filter({ hasText: targetTimeDot }).first();
                        }

                        if (await btnLocator.count() === 0) continue;

                        try {
                            await btnLocator.click({ timeout: 5000 });
                            await waitRandom();
                            const res = await extractAmbosMarcamLogic(page);
                            
                            if (res) {
                                anchorMinutes = match.h * 60 + match.m;
                                const anchorStr = minutesToTimeStr(anchorMinutes);
                                saveAnchorTime(compName, anchorStr);
                                await saveMatchData(compName, dateStr, match.h, match.m, res, csvPath);
                                console.log(`     [${compName}] ⚓ Anchor Definido: ${anchorStr} (Resultado: ${res})`);
                                await page.goBack();
                                await waitRandom();
                                break;
                            }
                            await page.goBack();
                            await waitRandom();
                        } catch (e) {
                            try { await page.goBack(); } catch (ex) {}
                        }
                    }

                    if (anchorMinutes !== -1) {
                        // Lookback
                        const anchorH = Math.floor(anchorMinutes / 60);
                        let startH = anchorH - config.LOOKBACK_HOURS;
                        if (startH < 0) startH = 0;
                        const limitMinutes = startH * 60;

                        console.log(`   [${compName}] 🔙 Coleta Lookback (>= ${startH}:00 até < ${minutesToTimeStr(anchorMinutes)})...`);

                        const lookbackMatches = scrapedMatches.filter(m => {
                            const mm = m.h * 60 + m.m;
                            return mm >= limitMinutes && mm < anchorMinutes;
                        });
                        // Sort DESC (or ASC, doesn't matter much for lookback, let's do DESC)
                        lookbackMatches.sort((a, b) => (b.h * 60 + b.m) - (a.h * 60 + a.m));

                        for (const match of lookbackMatches) {
                            const targetTime = `${String(match.h).padStart(2,'0')}:${String(match.m).padStart(2,'0')}`;
                            const targetTimeDot = `${String(match.h).padStart(2,'0')}.${String(match.m).padStart(2,'0')}`;
                            
                            let btnLocator = page.locator(`${matchesContainerSelector} > button`).filter({ hasText: targetTime }).first();
                            if (await btnLocator.count() === 0) {
                                btnLocator = page.locator(`${matchesContainerSelector} > button`).filter({ hasText: targetTimeDot }).first();
                            }

                            if (await btnLocator.count() > 0) {
                                try {
                                    await btnLocator.click({ timeout: 5000 });
                                    await waitRandom();
                                    const res = await extractAmbosMarcamLogic(page);
                                    if (res) {
                                        await saveMatchData(compName, dateStr, match.h, match.m, res, csvPath);
                                        console.log(`     [${compName}] 🔙 Lookback: ${match.h}:${match.m} -> ${res}`);
                                    }
                                    await page.goBack();
                                    await waitRandom();
                                } catch (e) { try { await page.goBack(); } catch (ex) {} }
                            }
                        }
                        needCalibration = false;
                    } else {
                        console.log(`   [${compName}] ⚠️ Nenhum resultado para calibrar. Aguardando...`);
                        await new Promise(r => setTimeout(r, config.POLLING_INTERVAL * 1000));
                        continue;
                    }
                }

                // 2. Incremental
                const matchesToCheck = scrapedMatches.filter(m => {
                    const mm = m.h * 60 + m.m;
                    return mm >= anchorMinutes;
                });
                matchesToCheck.sort((a, b) => (a.h * 60 + a.m) - (b.h * 60 + b.m)); // ASC

                // Load existing to skip
                const existingResults = new Set();
                if (fs.existsSync(csvPath)) {
                    try {
                        const content = fs.readFileSync(csvPath, 'utf8');
                        const lines = content.split('\n');
                        for (let i = 1; i < lines.length; i++) {
                            const vals = lines[i].split(',');
                            if (vals.length >= 5 && vals[1] === compName && vals[4] && vals[4].trim()) {
                                existingResults.add(`${parseInt(vals[2])}:${parseInt(vals[3])}`);
                            }
                        }
                    } catch (e) {}
                }

                if (matchesToCheck.length === 0) {
                    await new Promise(r => setTimeout(r, config.POLLING_INTERVAL * 1000));
                    continue;
                }

                console.log(`   [${compName}] ${matchesToCheck.length} jogos INCREMENTAIS pendentes (>= ${minutesToTimeStr(anchorMinutes)}).`);

                let shouldRestartLoop = false;

                for (const match of matchesToCheck) {
                    const matchKey = `${match.h}:${match.m}`;
                    if (existingResults.has(matchKey)) {
                        const mm = match.h * 60 + match.m;
                        if (mm > anchorMinutes) {
                            anchorMinutes = mm;
                            saveAnchorTime(compName, minutesToTimeStr(anchorMinutes));
                        }
                        continue;
                    }

                    const targetTime = `${String(match.h).padStart(2,'0')}:${String(match.m).padStart(2,'0')}`;
                    const targetTimeDot = `${String(match.h).padStart(2,'0')}.${String(match.m).padStart(2,'0')}`;
                    
                    let btnLocator = page.locator(`${matchesContainerSelector} > button`).filter({ hasText: targetTime }).first();
                    if (await btnLocator.count() === 0) {
                        btnLocator = page.locator(`${matchesContainerSelector} > button`).filter({ hasText: targetTimeDot }).first();
                    }

                    if (await btnLocator.count() === 0) {
                        console.log(`     [${compName}] ⚠️ Jogo ${targetTime} sumiu.`);
                        continue;
                    }

                    try {
                        await btnLocator.click({ timeout: 5000 });
                        await waitRandom();
                        const res = await extractAmbosMarcamLogic(page);

                        if (!res) {
                            console.log(`     [${compName}] ⚠️ ${targetTime} sem resultado.`);
                            console.log(`     [${compName}] 🔄 Retornando à Home e aguardando 30s...`);
                            await page.goto(config.TARGET_URL, { waitUntil: "domcontentloaded", timeout: 60000 });
                            await new Promise(r => setTimeout(r, 30000));
                            await navigateToCompetition(page, compName);
                            shouldRestartLoop = true;
                            break;
                        }

                        await saveMatchData(compName, dateStr, match.h, match.m, res, csvPath);
                        console.log(`     [${compName}] ✅ ${match.h}:${match.m} -> ${res}`);

                        const mm = match.h * 60 + match.m;
                        if (mm > anchorMinutes) {
                            anchorMinutes = mm;
                            saveAnchorTime(compName, minutesToTimeStr(anchorMinutes));
                        }

                        await page.goBack();
                        await waitRandom();

                    } catch (e) {
                         console.log(`     [${compName}] ❌ Erro jogo ${match.h}:${match.m}: ${e}`);
                         try {
                             if (!await page.isVisible(matchesContainerSelector)) await page.goBack();
                         } catch (ex) {}
                    }
                }

                if (shouldRestartLoop) continue;
                await new Promise(r => setTimeout(r, config.POLLING_INTERVAL * 1000));

            } catch (e) {
                console.error(`❌ [${compName}] Erro no loop: ${e}`);
                await new Promise(r => setTimeout(r, 10000));
                try { await page.reload(); } catch (ex) {}
            }
        }

    } catch (e) {
        console.error(`❌ [${compName}] Falha fatal: ${e}`);
    }
}

async function main() {
    console.log("🚀 Iniciando Sistema Multi-Abas (Node.js)...");

    const browser = await chromium.launch({
        channel: config.BROWSER_CHANNEL,
        headless: false,
        args: ["--no-default-browser-check", "--disable-infobars", "--start-maximized"]
    });

    const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
    await context.addInitScript(() => {
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        if (!window.chrome) window.chrome = { runtime: {} };
    });

    // --- LOGIN ---
    const page = await context.newPage();
    console.log(`🌍 Navegando para Login (${config.TARGET_URL})...`);
    await page.goto(config.TARGET_URL, { waitUntil: "domcontentloaded", timeout: 60000 });

    const loginBtnSelector = '#logged-out-container > div.mobileLoginSection > a';
    if (await page.isVisible(loginBtnSelector)) {
        console.log("🔑 Realizando Login...");
        await page.click(loginBtnSelector);
        await waitRandom();
        await page.fill('#txtUsername', config.USERNAME || "");
        await waitRandom();
        await page.fill('#txtPassword', config.PASSWORD || "");
        await waitRandom();
        await page.keyboard.press('Enter');

        console.log("⏳ Aguardando login...");
        try {
            await page.locator(loginBtnSelector).waitFor({ state: "detached", timeout: 30000 });
            console.log("✅ Login efetuado.");
        } catch (e) {
            console.log(`⚠️ Timeout login: ${e}`);
        }
        await new Promise(r => setTimeout(r, 5000));
    } else {
        console.log("✅ Já logado.");
    }

    try {
        const modalSelector = '#ResultsPage > div.modal.loggedin.hide-modal-for-members > button';
        if (await page.isVisible(modalSelector, { timeout: 5000 })) {
            await page.click(modalSelector);
        }
    } catch (e) {}

    await page.close();

    // --- WORKERS ---
    const dateFilename = dayjs().format('DD-MM-YYYY');
    const csvPath = path.join(HISTORY_DIR, `matches_${dateFilename}.csv`);

    const tasks = config.COMPETITIONS.map(comp => workerCompetition(context, comp, csvPath));
    console.log(`🔥 Iniciando ${tasks.length} workers...`);
    await Promise.all(tasks);
}

main().catch(console.error);
