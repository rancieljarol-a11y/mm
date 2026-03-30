#!/usr/bin/env python3
"""
Simulación de 50 ciclos - SOLO ANALIZA, NO OPERA
Verifica que todos los filtros se ejecuten en orden
"""
import sys
import time
import json
from datetime import datetime
sys.path.insert(0, '/home/mmkd/.local/share/Trash/files/binary-bot-master./binary-bot-master')
from iqoptionapi.stable_api import IQ_Option
import numpy as np

# ==================== COPIAR FUNCIONES DEL BOT ====================

def es_otc(par):
    return "-OTC" in par

def filtro_mercado_peligroso(opens, closes, highs, lows, rsi, atr):
    razones = []
    if atr < 0.0005:
        razones.append("ATR bajo")
    ultimas_5_rangos = [(highs[i] - lows[i]) / highs[i] for i in range(-5, 0)]
    rango_prom = sum(ultimas_5_rangos) / len(ultimas_5_rangos)
    if rango_prom < 0.0003:
        razones.append("Velas pequenas")
    e9, e20, e50 = sum(closes[-9:])/9, sum(closes[-20:])/20, sum(closes[-50:])/50
    if abs(e9-e20)/e20 < 0.001 and abs(e20-e50)/e50 < 0.001:
        razones.append("Mercado lateral")
    if rsi < 20 or rsi > 80:
        razones.append(f"RSI extremo {rsi:.0f}")
    bloqueos = [r for r in razones if "extremo" in r or "bajo" in r or "lateral" in r or "pequenas" in r]
    if bloqueos:
        return False, bloqueos[0]
    if razones:
        return True, f"ADVERTENCIA: {razones[0]}"
    return True, "mercado seguro"

def clasificar_zonas(opens, closes, highs, lows, emas, precio):
    zonas = {'debil': [], 'media': [], 'fuerte': []}
    e9, e20, e50 = emas['e9'], emas['e20'], emas['e50']
    
    # Zonas classic (swings)
    swing_highs = [highs[i] for i in range(10, len(highs)-10) if highs[i] == max(highs[i-10:i+11])]
    swing_lows = [lows[i] for i in range(10, len(lows)-10) if lows[i] == min(lows[i-10:i+11])]
    
    for nivel in set(swing_highs):
        toques = sum(1 for h in swing_highs if abs(h - nivel) / nivel < 0.002)
        fuerza = "debil" if toques == 1 else ("media" if toques == 2 else "fuerte")
        if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
            fuerza = "fuerte"
        zonas[fuerza].append({'tipo': 'SWING_HIGH', 'nivel': nivel, 'toques': toques})
    
    for nivel in set(swing_lows):
        toques = sum(1 for l in swing_lows if abs(l - nivel) / nivel < 0.002)
        fuerza = "debil" if toques == 1 else ("media" if toques == 2 else "fuerte")
        if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
            fuerza = "fuerte"
        zonas[fuerza].append({'tipo': 'SWING_LOW', 'nivel': nivel, 'toques': toques})
    
    zona_cerca = None
    for fuerza in ['fuerte', 'media', 'debil']:
        for z in zonas[fuerza]:
            dist = abs(precio - z['nivel']) / precio
            if dist < 0.002:
                zona_cerca = (z, fuerza)
                break
        if zona_cerca:
            break
    
    return zonas, zona_cerca

