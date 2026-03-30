#!/usr/bin/env python3
"""
OttO Trading Bot - Modo Automático
Ciclo cada 10 minutos
"""
import sys
import time
from datetime import datetime

sys.path.insert(0, '/home/mmkd/Escritorio/binary-bot-master./binary-bot-master')

from iqoptionapi.stable_api import IQ_Option
import numpy as np

PARES = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURGBP", "USDCAD", "EURJPY", "GBPJPY"]
EMAIL = "rancieljarol@gmail.com"
PASSWORD = "440Harold!!!!"
LOG_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/log.txt"

def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def analizar():
    log("Conectando...")
    IQ = IQ_Option(EMAIL, PASSWORD)
    IQ.connect()
    log("Conectado!")
    
    resultados = []
    
    for PAR in PARES:
        try:
            candles = IQ.get_candles(PAR, 300, 80, time.time())
            if not candles:
                continue
            
            data = [(c['open'], c['max'], c['min'], c['close']) for c in candles]
            closes = [d[3] for d in data]
            precio = closes[-1]
            
            # EMA
            ema20 = sum(closes[-20:])/20
            ema50 = sum(closes[-50:])/50
            tendencia = "CALL" if ema20 > ema50 else "PUT"
            
            # RSI
            deltas = np.diff(closes)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = np.mean(gains[-14:])
            avg_loss = np.mean(losses[-14:])
            rsi = 100 - (100 / (1 + avg_gain/(avg_loss+0.0001)))
            
            # Zonas
            zona_score = 0
            for i in range(len(closes)-20, len(closes)):
                toques = sum(1 for j in range(len(closes)-20, len(closes)) 
                           if abs(closes[j] - closes[i]) / closes[i] < 0.002)
                if toques >= 2:
                    zona_score = toques * 10
                    break
            
            # Patrones
            patrones = []
            for i in range(-3, 0):
                o, h, l, c = data[i]
                cuerpo = abs(c - o)
                if c > o and (min(o, c) - l) > cuerpo * 1.5:
                    patrones.append("HAMMER")
                elif c < o and (h - max(o, c)) > cuerpo * 1.5:
                    patrones.append("SHOOTING")
            
            # Score
            score = zona_score
            score += 15 if abs(ema20-ema50)/ema50 > 0.001 else 10
            score += 8 if rsi < 35 or rsi > 65 else 4
            score += len(patrones) * 15
            
            # Direccion
            direccion = tendencia
            if "HAMMER" in patrones:
                direccion = "CALL"
            elif "SHOOTING" in patrones:
                direccion = "PUT"
            
            resultados.append({
                'par': PAR,
                'precio': precio,
                'tendencia': tendencia,
                'rsi': rsi,
                'zona': zona_score,
                'patrones': patrones,
                'score': score,
                'direccion': direccion
            })
            
            log(f"  {PAR}: Score {score} | {direccion} | RSI {rsi:.1f}")
            
        except Exception as e:
            log(f"  {PAR}: Error - {e}")
    
    # Ordenar
    resultados.sort(key=lambda x: x['score'], reverse=True)
    
    # Ejecutar top 2
    ops = 0
    for r in resultados:
        if r['score'] >= 60 and ops < 2:
            log(f"  SEÑAL: {r['par']} {r['direccion']} (Score: {r['score']})")
            ops += 1
    
    if ops == 0:
        log("  Sin señales claras")
    
    log(f"Ciclo completado. Ops: {ops}")

# Loop
log("="*50)
log("INICIANDO BOT AUTOMATICO")
log("="*50)

while True:
    try:
        analizar()
    except Exception as e:
        log(f"Error: {e}")
    
    log("Durmiendo 10 minutos...")
    time.sleep(600)
