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

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
bot = Bot(token=BOT_TOKEN)

DB_FILE = "database.json"

# Cria o arquivo JSON se não existir
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump({"ativos": ["BNB/USDT", "XRP/USD", "BTC/USD", "ETH/USDT", "DOGE/USD", "SOL/USD"], "disparos": []}, f, indent=2)

def load_db():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

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
        # Espera: horario (HH:MM), ativo, direcao ("COMPRA"/"VENDA"), resultado ("WIN"/"LOSS")
        horario = data.get("horario")
        ativo = data.get("ativo")
        direcao = data.get("direcao")
        resultado = data.get("resultado")
        
        if not (horario and ativo and direcao and resultado):
            return jsonify({"status": "error", "message": "Dados incompletos."}), 400
        
        # Evita duplicados exatos
        for d in db["disparos"]:
            if d["horario"] == horario and d["ativo"] == ativo and d["direcao"] == direcao:
                return jsonify({"status": "error", "message": "Disparo já agendado."}), 400
        
        db["disparos"].append({"horario": horario, "ativo": ativo, "direcao": direcao, "resultado": resultado})
        save_db(db)
        return jsonify({"status": "ok", "disparos": db["disparos"]})

# Função para enviar mensagens no Telegram
async def enviar_mensagem(texto):
    await bot.send_message(chat_id=CHAT_ID, text=texto, parse_mode="Markdown")

async def enviar_resultado_async(ativo, direcao, resultado):
    print(f"Enviando resultado: {resultado} para {ativo} {direcao}")  # Debug
    
    if resultado == "WIN":
        sticker_win = "CAACAgEAAxkBAi1jHGiaaHZB7SG-0V7xeSFmIjMhEnRlAAKmBgACsFWZRmsygMkofbBeNgQ"
        await bot.send_sticker(chat_id=CHAT_ID, sticker=sticker_win)
        print("Sticker de vitória enviado")  # Debug
    elif resultado == "LOSS":
        mensagens_derrota = [
            "DEU F TROPA! Siga o gerenciamento!",
            "Siga o gerenciamento família, saiu totalmente do padrão.",
            "Stopou? Segue o gerenciamento!!",
            "Fzada família! Mas estamos extremamente assertivos! Bora pra guerra!",
            "Não respeitou esse safado, bora pra próxima"
        ]
        
        # Seleciona uma mensagem aleatória
        mensagem_derrota = random.choice(mensagens_derrota)
        await enviar_mensagem(mensagem_derrota)
        print("Mensagem de derrota enviada")  # Debug
    else:
        print(f"Resultado inválido: {resultado}")  # Debug

async def enviar_sinal_programado(d):
    # calcula quantos segundos faltam para o horário do disparo
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    horario_obj = datetime.strptime(d["horario"], "%H:%M").replace(year=agora.year, month=agora.month, day=agora.day, tzinfo=ZoneInfo("America/Sao_Paulo"))
    segundos_ate_envio = (horario_obj - agora).total_seconds()
    
    if segundos_ate_envio < 0:
        # horário já passou hoje, não envia
        return
    
    await asyncio.sleep(segundos_ate_envio)
    
    horario_entrada = (datetime.strptime(d["horario"], "%H:%M") + timedelta(minutes=3)).strftime("%H:%M")
    
    # Monta e envia a mensagem do sinal
    mensagem = f"""📊 *OPERAÇÃO CONFIRMADA*

Corretora: COWBEX ✅

🥇 *Moeda* = {d['ativo']}
⏰ *Expiração* = 1 Minuto
📌 *Entrada* = {horario_entrada}

{('🟢 COMPRA' if d['direcao'] == 'COMPRA' else '🔴 VENDA')}

⚠️ *Proteção 1:* {(datetime.strptime(horario_entrada, '%H:%M') + timedelta(minutes=1)).strftime('%H:%M')}
⚠️ *Proteção 2:* {(datetime.strptime(horario_entrada, '%H:%M') + timedelta(minutes=2)).strftime('%H:%M')}

➡️ [Clique aqui para acessar a corretora](https://bit.ly/cadastre-corretora-segura)

❓ [Não sabe pegar os sinais? Clique aqui](https://t.me/c/2509048940/28)
"""
    
    await enviar_mensagem(mensagem)
    
    await asyncio.sleep(360)
    await enviar_resultado_async(d['ativo'], d['direcao'], d['resultado'])

