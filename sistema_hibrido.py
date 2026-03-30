#!/usr/bin/env python3
"""
Sistema de Trading - MODO PRO DISCIPLINADO
- 1 operación por señal (OBLIGATORIO)
- 1 operación por vela por par
- Si ejecuta → NO vuelve a intentar esa señal
- Si falla → solo 1 reentrada
"""
import sys
import time
import os
import signal
import json
from datetime import datetime

sys.path.insert(0, '/home/mmkd/.local/share/Trash/files/binary-bot-master./binary-bot-master')
from iqoptionapi.stable_api import IQ_Option
import numpy as np

LOG_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/ciclo_log.txt"
SENAL_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/senal_ia.json"
STATE_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/estado.json"

CORRIENDO = True
MODO_SOLO_ANALISIS = False  # Solo análisis, sin ejecutar operaciones
ANALISIS_CADA = 900  # 15 minutos - menos análisis = menos operaciones
EJECUTOR_CADA = 15   # 15 segundos

IQ = None

# Límites
LIMITE_POR_VELA = 1
LIMITE_POR_PAR_CICLO = 1  # Solo 1 por par
LIMITE_TOTAL_CICLO = 1  # Solo 1 operación por ciclo
MAX_REUSO_SENAL = 1  # SOLO 1 INTENTO por señal

def cargar_estado():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {
            'operaciones_ciclo': 0,
            'operaciones_par': {},
            'operaciones_vela': {},
            'reuso_senal': 0,
            'senal_actual': None,
            'resultados_senal': [],
            'ultimo_resultado': {},
            'reentry_permitido': {},
            'inicio_ciclo': int(time.time()), 'ultima_operacion': 0,
            'ultima_senal_id': None
        }

def guardar_estado(estado):
    with open(STATE_FILE, "w") as f:
        json.dump(estado, f, indent=2)

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    linea = f"[{ts}] {msg}"
    print(linea)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(linea + "\n")
    except:
        pass

def signal_handler(sig, frame):
    global CORRIENDO
    log("🛑 Deteniendo sistema...")
    CORRIENDO = False

def get_iq():
    global IQ
    if IQ is None:
        try:
            IQ = IQ_Option("rancieljarol@gmail.com", "440Harold!!!!")
            IQ.connect()
        except Exception as e:
            log(f"❌ Error conexión: {str(e)[:50]}")
            return None
    return IQ

def detectar_swings(highs, lows):
    swings_high = []
    swings_low = []
    for i in range(3, len(highs)-3):
        if highs[i] == max(highs[i-3:i+4]):
            swings_high.append((i, highs[i]))
        if lows[i] == min(lows[i-3:i+4]):
            swings_low.append((i, lows[i]))
    return swings_high, swings_low

def detectar_bos(precio, swings_high, swings_low):
    bos = None
    if swings_high:
        ultimo_high = swings_high[-1][1]
        if precio > ultimo_high:
            bos = "BOS_ALCISTA"
    if swings_low:
        ultimo_low = swings_low[-1][1]
        if precio < ultimo_low:
            bos = "BOS_BAJISTA"
    return bos

def detectar_choch(estructura, precio, swings_high, swings_low):
    choch = False
    if estructura == "ALCISTA" and swings_low:
        ultimo_low = swings_low[-1][1]
        if precio < ultimo_low:
            choch = True
    if estructura == "BAJISTA" and swings_high:
        ultimo_high = swings_high[-1][1]
        if precio > ultimo_high:
            choch = True
    return choch

import pandas as pd

