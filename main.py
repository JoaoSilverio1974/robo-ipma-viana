import pandas as pd
import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager

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
        print(f"A descarregar: {nome_concelho}...")
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

                                # Cálculo da Humidade para Decimal (ex: 84.7 passa a 0.847)
                                final_h_max = (h_max / 100) if h_max is not None else "N/D"
                                final_h_min = (h_min / 100) if h_min is not None else "N/D"

                                # Ordem e nomes EXATOS conforme a imagem
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
                                    "Dia": dado_full_date
                                })
                        except ValueError:
                            pass
    except Exception as e:
        print(f"Erro a processar {nome_concelho}: {e}")

driver.quit()

print("📊 A preparar os ficheiros locais...")
df = pd.DataFrame(dados_finais)

if not df.empty:
    # Garantir a ordem exata das colunas
    ordem_colunas = [
        "Concelho", "Temp_Max", "Temp_Min", "Hum_Max", "Hum_Min", 
        "Vento_Int", "Vento_Dir", "Precip", "Risco", "Dia"
    ]
    df = df[ordem_colunas]

    # Ordenar por Dia e depois por Concelho
    df['Dia'] = pd.to_datetime(df['Dia'])
    df = df.dropna(subset=['Dia'])
    df = df.sort_values(by=['Dia', 'Concelho'])

    # Converter numéricos
    colunas_num = ["Temp_Max", "Temp_Min", "Hum_Max", "Hum_Min"]
    for col in colunas_num:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Formatar a data EXATAMENTE como na imagem: DD/MM/YYYY
    df['Dia'] = df['Dia'].dt.strftime('%d/%m/%Y')

    # Gerar os ficheiros
    nome_csv = "Painel_Mestre_IPMA.csv"
    df.to_csv(nome_csv, index=False, sep=',', encoding='utf-8-sig')

    nome_xlsx = "Painel_Mestre_IPMA.xlsx"
    df.to_excel(nome_xlsx, index=False)

    print("🎉 SUCESSO! Estrutura idêntica ao Excel original gerada.")
else:
    print("⚠️ Aviso: Nenhum dado foi extraído.")


# ==========================================
# REGISTO DE HORA (LIVRO DE PONTO DO ROBÔ)
# ==========================================
import os

# Capta a hora exata do servidor
agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
log_file = "log_execucao.csv"

# Se o ficheiro não existir, cria-o e faz o cabeçalho
if not os.path.exists(log_file):
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("Data_Hora_Execucao\n")

# Adiciona a nova hora na linha de baixo (sem apagar as antigas)
with open(log_file, "a", encoding="utf-8") as f:
    f.write(f"{agora}\n")

print(f"🕒 Registo de hora guardado no livro de ponto: {agora}")
