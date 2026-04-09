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

# --- 1. CONFIGURAÇÃO DO NAVEGADOR (MODO INVISÍVEL) ---
print("🤖 A iniciar o motor do Robô...")
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# --- 2. CONFIGURAÇÕES DOS DADOS ---
url = "https://www.ipma.pt/pt/riscoincendio/rcm.pt/"
concelhos_dico = {
    "1601": "Arcos de Valdevez", "1602": "Caminha", "1603": "Melgaço",
    "1604": "Monção", "1605": "Paredes de Coura", "1606": "Ponte da Barca",
    "1607": "Ponte de Lima", "1608": "Valença", "1609": "Viana do Castelo",
    "1610": "Vila Nova de Cerveira"
}

dict_vento = {1: "Fraco", 2: "Moderado", 3: "Forte", 4: "Muito Forte"}
dict_chuva = {0: "Sem Chuva", 1: "Chuva Fraca", 2: "Chuva Moderada", 3: "Chuva Forte"}
dict_risco = {1: "Reduzido", 2: "Moderado", 3: "Elevado", 4: "Muito Elevado", 5: "Máximo"}

# --- 3. EXTRAÇÃO DOS DADOS DO IPMA ---
print(f"🌍 A aceder ao IPMA: {url}")
driver.get(url)
time.sleep(6) # Espera o site carregar

dados_finais = []

try:
    # Selecionar Distrito de Viana do Castelo (16)
    caixa_distrito = None
    for caixa in driver.find_elements(By.TAG_NAME, "select"):
        if "Viana do Castelo" in caixa.text:
            caixa_distrito = Select(caixa)
            break
    if caixa_distrito:
        caixa_distrito.select_by_visible_text("Viana do Castelo")
        time.sleep(2)
        print("📍 Distrito Viana do Castelo selecionado.")
except Exception as e:
    print(f"⚠️ Erro ao selecionar distrito: {e}")

for codigo_id, nome_concelho in concelhos_dico.items():
    try:
        print(f"📥 A processar: {nome_concelho}...")
        caixa_concelho = None
        for caixa in driver.find_elements(By.TAG_NAME, "select"):
            if "Caminha" in caixa.text and "Melgaço" in caixa.text:
                caixa_concelho = Select(caixa)
                break
        
        if caixa_concelho:
            caixa_concelho.select_by_visible_text(nome_concelho)
            time.sleep(3) # Tempo para os gráficos amCharts carregarem
            
            # Injeção de JS para ler a memória do gráfico
            dados_brutos = driver.execute_script("""
                if (window.AmCharts && window.AmCharts.charts) {
                    return window.AmCharts.charts.map(c => c.dataProvider);
                }
                return null;
            """)
            
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
                        "Hum_Max": dado.get("hr_max"),
                        "Hum_Min": dado.get("hr_min"),
                        "Vento_Int": dict_vento.get(dado.get("ff_class"), "N/D"),
                        "Vento_Dir": dado.get("ff_class_2"),
                        "Precip": dict_chuva.get(dado.get("rr_class"), "N/D"),
                        "Risco": dict_risco.get(v_risco, "N/D")
                    })
    except Exception as e:
        print(f"❌ Erro em {nome_concelho}: {e}")

driver.quit()

# --- 4. GERAR O EXCEL ---
nome_ficheiro = "Painel_Mestre_IPMA.xlsx"
df = pd.DataFrame(dados_finais)
df.to_excel(nome_ficheiro, index=False)
print(f"📊 Excel gerado com {len(df)} linhas.")

# --- 5. UPLOAD PARA O GOOGLE DRIVE ---
# Substitui pelo ID da tua pasta (o que aparece no link do Google Drive)
ID_DA_PASTA = "1RtTVsxP3r9zWhSAJvmVhKs4VjNUeKEyg" 

print("☁️ A iniciar upload para o Google Drive...")
try:
    # Carregar credenciais a partir do "Secret" do GitHub
    creds_json = os.environ.get('GDRIVE_CREDENTIALS')
    if not creds_json:
        raise Exception("Secret GDRIVE_CREDENTIALS não encontrado!")
        
    info_chave = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(info_chave)
    service = build('drive', 'v3', credentials=creds)

    # Procurar se o ficheiro já existe na pasta para o atualizar
    query = f"name='{nome_ficheiro}' and '{ID_DA_PASTA}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])

    file_metadata = {'name': nome_ficheiro, 'parents': [ID_DA_PASTA]}
    media = MediaFileUpload(nome_ficheiro, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    if files:
        # Atualiza o ficheiro existente
        file_id = files[0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
        print(f"✅ Ficheiro atualizado com sucesso! ID: {file_id}")
    else:
        # Cria um novo ficheiro
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"✅ Novo ficheiro criado com sucesso! ID: {file.get('id')}")

except Exception as e:
    print(f"❌ Falha no upload para o Drive: {e}")