def detectar_zonas_pcr(closes, highs, lows, precio_actual, tolerancia=0.001, tf_sec=300):
    """Zonas S/R recientes con peso por recencia"""
    import time
    zonas = []
    todos_niveles = []
    n = len(closes)
    
    # Cada vela de 5m = 300s, de 15m = 900s
    seg_por_vela = tf_sec if tf_sec else 300
    
    for i in range(n):
        peso = (i + 1) / n  # más reciente = más peso
        todos_niveles.append((closes[i], peso))
        todos_niveles.append((highs[i], peso))
        todos_niveles.append((lows[i], peso))
    
    niveles_unicos = []
    for nivel, peso in todos_niveles:
        if abs(precio_actual - nivel) / precio_actual > 0.03:
            continue
        agregado = False
        for grupo in niveles_unicos:
            if abs(grupo['nivel'] - nivel) / nivel < tolerancia:
                grupo['toques'] += 1
                grupo['peso'] += peso
                grupo['nivel'] = (grupo['nivel'] * (grupo['toques'] - 1) + nivel) / grupo['toques']
                agregado = True
                break
        if not agregado:
            niveles_unicos.append({'nivel': nivel, 'toques': 1, 'peso': peso})
    
    for grupo in niveles_unicos:
        if grupo['toques'] >= 2:
            dist_pips = abs(precio_actual - grupo['nivel']) / precio_actual * 10000
            
            # Frescura basada en tiempo real
            ultimo_toque_idx = max(
                [i for i in range(len(closes)) 
                if abs(closes[i] - grupo['nivel']) / grupo['nivel'] < 0.001],
                default=0
            )
            velas_desde_toque = len(closes) - ultimo_toque_idx
            segundos_desde_toque = velas_desde_toque * seg_por_vela
            
            if segundos_desde_toque <= 4 * 3600:  # menos de 4 horas
                frescura = 'fresca'
                peso_frescura = 1.0
            elif segundos_desde_toque <= 24 * 3600:  # menos de 24 horas
                frescura = 'reciente'
                peso_frescura = 0.6
            else:
                frescura = 'vieja'
                peso_frescura = 0.2
            
            zonas.append({
                'nivel': grupo['nivel'],
                'toques': grupo['toques'],
                'peso': grupo['peso'],
                'distancia_pips': dist_pips,
                'frescura': frescura,
                'peso_frescura': peso_frescura
            })
    
    zonas.sort(key=lambda x: x['distancia_pips'])
    return zonas[:5]


def detectar_patron_pcr(opens, closes, highs, lows, zona_tipo):
    """Detecta patrón Y clasifica tipo PCR"""
    v = closes[-1]; o = opens[-1]
    h = highs[-1]; l = lows[-1]
    v2 = closes[-2]; o2 = opens[-2]
    h2 = highs[-2]; l2 = lows[-2]

    cuerpo = abs(v - o)
    mecha_a = h - max(v, o)
    mecha_b = min(v, o) - l
    cuerpo2 = abs(v2 - o2)
    rango = h - l

    if rango == 0:
        return "NINGUNO", "NINGUNO", 0

    # === SOPORTE -> buscar CALL ===
    if zona_tipo == "SOPORTE":
        # HAMMER / PINBAR CALL
        if mecha_b > cuerpo * 1.2 and mecha_a < mecha_b:
            patron = "HAMMER" if v >= o else "PINBAR_CALL"
            return patron, "REVERSAL", 20

        # BULLISH ENGULFING
        if v > o and v2 < o2 and cuerpo > cuerpo2 * 0.5:
            return "ENGULFING_CALL", "REVERSAL", 20

        # PIERCING LINE
        mitad_roja = o2 - (cuerpo2 * 0.5)
        if v2 < o2 and v > o and o < l2 and v > mitad_roja:
            return "PIERCING_LINE", "REVERSAL", 15

        # MORNING STAR
        if len(closes) >= 3:
            v3 = closes[-3]; o3 = opens[-3]
            cuerpo3 = abs(v3 - o3)
            cuerpo_medio = abs(v2 - o2)
            if (v3 < o3 and cuerpo_medio < cuerpo3 * 0.3
                and v > o and v > (o3 + v3) / 2):
                return "MORNING_STAR", "REVERSAL", 18

        # PULLBACK
        if (v > o and l <= min(lows[-5:-1]) * 1.001 and
            v > opens[-2] and cuerpo > cuerpo2 * 0.7):
            return "PULLBACK_CALL", "PULLBACK", 15

        # CONTINUIDAD
        if (v > o and cuerpo > (h - l) * 0.6 and mecha_b < cuerpo * 0.3):
            return "CONTINUIDAD_CALL", "CONTINUIDAD", 10

    # === RESISTENCIA -> buscar PUT ===
    elif zona_tipo == "RESISTENCIA":
        # SHOOTING STAR / PINBAR PUT
        if mecha_a > cuerpo * 1.2 and mecha_b < mecha_a:
            patron = "SHOOTING_STAR" if v <= o else "PINBAR_PUT"
            return patron, "REVERSAL", 20

        # BEARISH ENGULFING
        if v < o and v2 > o2 and cuerpo > cuerpo2 * 0.5:
            return "ENGULFING_PUT", "REVERSAL", 20

        # DARK CLOUD COVER
        mitad_verde = o2 + (cuerpo2 * 0.5)
        if v2 > o2 and v < o and o > h2 and v < mitad_verde:
            return "DARK_CLOUD", "REVERSAL", 15

        # EVENING STAR
        if len(closes) >= 3:
            v3 = closes[-3]; o3 = opens[-3]
            cuerpo3 = abs(v3 - o3)
            cuerpo_medio = abs(v2 - o2)
            if (v3 > o3 and cuerpo_medio < cuerpo3 * 0.3
                and v < o and v < (o3 + v3) / 2):
                return "EVENING_STAR", "REVERSAL", 18

        # PULLBACK PUT
        if (v < o and h >= max(highs[-5:-1]) * 0.999 and
            v < opens[-2] and cuerpo > cuerpo2 * 0.7):
            return "PULLBACK_PUT", "PULLBACK", 15

        # CONTINUIDAD PUT
        if (v < o and cuerpo > (h - l) * 0.6 and mecha_a < cuerpo * 0.3):
            return "CONTINUIDAD_PUT", "CONTINUIDAD", 10

    return "NINGUNO", "NINGUNO", 0
