import os
import json
import time
import pandas as pd
import pytz
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- 1. CONFIGURAÇÃO DO NAVEGADOR ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# --- 2. DICIONÁRIOS E CONFIGURAÇÕES ---
url = "https://www.ipma.pt/pt/riscoincendio/rcm.pt/"
concelhos_dico = {
    "1601": "Arcos de Valdevez", "1602": "Caminha", "1603": "Melgaço",
    "1604": "Monção", "1605": "Paredes de Coura", "1606": "Ponte da Barca",
    "1607": "Ponte de Lima", "1608": "Valença", "1609": "Viana do Castelo",
    "1610": "Vila Nova de Cerveira"
}

dict_vento = {1: "Fraco", 2: "Moderado", 3: "Forte", 4: "Muito Forte"}
dict_chuva = {0: "Sem chuva", 1: "Chuva fraca", 2: "Chuva moderada", 3: "Chuva forte"}
dict_risco = {1: "Reduzido", 2: "Moderado", 3: "Elevado", 4: "Muito Elevado", 5: "Máximo"}

# IDs dos ficheiros no teu Google Drive
ID_XLSX = "1FohuDErPimGRCudx5GULlFXIIvSTup3H"
ID_CSV = "1nNRoxh8BJczQDl292RZC6nphC16Sk0wa"

# --- 3. EXTRAÇÃO DOS DADOS ---
driver.get(url)
time.sleep(6)
dados_finais = []

# Selecionar Distrito
try:
    for caixa in driver.find_elements(By.TAG_NAME, "select"):
        if "Viana do Castelo" in caixa.text:
            Select(caixa).select_by_visible_text("Viana do Castelo")
            time.sleep(2)
            break
except Exception as e:
    print(f"Erro ao selecionar distrito: {e}")

for codigo_id, nome_concelho in concelhos_dico.items():
    try:
        for caixa in driver.find_elements(By.TAG_NAME, "select"):
            if "Caminha" in caixa.text and "Melgaço" in caixa.text:
                Select(caixa).select_by_visible_text(nome_concelho)
                time.sleep(3)
                break
        
        script = "return window.AmCharts && window.AmCharts.charts ? window.AmCharts.charts.map(c => c.dataProvider) : null;"
        dados_brutos = driver.execute_script(script)
        
        if dados_brutos:
            dados_tempo = dados_brutos[0]
            dados_risco = dados_brutos[1] if len(dados_brutos) > 1 else []
            for idx, dado in enumerate(dados_tempo):
                v_risco = dado.get("rcm")
                if v_risco is None and len(dados_risco) > idx:
                    v_risco = dados_risco[idx].get("rcm", dados_risco[idx].get("class"))
                
                dados_finais.append({
                    "Concelho": nome_concelho,
                    "Dia_Bruto": dado.get("dt"),
                    "Temp_Max": dado.get("tt_max"),
                    "Temp_Min": dado.get("tt_min"),
                    "Hum_Max": dado.get("hr_max") / 100 if dado.get("hr_max") else 0,
                    "Hum_Min": dado.get("hr_min") / 100 if dado.get("hr_min") else 0,
                    "Vento_Int": dict_vento.get(dado.get("ff_class"), "N/D"),
                    "Vento_Dir": dado.get("ff_class_2"),
                    "Precip": dict_chuva.get(dado.get("rr_class"), "N/D"),
                    "Risco": dict_risco.get(v_risco, "N/D")
                })
    except Exception as e:
        print(f"Erro no concelho {nome_concelho}: {e}")
        continue

driver.quit()

# --- 4. TRATAMENTO DE DADOS E TIMESTAMPS ---
df = pd.DataFrame(dados_finais)

# Definir fuso horário de Portugal para a coluna de criação
fuso_pt = pytz.timezone('Europe/Lisbon')
agora_pt = datetime.now(fuso_pt)
df['Data_Extracao'] = agora_pt.strftime('%d/%m/%Y %H:%M:%S')

def tratar_data_ipma(dia_extraido):
    try:
        dia = int(dia_extraido)
        # Usamos a data de PT para o cálculo do mês/ano
        ano, mes = agora_pt.year, agora_pt.month
        if dia < agora_pt.day - 10:
            mes += 1
            if mes > 12:
                mes = 1
                ano += 1
        return datetime(ano, mes, dia)
    except:
        return None

df['Dia'] = df['Dia_Bruto'].apply(tratar_data_ipma)
df = df.drop(columns=['Dia_Bruto'])

# Ordenar por Data e Concelho
df = df.sort_values(by=['Dia', 'Concelho'])

# Formato ISO para a coluna Dia (Excel amigável)
df['Dia'] = df['Dia'].dt.strftime('%Y-%m-%d')

# Gerar ficheiros locais
nome_xlsx = "Painel_Mestre_IPMA.xlsx"
nome_csv = "Painel_Mestre_IPMA.csv"
df.to_excel(nome_xlsx, index=False)
df.to_csv(nome_csv, index=False, encoding='utf-8-sig')

# --- 5. FUNÇÃO DE ATUALIZAÇÃO NO DRIVE ---
def upload_to_drive(file_path, file_id, mime_type):
    try:
        creds_json = os.environ.get('GDRIVE_CREDENTIALS')
        if not creds_json:
            print(f"⚠️ Credenciais não encontradas para {file_path}. Ignorando Drive.")
            return

        info_chave = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(info_chave)
        service = build('drive', 'v3', credentials=creds)

        media = MediaFileUpload(file_path, mimetype=mime_type)
        service.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True
        ).execute()
        print(f"✅ {file_path} atualizado com sucesso no Drive!")
    except Exception as e:
        print(f"❌ Erro ao enviar {file_path}: {e}")

# Executar os uploads
upload_to_drive(nome_xlsx, ID_XLSX, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
upload_to_drive(nome_csv, ID_CSV, 'text/csv')
