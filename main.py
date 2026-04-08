import os
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager

# 1. Configurar o Chrome para rodar no GitHub (sem ecrã)
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# --- A TUA LÓGICA DE EXTRAÇÃO (IGUAL AO COLAB) ---
url = "https://www.ipma.pt/pt/riscoincendio/rcm.pt/"
driver.get(url)
time.sleep(5)

dados_finais = []
concelhos_dico = {
    "1601": "Arcos de Valdevez", "1602": "Caminha", "1603": "Melgaço",
    "1604": "Monção", "1605": "Paredes de Coura", "1606": "Ponte da Barca",
    "1607": "Ponte de Lima", "1608": "Valença", "1609": "Viana do Castelo",
    "1610": "Vila Nova de Cerveira"
}

dict_vento = {1: "Fraco", 2: "Moderado", 3: "Forte", 4: "Muito Forte"}
dict_chuva = {0: "Sem Chuva", 1: "Chuva Fraca", 2: "Chuva Moderada", 3: "Chuva Forte"}
dict_risco = {1: "Reduzido", 2: "Moderado", 3: "Elevado", 4: "Muito Elevado", 5: "Máximo"}

# Selecionar Distrito
try:
    caixa_distrito = None
    for caixa in driver.find_elements(By.TAG_NAME, "select"):
        if "Viana do Castelo" in caixa.text:
            caixa_distrito = Select(caixa)
            break
    if caixa_distrito:
        caixa_distrito.select_by_visible_text("Viana do Castelo")
        time.sleep(2)
except:
    pass

# Loop de Concelhos
for codigo_id, nome_concelho in concelhos_dico.items():
    try:
        caixa_concelho = None
        for caixa in driver.find_elements(By.TAG_NAME, "select"):
            if "Caminha" in caixa.text and "Melgaço" in caixa.text:
                caixa_concelho = Select(caixa)
                break
        if caixa_concelho:
            caixa_concelho.select_by_visible_text(nome_concelho)
            time.sleep(3)
            dados_brutos = driver.execute_script("return (window.AmCharts && window.AmCharts.charts) ? window.AmCharts.charts.map(c => c.dataProvider) : null;")
            if dados_brutos:
                dados_tempo = dados_brutos[0]
                dados_risco = dados_brutos[1] if len(dados_brutos) > 1 else []
                for idx, dado in enumerate(dados_tempo):
                    val_risco = dado.get("rcm")
                    if val_risco is None and len(dados_risco) > idx:
                        val_risco = dados_risco[idx].get("rcm", dados_risco[idx].get("class"))
                    dados_finais.append({
                        "Concelho": nome_concelho,
                        "Dia": dado.get("dt"),
                        "T_Max": dado.get("tt_max"),
                        "T_Min": dado.get("tt_min"),
                        "H_Max": dado.get("hr_max"),
                        "H_Min": dado.get("hr_min"),
                        "Vento_Int": dict_vento.get(dado.get("ff_class"), "N/D"),
                        "Vento_Dir": dado.get("ff_class_2"),
                        "Precip": dict_chuva.get(dado.get("rr_class"), "N/D"),
                        "Risco": dict_risco.get(val_risco, "N/D")
                    })
    except:
        continue

driver.quit()
df = pd.DataFrame(dados_finais)
df.to_excel("Painel_Mestre_IPMA.xlsx", index=False)
print("Ficheiro gerado com sucesso!")