def analizar_estructura(closes, highs, lows):
    swings_alcistas = []
    swings_bajistas = []
    
    for i in range(5, len(lows)-5):
        if lows[i] == min(lows[i-5:i+6]):
            swings_alcistas.append((i, lows[i]))
    
    for i in range(5, len(highs)-5):
        if highs[i] == max(highs[i-5:i+6]):
            swings_bajistas.append((i, highs[i]))
    
    ultimos_5_ascendentes = swings_alcistas[-5:]
    ultimos_5_descendentes = swings_bajistas[-5:]
    
    estructura = "TRANSICION"
    ultimo_BOS = None
    choch_activo = False
    choch_detalle = ""
    
    if len(ultimos_5_ascendentes) >= 2 and len(ultimos_5_descendentes) >= 2:
        hh_ok = all(ultimos_5_descendentes[i][1] > ultimos_5_descendentes[i-1][1] 
                    for i in range(1, len(ultimos_5_descendentes)))
        hl_ok = all(ultimos_5_ascendentes[i][1] > ultimos_5_ascendentes[i-1][1] 
                    for i in range(1, len(ultimos_5_ascendentes)))
        
        if hh_ok and hl_ok:
            estructura = "ALCISTA"
        
        ll_ok = all(ultimos_5_ascendentes[i][1] < ultimos_5_ascendentes[i-1][1] 
                    for i in range(1, len(ultimos_5_ascendentes)))
        lh_ok = all(ultimos_5_descendentes[i][1] < ultimos_5_descendentes[i-1][1] 
                    for i in range(1, len(ultimos_5_descendentes)))
        
        if ll_ok and lh_ok:
            estructura = "BAJISTA"
    
    precio_actual = closes[-1]
    
    if estructura == "ALCISTA":
        ultimo_lh = None
        for i, precio in reversed(ultimos_5_descendentes[:-1]):
            if i < len(closes) - 10:
                ultimo_lh = precio
                break
        
        ultimo_hl = None
        for i, precio in reversed(ultimos_5_ascendentes[:-1]):
            if i < len(closes) - 10:
                ultimo_hl = precio
                break
        
        if ultimo_lh and precio_actual > ultimo_lh:
            ultimo_BOS = ("BOS_ALCISTA", ultimo_lh)
        
        if ultimo_hl and precio_actual < ultimo_hl:
            choch_activo = True
            choch_detalle = f"Precio < HL"
            estructura = "TRANSICION"
    
    elif estructura == "BAJISTA":
        ultimo_ll = None
        for i, precio in reversed(ultimos_5_ascendentes[:-1]):
            if i < len(closes) - 10:
                ultimo_ll = precio
                break
        
        ultimo_lh = None
        for i, precio in reversed(ultimos_5_descendentes[:-1]):
            if i < len(closes) - 10:
                ultimo_lh = precio
                break
        
        if ultimo_ll and precio_actual < ultimo_ll:
            ultimo_BOS = ("BOS_BAJISTA", ultimo_ll)
        
        if ultimo_lh and precio_actual > ultimo_lh:
            choch_activo = True
            choch_detalle = f"Precio > LH"
            estructura = "TRANSICION"
    
    return {
        'estructura': estructura,
        'ultimo_BOS': ultimo_BOS,
        'choch_activo': choch_activo,
        'choch_detalle': choch_detalle
    }

def calcular_pcr_score(estructura, zona_fuerza, patron, rsi):
    score = 0
    if estructura in ["ALCISTA", "BAJISTA"]:
        score += 25
    elif estructura == "DÉBIL":
        score += 10
    
    if zona_fuerza == "fuerte":
        score += 15
    elif zona_fuerza == "media":
        score += 10
    
    if patron != "NINGUNO":
        score += 25
    
    if 35 < rsi < 65:
        score += 10
    elif 30 < rsi < 70:
        score += 5
    
    if score >= 65:
        return score, "OPERAR"
    elif score >= 50:
        return score, "DÉBIL"
    return score, "NO"