def calcular_obstaculos_pcr(zonas, precio_actual, direccion, tf):
    """Zonas entre precio y objetivo"""
    rango = 40 if tf == '15m' else 20
    obstaculos = 0
    for z in zonas:
        if z['distancia_pips'] < 2:
            continue
        if z['distancia_pips'] > rango:
            continue
        if direccion == "CALL" and z['nivel'] > precio_actual:
            obstaculos += 1
        elif direccion == "PUT" and z['nivel'] < precio_actual:
            obstaculos += 1
    return obstaculos



def calcular_macd(closes, fast=12, slow=26, signal=9):
    """MACD - Moving Average Convergence Divergence"""
    if len(closes) < slow + signal:
        return None, None, None
    
    # EMAs
    ema_fast = []
    ema_slow = []
    mult_fast = 2 / (fast + 1)
    mult_slow = 2 / (slow + 1)
    
    ema = closes[0]
    for c in closes:
        ema = c * mult_fast + ema * (1 - mult_fast)
        ema_fast.append(ema)
    
    ema = closes[0]
    for c in closes:
        ema = c * mult_slow + ema * (1 - mult_slow)
        ema_slow.append(ema)
    
    macd_line = [f - s for f, s in zip(ema_fast[-len(ema_slow):], ema_slow)]
    
    signal_line = []
    mult_sig = 2 / (signal + 1)
    ema = macd_line[0]
    for m in macd_line:
        ema = m * mult_sig + ema * (1 - mult_sig)
        signal_line.append(ema)
    
    histogram = [m - s for m, s in zip(macd_line[-len(signal_line):], signal_line)]
    
    return (macd_line[-1] if macd_line else None,
            signal_line[-1] if signal_line else None,
            histogram[-1] if histogram else None)


