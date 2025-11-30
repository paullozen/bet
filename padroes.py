import pandas as pd
from pathlib import Path
from datetime import datetime
import time

def calcular_padroes(df):
    """
    Calcula as colunas de padrões 5x, 4x, 3x, 2x, 1x baseadas na coluna 'Ambos Marcam'.
    Lógica:
    5x: Compara com 6º anterior
    4x: Compara com 5º anterior
    3x: Compara com 4º anterior
    2x: Compara com 3º anterior
    1x: Compara com 2º anterior
    """
    # Garante que está ordenado por Competição e Horário
    # Convertendo Hora e Minuto para garantir ordenação correta
    df['Hora_Num'] = pd.to_numeric(df['Hora'], errors='coerce').fillna(0)
    df['Minuto_Num'] = pd.to_numeric(df['Minuto'], errors='coerce').fillna(0)
    
    df = df.sort_values(by=['Competição', 'Hora_Num', 'Minuto_Num'])
    
    # Função interna para aplicar em cada grupo (Competição)
    def processar_grupo(group):
        # Garante que o índice está resetado para os shifts funcionarem sequencialmente no grupo
        # Mas o shift do pandas opera na Series, então a ordem das linhas no grupo importa.
        
        am = group['Ambos Marcam']
        
        # 1x: 2º registro anterior (shift 2)
        p1x = (am == am.shift(2))
        group['1x'] = p1x.map({True: 'Sim', False: 'Não'})
        group.loc[am.shift(2).isna(), '1x'] = None # Se não tem anterior, fica vazio
        
        # 2x: 3º registro anterior (shift 3)
        p2x = (am == am.shift(3))
        group['2x'] = p2x.map({True: 'Sim', False: 'Não'})
        group.loc[am.shift(3).isna(), '2x'] = None

        # 3x: 4º registro anterior (shift 4)
        p3x = (am == am.shift(4))
        group['3x'] = p3x.map({True: 'Sim', False: 'Não'})
        group.loc[am.shift(4).isna(), '3x'] = None

        # 4x: 5º registro anterior (shift 5)
        p4x = (am == am.shift(5))
        group['4x'] = p4x.map({True: 'Sim', False: 'Não'})
        group.loc[am.shift(5).isna(), '4x'] = None

        # 5x: 6º registro anterior (shift 6)
        p5x = (am == am.shift(6))
        group['5x'] = p5x.map({True: 'Sim', False: 'Não'})
        group.loc[am.shift(6).isna(), '5x'] = None
        
        return group

    # Aplica a função agrupando por competição
    # group_keys=False para manter o índice original ou evitar multi-index desnecessário
    df_processado = df.groupby('Competição', group_keys=False).apply(processar_grupo)
    
    # Remove colunas auxiliares
    df_processado = df_processado.drop(columns=['Hora_Num', 'Minuto_Num'])
    
    return df_processado

def atualizar_arquivo_hoje():
    """
    Lê o CSV de hoje, calcula os padrões e salva novamente.
    """
    ROOT = Path(__file__).resolve().parent
    date_str = datetime.now().strftime('%d-%m-%Y')
    csv_filename = f"matches_{date_str}.csv"
    csv_path = ROOT / csv_filename
    
    if not csv_path.exists():
        print(f"⚠️ Arquivo {csv_filename} não encontrado para atualização de padrões.")
        return

    try:
        # Tenta ler o arquivo (pode ter conflito de leitura/escrita se o app2 estiver usando, então tentamos com retries simples)
        for attempt in range(3):
            try:
                df = pd.read_csv(csv_path)
                break
            except PermissionError:
                time.sleep(1)
        else:
            print("❌ Erro de permissão ao ler arquivo CSV (está aberto?).")
            return

        if df.empty:
            return

        # Calcula padrões
        df_atualizado = calcular_padroes(df)
        
        # Salva
        # Usa mode='w' para sobrescrever com as novas colunas
        for attempt in range(3):
            try:
                df_atualizado.to_csv(csv_path, index=False)
                print(f"✅ Padrões atualizados em {csv_filename}")
                break
            except PermissionError:
                time.sleep(1)
        else:
            print("❌ Erro de permissão ao salvar arquivo CSV.")

    except Exception as e:
        print(f"❌ Erro ao atualizar padrões: {e}")

if __name__ == "__main__":
    atualizar_arquivo_hoje()
