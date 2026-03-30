#!/usr/bin/env python3
"""
Análisis con IA - Se ejecuta cada 5 minutos
Guarda la mejor señal en senal_ia.json
"""
import sys
import time
import json
from datetime import datetime

sys.path.insert(0, '/home/mmkd/.local/share/Trash/files/binary-bot-master./binary-bot-master')
from iqoptionapi.stable_api import IQ_Option
import numpy as np

LOG_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/analisis_log.txt"
SENAL_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/senal_ia.json"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] {msg}\n")

def analizar_par(closes, highs, lows, opens, precio, rsi, atr, tf):
    """Análisis sin IA - basado en indicadores técnicos"""
    e9, e20, e50 = sum(closes[-9:])/9, sum(closes[-20:])/20, sum(closes[-50:])/50
    
    # Estructura
    if e9 > e20 > e50:
        estructura = "ALCISTA"
        direccion = "CALL"
    elif e9 < e20 < e50:
        estructura = "BAJISTA"
        direccion = "PUT"
    else:
        estructura = "LATERAL"
        direccion = "CALL" if e20 > e50 else "PUT"
    
    # Zona (soporte/resistencia)
    swing_h = [highs[i] for i in range(10, len(highs)-10) if highs[i] == max(highs[i-10:i+11])]
    swing_l = [lows[i] for i in range(10, len(lows)-10) if lows[i] == min(lows[i-10:i+11])]
    
    zona_fuerza = "debil"
    zona_tipo = "NINGUNO"
    zona_precio = 0
    
    # Buscar soporte
    for nivel in set(swing_l):
        toques = sum(1 for l in swing_l if abs(l - nivel) / nivel < 0.002)
        fuerza = "fuerte" if toques >= 3 else ("media" if toques == 2 else "debil")
        if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
            fuerza = "fuerte"
        dist = abs(precio - nivel) / precio
        if dist < 0.002 and (zona_fuerza == "debil" or fuerza == "fuerte"):
            zona_fuerza = fuerza
            zona_tipo = "SOPORTE"
            zona_precio = nivel
    
    # Buscar resistencia
    for nivel in set(swing_h):
        toques = sum(1 for h in swing_h if abs(h - nivel) / nivel < 0.002)
        fuerza = "fuerte" if toques >= 3 else ("media" if toques == 2 else "debil")
        if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
            fuerza = "fuerte"
        dist = abs(precio - nivel) / precio
        if dist < 0.002 and (zona_fuerza == "debil" or fuerza == "fuerte"):
            zona_fuerza = fuerza
            zona_tipo = "RESISTENCIA"
            zona_precio = nivel
    
    # Patrón PINBAR
    cuerpo = abs(closes[-1] - opens[-1])
    mecha_arriba = highs[-1] - max(opens[-1], closes[-1])
    mecha_abajo = min(opens[-1], closes[-1]) - lows[-1]
    
    patron = "NINGUNO"
    tiene_patron = False
    
    if zona_fuerza in ["media", "fuerte"]:
        if zona_tipo == "SOPORTE" and mecha_abajo > cuerpo * 2:
            patron = "PINBAR_CALL"
            tiene_patron = True
        elif zona_tipo == "RESISTENCIA" and mecha_arriba > cuerpo * 2:
            patron = "PINBAR_PUT"
            tiene_patron = True
    
    # Score
    score = 0
    if estructura in ["ALCISTA", "BAJISTA"]:
        score += 25
    elif estructura == "LATERAL" and zona_fuerza == "fuerte" and tiene_patron:
        score += 15
    
    if zona_fuerza == "fuerte":
        score += 15
    elif zona_fuerza == "media":
        score += 10
    
    if patron != "NINGUNO":
        score += 25
    
    if 35 < rsi < 65:
        score += 10
    
    if 15 < rsi < 85 and atr > 0.0002:
        score += 10
    
    # Decisión
    decision = "NO" if score < 50 else ("DÉBIL" if score < 65 else "OPERAR")
    
    return {
        'par': None,
        'tf': None,
        'estructura': estructura,
        'zona': zona_fuerza,
        'zona_tipo': zona_tipo,
        'zona_precio': zona_precio,
        'patron': patron,
        'direccion': direccion,
        'precio': precio,
        'score': score,
        'decision': decision,
        'rsi': rsi,
        'atr': atr,
        'timestamp': int(time.time())
    }

def ejecutar_analisis():
    log("="*50)
    log("🔄 ANÁLISIS IA (cada 5 min)")
    log("="*50)
    
    try:
        IQ = IQ_Option("rancieljarol@gmail.com", "440Harold!!!!")
        IQ.connect()
        balance = IQ.get_balance()
        log(f"✅ Conectado. Balance: ${balance}")
    except Exception as e:
        log(f"❌ Error conectando: {str(e)[:50]}")
        return
    
    PARES = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "EURGBP-OTC", "EURJPY-OTC", "GBPJPY-OTC"]
    resultados = []
    
    for PAR in PARES:
        for tf, tf_sec in [(300, "5m"), (900, "15m")]:
            try:
                time.sleep(0.2)
                candles = IQ.get_candles(PAR, tf, 60, int(time.time()))
                if type(candles) == list and len(candles) >= 50:
                    closes = [c['close'] for c in candles]
                    highs = [c['max'] for c in candles]
                    lows = [c['min'] for c in candles]
                    opens = [c['open'] for c in candles]
                    precio = closes[-1]
                    
                    # RSI
                    d = np.diff(closes)
                    g = np.where(d > 0, d, 0)
                    l = np.where(d < 0, -d, 0)
                    rsi = 100 - (100 / (1 + np.mean(g[-14:])/(np.mean(l[-14:])+0.0001)))
                    
                    # ATR
                    atr = sum(abs(closes[i] - closes[i-1]) for i in range(-14, 0)) / 14
                    
                    analisis = analizar_par(closes, highs, lows, opens, precio, rsi, atr, tf)
                    analisis['par'] = PAR
                    analisis['tf'] = tf_sec
                    resultados.append(analisis)
            except Exception as e:
                log(f"⚠️ {PAR} {tf_sec}: {str(e)[:30]}")
    
    # Ordenar por score
    resultados.sort(key=lambda x: x['score'], reverse=True)
    
    log("")
    log("📊 RESULTADOS:")
    for r in resultados[:6]:
        log(f"  {r['par']:12} {r['tf']:3} | Est:{r['estructura']:8} | Z:{r['zona']:6} | Pat:{r['patron']:12} | S:{r['score']:2}")
    
    # Guardar mejor señal
    mejor = None
    for r in resultados:
        if r['decision'] == "OPERAR":
            mejor = r
            break
    
    if mejor:
        log(f"")
        log(f"🎯 MEJOR SEÑAL: {mejor['par']} {mejor['tf']} -> {mejor['direccion']} (score {mejor['score']})")
        
        # Guardar para ejecutor
        with open(SENAL_FILE, "w") as f:
            json.dump(mejor, f)
        log(f"✅ Señal guardada en senal_ia.json")
    else:
        log("❌ Sin señales OPERAR")
        # Guardar aunque sea DÉBIL
        if resultados:
            mejor = resultados[0]
            with open(SENAL_FILE, "w") as f:
                json.dump(mejor, f)
    
    log("🏁 FIN ANÁLISIS")
    log("="*50)

if __name__ == "__main__":
    ejecutar_analisis()