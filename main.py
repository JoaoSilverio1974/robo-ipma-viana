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

# --- 1. DEFINIÇÃO EXATA DA DATA (FUSO HORÁRIO PT) ---
fuso_pt = zoneinfo.ZoneInfo("Europe/Lisbon")
current_date_today = datetime.now(fuso_pt).date()

# --- 2. CONFIGURAÇÃO UNIVERSAL DO NAVEGADOR (ANTI-BLOQUEIO) ---
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
# Enganar o firewall fazendo passar-se por um Chrome normal de Windows
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

concelhos_dico = {
    "1601": "Arcos de Valdevez", "1602": "Caminha", "1603": "Melgaço",
    "1604": "Monção", "1605": "Paredes de Coura", "1606": "Ponte da Barca",
    "1607": "Ponte de Lima", "1608": "Valença", "1609": "Viana do Castelo",
    "1610": "Vila Nova de Cerveira"
}

# ========================================================
# FASE 1: OBTER ID_TEMPO VIA SELENIUM (CONTORNA BLOQUEIOS)
# ========================================================
mapa_geral_tempo = {}

print("☁️ A descarregar IDs de Tempo via API interna do IPMA...")
for codigo_id, nome_concelho in concelhos_dico.items():
    global_id_local = f"1{codigo_id}00"
    mapa_geral_tempo[nome_concelho] = {}
    
    url_api = f"https://api.ipma.pt/public-data/forecast/aggregate/{global_id_local}.json"
    
    try:
        # Usamos o driver do Chrome em vez do urllib para não sermos bloqueados
        driver.get(url_api)
        time.sleep(1.5) # Pequena pausa para o navegador carregar o JSON
        
        # O Chrome coloca o JSON dentro da tag <body>
        body_text = driver.find_element(By.TAG_NAME, "body").text
        dados_api = json.loads(body_text)
        
        for dia_prev in dados_api:
            if str(dia_prev.get("idPeriodo")) == "24":
                data_completa = dia_prev.get("dataPrev") or ""
                if len(data_completa) >= 10:
                    data_str = data_completa[:10]
                    id_wt = dia_prev.get("idTipoTempo")
                    if id_wt is not None and str(id_wt) != "-99":
                        mapa_geral_tempo[nome_concelho][data_str] = id_wt
        print(f"✔️ Tempo recolhido com sucesso: {nome_concelho}")
        
    except Exception as e:
        print(f"⚠️ Erro ao recolher API de {nome_concelho}: {e}")

print("\n🌍 A entrar no Portal de Risco de Incêndio do IPMA...")
driver.get("https://www.ipma.pt/pt/riscoincendio/rcm.pt/")
time.sleep(5)

caixa_distrito = None
for caixa in driver.find_elements(By.TAG_NAME, "select"):
    if "Viana do Castelo" in caixa.text:
        caixa_distrito = Select(caixa)
        break

if caixa_distrito:
    caixa_distrito.select_by_visible_text("Viana do Castelo")
    time.sleep(2)

# ========================================================
# FASE 2: EXTRAIR GRÁFICOS E CRUZAR COM OS DADOS DE TEMPO
# ========================================================
dados_finais = []
dict_vento = {1: "Fraco", 2: "Moderado", 3: "Forte", 4: "Muito Forte"}
dict_chuva = {0: "Sem Chuva", 1: "Chuva Fraca", 2: "Chuva Moderada", 3: "Chuva Forte"}
dict_risco = {1: "Reduzido", 2: "Moderado", 3: "Elevado", 4: "Muito Elevado", 5: "Máximo"}

print("🔥 Início da Extração de Gráficos (Risco e Vento)...")
for codigo_id, nome_concelho in concelhos_dico.items():
    try:
        caixa_concelho = None
        for caixa in driver.find_elements(By.TAG_NAME, "select"):
            if "Caminha" in caixa.text and "Melgaço" in caixa.text:
                caixa_concelho = Select(caixa)
                break

        if caixa_concelho:
            caixa_concelho.select_by_visible_text(nome_concelho)
            time.sleep(2)

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

                                # ========================================================
                                # CRUZAMENTO FINAL COM OS DADOS CARREGADOS NA FASE 1
                                # ========================================================
                                data_formatada = dado_full_date.strftime("%Y-%m-%d")
                                # Vai ao dicionário específico deste concelho buscar a data
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
                                    "ID_Tempo": id_tempo_final,
                                    "Dia": dado_full_date
                                })
                        except ValueError:
                            pass
        print(f"✅ Processado: {nome_concelho}")
    except Exception as e:
        print(f"❌ Erro no gráfico de {nome_concelho}: {e}")

driver.quit()

print("\n📊 A preparar os ficheiros locais...")
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

    nome_csv = "Painel_Mestre_IPMA.csv"
    df.to_csv(nome_csv, index=False, sep=',', encoding='utf-8-sig')

    nome_xlsx = "Painel_Mestre_IPMA.xlsx"
    df.to_excel(nome_xlsx, index=False)

    print("🎉 SUCESSO TOTAL! Ficheiros gravados com ID_Tempo correto.")
else:
    print("⚠️ Aviso: Nenhum dado foi extraído.")

# ==========================================
# REGISTO DE HORA (LIVRO DE PONTO DO ROBÔ)
# ==========================================
agora = datetime.now(fuso_pt).strftime("%d/%m/%Y %H:%M:%S")
log_file = "log_execucao.csv"

with open(log_file, "w", encoding="utf-8") as f:
    f.write("Ultima_Atualizacao\n")
    f.write(f"{agora}\n")

print(f"🕒 Registo de hora atualizado com sucesso: {agora} (Hora PT)")
