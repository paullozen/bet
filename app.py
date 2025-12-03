import asyncio
import json
import random
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import padroes
from playwright.async_api import async_playwright

# ==========================
ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
ANCHOR_DIR = ROOT / "anchor_time"
ANCHOR_DIR.mkdir(exist_ok=True)

# Valores Padrão
config = {
    "TARGET_URL": "https://extra.bet365.bet.br/results/br?li=1",
    "BROWSER_CHANNEL": "chrome",
    "COMPETITIONS": ["Euro Cup", "Premier League", "Sul Americano", "Copa do Mundo"],
    "MAX_MATCHES": 0,
    "DELAY_MIN": 0.5,
    "DELAY_MAX": 1.5,
    "POLLING_INTERVAL": 30,
    "CONSECUTIVE_NONE_LIMIT": 1,
    "REST_TIME": 30,
    "LOOKBACK_HOURS": 1
}

# Carregar do arquivo se existir
if CONFIG_PATH.exists():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            loaded_config = json.load(f)
            config.update(loaded_config)
        print("✅ Configuração carregada do arquivo config.json")
    except Exception as e:
        print(f"⚠️ Erro ao carregar config.json: {e}")

# Normalização de nomes
if "COMPETITIONS" in config:
    config["COMPETITIONS"] = [c.replace("Premiere League", "Premier League") for c in config["COMPETITIONS"]]

# USERNAME e PASSWORD
USERNAME = config.get("USERNAME", "")
PASSWORD = config.get("PASSWORD", "")

if not USERNAME or not PASSWORD:
    print("⚠️ Credenciais não encontradas ou vazias no config.json")
    if not USERNAME:
        USERNAME = input("Digite o usuário Bet365: ")
    if not PASSWORD:
        PASSWORD = input("Digite a senha Bet365: ")
else:
    print(f"✅ Credenciais carregadas do config.json (Usuário: {USERNAME})")


TARGET_URL = config["TARGET_URL"]
BROWSER_CHANNEL = config["BROWSER_CHANNEL"]
COMPETITIONS_TO_RUN = config["COMPETITIONS"]
DELAY_MIN = config["DELAY_MIN"]
DELAY_MAX = config["DELAY_MAX"]
POLLING_INTERVAL = config.get("POLLING_INTERVAL", 60)
CONSECUTIVE_NONE_LIMIT = config.get("CONSECUTIVE_NONE_LIMIT", 1)
REST_TIME = config.get("REST_TIME", 120)
LOOKBACK_HOURS = config.get("LOOKBACK_HOURS", 5)

# Mapeamento de competições
competitions_map = {
    "Euro Cup": "#CompetitionList > div:nth-child(3) > button > div",
    "Premier League": "#CompetitionList > div:nth-child(5) > button > div",
    "Sul Americano": "#CompetitionList > div:nth-child(6) > button > div",
    "Copa do Mundo": "#CompetitionList > div:nth-child(8) > button > div"
}

# Lock global para escrita no CSV
csv_lock = asyncio.Lock()

# --- Anchor Time Helpers ---
def get_anchor_filename():
    return ANCHOR_DIR / f"anchor_time_{datetime.now().strftime('%Y-%m-%d')}.json"

def load_anchor_time(comp_name):
    f = get_anchor_filename()
    if f.exists():
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
                return data.get(comp_name)
        except: return None
    return None

def save_anchor_time(comp_name, time_str):
    f = get_anchor_filename()
    data = {}
    if f.exists():
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
        except: pass
    data[comp_name] = time_str
    with open(f, 'w') as fp:
        json.dump(data, fp, indent=4)

def time_str_to_minutes(t_str):
    try:
        t_str = t_str.replace(':', '.')
        h, m = map(int, t_str.split('.'))
        return h * 60 + m
    except: return -1

def minutes_to_time_str(minutes):
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}.{m:02d}"

async def wait_random():
    delay = random.uniform(DELAY_MIN, DELAY_MAX)
    await asyncio.sleep(delay)

