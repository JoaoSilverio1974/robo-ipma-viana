import pandas as pd
import time
from datetime import datetime
import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
import zoneinfo

print("🤖 A iniciar o motor do Robô no GitHub Actions...")

fuso_pt = zoneinfo.ZoneInfo("Europe/Lisbon")
current_date_today = datetime.now(fuso_pt).date()

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
# Fingir que somos um Humano a usar o Google Chrome no Windows
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)
# Dar tempo suficiente para o navegador processar as chamadas JS Assíncronas
driver.set_script_timeout(15) 

concelhos_dico = {
    "1601": "Arcos de Valdevez", "1602": "Caminha", "1603": "Melgaço",
    "1604": "Monção", "1605": "Paredes de Coura", "1606": "Ponte da Barca",
    "1607": "Ponte de Lima", "1608": "Valença", "1609": "Viana do Castelo",
    "1610": "Vila Nova de Cerveira"
}

url_base = "https://www.ipma.pt/pt/riscoincendio/rcm.pt/"
print(f"🌍 A entrar no Portal Principal do IPMA ({url_base})...")
driver.get(url_base)
time.sleep(5) # Pausa crucial para o Cloudflare validar a nossa entrada

# ========================================================
# FASE 1: DESCARREGAR "ID_TEMPO" POR DENTRO DO SITE (Anti-Bloqueio)
# ========================================================
print("☁️ A Extrair APIs de Previsão por dentro da página segura...")

# Este script em JS é o nosso "Cavalo de Troia". Usa a sessão limpa da página para ler a API!
script_fetch = """
    var uri = arguments[0];
    var callback = arguments[arguments.length - 1];
    fetch(uri)
        .then(response => {
            if (response.ok) { return response.text(); } 
            else { throw new Error("HTTP " + response.status); }
        })
        .then(text => callback(text))
        .catch(err => callback("ERRO: " + err.message));
"""

mapa_geral_tempo = {}

for codigo_id, nome_concelho in concelhos_dico.items():
    global_id_local = f"1{codigo_id}00" # Constrói o ID exato exigido pelo IPMA
    mapa_geral_tempo[nome_concelho] = {}
    url_api = f"https://api.ipma.pt/public-data/forecast/aggregate/{global_id_local}.json"
    
    try:
        # A magia acontece aqui: o Selenium executa o fetch internamente!
        resultado = driver.execute_async_script(script_fetch, url_api)
        
        if resultado and not str(resultado).startswith("ERRO"):
            dados_api = json.loads(resultado)
            count_dias = 0
            for dia_prev in dados_api:
                if str(dia_prev.get("idPeriodo")) == "24":
                    data_str = dia_prev.get("dataPrev", "")[:10]
                    id_wt = dia_prev.get("idTipoTempo")
                    if id_wt is not None and str(id_wt) != "-99":
                        mapa_geral_tempo[nome_concelho][data_str] = id_wt
                        count_dias += 1
            print(f"  ✔️ {nome_concelho}: {count_dias} dias ID_Tempo extraídos.")
        else:
            print(f"  ⚠️ {nome_concelho}: A API devolveu {resultado}")
            
    except Exception as e:
        print(f"  ❌ Erro interno no {nome_concelho}: {e}")

# ========================================================
# FASE 2: EXTRAIR GRÁFICOS E CRUZAR OS DADOS
# ========================================================
print("\n🔥 A Configurar a Vista de Viana do Castelo para extrair Gráficos...")
caixa_distrito = None
for caixa in driver.find_elements(By.TAG_NAME, "select"):
    if "Viana do Castelo" in caixa.text:
        caixa_distrito = Select(caixa)
        break
if caixa_distrito:
    caixa_distrito.select_by_visible_text("Viana do Castelo")
    time.sleep(2)

dados_finais = []
dict_vento = {1: "Fraco", 2: "Moderado", 3: "Forte", 4: "Muito Forte"}
dict_chuva = {0: "Sem Chuva", 1: "Chuva Fraca", 2: "Chuva Moderada", 3: "Chuva Forte"}
dict_risco = {1: "Reduzido", 2: "Moderado", 3: "Elevado", 4: "Muito Elevado", 5: "Máximo"}

