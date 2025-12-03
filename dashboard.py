from nicegui import ui, app
import pandas as pd
import subprocess
import json
import time
from pathlib import Path
from datetime import datetime
import asyncio
import sys

# --- IMPORTAÇÃO DE MÓDULOS ---
import padroes

# ==========================
# CONFIGURATION
# ==========================
ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
APP_SCRIPT = ROOT / "app.py"

# Global State
class State:
    def __init__(self):
        self.process = None
        self.process_pid = None
        self.config = {}
        self.load_config()
        self.selected_date = datetime.now().strftime('%Y-%m-%d')
        self.selected_pattern = "Resultados"
        self.lookback_hours = 5
        self.last_csv_hash = None
        self.df = pd.DataFrame()
        self.anchor_hour = ""

    def set_global_anchor(self):
        if not self.anchor_hour:
            ui.notify("Digite uma hora válida!", type="warning")
            return
        
        try:
            # Validate integer
            h = int(self.anchor_hour)
            if h < 0 or h > 23: raise ValueError
            
            # Create JSON
            anchor_data = {}
            # Default competitions list (should match app.py)
            comps = self.config.get("COMPETITIONS", ["Euro Cup", "Premier League", "Sul Americano", "Copa do Mundo"])
            
            time_str = f"{h:02d}.00"
            for c in comps:
                anchor_data[c] = time_str
            
            # Save to anchor_time/anchor_time_[YYYY-MM-DD].json
            # Note: The request says "criada com a data do dia" (created with today's date)
            today_str = datetime.now().strftime('%Y-%m-%d')
            anchor_dir = ROOT / "anchor_time"
            anchor_dir.mkdir(exist_ok=True)
            anchor_file = anchor_dir / f"anchor_time_{today_str}.json"
            
            with open(anchor_file, "w", encoding="utf-8") as f:
                json.dump(anchor_data, f, indent=4)
                
            ui.notify(f"Anchor Time definido para {time_str} em {today_str}", type="positive")
            
        except Exception as e:
            ui.notify(f"Erro ao definir Anchor: {e}", type="negative")

    def load_config(self):
        self.config = {
            "USERNAME": "Douglas_lima3",
            "PASSWORD": "#Carnaval20",
            "LOOKBACK_HOURS": 5
        }
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    self.config.update(saved)
            except: pass
        self.lookback_hours = self.config.get("LOOKBACK_HOURS", 5)

    def save_config(self):
        # Update config object from UI inputs before saving
        # (UI inputs will bind directly to self.config dict or specific attrs)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)
        ui.notify("Configurações salvas!", type="positive")

    def is_process_running(self):
        if self.process_pid is None: return False
        try:
            # Windows tasklist check
            result = subprocess.run(["tasklist", "/FI", f"PID eq {self.process_pid}"], capture_output=True, text=True)
            return str(self.process_pid) in result.stdout
        except:
            return False

    async def start_process(self):
        if self.is_process_running():
            ui.notify("Automação já está rodando!", type="warning")
            return

        self.save_config() # Save before starting
        
        try:
            # Using Popen to start independent process
            self.process = subprocess.Popen(
                [sys.executable, str(APP_SCRIPT)],
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            self.process_pid = self.process.pid
            ui.notify(f"Iniciado! PID: {self.process_pid}", type="positive")
        except Exception as e:
            ui.notify(f"Erro ao iniciar: {e}", type="negative")

    async def stop_process(self):
        if self.process_pid and self.is_process_running():
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(self.process_pid)])
                self.process_pid = None
                ui.notify("Parado.", type="positive")
            except Exception as e:
                ui.notify(f"Erro ao parar: {e}", type="negative")
        else:
            ui.notify("Nenhum processo rodando.", type="info")

state = State()