def calcular_adx(highs, lows, closes, period=14):
    """ADX - Average Directional Index"""
    if len(closes) < period + 1:
        return None
    
    plus_dm = []
    minus_dm = []
    
    for i in range(1, len(closes)):
        high_diff = highs[i] - highs[i-1]
        low_diff = lows[i-1] - lows[i]
        
        if high_diff > low_diff and high_diff > 0:
            plus_dm.append(high_diff)
        else:
            plus_dm.append(0)
        
        if low_diff > high_diff and low_diff > 0:
            minus_dm.append(low_diff)
        else:
            minus_dm.append(0)
    
    # ATR
    tr = []
    for i in range(1, len(closes)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr.append(max(hl, hc, lc))
    
    soft = 2 / (period + 1)
    atr = sum(tr[:period])
    for i in range(period, len(tr)):
        atr = (tr[i] * soft) + (atr * (1 - soft))
    
    # ADX
    plus_di = (sum(plus_dm[:period]) / atr * 100) if atr > 0 else 0
    minus_di = (sum(minus_dm[:period]) / atr * 100) if atr > 0 else 0
    
    if plus_di + minus_di > 0:
        adx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100
    else:
        adx = 0
    
    return adx

def validar_espacio_objetivo(precio, direccion, zonas, tf):
    """Verifica que hay espacio suficiente hacia el objetivo"""
    pips_minimo = 40 if tf == '15m' else 20
    
    if direccion == "CALL":
        # Buscar resistencia más cercana arriba
        resistencias = [z for z in zonas if z['nivel'] > precio]
        if not resistencias:
            return True, pips_minimo  # Camino libre
        siguiente = min(resistencias, key=lambda x: x['nivel'])
        espacio = (siguiente['nivel'] - precio) / precio * 10000
    else:
        # Buscar soporte más cercano abajo
        soportes = [z for z in zonas if z['nivel'] < precio]
        if not soportes:
            return True, pips_minimo
        siguiente = max(soportes, key=lambda x: x['nivel'])
        espacio = (precio - siguiente['nivel']) / precio * 10000
    
    tiene_espacio = espacio >= pips_minimo
    return tiene_espacio, round(espacio, 1)


def analizar_par(par, tf, tf_sec):
    """Análisis PCR completo - EMA real, zonas frescas, obstáculos, MACD"""
    iq = get_iq()
    if iq is None:
        return None
    
    try:
        candles = iq.get_candles(par, tf, 80, int(time.time()))
        if not candles or len(candles) < 30:
            return None
        
        import pandas as pd
        df = pd.DataFrame(candles)
        closes = df['close'].values
        highs = df['max'].values
        lows = df['min'].values
        opens = df['open'].values
        precio = closes[-1]
        
        # EMA REAL
        ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
        
        if ema20 > ema50 * 1.0001:
            estructura = "ALCISTA"
        elif ema20 < ema50 * 0.9999:
            estructura = "BAJISTA"
        else:
            estructura = "LATERAL"
        
        # MACD
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        macd_val = (ema12 - ema26).iloc[-1]
        macd_sig = (ema12 - ema26).ewm(span=9, adjust=False).mean().iloc[-1]
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi_s = 100 - (100 / (1 + gain / loss))
        rsi = rsi_s.iloc[-1]
        
        if pd.isna(rsi) or rsi < 15 or rsi > 85:
            return None
        
        # Zonas recientes (últimas 40 velas)
        v = 40
        zonas = detectar_zonas_pcr(closes[-v:], highs[-v:], lows[-v:], precio, tf_sec=tf)
        
        if not zonas:
            log(f"⛔ {par} {tf_sec}: Sin zonas relevantes")
            return None
        
        # Preferir zona alineada con estructura
        zona_actual = None
        for z in zonas:
            tipo_z = "SOPORTE" if z['nivel'] < precio else "RESISTENCIA"
            if (estructura == "ALCISTA" and tipo_z == "SOPORTE") or \
               (estructura == "BAJISTA" and tipo_z == "RESISTENCIA"):
                zona_actual = z
                break
        
        # Si no encuentra alineada, usa la más cercana
        if zona_actual is None:
            zona_actual = zonas[0]
        
        zona_precio = zona_actual['nivel']
        zona_tipo = "SOPORTE" if zona_precio < precio else "RESISTENCIA"
        direccion = "CALL" if zona_tipo == "SOPORTE" else "PUT"
        zona_toques = zona_actual['toques']
        zona_dist = zona_actual['distancia_pips']
        
        # Zona debe estar cerca
        max_pips = 25 if tf == 900 else 15
        if zona_dist > max_pips:
            log(f"⛔ {par} {tf_sec}: Zona lejos ({zona_dist:.1f} pips)")
            return None
        
        # Inicializar score base
        score = 0
        
        # Penalizar zonas viejas, bonus a zonas frescas
        if zona_actual.get('frescura') == 'vieja':
            score -= 10
            log(f"⚠️ {par} {tf_sec}: Zona vieja - penalizando score")
        elif zona_actual.get('frescura') == 'fresca':
            score += 5
            log(f"✅ {par} {tf_sec}: Zona fresca - bonus")
        
        # Dirección por zona
        direccion = "CALL" if zona_tipo == "SOPORTE" else "PUT"
        
        # Bloquear entradas contra tendencia fuerte
        if estructura == "ALCISTA" and direccion == "PUT":
            if score < 85:
                log(f"⛔ {par} {tf_sec}: Contra-tendencia ALCISTA con PUT bloqueado")
                return None
        
        if estructura == "BAJISTA" and direccion == "CALL":
            if score < 85:
                log(f"⛔ {par} {tf_sec}: Contra-tendencia BAJISTA con CALL bloqueado")
                return None
        
        # Patrón EN ZONA (obligatorio)
        patron, tipo_pcr, score_patron = detectar_patron_pcr(opens, closes, highs, lows, zona_tipo)
        
        if patron == "NINGUNO":
            log(f"⛔ {par} {tf_sec}: Sin patrón en zona {zona_tipo}")
            return None
        
        # Obstáculos
        obstaculos = calcular_obstaculos_pcr(zonas, precio, direccion, tf_sec)
        if obstaculos >= 2:
            log(f"⛔ {par} {tf_sec}: Camino bloqueado ({obstaculos} obstáculos)")
            return None
        
        # Validar espacio hacia objetivo
        tiene_espacio, espacio_pips = validar_espacio_objetivo(precio, direccion, zonas, tf_sec)
        
        if not tiene_espacio:
            log(f"⛔ {par} {tf_sec}: Sin espacio hacia objetivo ({espacio_pips} pips, mínimo {40 if tf_sec=='15m' else 20})")
            return None
        
        log(f"✅ {par} {tf_sec}: Espacio libre {espacio_pips} pips")
        
        # Score PCR
        # Score PCR (mantener ajuste de frescura)
        
        # Zona
        if zona_toques >= 3:
            score += 30
        elif zona_toques == 2:
            score += 20
        
        # 3er toque bonus
        if zona_toques >= 3:
            score += 10
        elif zona_toques == 2:
            score += 5
        
        # Tendencia
        dif_ema = abs(ema20 - ema50) / ema50
        if dif_ema > 0.002:
            score += 15
        elif dif_ema > 0.001:
            score += 10
        else:
            score += 5
        
        # Tendencia alineada con dirección
        if (estructura == "ALCISTA" and direccion == "CALL") or \
           (estructura == "BAJISTA" and direccion == "PUT"):
            score += 10
        elif (estructura == "ALCISTA" and direccion == "PUT") or \
           (estructura == "BAJISTA" and direccion == "CALL"):
            score -= 10
        
        # Patrón
        score += score_patron
        
        # MACD
        if (macd_val > macd_sig and direccion == "CALL") or \
           (macd_val < macd_sig and direccion == "PUT"):
            score += 5
        
        # RSI
        if (rsi < 30 and direccion == "CALL") or (rsi > 70 and direccion == "PUT"):
            score += 8
        elif 40 <= rsi <= 60:
            score += 4
        
        # Obstáculos
        if obstaculos == 0:
            score += 5
        elif obstaculos == 1:
            score -= 5
        
        # Decisión
        score_min = 85
        
        if score >= score_min:
            decision = "OPERAR"
        elif score >= score_min - 10:
            decision = "DÉBIL"
        else:
            decision = "NO"
        
        log(f"📊 {par} {tf_sec}: {estructura} | {zona_tipo} {zona_toques}T | " +
            f"{patron} | RSI:{rsi:.0f} | obs:{obstaculos} | score:{score} -> {decision}")
        
        return {
            'par': par,
            'tf': tf_sec,
            'estructura': estructura,
            'direccion': direccion,
            'zona': zona_tipo.lower(),
            'zona_tipo': zona_tipo,
            'zona_precio': zona_precio,
            'zona_toques': zona_toques,
            'zona_fuerza': 'fuerte' if zona_toques >= 3 else 'media',
            'zona_dist_pips': round(zona_dist, 1),
            'patron': patron,
            'rsi': round(rsi, 1),
            'macd_confirma': bool((macd_val > macd_sig and direccion == "CALL") or
                                  (macd_val < macd_sig and direccion == "PUT")),
            'obstaculos': obstaculos,
            'tipo_pcr': tipo_pcr,
            'score': score,
            'decision': decision,
            'precio': precio,
            'timestamp': int(time.time()),
            'vela_open_time': int(candles[-1]['from'])
        }
        
    except Exception as e:
        log(f"⚠️ Error analizando {par} {tf_sec}: {e}")
        return None




def generar_grafico_analisis(par, tf, tf_sec, df, zonas, mejor_resultado):
    """Genera imagen del análisis"""
    try:
        import mplfinance as mpf
        import matplotlib.pyplot as plt
        
        # Crear figura
        fig, ax = plt.subplots(figsize=(12, 6))
        
        # Obtener últimos 60 datos para el gráfico
        datos_grafico = df.tail(60).copy()
        
        # Agregar EMAs
        datos_grafico['EMA20'] = datos_grafico['close'].ewm(span=20, adjust=False).mean()
        datos_grafico['EMA50'] = datos_grafico['close'].ewm(span=50, adjust=False).mean()
        
        # Configurar columnas para mplfinance
        datos_grafico.index = pd.to_datetime(datos_grafico.index, unit='s')
        
        # Crear gráfico
        mpf.plot(datos_grafico, type='candle', style='yahoo', 
                ax=ax, volume=False, 
                ema=[20, 50], 
                title=f"{par} {tf_sec} - Score: {mejor_resultado.get('score', 0)}")
        
        # Agregar líneas de zonas
        if zonas:
            for z in zonas[:3]:
                nivel = z['nivel']
                toques = z['toques']
                ax.axhline(y=nivel, color='blue', linestyle='--', alpha=0.5, 
                          label=f"Zona {toques}T" if toques >= 3 else "")
        
        # Guardar
        plt.savefig('/home/mmkd/.openclaw/workspace/otto_trading/ultimo_analisis.png', 
                   dpi=100, bbox_inches='tight')
        plt.close()
        
        log(f"📈 Gráfico guardado: ultimo_analisis.png")
        
    except Exception as e:
        log(f"⚠️ Error generando gráfico: {e}")



def ejecutar_ciclo_analisis():
    log("="*50)
    log("🔄 ANÁLISIS (cada 5 min)")
    log("="*50)
    
    estado = cargar_estado()
    ahora = int(time.time())
    if ahora - estado.get('inicio_ciclo', 0) >= ANALISIS_CADA:
        estado['operaciones_ciclo'] = 0
        estado['operaciones_par'] = {}
        estado['operaciones_vela'] = {}
        estado['inicio_ciclo'] = ahora
    guardar_estado(estado)
    
    iq = get_iq()
    if iq is None:
        log("❌ Sin conexión")
        return
    
    try:
        balance = iq.get_balance()
        log(f"✅ Conectado. Balance: ${balance}")
    except Exception as e:
        log(f"❌ Error: {str(e)[:50]}")
        return
    
    PARES = [
        "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC",
        "USDCAD-OTC", "EURGBP-OTC", "EURJPY-OTC", "GBPJPY-OTC",
        "AUDJPY-OTC", "CADJPY-OTC"
    ]
    resultados = []
    
    for PAR in PARES:
        for tf, tf_sec in [(300, "5m"), (900, "15m")]:
            resultado = analizar_par(PAR, tf, tf_sec)
            if resultado:
                resultados.append(resultado)
    
    resultados.sort(key=lambda x: x['score'], reverse=True)
    
    log("")
    log("📊 RESULTADOS:")
    for r in resultados[:6]:
        imp = "🔥" if r.get('modo_impulso') else ""
        pb = "↓" if not r.get('pullback_ok') else ""
        log(f"  {r['par']:12} {r['tf']:3} | Est:{r['estructura']:8} | Z:{r['zona']:6} | S:{r['score']:2} {imp} {pb}")
    
    mejor = None
    for r in resultados:
        if r['decision'] == "OPERAR":
            mejor = r
            break
    
    if mejor:
        estado = cargar_estado()
        estado['reuso_senal'] = 0
        estado['senal_actual'] = f"{mejor['par']}_{mejor['tf']}_{mejor['timestamp']}"
        estado['ultima_senal_id'] = None
        guardar_estado(estado)
        
        log(f"🎯 SEÑAL: {mejor['par']} {mejor['tf']} -> {mejor['direccion']} (score {mejor['score']})")
        with open(SENAL_FILE, "w") as f:
            json.dump(mejor, f)
    else:
        log("❌ Sin señales OPERAR - NO se guarda")
        # Only save if OPERAR
    
    log("🏁 FIN ANÁLISIS")
    
    # Generar gráfico del mejor resultado
    if resultados:
        mejor = max(resultados, key=lambda x: x.get('score', 0))
        try:
            iq = get_iq()
            if iq:
                candles_graf = iq.get_candles(mejor['par'], 300 if mejor['tf']=='5m' else 900, 60, int(time.time()))
                if candles_graf:
                    df = pd.DataFrame(candles_graf)
                    zonas_graf = detectar_zonas_pcr(df['close'].values, df['max'].values, df['min'].values, df['close'].iloc[-1])
                    generar_grafico_analisis(mejor['par'], 300 if mejor['tf']=='5m' else 900, mejor['tf'], df, zonas_graf, mejor)
        except Exception as e:
            pass

def puede_operar(senal, estado):
    par = senal['par']
    
    # Signal ID único
    signal_id = f"{senal.get('par', '')}_{senal.get('tf', '')}_{senal.get('timestamp', 0)}"
    senal_actual = estado.get('senal_actual', '')
    
    log(f"🔍 [MODO PRO] Signal actual: {senal_actual}")
    log(f"🔍 [MODO PRO] Signal ID: {signal_id}")
    log(f"🔍 [MODO PRO] ultima_senal_id: {estado.get('ultima_senal_id')}")
    
    # Nueva señal - resetear
    if senal_actual != signal_id:
        estado['ultima_senal_id'] = None
        guardar_estado(estado)
        log(f"🔄 [MODO PRO] Nueva señal detectada - reseteando")
    
    # Ya se usó esta señal
    if estado.get('ultima_senal_id') == signal_id:
        log(f"⛔ [MODO PRO] Señal ya usada: {signal_id}")
        return False, "senal_usada"
    
    # Límite ciclo
    if estado.get('operaciones_ciclo', 0) >= LIMITE_TOTAL_CICLO:
        log(f"⛔ [MODO PRO] Límite ciclo ({LIMITE_TOTAL_CICLO})")
        return False, "limite_ciclo"
    
    # Límite par
    ops_par = estado.get('operaciones_par', {}).get(par, 0)
    if ops_par >= LIMITE_POR_PAR_CICLO:
        log(f"⛔ [MODO PRO] Límite par ({LIMITE_POR_PAR_CICLO})")
        return False, "limite_par"
    
    # Límite vela
    vela_key = f"{par}_{senal.get('tf', '')}_{senal.get('vela_open_time', 0)}"
    ops_vela = estado.get('operaciones_vela', {}).get(vela_key, 0)
    log(f"🔍 [MODO PRO] Intento #{ops_par+1} en {vela_key}")
    if ops_vela >= LIMITE_POR_VELA:
        log(f"⛔ [MODO PRO] Ya operó esta vela: {vela_key}")
        return False, "limite_vela"
    
    # Reuso de señal (1 solo intento)
    if estado.get('reuso_senal', 0) >= MAX_REUSO_SENAL:
        log(f"⛔ [MODO PRO] Máximo reuse ({MAX_REUSO_SENAL})")
        return False, "max_reuse"
    
    # Resultado anterior
    ultimo = estado.get('ultimo_resultado', {}).get(par)

    
    if ultimo == 'loss':
        reentry = estado.get('reentry_permitido', {}).get(par, True)
        if not reentry:
            log(f"⛔ [MODO PRO] Sin reentry permitido")
            return False, "sin_reentry"
    
    log(f"✅ [MODO PRO] Puede operar!")
    return True, "ok"

def ejecutar_operacion(senal, tiempo_desde_apertura):
    iq = get_iq()
    if iq is None:
        return False
    
    par = senal['par']
    direccion = senal['direccion']
    
    try:
        tf_sec_exec = {"5m": 300, "15m": 900}.get(senal.get("tf", "5m"), 300)
        candles = iq.get_candles(par, tf_sec_exec, 3, int(time.time()))
        if candles and len(candles) >= 1:
            precio_actual = candles[-1]['close']
            precio_senal = senal.get('precio', precio_actual)
            vela_open = candles[-1]['open']
            vela_high = candles[-1]['max']
            vela_low = candles[-1]['min']
            rango = vela_high - vela_low
            
            movimiento = abs(precio_actual - vela_open)
            if rango > 0 and movimiento > rango * 0.7:
                log(f"⛔ BLOQUEADO: Vela extendida")
                return False
            
            zona_precio = senal.get('zona_precio', 0)
            if zona_precio > 0:
                dist_zona = abs(precio_actual - zona_precio) / precio_actual
                if dist_zona > 0.003:
                    log(f"⚠️ Zona lejos: {dist_zona*100:.2f}%")
                    return False
            
            movimiento_pips = abs(precio_actual - precio_senal) / precio_senal * 10000
            if movimiento_pips > 20:
                log(f"⚠️ Movimiento: {movimiento_pips:.1f}p")
                return False
            
            dir_iq = 'call' if direccion == 'CALL' else 'put'
            
            # === EJECUTAR OPERACIÓN ===
            timeframes = {"1m": 1, "5m": 5, "15m": 15, "1m": 1}
            # Dynamic expiration - use remaining time in current candle
            tiempo_vela = senal.get("tiempo_restante", 60)
            # Round to nearest minute, max 5 min
            expiracion = min(5, max(1, int(tiempo_vela / 60)))
            log(f"⏱ Expir: {expiracion}min (vela={tiempo_vela}s)")
            resultado_buy = iq.buy(1, par, dir_iq, expiracion)
            if not resultado_buy[0]:
                log(f"❌ Compra fallida para {par} exp={expiracion}m")
                return False
            id = resultado_buy[1]
            log(f"⏱️ Expiración: {expiracion} minutos (TF: {senal.get('tf')})")
            log(f"✅ [MODO PRO] OPERACIÓN: {par} {dir_iq.upper()} $1 (id:{id})")
            
            # === ACTUALIZAR ESTADO ===
            estado = cargar_estado()
            
            # Contadores
            estado['operaciones_ciclo'] = estado.get('operaciones_ciclo', 0) + 1
            estado['operaciones_par'][par] = estado.get('operaciones_par', {}).get(par, 0) + 1
            
            vela_key = f"{par}_{senal.get('tf', '')}_{senal.get('vela_open_time', 0)}"
            estado['operaciones_vela'][vela_key] = estado.get('operaciones_vela', {}).get(vela_key, 0) + 1
            
            # Marcar señal como usada INMEDIATAMENTE
            signal_id = f"{senal.get('par', '')}_{senal.get('tf', '')}_{senal.get('timestamp', 0)}"
            estado['ultima_senal_id'] = signal_id
            estado['reuso_senal'] = estado.get('reuso_senal', 0) + 1
            guardar_estado(estado)

            # Verificar resultado real
            log(f"⏳ Esperando resultado de {par}...")
            
            # Esperar que expire la vela primero (duración TF + 10s margen)
            tiempo_espera = expiracion * 60 + 10
            log(f"⏳ Esperando {tiempo_espera}s a que expire la operación...")
            time.sleep(tiempo_espera)
            
            resultado = None
            for intento in range(3):
                time.sleep(5)
                try:
                    resultado = iq.check_win_v4(id)
                    if resultado is not None:
                        break
                except Exception as e:
                    log(f"⚠️ Error verificando resultado intento {intento+1}: {e}")

            if resultado is None:
                log(f"❓ Resultado desconocido: {par} - sin actualizar reentry")
                estado['ultimo_resultado'][par] = 'unknown'
            elif resultado > 0:
                log(f"✅ WIN: {par} +${resultado:.2f}")
                estado['ultimo_resultado'][par] = 'win'
                estado['reentry_permitido'][par] = False
            else:
                log(f"❌ LOSS: {par}")
                estado['ultimo_resultado'][par] = 'loss'
                estado['reentry_permitido'][par] = True

            guardar_estado(estado)
            log(f"💾 [MODO PRO] Estado guardado: ciclo={estado['operaciones_ciclo']}")
            log(f"📊 [MODO PRO] Estado: {estado}")

            return True
    except Exception as e:
        log(f"❌ Error: {str(e)[:40]}")
        return False

def ejecutar_ciclo_rapido():
    # Cargar estado primero
    estado = cargar_estado()
    log(f"🔍 [MODO PRO] Estado cargado: {estado.get('operaciones_ciclo', 0)} operaciones")
    
    try:
        with open(SENAL_FILE, "r") as f:
            senal = json.load(f)
    except:
        log(f"⏳ [MODO PRO] Sin señal")
        return
    
    if time.time() - senal.get('timestamp', 0) > 300:
        log(f"⏳ [MODO PRO] Señal vencida")
        return
    
    # Verificar puede operar
    puede, razon = puede_operar(senal, estado)
    if not puede:
        log(f"⛔ [MODO PRO] No puede operar: {razon}")
        return
    
    iq = get_iq()
    if iq is None:
        return
    
    try:
        tf_sec_rap = {"5m": 300, "15m": 900}.get(senal.get("tf", "5m"), 300)
        candles = iq.get_candles(senal["par"], tf_sec_rap, 2, int(time.time()))
        if candles and len(candles) >= 1:
            vela_open_time = candles[-1]['from']
            tiempo_desde_apertura = int(time.time()) - vela_open_time
        else:
            return
    except:
        tiempo_desde_apertura = int(time.time()) % 300
    
    # NUEVA LÓGICA: verificar tiempo restante según timeframe
    tf_map = {"1m": 60, "5m": 300, "15m": 900}
    tf_sec = tf_map.get(senal.get('tf', '5m'), 300)
    tiempo_restante = tf_sec - (time.time() - senal.get('vela_open_time', 0))
    
    if tiempo_restante < 60:
        log(f"⛔ Vela muy avanzada: quedan {int(tiempo_restante)}s")
        return
    
    if MODO_SOLO_ANALISIS:
        log(f"🔍 [MODO SOLO ANÁLISIS] {senal['par']} {senal['direccion']} score={senal.get('score',0)} - NO se ejecuta")
        return
    
    score = senal.get('score', 0)
    log(f"🎯 [MODO PRO] {senal['par']} {senal['direccion']} (score {score}) | {tiempo_desde_apertura}s")
    ejecutar_operacion(senal, tiempo_desde_apertura)

def main():
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    log("🚀 SISTEMA MODO PRO DISCIPLINADO INICIADO")
    log(f"   Análisis: {ANALISIS_CADA}s | Ejecutor: {EJECUTOR_CADA}s")
    log(f"   Límites: ciclo={LIMITE_TOTAL_CICLO} | par={LIMITE_POR_PAR_CICLO} | vela={LIMITE_POR_VELA} | reuse={MAX_REUSO_SENAL}")
    
    # Resetear estado
    estado = cargar_estado()
    estado['operaciones_ciclo'] = 0
    estado['operaciones_par'] = {}
    estado['operaciones_vela'] = {}
    estado['reuso_senal'] = 0
    estado['inicio_ciclo'] = int(time.time())
    estado['ultima_senal_id'] = None
    estado['ultimo_resultado'] = {}
    estado['reentry_permitido'] = {}
    guardar_estado(estado)
    
    log(f"Estado inicial: {estado}")
    
    ejecutar_ciclo_analisis()
    estado = cargar_estado()
    log(f"Estado después de análisis: {estado}")
    
    ultimo_analisis = time.time()
    ciclos_ejecutor = 0
    
    while CORRIENDO:
        ahora = time.time()
        
        if ahora - ultimo_analisis >= ANALISIS_CADA:
            ejecutar_ciclo_analisis()
            ultimo_analisis = ahora
            ciclos_ejecutor = 0
        
        if ahora - ultimo_analisis > 60:
            ciclos_ejecutor += 1
            if ciclos_ejecutor % EJECUTOR_CADA == 0:
                ejecutar_ciclo_rapido()
        
        time.sleep(1)
    
    log("🛑 Sistema detenido")

if __name__ == "__main__":
    main()