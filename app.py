import json
import os
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime, timedelta
import threading
import time
import asyncio
from zoneinfo import ZoneInfo
import random
from telegram import Bot
import requests

app = Flask(__name__)

# --- CONFIGURAÇÃO ---
# Certifique-se de que suas variáveis de ambiente estão configuradas
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Validação inicial para garantir que as credenciais foram carregadas
if not BOT_TOKEN or not CHAT_ID:
    raise ValueError("As variáveis de ambiente BOT_TOKEN e CHAT_ID não foram definidas.")

bot = Bot(token=BOT_TOKEN)

DB_FILE = "database.json"
INTERVALO_MINIMO_MINUTOS = 12

# Mapeamento dos ativos da sua base para os símbolos da Binance
BINANCE_SYMBOLS = {
    "BTC/USD": "BTCUSDT",
    "ETH/USDT": "ETHUSDT",
    "BSC/USDT": "BNBUSDT",
    "XRP/USD": "XRPUSDT",
    "DOGE/USD": "DOGEUSDT",
    "SOL/USD": "SOLUSDT"
}

# --- INICIALIZAÇÃO DO BANCO DE DADOS ---
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({
            "ativos": list(BINANCE_SYMBOLS.keys()),
            "disparos": []
        }, f, indent=2)

def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

# --- FUNÇÕES PRINCIPAIS ---

# ✅ CORRIGIDO: Função para pegar preço atual da Binance de forma segura
def get_price(ativo):
    symbol = BINANCE_SYMBOLS.get(ativo)
    if not symbol:
        print(f"[ERRO] Ativo '{ativo}' não encontrado no mapeamento BINANCE_SYMBOLS.")
        return None

    url = f"https://api.binance.us/api/v3/ticker/price?symbol={symbol}"
    
    try:
        resp = requests.get(url, timeout=10 ) # Adicionado timeout
        resp.raise_for_status()  # Lança um erro para respostas HTTP ruins (4xx ou 5xx)
        data = resp.json()

        if "price" in data:
            return float(data["price"])
        else:
            print(f"[ERRO] Resposta da API da Binance para o símbolo {symbol} não contém 'price'. Resposta: {data}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"[ERRO] Falha ao conectar com a API da Binance: {e}")
        return None
    except Exception as e:
        print(f"[ERRO] Erro inesperado ao obter preço para {ativo}: {e}")
        return None

def verificar_resultado(preco_entrada, preco_final, direcao):
    if direcao == "COMPRA":
        return "WIN" if preco_final > preco_entrada else "LOSS"
    elif direcao == "VENDA":
        return "WIN" if preco_final < preco_entrada else "LOSS"
    return "LOSS"

# --- ROTAS DA API FLASK ---

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/ativos', methods=['GET', 'POST'])
def ativos():
    db = load_db()
    if request.method == 'GET':
        return jsonify(db["ativos"])
    elif request.method == 'POST':
        data = request.json
        ativo = data.get("ativo")
        if ativo and ativo not in db["ativos"]:
            db["ativos"].append(ativo)
            save_db(db)
            return jsonify({"status": "ok", "ativos": db["ativos"]})
        return jsonify({"status": "error", "message": "Ativo inválido ou já existe."}), 400

@app.route('/api/disparos', methods=['GET', 'POST'])
def disparos():
    db = load_db()
    if request.method == 'GET':
        return jsonify(db["disparos"])
    elif request.method == 'POST':
        data = request.json
        horario = data.get("horario")
        ativo = data.get("ativo")
        direcao = data.get("direcao")
        
        if not (horario and ativo and direcao):
            return jsonify({"status": "error", "message": "Dados incompletos."}), 400
        
        for d in db["disparos"]:
            if d["horario"] == horario and d["ativo"] == ativo and d["direcao"] == direcao:
                return jsonify({"status": "error", "message": "Disparo já agendado."}), 400
        
        # ✅ CORRIGIDO: Verifica se o preço foi obtido com sucesso
        preco_entrada = get_price(ativo)
        if preco_entrada is None:
            return jsonify({"status": "error", "message": f"Não foi possível obter o preço do ativo {ativo}. Agendamento cancelado."}), 400
        
        db["disparos"].append({
            "horario": horario,
            "ativo": ativo,
            "direcao": direcao,
            "preco_entrada": preco_entrada
        })
        save_db(db)
        return jsonify({"status": "ok", "disparos": db["disparos"]})

# --- LÓGICA DO TELEGRAM (ASYNC) ---

async def enviar_mensagem(texto):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=texto, parse_mode="Markdown")
    except Exception as e:
        print(f"Erro ao enviar mensagem no Telegram: {e}")