def analizar_par(iq, par, tf):
    """Análisis completo de un par - NO OPERA"""
    if es_otc(par):
        return None
    
    try:
        candles = iq.get_candles(par, tf, 100, int(time.time()))
        if not candles or len(candles) < 50:
            return None
        
        closes = [c['close'] for c in candles]
        highs = [c['max'] for c in candles]
        lows = [c['min'] for c in candles]
        opens = [c['open'] for c in candles]
        
        precio = closes[-1]
        vela = "CALL" if closes[-1] > opens[-1] else "PUT"
        
        # 1. RSI
        d = np.diff(closes)
        g = np.where(d > 0, d, 0)
        l = np.where(d < 0, -d, 0)
        rsi = 100 - (100 / (1 + np.mean(g[-14:])/(np.mean(l[-14:])+0.0001)))
        
        # 2. ATR
        atr = sum(abs(closes[i] - closes[i-1]) for i in range(-14, 0)) / 14
        
        # 3. FILTRO MERCADO PELIGROSO
        seguro, razon_mercado = filtro_mercado_peligroso(opens, closes, highs, lows, rsi, atr)
        
        # 4. EMAs
        e9, e20, e50 = sum(closes[-9:])/9, sum(closes[-20:])/20, sum(closes[-50:])/50
        emas = {'e9': e9, 'e20': e20, 'e50': e50}
        
        # 5. CLASIFICAR ZONAS
        _, zona_cerca = clasificar_zonas(opens, closes, highs, lows, emas, precio)
        
        # 6. ESTRUCTURA
        estructura = analizar_estructura(closes, highs, lows)
        
        # 7. FILTRO CHOCH
        if estructura['choch_activo']:
            return {
                'par': par, 'timeframe': tf,
                'estructura': estructura['estructura'],
                'choch': True,
                'zona': zona_cerca[1] if zona_cerca else 'NONE',
                'patron': 'NINGUNO',
                'score': 0,
                'decision': 'NO',
                'razon': f"CHOCH activo",
                'filtros': ['MERCADO', 'ESTRUCTURA', 'CHOCH']
            }
        
        # 8. Dirección
        if estructura['estructura'] == "ALCISTA":
            direccion = "CALL"
        elif estructura['estructura'] == "BAJISTA":
            direccion = "PUT"
        else:
            direccion = "CALL" if e20 > e50 else "PUT"
        
        # 9. Filtro zona
        if not zona_cerca or zona_cerca[1] == "debil":
            return {
                'par': par, 'timeframe': tf,
                'estructura': estructura['estructura'],
                'choch': False,
                'zona': 'debil',
                'patron': 'NINGUNO',
                'score': 0,
                'decision': 'NO',
                'razon': 'Zona debil',
                'filtros': ['MERCADO', 'ESTRUCTURA', 'ZONA']
            }
        
        # 10. Buscar patrón
        cuerpo = abs(closes[-1] - opens[-1])
        mecha_arriba = highs[-1] - max(opens[-1], closes[-1])
        mecha_abajo = min(opens[-1], closes[-1]) - lows[-1]
        
        patron = "NINGUNO"
        zona_nivel = zona_cerca[0]['nivel']
        
        if mecha_abajo > cuerpo * 2 and abs(precio - zona_nivel) / precio < 0.001:
            patron = "PINBAR_CALL"
        elif mecha_arriba > cuerpo * 2 and abs(precio - zona_nivel) / precio < 0.001:
            patron = "PINBAR_PUT"
        
        # 11. Filtros previos
        filtros_ok = True
        if patron == "NINGUNO":
            filtros_ok = False
        if vela != direccion:
            filtros_ok = False
        if rsi < 25 or rsi > 75:
            filtros_ok = False
        
        # 12. PCR
        if filtros_ok:
            zona_fuerza = zona_cerca[1]
            score, decision = calcular_pcr_score(estructura['estructura'], zona_fuerza, patron, rsi)
            
            return {
                'par': par, 'timeframe': tf,
                'estructura': estructura['estructura'],
                'choch': False,
                'zona': zona_fuerza,
                'patron': patron,
                'vela': vela,
                'direccion': direccion,
                'rsi': rsi,
                'score': score,
                'decision': decision,
                'razon': 'Análisis completo',
                'filtros': ['MERCADO', 'ESTRUCTURA', 'CHOCH', 'ZONA', 'PATRON', 'VELA', 'RSI', 'PCR']
            }
        else:
            return {
                'par': par, 'timeframe': tf,
                'estructura': estructura['estructura'],
                'choch': False,
                'zona': zona_cerca[1] if zona_cerca else 'NONE',
                'patron': patron,
                'score': 0,
                'decision': 'NO',
                'razon': 'Filtros previos fallaron',
                'filtros': ['MERCADO', 'ESTRUCTURA', 'CHOCH', 'ZONA']
            }
    
    except Exception as e:
        return None