for codigo_id, nome_concelho in concelhos_dico.items():
    try:
        caixa_concelho = None
        for caixa in driver.find_elements(By.TAG_NAME, "select"):
            if "Caminha" in caixa.text and "Melgaço" in caixa.text:
                caixa_concelho = Select(caixa)
                break

        if caixa_concelho:
            caixa_concelho.select_by_visible_text(nome_concelho)
            time.sleep(2.5)

            dados_brutos = driver.execute_script("""
                let extraidos = [];
                if (window.AmCharts && window.AmCharts.charts) {
                    for (let i = 0; i < window.AmCharts.charts.length; i++) {
                        extraidos.push(window.AmCharts.charts[i].dataProvider);
                    }
                }
                return extraidos;
            """)

            if dados_brutos and len(dados_brutos) > 0:
                dados_tempo = dados_brutos[0]
                dados_risco = dados_brutos[1] if len(dados_brutos) > 1 else []

                for idx, dado in enumerate(dados_tempo):
                    dado_day = dado.get("dt")
                    if dado_day is not None:
                        try:
                            day_int = int(dado_day)
                            y = current_date_today.year
                            m = current_date_today.month

                            if day_int < current_date_today.day - 10:
                                m += 1
                                if m > 12:
                                    m = 1
                                    y += 1

                            dado_full_date = datetime(y, m, day_int).date()
                            delta_days = (dado_full_date - current_date_today).days
                            
                            if 0 <= delta_days <= 9:
                                h_max = dado.get("hr_max")
                                h_min = dado.get("hr_min")

                                valor_risco_num = dado.get("rcm")
                                if valor_risco_num is None and len(dados_risco) > idx:
                                    valor_risco_num = dados_risco[idx].get("rcm", dados_risco[idx].get("class"))

                                final_h_max = (h_max / 100) if h_max is not None else "N/D"
                                final_h_min = (h_min / 100) if h_min is not None else "N/D"

                                # --- CRUZAMENTO --- (Vai buscar à memória os valores obtidos na Fase 1)
                                data_formatada = dado_full_date.strftime("%Y-%m-%d")
                                id_tempo_final = mapa_geral_tempo.get(nome_concelho, {}).get(data_formatada, "N/D")

                                dados_finais.append({
                                    "Concelho": nome_concelho,
                                    "Temp_Max": dado.get("tt_max", "N/D"),
                                    "Temp_Min": dado.get("tt_min", "N/D"),
                                    "Hum_Max": final_h_max,
                                    "Hum_Min": final_h_min,
                                    "Vento_Int": dict_vento.get(dado.get("ff_class", 1), "N/D"),
                                    "Vento_Dir": dado.get("ff_class_2", "N/D"),
                                    "Precip": dict_chuva.get(dado.get("rr_class", 0), "N/D"),
                                    "Risco": dict_risco.get(valor_risco_num, "N/D"),
                                    "ID_Tempo": id_tempo_final, # 🚀 Aqui vai o ID Real
                                    "Dia": dado_full_date
                                })
                        except ValueError:
                            pass
        print(f"📊 Gráficos processados: {nome_concelho}")
    except Exception as e:
        print(f"❌ Erro gráfico no {nome_concelho}: {e}")

driver.quit()

# ========================================================
# FASE 3: GRAVAÇÃO E TRATAMENTO
# ========================================================
print("\n💾 A gravar ficheiros de saída (Excel e CSV)...")
df = pd.DataFrame(dados_finais)

if not df.empty:
    ordem_colunas = [
        "Concelho", "Temp_Max", "Temp_Min", "Hum_Max", "Hum_Min", 
        "Vento_Int", "Vento_Dir", "Precip", "Risco", "ID_Tempo", "Dia"
    ]
    df = df[ordem_colunas]

    df['Dia'] = pd.to_datetime(df['Dia'])
    df = df.dropna(subset=['Dia'])
    df = df.sort_values(by=['Dia', 'Concelho'])

    colunas_num = ["Temp_Max", "Temp_Min", "Hum_Max", "Hum_Min"]
    for col in colunas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    df['Dia'] = df['Dia'].dt.strftime('%d/%m/%Y')

    df.to_csv("Painel_Mestre_IPMA.csv", index=False, sep=',', encoding='utf-8-sig')
    df.to_excel("Painel_Mestre_IPMA.xlsx", index=False)

    print("🎉 SUCESSO TOTAL! Os 10 concelhos e os 10 dias foram processados.")
else:
    print("⚠️ Aviso: Nenhum dado foi extraído.")

# REGISTO DE PONTO
agora = datetime.now(fuso_pt).strftime("%d/%m/%Y %H:%M:%S")
with open("log_execucao.csv", "w", encoding="utf-8") as f:
    f.write("Ultima_Atualizacao\n")
    f.write(f"{agora}\n")
print(f"🕒 Fim da Execução: {agora}")