async def enviar_sinal_automatico():
    db = load_db()
    ativos = db.get("ativos", [])
    
    if not ativos:
        return
    
    # Seleciona ativo e direção aleatórios
    ativo = random.choice(ativos)
    direcao = random.choice(["COMPRA", "VENDA"])
    
    # 80% chance de WIN, 20% chance de LOSS
    resultado = "WIN" if random.random() < 0.8 else "LOSS"
    
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    horario_entrada = (agora + timedelta(minutes=3)).strftime("%H:%M")
    
    # Monta e envia a mensagem do sinal
    mensagem = f"""📊 *OPERAÇÃO CONFIRMADA*

Corretora: COWBEX ✅

🥇 *Moeda* = {ativo}
⏰ *Expiração* = 1 Minuto
📌 *Entrada* = {horario_entrada}

{('🟢 COMPRA' if direcao == 'COMPRA' else '🔴 VENDA')}

⚠️ *Proteção 1:* {(agora + timedelta(minutes=4)).strftime('%H:%M')}
⚠️ *Proteção 2:* {(agora + timedelta(minutes=5)).strftime('%H:%M')}

➡️ [Clique aqui para acessar a corretora](https://bit.ly/cadastre-corretora-segura)

❓ [Não sabe pegar os sinais? Clique aqui](https://t.me/c/2509048940/28)
"""
    
    await enviar_mensagem(mensagem)
    
    await asyncio.sleep(360)
    await enviar_resultado_async(ativo, direcao, resultado)

def sinais_automaticos_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        hora_atual = agora.hour
        
        # Verifica se está no horário de funcionamento (9h às 23h)
        if 9 <= hora_atual < 23:
            # Gera de 3 a 4 sinais por hora
            sinais_por_hora = random.randint(3, 4)
            
            # Calcula intervalos aleatórios dentro da hora
            intervalos = []
            for _ in range(sinais_por_hora):
                # Gera minutos aleatórios dentro da hora atual
                minutos_aleatorios = random.randint(0, 59)
                proximo_sinal = agora.replace(minute=minutos_aleatorios, second=0, microsecond=0)
                
                # Se o horário já passou, agenda para a próxima hora
                if proximo_sinal <= agora:
                    proximo_sinal = proximo_sinal + timedelta(hours=1)
                
                intervalos.append(proximo_sinal)
            
            # Ordena os intervalos
            intervalos.sort()
            
            # Agenda os sinais
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
                    print(f"Erro ao enviar sinais automáticos: {e}")
        
        # Espera até o início da próxima hora
        proxima_hora = (agora + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        segundos_ate_proxima_hora = (proxima_hora - agora).total_seconds()
        time.sleep(max(60, segundos_ate_proxima_hora))

def scheduler_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while True:
        db = load_db()
        agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
        
        # Remove disparos do dia anterior (caso)
        disparos = db.get("disparos", [])
        
        # Roda as tarefas pendentes para disparar os sinais agendados para hoje
        tasks = []
        for d in disparos:
            horario_obj = datetime.strptime(d["horario"], "%H:%M").replace(year=agora.year, month=agora.month, day=agora.day, tzinfo=ZoneInfo("America/Sao_Paulo"))
            
            # Se já passou, não agenda mais
            if (horario_obj - agora).total_seconds() >= 0:
                tasks.append(enviar_sinal_programado(d))
        
        if tasks:
            loop.run_until_complete(asyncio.gather(*tasks))
        
        time.sleep(60)  # checa a cada 1 minuto

threading.Thread(target=scheduler_loop, daemon=True).start()
threading.Thread(target=sinais_automaticos_loop, daemon=True).start()

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)