# ==========================
# UI LAYOUT
# ==========================
@ui.page('/')
def main_page():
    ui.dark_mode().enable()
    ui.colors(primary='#28a745', secondary='#6c757d', accent='#17a2b8', positive='#21ba45')

    # --- HEADER ---
    with ui.header().classes(replace='row items-center') as header:
        ui.icon('sports_soccer', size='md', color='white')
        ui.label('Automação Futebol Virtual').classes('text-h6 text-white')
        ui.space()
        status_label = ui.label('Parado').classes('text-white text-bold')

    # --- SIDEBAR ---
    with ui.left_drawer(value=True).classes('bg-grey-9') as drawer:
        ui.label('Configurações').classes('text-h6 q-mb-md')
        
        ui.input('Usuário Bet365').bind_value(state.config, 'USERNAME')
        ui.input('Senha Bet365', password=True).bind_value(state.config, 'PASSWORD')
        ui.number('Janela (Horas)', min=1).bind_value(state.config, 'LOOKBACK_HOURS')
        
        ui.button('Salvar Config', on_click=state.save_config).classes('full-width q-mt-md')
        
        ui.separator().classes('q-my-md')
        
        # --- ANCHOR TIME SETTINGS ---
        ui.label('Definir Anchor Time').classes('text-h6')
        ui.input('Hora (Ex: 14)').bind_value(state, 'anchor_hour')
        ui.button('Setar Anchor Geral', on_click=state.set_global_anchor).classes('full-width q-mt-sm')

        ui.separator().classes('q-my-md')
        
        ui.label('Visualização').classes('text-h6')
        
        # Dynamic Date Selector based on CSV files
        def get_csv_dates():
            files = sorted(list((ROOT / "historico").glob("matches_*.csv")), reverse=True)
            options = {}
            for f in files:
                # filename: matches_DD-MM-YYYY.csv
                try:
                    date_part = f.stem.replace("matches_", "")
                    # Convert to YYYY-MM-DD for internal state consistency
                    dt = datetime.strptime(date_part, "%d-%m-%Y")
                    val = dt.strftime("%Y-%m-%d")
                    label = dt.strftime("%d/%m/%Y")
                    options[val] = label
                except: pass
            return options

        ui.select(options=get_csv_dates(), label='Selecionar Data').bind_value(state, 'selected_date')
        
        ui.label('Padrões').classes('q-mt-sm')
        ui.radio(["Resultados", "5x", "4x", "3x", "2x", "1x"]).bind_value(state, 'selected_pattern')

    # --- MAIN CONTENT ---
    with ui.column().classes('w-full q-pa-md'):
        
        # Control Buttons
        with ui.row().classes('w-full q-mb-md'):
            ui.button('Iniciar Automação', on_click=state.start_process, icon='play_arrow').props('color=positive')
            ui.button('Parar Automação', on_click=state.stop_process, icon='stop').props('color=negative')

        # Matrices Container
        matrices_container = ui.column().classes('w-full')

        # General Table Container
        ui.label('Tabela Geral').classes('text-h5 q-mt-lg')
        table_container = ui.column().classes('w-full')

    # --- UPDATE LOGIC ---
    def update_dashboard():
        # Update Status Label
        if state.is_process_running():
            status_label.text = f"Rodando (PID: {state.process_pid})"
            status_label.classes(replace='text-green-3 text-bold')
        else:
            status_label.text = "Parado"
            status_label.classes(replace='text-red-3 text-bold')

        # Load Data
        try:
            # Convert YYYY-MM-DD to DD-MM-YYYY for filename
            d = datetime.strptime(state.selected_date, '%Y-%m-%d')
            date_str = d.strftime('%d-%m-%Y')
            csv_filename = f"matches_{date_str}.csv"
            csv_path = ROOT / "historico" / csv_filename

            if not csv_path.exists():
                matrices_container.clear()
                table_container.clear()
                with matrices_container:
                    ui.label(f"Nenhum dado para {date_str}").classes('text-grey')
                return

            # Read CSV with Retry Logic (Handle File Locking)
            df = None
            for _ in range(3):
                try:
                    df = pd.read_csv(csv_path)
                    break
                except Exception:
                    time.sleep(0.1)
            
            if df is None:
                print(f"⚠️ Could not read CSV {csv_filename} (Locked?)")
                return # Skip this update cycle

            if df.empty:
                return

            # Basic Cleaning
            df['Hora'] = pd.to_numeric(df['Hora'], errors='coerce').fillna(0).astype(int)
            df['Minuto'] = pd.to_numeric(df['Minuto'], errors='coerce').fillna(0).astype(int)
            
            # Check required columns
            if 'Ambos Marcam' not in df.columns:
                return

            # Calculate Patterns (Suppress FutureWarning if any)
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = padroes.calcular_padroes(df)
            
            # --- REBUILD MATRICES ---
            matrices_container.clear()
            with matrices_container:
                ui.label("Matrizes por Competição").classes('text-h5')
                
                competitions = df['Competição'].unique()
                for comp in competitions:
                    with ui.card().classes('w-full q-mb-md'):
                        ui.label(f"🏆 {comp}").classes('text-h6 q-pa-sm')
                        
                        df_comp = df[df['Competição'] == comp]
                        if df_comp.empty: continue

                        col_val = state.selected_pattern
                        if col_val not in df_comp.columns: col_val = 'Ambos Marcam'

                        # Pivot
                        matrix = df_comp.pivot_table(index='Hora', columns='Minuto', values=col_val, aggfunc='first')
                        
                        # Sort
                        matrix = matrix.sort_index(ascending=False)
                        matrix = matrix.sort_index(axis=1, ascending=True)

                        # Custom HTML Table Builder
                        html = '<table style="width:100%; border-collapse: collapse; text-align: center;">'
                        
                        # Header
                        html += '<thead><tr><th>Hora</th>'
                        for col in matrix.columns:
                            html += f'<th style="padding: 4px; border: 1px solid #444;">{col}</th>'
                        html += '</tr></thead><tbody>'
                        
                        # Rows
                        for idx, row in matrix.iterrows():
                            html += f'<tr><td style="font-weight:bold; border: 1px solid #444;">{idx}</td>'
                            for col in matrix.columns:
                                val = row.get(col, '')
                                bg_color = '#1d1d1d'
                                color = '#fff'
                                if val == 'Sim': 
                                    bg_color = '#28a745'
                                    color = '#fff'
                                elif val == 'Não': 
                                    bg_color = '#dc3545'
                                    color = '#fff'
                                elif pd.isna(val):
                                    bg_color = '#333'
                                else:
                                    bg_color = '#6c757d'
                                    color = '#fff'
                                
                                display_val = val if not pd.isna(val) else ''
                                html += f'<td style="background-color: {bg_color}; color: {color}; border: 1px solid #444; padding: 4px;">{display_val}</td>'
                            html += '</tr>'
                        html += '</tbody></table>'
                        
                        ui.html(html, sanitize=False).classes('w-full')

            # --- REBUILD GENERAL TABLE ---
            table_container.clear()
            with table_container:
                cols_to_show = ['Data', 'Competição', 'Hora', 'Minuto', 'Ambos Marcam']
                for p in ['5x', '4x', '3x', '2x', '1x']:
                    if p in df.columns: cols_to_show.append(p)
                
                df_sorted = df[cols_to_show].sort_values(by=['Hora', 'Minuto'], ascending=[False, False])
                
                # Convert to list of dicts for ui.table
                rows = df_sorted.to_dict('records')
                columns = [{'name': c, 'label': c, 'field': c, 'sortable': True} for c in cols_to_show]
                
                ui.table(columns=columns, rows=rows, pagination=10).classes('w-full')

        except Exception as e:
            print(f"Error updating: {e}")
            # ui.notify(f"Erro na atualização: {e}", type="negative") # Suppress UI notify for transient errors

    # Timer for auto-refresh (every 3 seconds)
    ui.timer(3.0, update_dashboard)

ui.run(title='Bet365 Auto', port=8080, reload=False)
