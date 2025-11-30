import asyncio
import json
import random
from pathlib import Path
from datetime import datetime
import pandas as pd

# ==========================
ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

# Valores Padrão
config = {
    "TARGET_URL": "https://extra.bet365.bet.br/results/br?li=1",
    "BROWSER_CHANNEL": "chrome",
    "COMPETITIONS": ["Euro Cup", "Premier League", "Sul Americano", "Copa do Mundo"],
    "MAX_MATCHES": 0,
    "DELAY_MIN": 0.5,
    "DELAY_MAX": 1.5,
    "POLLING_INTERVAL": 120,
    "CONSECUTIVE_NONE_LIMIT": 3,
    "REST_TIME": 120
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

# Normalização de nomes (Correção de Typos do config.json)
if "COMPETITIONS" in config:
    config["COMPETITIONS"] = [c.replace("Premiere League", "Premier League") for c in config["COMPETITIONS"]]

# USERNAME e PASSWORD vêm do config.json ou via input()
if "USERNAME" in config and "PASSWORD" in config:
    USERNAME = config["USERNAME"]
    PASSWORD = config["PASSWORD"]
    print(f"✅ Credenciais carregadas do config.json (Usuário: {USERNAME})")
else:
    print("⚠️ Credenciais não encontradas no config.json")
    USERNAME = input("Digite o usuário Bet365: ")
    PASSWORD = input("Digite a senha Bet365: ")


TARGET_URL = config["TARGET_URL"]
BROWSER_CHANNEL = config["BROWSER_CHANNEL"]
COMPETITIONS_TO_RUN = config["COMPETITIONS"]
MAX_MATCHES = config["MAX_MATCHES"]
DELAY_MIN = config["DELAY_MIN"]
DELAY_MAX = config["DELAY_MAX"]
POLLING_INTERVAL = config.get("POLLING_INTERVAL", 60)
CONSECUTIVE_NONE_LIMIT = config.get("CONSECUTIVE_NONE_LIMIT", 3)
REST_TIME = config.get("REST_TIME", 60)



# Mapeamento de competições
competitions_map = {
    "Euro Cup": "#CompetitionList > div:nth-child(3) > button > div",
    "Premier League": "#CompetitionList > div:nth-child(5) > button > div",
    "Sul Americano": "#CompetitionList > div:nth-child(6) > button > div",
    "Copa do Mundo": "#CompetitionList > div:nth-child(8) > button > div"
}

async def main():
    print(f"🚀 Launching browser...")

    
    # Tenta matar processos Chrome que possam estar usando o perfil
    print("🔍 Verificando processos Chrome existentes...")
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        try:
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/FO", "CSV"],
                capture_output=True,
                text=True
            )

            browser = await p.chromium.launch(
                channel=BROWSER_CHANNEL,
                headless=False,
                args=[
                    "--no-default-browser-check",
                    "--disable-infobars",
                    "--start-maximized"
                ]
            )
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
        except Exception as e:
            print(f"❌ Erro ao iniciar o browser: {e}")
            return

        # Scripts anti-detecção
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            if (!window.chrome) window.chrome = { runtime: {} };
        """)

        page = context.pages[0] if context.pages else await context.new_page()
        
        print(f"🌍 Navigating to {TARGET_URL}...")
        try:
            await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"⚠️ Warning during navigation: {e}")

        # ==========================
        # AUTOMAÇÃO
        # ==========================

        async def wait_random():
            delay = random.uniform(DELAY_MIN, DELAY_MAX)
            await asyncio.sleep(delay)

        # --- Função Auxiliar de Extração "Ambos Marcam" ---
        async def extract_ambos_marcam_logic(page):
            ambos_marcam = ""
            clicked_ambos = False
            
            # 1. Tenta clicar na aba/botão "Ambos Marcam"
            ambos_btn_selector = '#ResultsComponent > div:nth-child(4) > div > div.market-search > div.market-search__link-wrapper > div:nth-child(21) > button'
            
            if await page.is_visible(ambos_btn_selector):
                try:
                    await page.click(ambos_btn_selector)
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

        def get_collected_times(csv_path, target_comp):
            if not csv_path.exists():
                return set()
            try:
                df = pd.read_csv(csv_path)
                if df.empty: return set()
                df = df[df['Competição'] == target_comp]
                times = set()
                for _, row in df.iterrows():
                    try:
                        val = str(row.get('Ambos Marcam', '')).strip().lower()
                        if val not in ['', 'nan', 'none']:
                            h = int(float(row['Hora']))
                            m = int(float(row['Minuto']))
                            times.add((h, m))
                    except: pass
                return times
            except Exception as e:
                print(f"⚠️ Erro ao ler tempos coletados ({target_comp}): {e}")
                return set()

        async def extract_match_data(comp_name, lookback_hours):
            print(f"   Extraindo dados das partidas de {comp_name} (Lookback: {lookback_hours}h)...")
            try:
                now_extract = datetime.now()
                date_str = now_extract.strftime('%d/%m/%Y')

                matches_container_selector = "#ResultsComponent > div:nth-child(3) > div"
                buttons = page.locator(f"{matches_container_selector} > button")
                count = await buttons.count()
                
                if count == 0:
                    print("   ⚠️ Nenhum botão de partida encontrado.")
                    return True

                if MAX_MATCHES > 0:
                    limit = min(count, MAX_MATCHES)
                else:
                    limit = count
                    
                collected_times = get_collected_times(csv_path, comp_name)
                
                valid_indices = []
                try:
                    print("   ⏳ Analisando horários das partidas...")
                    all_buttons = page.locator(f"{matches_container_selector} > button")
                    button_texts = await all_buttons.all_inner_texts()
                    
                    parsed_matches = []
                    for idx, text in enumerate(button_texts):
                        lines = text.split('\n')
                        if lines:
                            first_part = lines[0].strip()
                            if '.' in first_part:
                                try:
                                    h_str, m_str = first_part.split('.')[:2]
                                    if " " in h_str: h_str = h_str.split(" ")[0]
                                    if " " in m_str: m_str = m_str.split(" ")[0]
                                    h, m = int(h_str), int(m_str)
                                    parsed_matches.append((idx, h, m))
                                except: pass
                    
                    if parsed_matches:
                        max_h_page = max(p[1] for p in parsed_matches)
                        min_h_page = max_h_page - lookback_hours
                        if min_h_page < 0: min_h_page = 0
                        
                        print(f"   🕒 Filtro de Janela: [{min_h_page}h - {max_h_page}h].")
                        
                        filtered_indices = []
                        for pm in parsed_matches:
                            idx, ph, pm_min = pm
                            if not (min_h_page <= ph <= max_h_page):
                                continue
                            if (ph, pm_min) in collected_times:
                                continue
                            filtered_indices.append(idx)
                        
                        valid_indices = filtered_indices
                        print(f"   🎯 {len(valid_indices)} NOVAS partidas encontradas (não coletadas).")
                    else:
                        print("   ⚠️ Não foi possível extrair horários. Usando limite padrão.")
                        valid_indices = range(limit)

                except Exception as e_filter:
                    print(f"   ❌ Erro no filtro de horário: {e_filter}. Usando limite padrão.")
                    valid_indices = range(limit)

                print(f"   Processando {len(valid_indices)} partidas selecionadas.")
                
                consecutive_none_count = 0

                for i in valid_indices:
                    if not await page.is_visible(matches_container_selector):
                        print("   ⚠️ Container de partidas sumiu. Retornando False...")
                        return False

                    try:
                        buttons = page.locator(f"{matches_container_selector} > button")
                        btn = buttons.nth(i)
                        
                        # Extrai info básica
                        text_content = await btn.inner_text()
                        lines = [l.strip() for l in text_content.split('\n') if l.strip()]
                        
                        if len(lines) < 2:
                            continue
                        
                        # Inicializa variáveis
                        hour, minute = 0, 0
                        team1, team2 = "Time1", "Time2"
                        time_str = ""

                        # Cenário A: 3 linhas (Hora, Time1, Time2)
                        if len(lines) >= 3:
                            time_str = lines[0]
                            team1 = lines[1]
                            team2 = lines[2]
                        
                        # Cenário B: 2 linhas
                        elif len(lines) == 2:
                            # Verifica se a primeira linha tem formato "HH.MM Time1"
                            # Ex: "3.02 Inglaterra"
                            line0 = lines[0]
                            line1 = lines[1]
                            
                            # Tenta separar Hora e Time1 pelo primeiro espaço
                            parts = line0.split(' ', 1)
                            if len(parts) == 2 and ('.' in parts[0] or ':' in parts[0]):
                                time_str = parts[0]
                                team1 = parts[1]
                                team2 = line1
                            else:
                                # Fallback: Formato antigo "Hora \n Time1 v Time2"
                                time_str = line0
                                if " v " in line1:
                                    team1, team2 = line1.split(" v ")
                                elif " x " in line1:
                                    team1, team2 = line1.split(" x ")
                                else:
                                    team1 = line1 # Assume que a linha 2 é só o time 1? Ou mantém Time2 default
                        
                        # Parse Hora/Minuto a partir de time_str
                        if time_str:
                            try:
                                # Remove pontos finais se houver (ex: "3.02.")
                                clean_time = time_str.rstrip('.')
                                separator = '.' if '.' in clean_time else ':'
                                if separator in clean_time:
                                    h_str, m_str = clean_time.split(separator)[:2]
                                    hour = int(h_str)
                                    minute = int(m_str)
                            except: pass
                        
                        match_info = f"{team1} x {team2}"
                        match_key = (comp_name, str(hour), str(minute), match_info)
                        
                        if match_key in existing_keys:
                            continue

                        print(f"   Processando partida {i+1}/{count}: {team1} x {team2} ({hour}:{minute})")
                        try:
                            await btn.click()
                            await wait_random()

                            ambos_marcam = await extract_ambos_marcam_logic(page)
                            
                            if not ambos_marcam or ambos_marcam.strip() == '':
                                print(f"     ⚠️ 'Ambos Marcam' não encontrado. Não salvando.")
                                consecutive_none_count += 1
                                
                                if consecutive_none_count >= CONSECUTIVE_NONE_LIMIT:
                                    print(f"   🛑 Limite de vazios atingido ({CONSECUTIVE_NONE_LIMIT}). Executando reset solicitado...")
                                    
                                    await asyncio.sleep(1)
                                    # 1. Clicar no botão especificado (Reset/Fechar)
                                    try:
                                        reset_selector = '#ResultsPage > div.home-page > main > div:nth-child(3) > div > div > button'
                                        if await page.is_visible(reset_selector):
                                            await page.click(reset_selector)
                                            print("   🔘 Botão de reset clicado.")
                                    except Exception as e_r1:
                                        print(f"   ⚠️ Erro ao clicar no reset: {e_r1}")

                                    # 2. Clicar no botão de voltar para competições
                                    try:
                                        back_selector = '#ResultsComponent > div.result-page__bread-crumb-wrapper > button:nth-child(3)'
                                        await page.click(back_selector)
                                        print("   🔙 Retornando para lista de competições...")
                                    except Exception as e_r2:
                                        print(f"   ⚠️ Erro ao voltar para competições: {e_r2}")
                                    
                                    return "SKIP"
                                
                                await page.go_back()
                                delay = random.uniform(DELAY_MIN, DELAY_MAX)
                                await asyncio.sleep(delay)
                                continue
                            
                            consecutive_none_count = 0
                            print(f"     Resultado: Ambos Marcam = '{ambos_marcam}'")
                            
                            match_info_dict = {
                                "Data": date_str,
                                "Competição": comp_name,
                                "Hora": hour,
                                "Minuto": minute,
                                "Times": f"{team1} x {team2}",
                                "Ambos Marcam": ambos_marcam
                            }
                            
                            try:
                                if csv_path.exists():
                                    df_current = pd.read_csv(csv_path)
                                    df_current['Hora'] = df_current['Hora'].astype(str)
                                    df_current['Minuto'] = df_current['Minuto'].astype(str)
                                else:
                                    df_current = pd.DataFrame(columns=["Data", "Competição", "Hora", "Minuto", "Times", "Ambos Marcam"])

                                mask = (
                                    (df_current['Competição'] == comp_name) &
                                    (df_current['Hora'] == str(hour)) &
                                    (df_current['Minuto'] == str(minute)) &
                                    (df_current['Times'] == f"{team1} x {team2}")
                                )

                                if mask.any():
                                    existing_val = df_current.loc[mask, 'Ambos Marcam'].values[0]
                                    is_existing_empty = pd.isna(existing_val) or str(existing_val).strip() == '' or str(existing_val).lower() == 'nan'
                                    if is_existing_empty:
                                        df_current.loc[mask, 'Ambos Marcam'] = ambos_marcam
                                        print(f"     🔄 Registro vazio atualizado no CSV.")
                                    else:
                                        print(f"     ℹ️ Registro já possui valor ('{existing_val}'). Mantendo original.")
                                else:
                                    new_row = pd.DataFrame([match_info_dict])
                                    df_current = pd.concat([df_current, new_row], ignore_index=True)
                                    print(f"     💾 Novo jogo salvo no CSV.")

                                df_current.to_csv(csv_path, index=False, encoding='utf-8-sig')
                                
                            except Exception as e_save:
                                print(f"     ❌ Erro ao salvar/atualizar CSV: {e_save}")

                            existing_keys.add(match_key)
                            await page.go_back()
                            delay = random.uniform(DELAY_MIN, DELAY_MAX)
                            await asyncio.sleep(delay)
                            
                        except Exception as e_match:
                            print(f"❌ Erro ao processar partida {i}: {e_match}")
                            await page.go_back()

                    except Exception as e_btn:
                         print(f"❌ Erro ao acessar botão {i}: {e_btn}")
                         if not await page.is_visible(matches_container_selector):
                             return False

            except Exception as e:
                print(f"❌ Erro na extração: {e}")
                return False
            
            return True

        # --- Função Auxiliar de Navegação ---
        async def ensure_competition_list(page):
            # 1. Verifica se já está na lista
            if await page.is_visible("#CompetitionList"):
                return True
            
            print("   ⚠️ Lista de competições não visível. Tentando recuperar...")
            
            # 2. Tenta voltar (caso esteja dentro de uma competição ou jogo)
            try:
                back_btn = '#ResultsComponent > div.result-page__bread-crumb-wrapper > button:nth-child(3)'
                if await page.is_visible(back_btn):
                    print("   🔙 Clicando no botão voltar...")
                    await page.click(back_btn)
                    await asyncio.sleep(2)
                    if await page.is_visible("#CompetitionList"): return True
            except: pass

            # 3. Tenta clicar em Futebol Virtual na lista de esportes (caso tenha voltado demais)
            try:
                fv_selector = '#ResultsSportsList > div:nth-child(43) > button > div'
                if await page.is_visible(fv_selector):
                    print("   Clicando em Futebol Virtual (Recuperação)...")
                    await page.click(fv_selector)
                    await asyncio.sleep(2)
                    if await page.is_visible("#CompetitionList"): return True
            except: pass
            
            return False

        # --- Loop Principal de Navegação e Coleta ---
        print("\n--- Iniciando Loop Principal ---")
        
        # Variáveis globais de estado
        HISTORY_DIR = ROOT / "historico"
        HISTORY_DIR.mkdir(exist_ok=True)

        date_filename = datetime.now().strftime('%d-%m-%Y')
        csv_filename = f"matches_{date_filename}.csv"
        csv_path = HISTORY_DIR / csv_filename
        existing_keys = set()
        
        # Verifica se precisa de catchup (5 horas)
        initial_catchup = True
        if csv_path.exists():
            try:
                df_check = pd.read_csv(csv_path)
                if not df_check.empty:
                    initial_catchup = False
                    print("✅ Dados já existem para hoje. Usando janela padrão de 3h.")
                    # Carrega chaves existentes
                    for _, row in df_check.iterrows():
                        ambos_val = str(row.get('Ambos Marcam', '')).strip()
                        if ambos_val and ambos_val.lower() != 'nan':
                            key = (str(row['Competição']), str(row['Hora']), str(row['Minuto']), str(row['Times']))
                            existing_keys.add(key)
            except: pass
        
        if initial_catchup:
            print("⚠️ Nenhum dado encontrado para hoje. Usando janela estendida de 5h.")

        while True:
            try:
                # --- SMART SETUP: Verifica se já estamos prontos ---
                setup_needed = True
                if await page.is_visible("#CompetitionList"):
                    print("\n✅ Já estamos na lista de competições. Pulando setup inicial...")
                    setup_needed = False
                
                if setup_needed:
                    # 1. Login
                    print("\n1. Verificando Login...")
                    login_btn_selector = '#logged-out-container > div.mobileLoginSection > a'
                    if await page.is_visible(login_btn_selector):
                        print("   Botão de login encontrado. Iniciando login...")
                        await page.click(login_btn_selector)
                        await wait_random()
                        await page.fill('#txtUsername', USERNAME)
                        await wait_random()
                        await page.fill('#txtPassword', PASSWORD)
                        await wait_random()
                        await page.keyboard.press('Enter')
                        await wait_random()
                    
                    # 5. Modal
                    print("5. Verificando modal...")
                    await asyncio.sleep(5)
                    modal_selector = '#ResultsPage > div.modal.loggedin.hide-modal-for-members > button'
                    if await page.is_visible(modal_selector, timeout=3000):
                        await page.click(modal_selector)
                        print("   Modal clicado.")
                    
                    # 6. Encontrar Resultado (Ponto de Retorno)
                    print("6. Navegando para 'Encontrar um Resultado'...")
                    find_result_selector = '#ResultsComponent > div.home-page__inner > button > div'
                    
                    # Se não achar o botão, tenta ir para a URL base primeiro
                    if not await page.is_visible(find_result_selector):
                        print("   Botão não visível. Recarregando página...")
                        await page.goto(TARGET_URL)
                        await asyncio.sleep(3)
                    
                    if await page.is_visible(find_result_selector):
                        await page.click(find_result_selector)
                    else:
                        # Tenta busca por texto se seletor falhar
                        print("   Seletor falhou. Tentando texto 'Encontrar um Resultado'...")
                        found_btn = page.get_by_text("Encontrar um Resultado").first
                        if await found_btn.is_visible():
                            await found_btn.click()
                        else:
                            print("❌ Não foi possível encontrar 'Encontrar um Resultado'. Reiniciando loop...")
                            continue # Retorna ao início do while True
                    
                    await wait_random()

                    # 7. Futebol Virtual
                    print("7. Selecionando 'Futebol Virtual'...")
                    fv_selector = '#ResultsSportsList > div:nth-child(43) > button > div'
                    fv_clicked = False
                    
                    if await page.is_visible(fv_selector):
                        await page.click(fv_selector)
                        fv_clicked = True
                    else:
                        # Procura na lista
                        print("   Seletor direto falhou. Procurando na lista...")
                        try:
                            fv_btn = page.locator("#ResultsSportsList").get_by_text("Futebol Virtual").first
                            if await fv_btn.is_visible():
                                await fv_btn.click()
                                fv_clicked = True
                        except: pass
                    
                    if not fv_clicked:
                        print("❌ Falha ao selecionar Futebol Virtual. Reiniciando loop...")
                        continue

                    await wait_random()

                    # 8. Data
                    print("8. Configurando Data...")
                    try:
                        now = datetime.now()
                        current_day = now.day
                        
                        # Mês/Ano
                        month_selector = '#ResultsDatePicker > div > div.date-picker__selector-wrapper > div.date-picker__selector > div.date-picker__month > div'
                        if await page.is_visible(month_selector):
                            print(f"   Mês/Ano: {await page.inner_text(month_selector)}")
                        
                        # Dia
                        dates_container_selector = '#ResultsDatePicker > div > div.date-picker__selector-wrapper > div.date-picker__selector > div.date-picker__dates'
                        dates_container = page.locator(dates_container_selector)
                        day_locator = dates_container.get_by_text(str(current_day), exact=True)
                        
                        await day_locator.wait_for(state="visible", timeout=5000)
                        await day_locator.click(force=True)
                        print(f"   Dia {current_day} selecionado.")
                        await day_locator.click()
                        
                        # 9. Confirmar
                        await page.click('#ResultsDatePicker > div > button')
                        await wait_random()
                    except Exception as e_date:
                        print(f"❌ Erro na configuração de data: {e_date}. Reiniciando loop...")
                        continue

                # 10. Competições
                print("10. Iniciando Coleta das Competições...")
                if not await ensure_competition_list(page):
                    print("❌ Lista de competições não visível após setup. Reiniciando loop...")
                    continue

                skips_in_cycle = 0
                
                # Loop de competições
                for comp_name in COMPETITIONS_TO_RUN:
                    # Verifica novamente se estamos na lista antes de tentar entrar
                    if not await ensure_competition_list(page):
                        print("❌ Perda de navegação (Lista não visível). Reiniciando fluxo...")
                        raise Exception("Navigation Lost - List Check")

                    print(f"\n🏆 Acessando: {comp_name}")
                    comp_selector = competitions_map.get(comp_name)
                    
                    # Tenta clicar na competição
                    comp_clicked = False
                    
                    # Seletor
                    if comp_selector and await page.is_visible(comp_selector):
                        await page.click(comp_selector)
                        comp_clicked = True
                    else:
                        # Texto
                        try:
                            # Mapeamento de nomes alternativos se necessário
                            search_name = comp_name
                            if comp_name == "Sul Americano": search_name = "Super Liga Sul-Americana"
                            
                            c_btn = page.locator("#CompetitionList").get_by_text(search_name).first
                            if await c_btn.is_visible():
                                await c_btn.click()
                                comp_clicked = True
                        except: pass
                    
                    if not comp_clicked:
                        print(f"⚠️ Não foi possível entrar em {comp_name}. Pulando...")
                        print("❌ Falha crítica de navegação. Retornando ao início do fluxo...")
                        raise Exception("Navigation Lost") 

                    await wait_random()
                    
                    # Coleta
                    lookback = 5 if initial_catchup else 3
                    result = await extract_match_data(comp_name, lookback)
                    
                    if result == "SKIP":
                        print(f"⚠️ Competição {comp_name} pulada devido a falhas consecutivas.")
                        skips_in_cycle += 1
                        continue # Já voltou para a lista de competições dentro da função
                    
                    if not result:
                        print("⚠️ Coleta falhou ou perdeu navegação. Reiniciando fluxo...")
                        raise Exception("Collection Failed")

                    # Voltar para lista de competições (Caso Normal)
                    print("   🔙 Voltando para lista de competições...")
                    back_btn = '#ResultsComponent > div.result-page__bread-crumb-wrapper > button:nth-child(3)'
                    if await page.is_visible(back_btn):
                        await page.click(back_btn)
                    else:
                        raise Exception("Navigation Lost on Back")
                    
                    await wait_random()

                if skips_in_cycle == len(COMPETITIONS_TO_RUN):
                    print("🛑 Todas as competições falharam (Regra dos 3). Aguardando 120s na lista...")
                    # Garante que estamos na lista
                    await ensure_competition_list(page)
                    await asyncio.sleep(120)
                    # O loop reinicia, e o 'setup_needed' será False, pulando login/data
                else:
                    print(f"💤 Ciclo completo. Aguardando {POLLING_INTERVAL}s...")
                    await asyncio.sleep(POLLING_INTERVAL)
                
                # Após o primeiro ciclo com sucesso, não é mais catchup
                initial_catchup = False

            except Exception as e:
                print(f"🔄 Erro no fluxo principal: {e}")
                print("   Reiniciando do passo 6 (ou Login)...")
                await asyncio.sleep(2)
                # O loop while True irá reiniciar
                try:
                    await page.goto(TARGET_URL)
                except: pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Exiting...")