async def save_match_data(comp_name, date_str, hour, minute, ambos_marcam, csv_path):
    async with csv_lock:
        try:
            match_info_dict = {
                "Data": date_str,
                "Competição": comp_name,
                "Hora": hour,
                "Minuto": minute,
                "Ambos Marcam": ambos_marcam
            }
            
            if csv_path.exists():
                df_current = pd.read_csv(csv_path)
                df_current['Hora'] = df_current['Hora'].astype(str)
                df_current['Minuto'] = df_current['Minuto'].astype(str)
            else:
                df_current = pd.DataFrame(columns=["Data", "Competição", "Hora", "Minuto", "Ambos Marcam"])

            # Verifica se já existe (chave: Competição, Hora, Minuto)
            mask = (
                (df_current['Competição'] == comp_name) &
                (df_current['Hora'].astype(str) == str(hour)) &
                (df_current['Minuto'].astype(str) == str(minute))
            )
            
            if mask.any():
                # Atualiza se o valor novo não for nulo/vazio
                if ambos_marcam:
                    df_current.loc[mask, 'Ambos Marcam'] = ambos_marcam
                else:
                    pass # Se ambos_marcam for None, não sobrescreve dados existentes
            else:
                new_row = pd.DataFrame([match_info_dict])
                df_current = pd.concat([df_current, new_row], ignore_index=True)
                if ambos_marcam:
                    print(f"     [{comp_name}] 💾 Salvo no CSV: {hour:02d}:{minute:02d} - {ambos_marcam}")
                else:
                    # print(f"     [{comp_name}] 💾 Jogo registrado: {hour:02d}:{minute:02d}")
                    pass

            # Calcular padrões em memória antes de salvar (apenas se tivermos dados novos de resultado)
            if ambos_marcam:
                try:
                    df_current = padroes.calcular_padroes(df_current)
                except Exception as e_patt:
                    print(f"     ⚠️ Erro ao calcular padrões: {e_patt}")

            df_current.to_csv(csv_path, index=False, encoding='utf-8-sig')
            
        except Exception as e:
            print(f"     [{comp_name}] ❌ Erro ao salvar CSV: {e}")

async def extract_ambos_marcam_logic(page):
    ambos_marcam = ""
    clicked_ambos = False
    
    # 1. Tenta clicar na aba/botão "Ambos Marcam"
    ambos_btn_selector = '#ResultsComponent > div:nth-child(4) > div > div.market-search > div.market-search__link-wrapper > div:nth-child(21) > button'
    
    if await page.is_visible(ambos_btn_selector):
        try:
            await page.click(ambos_btn_selector)
            await asyncio.sleep(1)
            clicked_ambos = True
        except: pass
    
    if not clicked_ambos:
        try:
            # Tenta achar botão pelo texto exato ou aproximado
            ambos_btn = page.locator(".market-search__link-wrapper").get_by_text("Ambos Marcam", exact=True)
            if await ambos_btn.count() == 0:
                ambos_btn = page.locator(".market-search__link-wrapper button").filter(has_text="Ambos Marcam").first
            
            if await ambos_btn.is_visible():
                await ambos_btn.click()
                await asyncio.sleep(1)
                clicked_ambos = True
        except: pass

    if clicked_ambos:
        await asyncio.sleep(1)
        
        # --- Estratégia 1: Seletor Fixo (Original) ---
        try:
            vars_selector = '#ResultsComponent > div:nth-child(4) > div > div.market-search > div.market-search__link-wrapper > div:nth-child(21) > div > div.market-search__link-variables'
            if await page.is_visible(vars_selector):
                rows = page.locator(f"{vars_selector} > div.market-search__link-variables-row")
                count = await rows.count()
                for r in range(count):
                    row_el = rows.nth(r)
                    name = await row_el.locator(".market-search__link-variables-name").inner_text()
                    value = await row_el.locator(".market-search__link-variables-value").inner_text()
                    name, value = name.strip(), value.strip()
                    if value == "Won":
                        if name == "Sim": return "Sim"
                        elif name == "Não": return "Não"
        except: pass
        
        # --- Estratégia 2: Busca por Título Exato "Ambos Marcam" (Fallback Robusto) ---
        try:
            candidates = page.get_by_text("Ambos Marcam", exact=True)
            cand_count = await candidates.count()
            
            for i in range(cand_count):
                cand = candidates.nth(i)
                tag = await cand.evaluate("el => el.tagName")
                if tag == "BUTTON": continue
                
                parent = cand.locator("..")
                vars_container = parent.locator(".market-search__link-variables")
                
                if await vars_container.count() == 0:
                    parent = parent.locator("..")
                    vars_container = parent.locator(".market-search__link-variables")
                    
                if await vars_container.count() > 0:
                    rows = vars_container.first.locator(".market-search__link-variables-row")
                    r_count = await rows.count()
                    for r in range(r_count):
                        row_el = rows.nth(r)
                        name = await row_el.locator(".market-search__link-variables-name").inner_text()
                        value = await row_el.locator(".market-search__link-variables-value").inner_text()
                        name, value = name.strip(), value.strip()
                        if value == "Won":
                            if name == "Sim": return "Sim"
                            elif name == "Não": return "Não"
        except: pass

    return ""

