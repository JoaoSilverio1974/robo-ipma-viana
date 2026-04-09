import os
import json
import time
import pandas as pd
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

# --- 2. DICIONÁRIOS ---
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

# --- 3. EXTRAÇÃO DOS DADOS ---
driver.get(url)
time.sleep(6)
dados_finais = []

try:
    for caixa in driver.find_elements(By.TAG_NAME, "select"):
        if "Viana do Castelo" in caixa.text:
            Select(caixa).select_by_visible_text("Viana do Castelo")
            time.sleep(2)
            break
except: pass

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
                    "Dia": dado.get("dt"),
                    "Temp_Max": dado.get("tt_max"),
                    "Temp_Min": dado.get("tt_min"),
                    "Hum_Max": dado.get("hr_max") / 100 if dado.get("hr_max") else 0,
                    "Hum_Min": dado.get("hr_min") / 100 if dado.get("hr_min") else 0,
                    "Vento_Int": dict_vento.get(dado.get("ff_class"), "N/D"),
                    "Vento_Dir": dado.get("ff_class_2"),
                    "Precip": dict_chuva.get(dado.get("rr_class"), "N/D"),
                    "Risco": dict_risco.get(v_risco, "N/D")
                })
    except: continue

driver.quit()

# --- 4. TRATAMENTO E ORDENAÇÃO (O SEGREDO ESTÁ AQUI) ---
df = pd.DataFrame(dados_finais)

# 1. Garante que o Dia é tratado como data para ordenar cronologicamente
df['Dia'] = pd.to_datetime(df['Dia'])

# 2. Ordena PRIMEIRO por Data e DEPOIS por Concelho (Exatamente como no Colab)
df = df.sort_values(by=['Dia', 'Concelho'])

# 3. Transforma a data no formato de leitura do Excel
df['Dia'] = df['Dia'].dt.strftime('%d-%m-%Y')

nome_ficheiro = "Painel_Mestre_IPMA.xlsx"
df.to_excel(nome_ficheiro, index=False)

# --- 5. ATUALIZAÇÃO NO GOOGLE DRIVE ---
ID_DO_FICHEIRO = "1FohuDErPimGRCudx5GULlFXIIvSTup3H" 

try:
    creds_json = os.environ.get('GDRIVE_CREDENTIALS')
    info_chave = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(info_chave)
    service = build('drive', 'v3', credentials=creds)

    media = MediaFileUpload(nome_ficheiro, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    service.files().update(
        fileId=ID_DO_FICHEIRO,
        media_body=media,
        supportsAllDrives=True
    ).execute()
    print("✅ Ficheiro atualizado com a ordenação correta!")
except Exception as e:
    print(f"❌ Erro: {e}")