# ==================== SIMULACIÓN 50 CICLOS ====================

print("="*70)
print("SIMULACIÓN DE 50 CICLOS - SOLO ANALIZA, NO OPERA")
print("="*70)

PARES = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURGBP", "USDCAD"]

IQ = IQ_Option("rancieljarol@gmail.com", "440Harold!!!!")
IQ.connect()
print("Conectado a IQ Option\n")

# Contadores
ciclos = 0
senales_validas = 0
operar = 0
debil = 0
no_operar = 0
bloqueos = {"MERCADO": 0, "CHOCH": 0, "ZONA": 0, "PATRON": 0, "RSI": 0, "DÉBIL": 0}

while ciclos < 50:
    # Obtener timestamp actual
    ts = int(time.time())
    segundo = ts % 300
    
    # Solo analizar al inicio de cada vela (cada 5 min)
    if segundo > 30:
        time.sleep(10)
        continue
    
    print(f"\n--- CICLO {ciclos + 1} ---")
    
    # Analizar todos los pares
    resultados = []
    
    for PAR in PARES:
        for tf in [300, 900]:
            r = analizar_par(IQ, PAR, tf)
            if r:
                resultados.append(r)
    
    # Ordenar por score
    resultados.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    if resultados:
        mejor = resultados[0]
        decision = mejor.get('decision', 'NO')
        
        print(f"  Par: {mejor['par']} | TF: {mejor['timeframe']}m")
        print(f"  Estructura: {mejor['estructura']} | CHOCH: {mejor['choch']}")
        print(f"  Zona: {mejor['zona']} | Patron: {mejor['patron']}")
        print(f"  Score: {mejor['score']} | Decision: {decision}")
        print(f"  Filtros ejecutados: {' > '.join(mejor.get('filtros', []))}")
        
        senales_validas += 1
        
        if decision == "OPERAR":
            operar += 1
        elif decision == "DÉBIL":
            debil += 1
            no_operar += 1
        else:
            no_operar += 1
        
        # Contar bloqueos
        if "CHOCH" in mejor.get('razon', ''):
            bloqueos["CHOCH"] += 1
        elif "Zona" in mejor.get('razon', ''):
            bloqueos["ZONA"] += 1
        elif "Patron" in mejor.get('razon', ''):
            bloqueos["PATRON"] += 1
        elif "RSI" in mejor.get('razon', ''):
            bloqueos["RSI"] += 1
        elif "MERCADO" in mejor.get('razon', ''):
            bloqueos["MERCADO"] += 1
    else:
        print("  Sin análisis válido")
    
    ciclos += 1
    
    # Esperar 1 minuto entre ciclos
    time.sleep(60)

# ==================== RESUMEN ====================
print("\n" + "="*70)
print("RESUMEN DE 50 CICLOS")
print("="*70)
print(f"Total ciclos ejecutados: {ciclos}")
print(f"Señales analizadas: {senales_validas}")
print(f"")
print(f"Decisiones:")
print(f"  OPERAR: {operar}")
print(f"  DÉBIL (ignorar): {debil}")
print(f"  NO OPERAR: {no_operar}")
print(f"")
print(f"Bloqueos por filtro:")
for k, v in bloqueos.items():
    print(f"  {k}: {v}")
print("="*70)