async def navigate_to_competition(page, comp_name):
    try:
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        await wait_random()
        
        # 1. Encontrar Resultado
        find_result_selector = '#ResultsComponent > div.home-page__inner > button > div'
        if await page.is_visible(find_result_selector):
            await page.click(find_result_selector)
        else:
             # Tenta busca por texto
            found_btn = page.get_by_text("Encontrar um Resultado").first
            if await found_btn.is_visible():
                await found_btn.click()
        await wait_random()

        # 2. Futebol Virtual
        fv_selector = '#ResultsSportsList > div:nth-child(43) > button > div'
        if await page.is_visible(fv_selector):
            await page.click(fv_selector)
        else:
             fv_btn = page.locator("#ResultsSportsList").get_by_text("Futebol Virtual").first
             if await fv_btn.is_visible():
                 await fv_btn.click()
        await wait_random()

        # 3. Data
        try:
            now = datetime.now()
            current_day = now.day
            dates_container_selector = '#ResultsDatePicker > div > div.date-picker__selector-wrapper > div.date-picker__selector > div.date-picker__dates'
            dates_container = page.locator(dates_container_selector)
            day_locator = dates_container.get_by_text(str(current_day), exact=True)
            if await day_locator.is_visible():
                await day_locator.click(force=True)
                await day_locator.click() # Garantir click
            await page.click('#ResultsDatePicker > div > button') # Confirmar
            await wait_random()
        except:
            print(f"⚠️ [{comp_name}] Erro ao setar data (pode já estar correta).")

        # 4. Selecionar a Competição
        comp_selector = competitions_map.get(comp_name)
        if comp_selector and await page.is_visible(comp_selector):
            await page.click(comp_selector)
        else:
             search_name = comp_name
             if comp_name == "Sul Americano": search_name = "Super Liga Sul-Americana"
             c_btn = page.locator("#CompetitionList").get_by_text(search_name).first
             if await c_btn.is_visible():
                 await c_btn.click()
        
        print(f"✅ [{comp_name}] Navegação inicial concluída.")
        await wait_random()
    except Exception as e:
        print(f"❌ [{comp_name}] Erro na navegação: {e}")
        raise e

