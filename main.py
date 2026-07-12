import pandas as pd
import time
from datetime import datetime
import json
import urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
import zoneinfo

print("🤖 A iniciar o motor do Robô no GitHub Actions...")

# --- 1. CONFIGURAÇÃO UNIVERSAL DO NAVEGADOR ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

url = "https://www.ipma.pt/pt/riscoincendio/rcm.pt/"
print(f"🌍 A entrar no IPMA: {url}")
driver.get(url)
time.sleep(5)

# ========================================================
# 🌊 EXTRAÇÃO PRÉVIA: MAR TOTAL (Área Minho)
# ========================================================
mapa_mar = {}
try:
    # API Oceanografia IPMA (Zona Minho)
    url_mar = "https://api.ipma.pt/open-data/forecast/oceanography/daily/hp-daily-sea-forecast-day0.json"
    req_mar = urllib.request.Request(url_mar, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req_mar) as response:
        dados_mar_api = json.loads(response.read().decode())
        for item in dados_mar_api:
            if item.get("area") == "Minho":
                # Guardar altura total da onda por data
                data_mar = item.get("dataPrev", "")[:10]
                mapa_mar[data_mar] = item.get("totalHeight", "N/D")
except Exception as e_mar:
    print(f"⚠️ Erro ao aceder API do Mar: {e_mar}")

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

caixa_distrito = None
for caixa in driver.find_elements(By.TAG_NAME, "select"):
    if "Viana do Castelo" in caixa.text:
        caixa_distrito = Select(caixa)
        break
if caixa_distrito:
    caixa_distrito.select_by_visible_text("Viana do Castelo")
    time.sleep(2)

current_date_today = datetime.now().date()

print("✅ Início da Extração de Dados...")
for codigo_id, nome_concelho in concelhos_dico.items():
    try:
        global_id_local = f"1{codigo_id}00"
        mapa_id_tempo = {}
        
        try:
            url_api = f"https://api.ipma.pt/public-data/forecast/aggregate/{global_id_local}.json"
            req = urllib.request.Request(url_api, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                dados_api = json.loads(response.read().decode())
                for dia_prev in dados_api:
                    if str(dia_prev.get("idPeriodo")) == "24":
                        data_completa = dia_prev.get("dataPrev", "")
                        data_str = data_completa[:10]
                        id_wt = dia_prev.get("idTipoTempo")
                        if id_wt is not None and str(id_wt) != "-99":
                            mapa_id_tempo[data_str] = id_wt
        except Exception as e_api:
            print(f"⚠️ Erro ao aceder à API para {nome_concelho}: {e_api}")

        caixa_concelho = None
        for caixa in driver.find_elements(By.TAG_NAME, "select"):
            if "Caminha" in caixa.text and "Melgaço" in caixa.text:
                caixa_concelho = Select(caixa)
                break

        if caixa_concelho:
            caixa_concelho.select_by_visible_text(nome_concelho)
            time.sleep(2.5)
            dados_brutos = driver.execute_script("return (window.AmCharts && window.AmCharts.charts) ? window.AmCharts.charts.map(c => c.dataProvider) : [];")

            if dados_brutos and len(dados_brutos) > 0:
                dados_tempo = dados_brutos[0]
                dados_risco = dados_brutos[1] if len(dados_brutos) > 1 else []

                for idx, dado in enumerate(dados_tempo):
                    dado_day = dado.get("dt")
                    if dado_day is not None:
                        try:
                            day_int = int(dado_day)
                            y, m = current_date_today.year, current_date_today.month
                            if day_int < current_date_today.day - 10:
                                m += 1
                                if m > 12: m, y = 1, y + 1
                            dado_full_date = datetime(y, m, day_int).date()
                            
                            delta_days = (dado_full_date - current_date_today).days
                            if 0 <= delta_days <= 9:
                                data_formatada = dado_full_date.strftime("%Y-%m-%d")
                                
                                dados_finais.append({
                                    "Concelho": nome_concelho,
                                    "Temp_Max": dado.get("tt_max", "N/D"),
                                    "Temp_Min": dado.get("tt_min", "N/D"),
                                    "Hum_Max": (dado.get("hr_max") / 100) if dado.get("hr_max") else "N/D",
                                    "Hum_Min": (dado.get("hr_min") / 100) if dado.get("hr_min") else "N/D",
                                    "Vento_Int": dict_vento.get(dado.get("ff_class", 1), "N/D"),
                                    "Vento_Dir": dado.get("ff_class_2", "N/D"),
                                    "Precip": dict_chuva.get(dado.get("rr_class", 0), "N/D"),
                                    "Risco": dict_risco.get(dado.get("rcm") or (dados_risco[idx].get("rcm") if len(dados_risco)>idx else None), "N/D"),
                                    "ID_Tempo": mapa_id_tempo.get(data_formatada, "N/D"),
                                    "Dia": dado_full_date,
                                    "Mar_Total": mapa_mar.get(data_formatada, "N/D") # <-- Coluna Nova no final
                                })
                        except ValueError: pass
    except Exception as e:
        print(f"Erro a processar {nome_concelho}: {e}")

driver.quit()

print("📊 A preparar os ficheiros locais...")
df = pd.DataFrame(dados_finais)

if not df.empty:
    ordem_colunas = [
        "Concelho", "Temp_Max", "Temp_Min", "Hum_Max", "Hum_Min", 
        "Vento_Int", "Vento_Dir", "Precip", "Risco", "ID_Tempo", "Dia", "Mar_Total"
    ]
    df = df[ordem_colunas]
    df['Dia'] = pd.to_datetime(df['Dia']).dt.strftime('%d/%m/%Y')
    
    df.to_csv("Painel_Mestre_IPMA.csv", index=False, sep=',', encoding='utf-8-sig')
    df.to_excel("Painel_Mestre_IPMA.xlsx", index=False)
    print("🎉 SUCESSO! Dados do Mar incluídos no final.")
