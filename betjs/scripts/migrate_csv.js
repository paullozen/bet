const fs = require('fs-extra');
const path = require('path');
const { createObjectCsvWriter } = require('csv-writer');

const HISTORY_DIR = path.join(__dirname, '..', 'historico');

// Helper to convert HH:MM to minutes
function timeToMinutes(h, m) {
    return parseInt(h) * 60 + parseInt(m);
}

// Logic: Compare current result with result at (minutes - offset)
// N=1 (1x) -> offset = (1+1)*3 = 6 mins
// N=2 (2x) -> offset = (2+1)*3 = 9 mins
// ...
function calculatePatterns(rows) {
    // Map: "Competição|Minutes" -> "Ambos Marcam"
    const lookup = new Map();
    rows.forEach(r => {
        const key = `${r['Competição']}|${timeToMinutes(r['Hora'], r['Minuto'])}`;
        lookup.set(key, r['Ambos Marcam']);
    });

    return rows.map(row => {
        const currentRes = row['Ambos Marcam'];
        if (!currentRes) return row;

        const currentMins = timeToMinutes(row['Hora'], row['Minuto']);
        const comp = row['Competição'];

        for (let n = 1; n <= 5; n++) {
            const offset = (n + 1) * 3;
            const targetMins = currentMins - offset;
            const targetKey = `${comp}|${targetMins}`;
            
            const targetRes = lookup.get(targetKey);
            
            if (targetRes) {
                // If match -> Sim, else -> Não
                // "Sim" == "Sim" -> Sim
                // "Não" == "Não" -> Sim
                // "Sim" != "Não" -> Não
                row[`${n}x`] = (currentRes === targetRes) ? 'Sim' : 'Não';
            } else {
                row[`${n}x`] = '';
            }
        }
        return row;
    });
}

async function migrate() {
    if (!fs.existsSync(HISTORY_DIR)) {
        console.log("Pasta historico nao encontrada.");
        return;
    }

    const files = fs.readdirSync(HISTORY_DIR).filter(f => f.endsWith('.csv'));

    for (const file of files) {
        console.log(`Processando ${file}...`);
        const filePath = path.join(HISTORY_DIR, file);
        
        try {
            const content = fs.readFileSync(filePath, 'utf8');
            const lines = content.split('\n').filter(l => l.trim());
            
            if (lines.length < 2) continue;

            const headers = lines[0].split(',').map(h => h.trim());
            const rows = [];

            for (let i = 1; i < lines.length; i++) {
                const vals = lines[i].split(',');
                // Basic parsing, assuming fixed structure or at least first 5 cols
                // Data,Competição,Hora,Minuto,Ambos Marcam
                if (vals.length >= 5) {
                    const row = {
                        'Data': vals[0],
                        'Competição': vals[1],
                        'Hora': vals[2],
                        'Minuto': vals[3],
                        'Ambos Marcam': vals[4]
                    };
                    // Preserve existing patterns if any? No, recalc is safer.
                    rows.push(row);
                }
            }

            // Calculate
            const enrichedRows = calculatePatterns(rows);

            // Write back
            const csvWriter = createObjectCsvWriter({
                path: filePath,
                header: [
                    {id: 'Data', title: 'Data'},
                    {id: 'Competição', title: 'Competição'},
                    {id: 'Hora', title: 'Hora'},
                    {id: 'Minuto', title: 'Minuto'},
                    {id: 'Ambos Marcam', title: 'Ambos Marcam'},
                    {id: '1x', title: '1x'},
                    {id: '2x', title: '2x'},
                    {id: '3x', title: '3x'},
                    {id: '4x', title: '4x'},
                    {id: '5x', title: '5x'}
                ]
            });

            await csvWriter.writeRecords(enrichedRows);
            console.log(`✅ ${file} atualizado.`);

        } catch (e) {
            console.error(`❌ Erro em ${file}:`, e);
        }
    }
}

migrate();
