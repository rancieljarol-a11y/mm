#!/usr/bin/env python3
"""
Ciclo de Trading - Análisis + Ejecución con filtros de calidad
"""
import sys
import time
import json
from datetime import datetime

sys.path.insert(0, '/home/mmkd/.local/share/Trash/files/binary-bot-master./binary-bot-master')
from iqoptionapi.stable_api import IQ_Option
import numpy as np

LOG_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/ciclo_log.txt"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    linea = f"[{ts}] {msg}"
    print(linea)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(linea + "\n")
    except:
        pass

def filtro_mercado(opens, closes, highs, lows, rsi, atr, zona_fuerza, tiene_patron):
    if atr < 0.0002:
        return False, "ATR muy bajo"
    if rsi < 15 or rsi > 85:
        return False, f"RSI {rsi:.0f} extremo"
    e9, e20, e50 = sum(closes[-9:])/9, sum(closes[-20:])/20, sum(closes[-50:])/50
    estructura = "LATERAL"
    if e9 > e20 > e50:
        estructura = "ALCISTA"
    elif e9 < e20 < e50:
        estructura = "BAJISTA"
    if estructura in ["ALCISTA", "BAJISTA"]:
        return True, f"Estructura {estructura}"
    if zona_fuerza == "fuerte" and tiene_patron:
        return True, "Zona fuerte + patron en lateral"
    if zona_fuerza in ["media", "fuerte"]:
        return True, f"Zona {zona_fuerza}"
    return True, "Mercado ok"

def analizar_par(closes, highs, lows, opens, precio, tf):
    vela = "CALL" if closes[-1] > opens[-1] else "PUT"
    d = np.diff(closes)
    g = np.where(d > 0, d, 0)
    l = np.where(d < 0, -d, 0)
    rsi = 100 - (100 / (1 + np.mean(g[-14:])/(np.mean(l[-14:])+0.0001)))
    atr = sum(abs(closes[i] - closes[i-1]) for i in range(-14, 0)) / 14
    e9, e20, e50 = sum(closes[-9:])/9, sum(closes[-20:])/20, sum(closes[-50:])/50
    if e9 > e20 > e50:
        estructura = "ALCISTA"
        direccion = "CALL"
    elif e9 < e20 < e50:
        estructura = "BAJISTA"
        direccion = "PUT"
    else:
        estructura = "LATERAL"
        direccion = "CALL" if e20 > e50 else "PUT"
    swing_h = [highs[i] for i in range(10, len(highs)-10) if highs[i] == max(highs[i-10:i+11])]
    swing_l = [lows[i] for i in range(10, len(lows)-10) if lows[i] == min(lows[i-10:i+11])]
    zona_fuerza = "debil"
    zona_tipo = "NINGUNO"
    for nivel in set(swing_h):
        toques = sum(1 for h in swing_h if abs(h - nivel) / nivel < 0.002)
        fuerza = "media" if toques == 2 else ("fuerte" if toques >= 3 else "debil")
        if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
            fuerza = "fuerte"
        dist = abs(precio - nivel) / precio
        if dist < 0.002 and (zona_fuerza == "debil" or fuerza == "fuerte"):
            zona_fuerza = fuerza
            zona_tipo = "RESISTENCIA"
    for nivel in set(swing_l):
        toques = sum(1 for l in swing_l if abs(l - nivel) / nivel < 0.002)
        fuerza = "media" if toques == 2 else ("fuerte" if toques >= 3 else "debil")
        if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
            fuerza = "fuerte"
        dist = abs(precio - nivel) / precio
        if dist < 0.002 and (zona_fuerza == "debil" or fuerza == "fuerte"):
            zona_fuerza = fuerza
            zona_tipo = "SOPORTE"
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
    seguro, razon_mercado = filtro_mercado(opens, closes, highs, lows, rsi, atr, zona_fuerza, tiene_patron)
    score = 0
    if seguro:
        score += 10
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
    if vela == direccion:
        score += 10
    decision = "NO"
    if score >= 85 and seguro:
        decision = "OPERAR"
    elif score >= 75 and seguro:
        decision = "DÉBIL"
    return {
        'estructura': estructura,
        'zona': zona_fuerza,
        'patron': patron,
        'direccion': direccion,
        'vela': vela,
        'rsi': rsi,
        'atr': atr,
        'score': score,
        'decision': decision,
        'razon': razon_mercado
    }