async def worker_competition(context, comp_name, csv_path):
    """
    Função que roda em uma aba separada para cada competição.
    """
    print(f"🚀 [{comp_name}] Iniciando worker...")
    page = await context.new_page()
    
    try:
        await navigate_to_competition(page, comp_name)

        # Estado do Worker
        anchor_minutes = -1
        
        # Tenta carregar Anchor existente
        saved_anchor = load_anchor_time(comp_name)
        if saved_anchor:
            anchor_minutes = time_str_to_minutes(saved_anchor)
            print(f"   [{comp_name}] ⚓ Anchor carregado do arquivo: {saved_anchor}")
        
        # Flag para indicar se precisamos fazer a calibração inicial (busca do anchor + lookback)
        # Se já carregamos um anchor, assumimos que estamos em modo incremental (ou o usuário quer recalibrar sempre?)
        # O prompt diz: "ao entrar na lista... deve-se iniciar a busca...". 
        # Mas também diz: "casos de interrupção, iniciar a partir desse anchor_time".
        # Vamos assumir: Se tem arquivo, usa. Se não tem, calibra.
        need_calibration = (anchor_minutes == -1)

        # --- LOOP INFINITO DA COMPETIÇÃO ---
        while True:
            try:
                # Verifica se estamos na lista de partidas
                matches_container_selector = "#ResultsComponent > div:nth-child(3) > div"
                if not await page.is_visible(matches_container_selector):
                    print(f"⚠️ [{comp_name}] Container de partidas não visível. Reiniciando ciclo...")
                    await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                    print(f"⏳ [{comp_name}] Aguardando 30s na lista de competições...")
                    await asyncio.sleep(30)
                    await navigate_to_competition(page, comp_name)
                    continue

                now_extract = datetime.now()
                date_str = now_extract.strftime('%d/%m/%Y')
                
                # Coleta botões
                all_buttons = page.locator(f"{matches_container_selector} > button")
                count = await all_buttons.count()
                
                if count == 0:
                    print(f"   [{comp_name}] 0 partidas. Aguardando...")
                    await asyncio.sleep(POLLING_INTERVAL)
                    continue

                scraped_matches = []
                for i in range(count):
                    btn = all_buttons.nth(i)
                    text_content = await btn.inner_text()
                    lines = [l.strip() for l in text_content.split('\n') if l.strip()]
                    if not lines: continue
                    
                    # Parse Hora
                    h, m = 0, 0
                    time_str = ""
                    if len(lines) > 0:
                        parts = lines[0].split(' ', 1)
                        if len(parts) >= 1: time_str = parts[0]
                    
                    if time_str:
                        try:
                            clean_time = time_str.rstrip('.')
                            separator = '.' if '.' in clean_time else ':'
                            if separator in clean_time:
                                h_str, m_str = clean_time.split(separator)[:2]
                                h, m = int(h_str), int(m_str)
                        except: pass
                    
                    scraped_matches.append({
                        "h": h, "m": m, "btn": btn, "index": i, "time_str": time_str
                    })
                
                # Ordena (mais recente primeiro) para processamento inicial
                scraped_matches.sort(key=lambda x: (x['h'], x['m']), reverse=True)

                # --- 1. Calibração e Lookback (Executado apenas se não temos Anchor) ---
                if need_calibration:
                    print(f"   [{comp_name}] 🔍 Iniciando Calibração (Buscando maior hora com resultado)...")
                    
                    found_anchor_match = None
                    
                    # Percorre do mais recente para o mais antigo
                    for match in scraped_matches:
                        # Tenta clicar e ver se tem resultado
                        target_time = f"{match['h']:02d}:{match['m']:02d}"
                        
                        # Busca dinâmica
                        btn_locator = page.locator(f"{matches_container_selector} > button").filter(has_text=target_time).first
                        if await btn_locator.count() == 0:
                             target_time_dot = f"{match['h']:02d}.{match['m']:02d}"
                             btn_locator = page.locator(f"{matches_container_selector} > button").filter(has_text=target_time_dot).first
                        
                        if await btn_locator.count() == 0: continue

                        try:
                            await btn_locator.click(timeout=5000)
                            await wait_random()
                            res = await extract_ambos_marcam_logic(page)
                            
                            if res:
                                # ACHOU!
                                found_anchor_match = match
                                anchor_minutes = match['h'] * 60 + match['m']
                                anchor_str = minutes_to_time_str(anchor_minutes)
                                save_anchor_time(comp_name, anchor_str)
                                await save_match_data(comp_name, date_str, match['h'], match['m'], res, csv_path)
                                print(f"     [{comp_name}] ⚓ Anchor Definido: {anchor_str} (Resultado: {res})")
                                await page.go_back()
                                await wait_random()
                                break
                            
                            # Se não achou resultado, volta e tenta o próximo (mais antigo)
                            await page.go_back()
                            await wait_random()
                        except Exception as e_calib:
                            print(f"     [{comp_name}] ⚠️ Erro na calibração jogo {target_time}: {e_calib}")
                            try: await page.go_back() 
                            except: pass

                    if anchor_minutes != -1:
                        # --- Lookback Collection ---
                        # Ajuste: Coletar a partir da Hora cheia (minuto 0)
                        anchor_h = anchor_minutes // 60
                        start_h = anchor_h - LOOKBACK_HOURS
                        if start_h < 0: start_h = 0
                        limit_minutes = start_h * 60
                        
                        print(f"   [{comp_name}] 🔙 Iniciando Coleta de Lookback (A partir das {start_h:02d}:00 até {minutes_to_time_str(anchor_minutes)})...")
                        
                        # Filtra jogos entre Limit e Anchor (exclusivo do Anchor pois já coletamos)
                        lookback_matches = []
                        for m in scraped_matches:
                            m_min = m['h'] * 60 + m['m']
                            if limit_minutes <= m_min < anchor_minutes:
                                lookback_matches.append(m)
                        
                        # Ordena Lookback (pode ser do mais antigo pro novo ou vice-versa, tanto faz, vamos pegar tudo)
                        lookback_matches.sort(key=lambda x: (x['h'], x['m']), reverse=True)
                        
                        for match in lookback_matches:
                            try:
                                target_time = f"{match['h']:02d}:{match['m']:02d}"
                                btn_locator = page.locator(f"{matches_container_selector} > button").filter(has_text=target_time).first
                                if await btn_locator.count() == 0:
                                     target_time_dot = f"{match['h']:02d}.{match['m']:02d}"
                                     btn_locator = page.locator(f"{matches_container_selector} > button").filter(has_text=target_time_dot).first
                                
                                if await btn_locator.count() > 0:
                                    await btn_locator.click(timeout=5000)
                                    await wait_random()
                                    res = await extract_ambos_marcam_logic(page)
                                    if res:
                                        await save_match_data(comp_name, date_str, match['h'], match['m'], res, csv_path)
                                        print(f"     [{comp_name}] 🔙 Lookback: {match['h']:02d}:{match['m']:02d} -> {res}")
                                    await page.go_back()
                                    await wait_random()
                            except:
                                try: await page.go_back()
                                except: pass
                        
                        need_calibration = False # Calibração concluída
                    else:
                        print(f"   [{comp_name}] ⚠️ Nenhum resultado encontrado na lista para calibrar. Aguardando...")
                        await asyncio.sleep(POLLING_INTERVAL)
                        continue

                # --- 2. Coleta Incremental (Jogos > Anchor) ---
                matches_to_check = []
                for match in scraped_matches:
                    match_minutes = match['h'] * 60 + match['m']
                    if match_minutes >= anchor_minutes:
                        matches_to_check.append(match)

                # Ordena crescente (do mais antigo para o mais novo) para processar na ordem correta
                matches_to_check.sort(key=lambda x: (x['h'], x['m']))

                # [NOVO] Carregar resultados existentes para pular
                existing_results = set()
                if csv_path.exists():
                    try:
                        df_check = pd.read_csv(csv_path)
                        df_comp = df_check[df_check['Competição'] == comp_name]
                        valid_rows = df_comp[df_comp['Ambos Marcam'].notna() & (df_comp['Ambos Marcam'] != '')]
                        for _, row in valid_rows.iterrows():
                            try:
                                h_e = int(row['Hora'])
                                m_e = int(row['Minuto'])
                                existing_results.add(f"{h_e}:{m_e}")
                            except: pass
                    except: pass

                if not matches_to_check:
                    # print(f"   [{comp_name}] Nada novo acima do Anchor. Aguardando...")
                    await asyncio.sleep(POLLING_INTERVAL)
                    continue
                
                print(f"   [{comp_name}] {len(matches_to_check)} jogos INCREMENTAIS pendentes (>= {minutes_to_time_str(anchor_minutes)}).")
                
                should_restart_loop = False
                
                for match in matches_to_check:
                    # [NOVO] Verifica se já existe
                    match_key = f"{match['h']}:{match['m']}"
                    if match_key in existing_results:
                        # print(f"     [{comp_name}] ⏭️ {match_key} já coletado. Pulando.")
                        # Atualiza Anchor se necessário para não ficar preso
                        match_minutes = match['h'] * 60 + match['m']
                        if match_minutes > anchor_minutes:
                            anchor_minutes = match_minutes
                            new_anchor_str = minutes_to_time_str(anchor_minutes)
                            save_anchor_time(comp_name, new_anchor_str)
                        continue
                    try:
                        target_time = f"{match['h']:02d}:{match['m']:02d}"
                        
                        btn_locator = page.locator(f"{matches_container_selector} > button").filter(has_text=target_time).first
                        if await btn_locator.count() == 0:
                             target_time_dot = f"{match['h']:02d}.{match['m']:02d}"
                             btn_locator = page.locator(f"{matches_container_selector} > button").filter(has_text=target_time_dot).first
                        
                        if await btn_locator.count() == 0:
                            print(f"     [{comp_name}] ⚠️ Jogo {target_time} sumiu. Pulando.")
                            continue

                        await btn_locator.click(timeout=5000)
                        await wait_random()
                        
                        res = await extract_ambos_marcam_logic(page)
                        
                        if not res:
                            # --- FLUXO DE NÃO ENCONTRADO (Apenas no Incremental) ---
                            print(f"     [{comp_name}] ⚠️ {target_time} sem resultado 'Ambos Marcam'.")
                            print(f"     [{comp_name}] 🔄 Retornando à Home e aguardando 30s...")
                            
                            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
                            await asyncio.sleep(30)
                            await navigate_to_competition(page, comp_name)
                            
                            should_restart_loop = True
                            break 

                        # Salva resultado
                        await save_match_data(comp_name, date_str, match['h'], match['m'], res, csv_path)
                        print(f"     [{comp_name}] ✅ {match['h']:02d}:{match['m']:02d} -> {res}")
                        
                        # Atualiza Anchor Time
                        match_minutes = match['h'] * 60 + match['m']
                        if match_minutes > anchor_minutes:
                            anchor_minutes = match_minutes
                            new_anchor_str = minutes_to_time_str(anchor_minutes)
                            save_anchor_time(comp_name, new_anchor_str)

                        await page.go_back()
                        await wait_random()
                        
                    except Exception as e_match:
                        print(f"     [{comp_name}] ❌ Erro no jogo {match['h']}:{match['m']}: {e_match}")
                        try:
                            if not await page.is_visible(matches_container_selector):
                                await page.go_back()
                        except: pass

                if should_restart_loop:
                    continue

                await asyncio.sleep(POLLING_INTERVAL)

            except Exception as e_loop:
                print(f"❌ [{comp_name}] Erro no loop: {e_loop}")
                await asyncio.sleep(10)
                try:
                    await page.reload()
                except: pass

    except Exception as e_worker:
        print(f"❌ [{comp_name}] Falha fatal no worker: {e_worker}")

