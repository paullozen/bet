import streamlit as st
import pandas as pd
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime

# --- IMPORTAÇÃO DE MÓDULOS ---
import padroes # Para calcular colunas 5x, 4x, etc.

# ==========================
# CONFIGURATION
# ==========================
ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
APP_SCRIPT = ROOT / "app.py" # O script do scraper

st.set_page_config(
    page_title="Bet365 Automation",
    page_icon="⚽",
    layout="wide"
)

st.title("⚽ Automação Futebol Virtual")

# ==========================
# SIDEBAR
# ==========================
with st.sidebar:
    st.header("Configurações")
    username = st.text_input("Usuário Bet365", value="Douglas_lima3")
    password = st.text_input("Senha Bet365", type="password", value="#Carnaval20")
    
    st.divider()
    
    # --- SELEÇÃO DE PADRÕES ---
    st.header("Padrões")
    # Usando radio para seleção única e imediata
    padrao_selecionado = st.radio(
        "Selecione a Visualização:",
        options=["Resultados", "5x", "4x", "3x", "2x", "1x"],
        index=0
    )
    
    st.divider()
    
    # --- VISUALIZAÇÃO ---
    st.header("Filtros")
    selected_date = st.date_input("Filtrar por Data", value=datetime.now())
    
    # Filtro Últimas Horas
    ultimas_horas = st.number_input("Últimas Horas (X)", min_value=0, value=0, step=1, help="Mostra as últimas X+1 linhas")

# ==========================
# ÁREA PRINCIPAL - CONTROLE
# ==========================
col1, col2 = st.columns(2)

# Lógica de Controle de Processo
if "process_pid" not in st.session_state:
    st.session_state.process_pid = None

def is_process_running(pid):
    if pid is None: return False
    try:
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True)
        return str(pid) in result.stdout
    except:
        return False

with col1:
    if st.button("▶️ Iniciar Automação", type="primary", use_container_width=True):
        if st.session_state.process_pid and is_process_running(st.session_state.process_pid):
            st.warning("Automação já está rodando!")
        else:
            # Salvar Configurações
            config = {
                "USERNAME": username,
                "PASSWORD": password,
                "TARGET_URL": "https://extra.bet365.bet.br/results/br?li=1",
                "BROWSER_CHANNEL": "chrome",
                "COMPETITIONS": ["Euro Cup", "Premier League", "Sul Americano", "Copa do Mundo"],
                "MAX_MATCHES": 0,
                "DELAY_MIN": 0.5,
                "DELAY_MAX": 1.5
            }
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4)
            
            try:
                process = subprocess.Popen(
                    ["python", str(APP_SCRIPT)],
                    cwd=str(ROOT),
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                st.session_state.process_pid = process.pid
                st.success(f"Iniciado! PID: {process.pid}")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao iniciar: {e}")

with col2:
    if st.session_state.process_pid and is_process_running(st.session_state.process_pid):
        if st.button("🛑 Parar Automação", type="primary", use_container_width=True):
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(st.session_state.process_pid)])
                st.session_state.process_pid = None
                st.success("Parado.")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao parar: {e}")
        st.info(f"🔄 Rodando (PID: {st.session_state.process_pid})")
    else:
        st.info("Nenhum processo rodando.")

# ==========================
# VISUALIZAÇÃO DE DADOS
# ==========================
date_str = selected_date.strftime('%d-%m-%Y')
csv_filename = f"matches_{date_str}.csv"
csv_path = ROOT / csv_filename

st.divider()
st.subheader(f"📅 Dados de {date_str} - Visualizando: {padrao_selecionado}")

if csv_path.exists():
    # st.success(f"Arquivo carregado: {csv_filename}")
    
    try:
        df = pd.read_csv(csv_path)
        
        # Limpeza
        df['Hora'] = pd.to_numeric(df['Hora'], errors='coerce').fillna(0).astype(int)
        df['Minuto'] = pd.to_numeric(df['Minuto'], errors='coerce').fillna(0).astype(int)
        
        # --- CÁLCULO DE PADRÕES (ON-THE-FLY) ---
        # Garante que as colunas existam mesmo que o CSV não tenha sido atualizado pelo app2
        df = padroes.calcular_padroes(df)
        
        # --- MATRIZES (GRID 2x2) ---
        st.header("🎨 Matrizes por Competição")
        
        competitions = df['Competição'].unique()
        
        # Grid 2x2
        cols = st.columns(2)
        
        for i, comp in enumerate(competitions):
            col = cols[i % 2]
            with col:
                st.subheader(f"🏆 {comp}")
                df_comp = df[df['Competição'] == comp]
                
                if df_comp.empty:
                    st.info("Sem dados.")
                    continue
                
                try:
                    # Define qual coluna usar como valor
                    coluna_valor = padrao_selecionado
                    
                    # Verifica se a coluna existe (segurança)
                    if coluna_valor not in df_comp.columns:
                        coluna_valor = 'Ambos Marcam'
                    
                    matrix = df_comp.pivot_table(index='Hora', columns='Minuto', values=coluna_valor, aggfunc='first')
                    
                    # Limpeza de colunas vazias (>80%)
                    threshold = 0.8
                    matrix = matrix.loc[:, matrix.isnull().mean() < threshold]
                    
                    # Ordenação
                    matrix = matrix.sort_index(ascending=False)
                    matrix = matrix.sort_index(axis=1, ascending=True)
                    
                    # Filtro Últimas Horas
                    if ultimas_horas > 0:
                        limit = ultimas_horas + 1
                        matrix = matrix.head(limit)
                    
                    def color_cell(val):
                        if val == 'Sim': return 'background-color: #28a745; color: white'
                        elif val == 'Não': return 'background-color: #dc3545; color: white'
                        return 'background-color: #6c757d; color: white'

                    st.dataframe(matrix.style.map(color_cell), use_container_width=True)
                except Exception as e:
                    st.error(f"Erro na matriz: {e}")
                
                st.divider()
        
        # --- TABELA GERAL (EMBAIXO) ---
        st.header("📋 Tabela Geral de Jogos")
        
        # Mostra colunas relevantes
        cols_to_show = ['Data', 'Competição', 'Hora', 'Minuto', 'Times', 'Ambos Marcam']
        # Adiciona as colunas de padrões se existirem
        for p in ['5x', '4x', '3x', '2x', '1x']:
            if p in df.columns:
                cols_to_show.append(p)
                
        df_sorted = df[cols_to_show].sort_values(by=['Hora', 'Minuto'], ascending=[False, False])
        st.dataframe(df_sorted, use_container_width=True)
            
    except Exception as e:
        st.error(f"Erro ao ler CSV: {e}")
else:
    st.warning(f"Nenhum arquivo encontrado para a data {date_str} ({csv_filename}).")