def ejecutar_ciclo():
    log("="*50)
    log("🔄 INICIANDO CICLO DE ANÁLISIS")
    log("="*50)
    try:
        IQ = IQ_Option("rancieljarol@gmail.com", "440Harold!!!!")
        IQ.connect()
        balance = IQ.get_balance()
        log(f"✅ Conectado. Balance: ${balance}")
    except Exception as e:
        log(f"❌ Error conectando: {str(e)[:50]}")
        return
    
    PARES = ["EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC", "EURGBP-OTC", "USDCAD-OTC", "EURJPY-OTC", "GBPJPY-OTC"]
    resultados = []
    
    for PAR in PARES:
        for tf, tf_sec in [(300, "5m"), (900, "15m")]:
            try:
                time.sleep(0.3)
                candles = IQ.get_candles(PAR, tf, 100, int(time.time()))
                if type(candles) == list and len(candles) >= 50:
                    closes = [c['close'] for c in candles]
                    highs = [c['max'] for c in candles]
                    lows = [c['min'] for c in candles]
                    opens = [c['open'] for c in candles]
                    precio = closes[-1]
                    analisis = analizar_par(closes, highs, lows, opens, precio, tf)
                    analisis['par'] = PAR
                    analisis['tf'] = tf_sec
                    resultados.append(analisis)
            except Exception as e:
                log(f"⚠️ Error {PAR} {tf_sec}: {str(e)[:30]}")
    
    resultados.sort(key=lambda x: x['score'], reverse=True)
    
    log("")
    log("📊 RESULTADOS:")
    log("-"*50)
    
    for r in resultados[:8]:
        log(f"  {r['par']:12} {r['tf']:3} | Est:{r['estructura']:8} | Z:{r['zona']:6} | Pat:{r['patron']:12} | S:{r['score']:2} | {r['decision']}")
    
    mejor = None
    for r in resultados:
        if r['decision'] == "OPERAR":
            mejor = r
            break
    
    if mejor:
        log(f"")
        log(f"🎯 SEÑAL: {mejor['par']} {mejor['tf']} -> {mejor['direccion']}")
        log(f"   Score: {mejor['score']} | Porque: {mejor['razon']}")
        
        # Obtener datos de vela actual para filtros de calidad
        try:
            candles_recientes = IQ.get_candles(mejor['par'], 300, 5, int(time.time()))
            if candles_recientes and len(candles_recientes) >= 2:
                vela_abierta = candles_recientes[-1]
                open_price = vela_abierta['open']
                current_price = vela_abierta['close']
                high_price = vela_abierta['max']
                low_price = vela_abierta['min']
                segundo_vela = int(time.time()) % 300
                
                # Multiplicador correcto para pares JPY (100) vs otros (10000)
                par_nombre = mejor['par'].replace('-OTC', '')
                multiplicador = 100 if par_nombre in ["USDJPY", "GBPJPY", "EURJPY"] else 10000
                
                movimiento_pips = abs(current_price - open_price) * multiplicador
                rango_vela_pips = (high_price - low_price) * multiplicador
                
                # Pullback
                direccion = mejor['direccion']
                if direccion == 'CALL':
                    pullback = (high_price - current_price) / high_price * multiplicador
                else:
                    pullback = (current_price - low_price) / low_price * multiplicador
                
                # Detectar volatilidad
                volatilidades_alta = rango_vela_pips > 30
                limite_tiempo = 8 if volatilidades_alta else 15
                
                # Detectar modo impulso
                closes = [c['close'] for c in candles_recientes]
                opens_c = [c['open'] for c in candles_recientes]
                highs_c = [c['max'] for c in candles_recientes]
                lows_c = [c['min'] for c in candles_recientes]
                
                cuerpo1 = abs(closes[-1] - opens_c[-1])
                rango1 = highs_c[-1] - lows_c[-1]
                cuerpo2 = abs(closes[-2] - opens_c[-2])
                rango2 = highs_c[-2] - lows_c[-2]
                fuerza_vela1 = cuerpo1 / rango1 if rango1 > 0 else 0
                fuerza_vela2 = cuerpo2 / rango2 if rango2 > 0 else 0
                
                e9, e20 = sum(closes[-9:])/9, sum(closes[-20:])/20
                tendencia_fuerte = abs(e9 - e20) / e20 > 0.002
                
                modo_impulso = False
                if (tendencia_fuerte and fuerza_vela1 > 0.7 and fuerza_vela2 > 0.7 and 
                    50 < mejor['rsi'] < 70 and mejor['atr'] > 0.0005):
                    modo_impulso = True
                    log(f"🔥 MODO IMPULSO detectado (fuerza {fuerza_vela1*100:.0f}%/{fuerza_vela2*100:.0f}%)")
                
                # Aplicar filtros
                entrada_valida = True
                razon_rechazo = ""
                
                # Filtro tiempo - permitir ejecución en primeros 4 minutos
                # Solo rechazar en último minuto (240-300s)
                limite_tiempo_impulso = 295 if modo_impulso else 295
                if segundo_vela > limite_tiempo_impulso:
                    entrada_valida = False
                    razon_rechazo = f"Fuera de tiempo ({segundo_vela}s)"
                
                # Filtro movimiento
                par_nombre = mejor['par'].replace('-OTC', '')
                max_pips = 40 if par_nombre in ["USDJPY", "GBPJPY", "EURJPY"] else 15
                if entrada_valida and movimiento_pips > max_pips:
                    entrada_valida = False
                    razon_rechazo = f"Movimiento excesivo ({movimiento_pips:.1f}p)"
                
                # Filtro pullback (ignorado en modo impulso) - permitir hasta 2 min
                if entrada_valida:
                    min_pullback = 2 if volatilidades_alta else 3
                    if not modo_impulso and pullback < min_pullback:
                        if segundo_vela > 120:
                            entrada_valida = False
                            razon_rechazo = f"Impulso directo sin pullback ({pullback:.1f}p)"
                
                # Filtro 50% vela - permitir hasta 4 minutos
                if entrada_valida and segundo_vela > 295:
                    entrada_valida = False
                    razon_rechazo = f"Demasiado tarde ({segundo_vela}s > 150s)"
                
                # Ejecutar si todo ok
                if entrada_valida:
                    segundo = int(time.time()) % 300
                    if segundo < 30:
                        try:
                            direccion = 'call' if mejor['direccion'] == 'CALL' else 'put'
                            IQ.buy(1, mejor['par'], direccion, 15)
                            tipo_modo = "IMPULSO" if modo_impulso else "SNIPER"
                            log(f"✅ OPERACIÓN {tipo_modo}: {mejor['par']} {direccion.upper()} $1")
                        except Exception as e:
                            log(f"❌ Error: {str(e)[:40]}")
                    else:
                        tiempo_espera = 300 - segundo
                        log(f"⏰ Tiempo inadecuado. Ejecutar en {tiempo_espera}s...")
                        with open("/home/mmkd/.openclaw/workspace/otto_trading/senal.json", "w") as f:
                            json.dump(mejor, f)
                else:
                    log(f"❌ Entrada rechazada: {razon_rechazo}")
        except Exception as e:
            log(f"⚠️ Error: {str(e)[:40]}")
    else:
        log("❌ Sin señales OPERAR")
        if resultados:
            r = resultados[0]
            if r['patron'] == "NINGUNO":
                log("💡 Falta: Patrón")
    
    log("")
    log("🏁 FIN CICLO")
    log("="*50)

if __name__ == "__main__":
    ejecutar_ciclo()