async def enviar_resultado_async(ativo, direcao, preco_entrada):
    # ✅ CORRIGIDO: Verifica se o preço final foi obtido
    preco_final = get_price(ativo)
    if preco_final is None:
        print(f"[AVISO] Não foi possível obter o preço final para {ativo}. Verificação de resultado cancelada.")
        await enviar_mensagem("Não foi possível verificar o resultado do último sinal por uma falha na obtenção de preço.")
        return

    resultado = verificar_resultado(preco_entrada, preco_final, direcao)
    print(f"Resultado verificado: {resultado} | Entrada: {preco_entrada} | Final: {preco_final}")
    
    try:
        if resultado == "WIN":
            sticker_win = "CAACAgEAAxkBAi1jHGiaaHZB7SG-0V7xeSFmIjMhEnRlAAKmBgACsFWZRmsygMkofbBeNgQ"
            await bot.send_sticker(chat_id=CHAT_ID, sticker=sticker_win)
        else:
            mensagens_derrota = [
                "DEU F TROPA! Siga o gerenciamento!",
                "Siga o gerenciamento família, saiu totalmente do padrão.",
                "Stopou? Segue o gerenciamento!!",
                "Fzada família! Mas estamos extremamente assertivos! Bora pra guerra!",
                "Não respeitou esse safado, bora pra próxima"
            ]
            mensagem_derrota = random.choice(mensagens_derrota)
            await enviar_mensagem(mensagem_derrota)
    except Exception as e:
        print(f"Erro ao enviar resultado no Telegram: {e}")

async def enviar_sinal_programado(d):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    horario_obj = datetime.strptime(d["horario"], "%H:%M").replace(
        year=agora.year, month=agora.month, day=agora.day, tzinfo=ZoneInfo("America/Sao_Paulo"))
    segundos_ate_envio = (horario_obj - agora).total_seconds()
    
    if segundos_ate_envio < 0:
        return
    
    await asyncio.sleep(segundos_ate_envio)
    
    horario_entrada = (datetime.strptime(d["horario"], "%H:%M") + timedelta(minutes=3)).strftime("%H:%M")
    
    mensagem = f"""📊 *OPERAÇÃO CONFIRMADA*

Corretora: COWBEX ✅

🥇 *Moeda* = {d['ativo']}
⏰ *Expiração* = 1 Minuto
📌 *Entrada* = {horario_entrada}

{('🟢 COMPRA' if d['direcao'] == 'COMPRA' else '🔴 VENDA')}

⚠️ *Proteção 1:* {(datetime.strptime(horario_entrada, '%H:%M') + timedelta(minutes=1)).strftime('%H:%M')}
⚠️ *Proteção 2:* {(datetime.strptime(horario_entrada, '%H:%M') + timedelta(minutes=2)).strftime('%H:%M')}

➡️ [Clique aqui para acessar a corretora](https://bit.ly/cadastre-corretora-segura )

❓ [Não sabe pegar os sinais? Clique aqui](https://t.me/c/2509048940/28 )
"""
    await enviar_mensagem(mensagem)
    
    await asyncio.sleep(360) # Espera 6 minutos para verificação
    await enviar_resultado_async(d['ativo'], d['direcao'], d['preco_entrada'])

