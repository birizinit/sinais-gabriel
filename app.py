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

BOT_TOKEN = "7977214804:AAEepDqlFc130dIRCEfV89hNCwxJf0xKVdw"
CHAT_ID = "-1002562295376"
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
    if resultado == "WIN":
        sticker_win = "CAACAgEAAxkBAi1jHGiaaHZB7SG-0V7xeSFmIjMhEnRlAAKmBgACsFWZRmsygMkofbBeNgQ"
        await bot.send_sticker(chat_id=CHAT_ID, sticker=sticker_win)
    else:
        mensagem_derrota = (
            "DEU F TROPA! Siga o gerenciamento!\n\n"
            "Siga o gerenciamento família, saiu totalmente do padrão.\n\n"
            "Stopou? Segue o gerenciamento!!\n\n"
            "Fzada família! Mas estamos extremamente assertivos! Bora pra guerra!\n\n"
            "Não respeitou esse safado, bora pra próxima"
        )
        await enviar_mensagem(mensagem_derrota)

async def enviar_sinal_programado(d):
    # calcula quantos segundos faltam para o horário do disparo
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    horario_obj = datetime.strptime(d["horario"], "%H:%M").replace(year=agora.year, month=agora.month, day=agora.day, tzinfo=ZoneInfo("America/Sao_Paulo"))
    segundos_ate_envio = (horario_obj - agora).total_seconds()
    if segundos_ate_envio < 0:
        # horário já passou hoje, não envia
        return

    await asyncio.sleep(segundos_ate_envio)

    # Monta e envia a mensagem do sinal
    mensagem = f"""📊 *OPERAÇÃO CONFIRMADA*
Corretora: COWBEX ✅

🥇 *Moeda* = {d['ativo']}
⏰ *Expiração* = 1 Minuto
📌 *Entrada* = {d['horario']}

{('🟢 COMPRA' if d['direcao'] == 'COMPRA' else '🔴 VENDA')}

⚠️ *Proteção 1:* {(datetime.strptime(d['horario'], '%H:%M') + timedelta(minutes=1)).strftime('%H:%M')}
⚠️ *Proteção 2:* {(datetime.strptime(d['horario'], '%H:%M') + timedelta(minutes=2)).strftime('%H:%M')}

➡️ [Clique aqui para acessar a corretora](https://bit.ly/cadastre-corretora-segura)

❓ [Não sabe pegar os sinais? Clique aqui](https://t.me/c/2509048940/28)
"""
    await enviar_mensagem(mensagem)

    # Espera 1 min após o 2º gale para enviar resultado (total 3 min)
    await asyncio.sleep(180)
    await enviar_resultado_async(d['ativo'], d['direcao'], d['resultado'])

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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug)