async def main():
    print(f"🚀 Iniciando Sistema Multi-Abas (teste2.py)...")
    
    # Setup Inicial (Login Único)
    async with async_playwright() as p:
        # Tenta matar processos Chrome
        import subprocess
        subprocess.run(["tasklist", "/FI", "IMAGENAME eq chrome.exe"], capture_output=True)
        
        browser = await p.chromium.launch(
            channel=BROWSER_CHANNEL,
            headless=False,
            args=["--no-default-browser-check", "--disable-infobars", "--start-maximized"]
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 720})
        
        # Scripts anti-detecção
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            if (!window.chrome) window.chrome = { runtime: {} };
        """)

        # --- FASE 1: LOGIN CENTRALIZADO ---
        page = await context.new_page()
        print(f"🌍 Navegando para Login ({TARGET_URL})...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        
        login_btn_selector = '#logged-out-container > div.mobileLoginSection > a'
        user_icon_selector = '.hm-MainHeaderMembers'  # Exemplo de seletor de usuário logado (pode variar)
        
        if await page.is_visible(login_btn_selector):
            print("🔑 Realizando Login...")
            await page.click(login_btn_selector)
            await wait_random()
            await page.fill('#txtUsername', USERNAME)
            await wait_random()
            await page.fill('#txtPassword', PASSWORD)
            await wait_random()
            await page.keyboard.press('Enter')
            
            print("⏳ Aguardando processamento do login...")
            try:
                # Espera o botão de login sumir (indica sucesso)
                await page.locator(login_btn_selector).wait_for(state="detached", timeout=30000)
                print("✅ Login efetuado (botão de login desapareceu).")
            except Exception as e:
                print(f"⚠️ Timeout ou erro aguardando login: {e}")
            
            await asyncio.sleep(5) # Buffer extra para cookies assentarem
        else:
            print("✅ Já logado (ou botão de login não encontrado).")

        # Modal de boas-vindas ou mensagens
        modal_selector = '#ResultsPage > div.modal.loggedin.hide-modal-for-members > button'
        try:
            if await page.is_visible(modal_selector, timeout=5000):
                await page.click(modal_selector)
        except: pass
        
        # Fecha a página de login, vamos abrir abas limpas para os workers
        await page.close()

        # --- FASE 2: LANÇAR WORKERS ---
        HISTORY_DIR = ROOT / "historico"
        HISTORY_DIR.mkdir(exist_ok=True)
        date_filename = datetime.now().strftime('%d-%m-%Y')
        csv_path = HISTORY_DIR / f"matches_{date_filename}.csv"

        tasks = []
        for comp in COMPETITIONS_TO_RUN:
            tasks.append(worker_competition(context, comp, csv_path))
        
        print(f"🔥 Iniciando {len(tasks)} workers concorrentes...")
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Exiting...")