async def enviar_sinal_automatico():
    global ultimo_sinal_automatico
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    
    if ultimo_sinal_automatico:
        tempo_desde_ultimo = (agora - ultimo_sinal_automatico).total_seconds() / 60
        if tempo_desde_ultimo < INTERVALO_MINIMO_MINUTOS:
            return
    
    db = load_db()
    ativos = db.get("ativos", [])
    if not ativos:
        return
    
    ativo = random.choice(ativos)
    direcao = random.choice(["COMPRA", "VENDA"])
    
    # ✅ CORRIGIDO: Verifica se o preço foi obtido com sucesso
    preco_entrada = get_price(ativo)
    if preco_entrada is None:
        print(f"[AVISO] Não foi possível obter o preço para o ativo {ativo}. Sinal automático cancelado.")
        return

    ultimo_sinal_automatico = agora
    horario_entrada = (agora + timedelta(minutes=3)).strftime("%H:%M")
    
    mensagem = f"""📊 *OPERAÇÃO CONFIRMADA*

Corretora: COWBEX ✅

🥇 *Moeda* = {ativo}
⏰ *Expiração* = 1 Minuto
📌 *Entrada* = {horario_entrada}

{('🟢 COMPRA' if direcao == 'COMPRA' else '🔴 VENDA')}

⚠️ *Proteção 1:* {(agora + timedelta(minutes=4)).strftime('%H:%M')}
⚠️ *Proteção 2:* {(agora + timedelta(minutes=5)).strftime('%H:%M')}

➡️ [Clique aqui para acessar a corretora](https://bit.ly/cadastre-corretora-segura )

❓ [Não sabe pegar os sinais? Clique aqui](https://t.me/c/2509048940/28 )
"""
    await enviar_mensagem(mensagem)
    print(f"[DEBUG] Sinal automático enviado: {ativo} {direcao} | Entrada {preco_entrada}")
    
    await asyncio.sleep(360) # Espera 6 minutos
    await enviar_resultado_async(ativo, direcao, preco_entrada)

# --- LOOPS DE EXECUÇÃO EM BACKGROUND ---

ultimo_sinal_automatico = None

def sinais_automaticos_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        if 9 <= agora.hour < 23:
            tentativas_por_hora = random.randint(2, 3)
            intervalos = []
            for _ in range(tentativas_por_hora):
                minutos_aleatorios = random.randint(0, 59)
                proximo_sinal = agora.replace(minute=minutos_aleatorios, second=0, microsecond=0)
                if proximo_sinal <= agora:
                    proximo_sinal += timedelta(hours=1)
                intervalos.append(proximo_sinal)
            intervalos.sort()
            tasks = []
            for horario_sinal in intervalos:
                segundos_ate_sinal = (horario_sinal - agora).total_seconds()
                if segundos_ate_sinal > 0:
                    async def enviar_com_delay(delay):
                        await asyncio.sleep(delay)
                        await enviar_sinal_automatico()
                    tasks.append(enviar_com_delay(segundos_ate_sinal))
            if tasks:
                try:
                    loop.run_until_complete(asyncio.gather(*tasks))
                except Exception as e:
                    # O erro original acontecia aqui. Agora a função interna já trata.
                    print(f"Erro no loop de sinais automáticos: {e}")
        proxima_hora = (agora + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        time.sleep(max(60, (proxima_hora - agora).total_seconds()))

def scheduler_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        db = load_db()
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        tasks = []
        disparos_validos = []
        
        for d in db.get("disparos", []):
            horario_obj = datetime.strptime(d["horario"], "%H:%M").replace(
                year=agora.year, month=agora.month, day=agora.day, tzinfo=ZoneInfo("America/Sao_Paulo"))
            
            # Processa apenas sinais de hoje que ainda não passaram
            if horario_obj.date() == agora.date() and horario_obj > agora:
                tasks.append(enviar_sinal_programado(d))
                disparos_validos.append(d)

        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks))
        
        # Limpa os disparos que já passaram para não serem reprocessados
        db['disparos'] = disparos_validos
        save_db(db)

        time.sleep(60)

# --- INICIALIZAÇÃO DO SERVIDOR ---

if __name__ == '__main__':
    threading.Thread(target=scheduler_loop, daemon=True).start()
    threading.Thread(target=sinais_automaticos_loop, daemon=True).start()
    
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
