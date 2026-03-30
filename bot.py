#!/usr/bin/env python3
"""
OttO Trading Bot - V22 SISTEMA HÍBRIDO: ESTRUCTURA + ZONA + PATRÓN + PCR
El PCR ahora es FILTRO FINAL DE CALIDAD, no el jefe
"""
import sys, time
import json
from datetime import datetime
sys.path.insert(0, '/home/mmkd/.local/share/Trash/files/binary-bot-master./binary-bot-master')
from iqoptionapi.stable_api import IQ_Option
import numpy as np

# ==================== PCR COMO FILTRO FINAL ====================

def calcular_pcr_score(opens, closes, highs, lows, emas, estructura, zona_fuerza, patron, rsi):
    """
    PCR como FILTRO FINAL de calidad
    Solo se calcula si TODOS los filtros previos pasaron
    
    Returns: (score, decision, razones)
    """
    
    score = 0
    razones = []
    
    e9, e20, e50 = emas['e9'], emas['e20'], emas['e50']
    
    # === 1. PUNTOS DE ESTRUCTURA (más importante) ===
    if estructura in ["ALCISTA", "BAJISTA"]:
        score += 25
        razones.append("Estructura clara")
    elif estructura == "DÉBIL":
        score += 10
        razones.append("Estructura debil")
    
    # === 2. PUNTOS DE ZONA (menos peso, ya es obligatoria) ===
    if zona_fuerza == "fuerte":
        score += 15
        razones.append("Zona fuerte")
    elif zona_fuerza == "media":
        score += 10
        razones.append("Zona media")
    
    # === 3. PUNTOS DE PATRÓN (más importante si existe) ===
    if patron != "NINGUNO":
        score += 25
        razones.append(f"Patron: {patron}")
    
    # === 4. PUNTOS DE RSI ===
    if 35 < rsi < 65:
        score += 10
        razones.append("RSI ok")
    elif 30 < rsi < 70:
        score += 5
        razones.append("RSI borderline")
    
    # === 5. PUNTOS DE PULLBACK (detectar si viene de impulso) ===
    # Si el precio viene de un movimiento fuerte reciente
    rango_ultimas_5 = max(highs[-5:]) - min(lows[-5:])
    rango_promedio = sum(highs[-20:] - lows[-20:]) / 20
    
    if rango_ultimas_5 > rango_promedio * 1.5:
        score += 15
        razones.append("Pullback detected")
    
    # === 6. PUNTOS DE CONTINUIDAD ===
    # Si vela actual confirma tendencia
    vela_actual = "CALL" if closes[-1] > opens[-1] else "PUT"
    tendencia = "CALL" if estructura == "ALCISTA" else ("PUT" if estructura == "BAJISTA" else None)
    
    if tendencia and vela_actual == tendencia:
        score += 10
        razones.append("Vela confirma tendencia")
    
    # === DECISIÓN FINAL ===
    if score >= 65:
        decision = "OPERAR"
    elif score >= 50:
        decision = "DÉBIL"  # Ignorar
    else:
        decision = "NO"
    
    return score, decision, razones

# ==================== SISTEMA DE ZONAS MEJORADO ====================

def clasificar_zonas(opens, closes, highs, lows, emas, precio):
    """
    Detecta y clasifica zonas por FUERZA:
    - Zonas de IMPULSO: velas marubozu (cuerpo grande)
    - Zonas de RECHAZO: mechas largas repetidas
    - Zonas CLASSIC: swings highs/lows
    
    Returns: zonas clasificadas + nivel de fuerza
    """
    
    zonas = {
        'debil': [],      # 1 toque, sin confluencia
        'media': [],      # 2 toques o EMA
        'fuerte': []      # 3+ toques + confluencia
    }
    
    e9, e20, e50 = emas['e9'], emas['e20'], emas['e50']
    precio_actual = precio
    
    # === 1. ZONAS DE IMPULSO (Marubozu) ===
    for i in range(-20, -1):
        cuerpo = abs(closes[i] - opens[i])
        rango = highs[i] - lows[i]
        
        if rango > 0 and cuerpo / rango > 0.85:  # Marubozu
            nivel = (highs[i] + lows[i]) / 2
            fuerza = "media"
            
            # Verificar confluencia con EMA
            if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
                fuerza = "fuerte"
            
            zonas[fuerza].append({
                'tipo': 'IMPULSO',
                'nivel': nivel,
                'direccion': 'CALL' if closes[i] > opens[i] else 'PUT'
            })
    
    # === 2. Zonas de RECHAZO (mechas largas) ===
    for i in range(-20, -1):
        cuerpo = abs(closes[i] - opens[i])
        rango = highs[i] - lows[i]
        
        mecha_arriba = highs[i] - max(opens[i], closes[i])
        mecha_abajo = min(opens[i], closes[i]) - lows[i]
        
        # Mecha larga (> 2x cuerpo)
        if mecha_arriba > cuerpo * 2:
            nivel = highs[i]
            fuerza = "media"
            if abs(nivel - e20) / nivel < 0.002:
                fuerza = "fuerte"
            zonas[fuerza].append({
                'tipo': 'RECHAZO_BAJA',
                'nivel': nivel,
                'direccion': 'PUT'
            })
        
        if mecha_abajo > cuerpo * 2:
            nivel = lows[i]
            fuerza = "media"
            if abs(nivel - e20) / nivel < 0.002:
                fuerza = "fuerte"
            zonas[fuerza].append({
                'tipo': 'RECHAZO_ALTA',
                'nivel': nivel,
                'direccion': 'CALL'
            })
    
    # === 3. Zonas CLÁSICAS (swings) ===
    swing_highs = [highs[i] for i in range(10, len(highs)-10) if highs[i] == max(highs[i-10:i+11])]
    swing_lows = [lows[i] for i in range(10, len(lows)-10) if lows[i] == min(lows[i-10:i+11])]
    
    # Agrupar por toques
    for nivel in set(swing_highs):
        toques = sum(1 for h in swing_highs if abs(h - nivel) / nivel < 0.002)
        
        fuerza = "debil"
        if toques == 2:
            fuerza = "media"
        elif toques >= 3:
            fuerza = "fuerte"
        
        # Verificar confluencia EMA
        if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
            fuerza = "fuerte"
        
        zonas[fuerza].append({
            'tipo': 'SWING_HIGH',
            'nivel': nivel,
            'toques': toques,
            'direccion': 'PUT'
        })
    
    for nivel in set(swing_lows):
        toques = sum(1 for l in swing_lows if abs(l - nivel) / nivel < 0.002)
        
        fuerza = "debil"
        if toques == 2:
            fuerza = "media"
        elif toques >= 3:
            fuerza = "fuerte"
        
        if abs(nivel - e20) / nivel < 0.002 or abs(nivel - e50) / nivel < 0.002:
            fuerza = "fuerte"
        
        zonas[fuerza].append({
            'tipo': 'SWING_LOW',
            'nivel': nivel,
            'toques': toques,
            'direccion': 'CALL'
        })
    
    # === 4. BUSCAR ZONA MÁS CERCANA ===
    zona_cerca = None
    for fuerza in ['fuerte', 'media', 'debil']:
        for z in zonas[fuerza]:
            dist = abs(precio_actual - z['nivel']) / precio_actual
            if dist < 0.002:  # < 20 pips
                zona_cerca = (z, fuerza)
                break
        if zona_cerca:
            break
    
    return zonas, zona_cerca

# ==================== FILTRO DE MERCADO PELIGROSO (ADAPTATIVO) ====================

def filtro_mercado_peligroso(opens, closes, highs, lows, rsi, atr, zona_fuerza="debil", tiene_patron=False):
    """
    Filtro ADAPTATIVO - menos rígido
    Permite operar si hay zona FUERTE + patrón válido aunque sea mercado lateral
    Solo bloquea en casos EXTREMOS (no solo advertencias)
    
    Returns: (seguro: True/False, razon: str, tipo: 'SEGURO'/'ADVERTENCIA'/'BLOQUEO')
    """
    
    razones = []
    tipo = "SEGURO"
    
    # === 1. ATR bajo - SOLO BLOQUEAR si es muy extremo ===
    if atr < 0.0002:  # < 2 pips - muy muerto
        return False, "ATR muy bajo (mercado muerto)", "BLOQUEO"
    elif atr < 0.0004:
        razones.append("ATR bajo")
        tipo = "ADVERTENCIA"
    
    # === 2. RSI extremo - BLOQUEO ===
    if rsi < 15 or rsi > 85:
        return False, f"RSI extremo ({rsi:.0f})", "BLOQUEO"
    elif rsi < 25 or rsi > 75:
        razones.append(f"RSI {rsi:.0f}")
        tipo = "ADVERTENCIA"
    
    # === 3. Mercado LATERAL - PERMITIR si hay zona FUERTE + patrón ===
    e9 = sum(closes[-9:])/9
    e20 = sum(closes[-20:])/20
    e50 = sum(closes[-50:])/50
    
    emas_cerca = abs(e9 - e20) / e20 < 0.001 and abs(e20 - e50) / e50 < 0.001
    
    if emas_cerca:
        # Verificar si hay estructura por swings
        swing_h = [highs[i] for i in range(5, len(highs)-5) if highs[i] == max(highs[i-5:i+6])]
        swing_l = [lows[i] for i in range(5, len(lows)-5) if lows[i] == min(lows[i-5:i+6])]
        
        if len(swing_h) >= 3 and len(swing_l) >= 3:
            # Tiene estructura de swings - NO es lateral verdadero
            tipo = "ADVERTENCIA"
            razones.append("EMAs cerca pero hay estructura")
        else:
            # Es lateral verdadero
            if zona_fuerza == "fuerte" and tiene_patron:
                # EXCEPCIÓN: Permitir en rebote de zona FUERTE
                razones.append("Lateral pero zona FUERTE + patrón")
                tipo = "ADVERTENCIA"
            else:
                razones.append("Mercado lateral")
                tipo = "ADVERTENCIA"
    
    # === 4. Resumen ===
    if tipo == "BLOQUEO":
        return False, razones[0] if razones else "Mercado peligroso", "BLOQUEO"
    
    if razones:
        return True, " | ".join(razones), tipo
    
    return True, "mercado ok", "SEGURO"

# ==================== MEMORIA DE CONTEXTO ====================

class MemoriaContexto:
    """
    Sistema de memoria que:
    - Guarda dirección de últimas 20 velas
    - Guarda resultado de últimas 5 operaciones
    - Detecta mercado AGOTADO o LATERAL
    - Bloquea operaciones si hay malas condiciones
    """
    
    def __init__(self, archivo="contexto.json"):
        self.archivo = archivo
        self.cargar()
    
    def cargar(self):
        """Cargar estado desde archivo"""
        try:
            with open(self.archivo, "r") as f:
                datos = json.load(f)
                self.ultimas_velas = datos.get("ultimas_velas", [])
                self.resultados_operaciones = datos.get("resultados_operaciones", [])
                self.bloqueo_hasta = datos.get("bloqueo_hasta", 0)
        except:
            self.ultimas_velas = []
            self.resultados_operaciones = []
            self.bloqueo_hasta = 0
    
    def guardar(self):
        """Guardar estado a archivo"""
        with open(self.archivo, "w") as f:
            json.dump({
                "ultimas_velas": self.ultimas_velas,
                "resultados_operaciones": self.resultados_operaciones,
                "bloqueo_hasta": self.bloqueo_hasta
            }, f)
    
    def agregar_vela(self, direccion):
        """Agregar dirección de vela (CALL/PUT)"""
        self.ultimas_velas.append(direccion)
        # Mantener solo últimas 20
        if len(self.ultimas_velas) > 20:
            self.ultimas_velas = self.ultimas_velas[-20:]
        self.guardar()
    
    def agregar_resultado(self, resultado):
        """Agregar resultado de operación (ganada/perdida)"""
        self.resultados_operaciones.append(resultado)
        # Mantener últimos 5
        if len(self.resultados_operaciones) > 5:
            self.resultados_operaciones = self.resultados_operaciones[-5:]
        self.guardar()
    
    def analizar_estado(self, closes, highs, lows, opens):
        """
        Analizar estado actual del mercado
        Returns: NORMAL, AGOTADO, o LATERAL
        """
        
        # === 1. DETECTAR AGOTAMIENTO ===
        # Contar últimas 10 velas de mismo color
        ultimas_10 = self.ultimas_velas[-10:] if len(self.ultimas_velas) >= 10 else self.ultimas_velas
        
        mismo_color = 0
        for v in reversed(ultimas_10):
            if v == ultimas_10[-1]:
                mismo_color += 1
            else:
                break
        
        # Si 8+ velas del mismo color = AGOTADO
        if mismo_color >= 8:
            # Bloquear por 15 minutos
            self.bloqueo_hasta = time.time() + 900
            self.guardar()
            return "AGOTADO"
        
        # === 2. DETECTAR MERCADO LATERAL (ADAPTATIVO) ===
        # Ya NO bloqueamos completamente en lateral
        # Permitimos operaciones si hay zona FUERTE + patrón
        # Solo detectamos para informar, no para bloquear
        
        e9 = sum(closes[-9:])/9
        e20 = sum(closes[-20:])/20
        e50 = sum(closes[-50:])/50
        
        # Solo marcar lateral si EMAs muy cerca Y sin estructura de swings
        diff_9_20 = abs(e9 - e20) / e20
        diff_20_50 = abs(e20 - e50) / e50
        
        es_lateral = False
        if diff_9_20 < 0.001 and diff_20_50 < 0.001:
            # Verificar si hay estructura de swings
            swing_h = [highs[i] for i in range(5, len(highs)-5) if highs[i] == max(highs[i-5:i+6])]
            swing_l = [lows[i] for i in range(5, len(lows)-5) if lows[i] == min(lows[i-5:i+6])]
            
            # Si hay estructura de swings, NO es lateral verdadero
            if len(swing_h) >= 3 and len(swing_l) >= 3:
                # Tiene estructura - no es lateral
                es_lateral = False
            else:
                # Sin estructura clara - puede ser lateral
                # Pero ya no bloqueamos - permitimos con warning
                es_lateral = True
        
        # Guardar estado pero NO bloquear
        # El filtro de mercado perigroso handlea el bloqueo
        
        # === 3. VERIFICAR BLOQUEO ACTIVO ===
        if time.time() < self.bloqueo_hasta:
            tiempo_restante = int(self.bloqueo_hasta - time.time())
            log(f"🔒 BLOQUEADO por {tiempo_restante//60}min más")
            return "BLOQUEADO"
        
        # === 4. VERIFICAR rachas de PERDIDAS ===
        if len(self.resultados_operaciones) >= 3:
            ultimas_3 = self.resultados_operaciones[-3:]
            if ultimas_3.count("PERDIDA") >= 3:
                # 3 pérdidas consecutivas = posible racha mala
                # Reducir confianza temporalmente
                log("⚠️ 3 pérdidas seguidas - tener cuidado")
        
        return "NORMAL"
    
    def obtener_stats(self):
        """Obtener estadísticas de memoria"""
        return {
            "ultimas_velas": self.ultimas_velas[-10:],
            "resultados": self.resultados_operaciones,
            "bloqueo_activo": time.time() < self.bloqueo_hasta
        }

# ==================== DETECCIÓN DE ESTRUCTURA ====================

def analizar_estructura(closes, highs, lows):
    """
    Analiza estructura HH/HL/LH/LL + BOS + CHOCH
    
    CHOCH (Change of Character):
    - En tendencia ALCISTA: precio rompe el ÚLTIMO HL (soporte)
    - En tendencia BAJISTA: precio rompe el ÚLTIMO LH (resistencia)
    """
    
    swings_alcistas = []  # HL - Higher Lows
    swings_bajistas = []   # LH - Lower Highs
    
    # Encontrar swing lows (mínimos locales)
    for i in range(5, len(lows)-5):
        if lows[i] == min(lows[i-5:i+6]):
            swings_alcistas.append((i, lows[i]))
    
    # Encontrar swing highs (máximos locales)
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
        # Verificar HH + HL (tendencia alcista)
        hh_ok = all(ultimos_5_descendentes[i][1] > ultimos_5_descendentes[i-1][1] 
                    for i in range(1, len(ultimos_5_descendentes)))
        hl_ok = all(ultimos_5_ascendentes[i][1] > ultimos_5_ascendentes[i-1][1] 
                    for i in range(1, len(ultimos_5_ascendentes)))
        
        if hh_ok and hl_ok:
            estructura = "ALCISTA"
        
        # Verificar LL + LH (tendencia bajista)
        ll_ok = all(ultimos_5_ascendentes[i][1] < ultimos_5_ascendentes[i-1][1] 
                    for i in range(1, len(ultimos_5_ascendentes)))
        lh_ok = all(ultimos_5_descendentes[i][1] < ultimos_5_descendentes[i-1][1] 
                    for i in range(1, len(ultimos_5_descendentes)))
        
        if ll_ok and lh_ok:
            estructura = "BAJISTA"
    
    # Detectar BOS y CHOCH
    precio_actual = closes[-1]
    
    if estructura == "ALCISTA":
        # Buscar último LH significativo (no el más reciente)
        ultimo_lh = None
        for i, precio in reversed(ultimos_5_descendentes[:-1]):
            if i < len(closes) - 10:
                ultimo_lh = precio
                break
        
        # Buscar último HL significativo
        ultimo_hl = None
        for i, precio in reversed(ultimos_5_ascendentes[:-1]):
            if i < len(closes) - 10:
                ultimo_hl = precio
                break
        
        # BOS: precio rompe encima del último LH (continuidad alcista)
        if ultimo_lh and precio_actual > ultimo_lh:
            ultimo_BOS = ("BOS_ALCISTA", ultimo_lh)
        
        # CHOCH: precio rompe DEBAJO del último HL (cambio de carácter)
        if ultimo_hl and precio_actual < ultimo_hl:
            choch_activo = True
            choch_detalle = f"Precio {precio_actual:.5f} < HL {ultimo_hl:.5f}"
            estructura = "TRANSICION"  # Cambia a transición
    
    elif estructura == "BAJISTA":
        # Buscar último LL significativo
        ultimo_ll = None
        for i, precio in reversed(ultimos_5_ascendentes[:-1]):
            if i < len(closes) - 10:
                ultimo_ll = precio
                break
        
        # Buscar último LH significativo
        ultimo_lh = None
        for i, precio in reversed(ultimos_5_descendentes[:-1]):
            if i < len(closes) - 10:
                ultimo_lh = precio
                break
        
        # BOS: precio rompe debajo del último LL (continuidad bajista)
        if ultimo_ll and precio_actual < ultimo_ll:
            ultimo_BOS = ("BOS_BAJISTA", ultimo_ll)
        
        # CHOCH: precio rompe ARRIBA del último LH (cambio de carácter)
        if ultimo_lh and precio_actual > ultimo_lh:
            choch_activo = True
            choch_detalle = f"Precio {precio_actual:.5f} > LH {ultimo_lh:.5f}"
            estructura = "TRANSICION"  # Cambia a transición
    
    return {
        'estructura': estructura,
        'ultimo_BOS': ultimo_BOS,
        'choch_activo': choch_activo,
        'choch_detalle': choch_detalle
    }

# ==================== RESTO DEL SISTEMA ====================

def es_otc(par):
    return "-OTC" in par

def confirmacion_valida(opens, closes, highs, lows, direccion):
    cuerpo = abs(closes[-1] - opens[-1])
    rango = highs[-1] - lows[-1]
    if rango == 0:
        return False
    cuerpo_fuerte = cuerpo > rango * 0.5
    
    if direccion == "CALL":
        return closes[-1] > opens[-1] and cuerpo_fuerte
    else:
        return closes[-1] < opens[-1] and cuerpo_fuerte

def analisis_v21(iq, par, timeframe, memoria):
    """Análisis V21 con zonas mejoradas + filtro mercado peligroso"""
    if es_otc(par):
        return None
    
    try:
        candles = iq.get_candles(par, timeframe, 100, time.time())
        if not candles or len(candles) < 50:
            return None
        
        closes = [x['close'] for x in candles]
        highs = [x['max'] for x in candles]
        lows = [x['min'] for x in candles]
        opens = [x['open'] for x in candles]
        
        precio = closes[-1]
        
        # === ANALIZAR ESTADO CON MEMORIA ===
        estado = memoria.analizar_estado(closes, highs, lows, opens)
        
        # Si mercado bloqueado, no operar
        if estado in ["AGOTADO", "LATERAL", "BLOQUEADO"]:
            return {
                'par': par,
                'estado_mercado': estado,
                'puede_operar': False,
                'razon': f"MERCADO {estado}"
            }
        
        # === RSI ===
        d = np.diff(closes)
        g = np.where(d > 0, d, 0)
        l = np.where(d < 0, -d, 0)
        rsi = 50
        if len(g) >= 14:
            rsi = 100 - (100 / (1 + np.mean(g[-14:])/(np.mean(l[-14:])+0.0001)))
        
        # === ATR ===
        atr = sum(abs(closes[i] - closes[i-1]) for i in range(-14, 0)) / 14
        
        # === EMAs ===
        e9 = sum(closes[-9:])/9
        e20 = sum(closes[-20:])/20
        e50 = sum(closes[-50:])/50
        emas = {'e9': e9, 'e20': e20, 'e50': e50}
        
        # === CLASIFICAR ZONAS (MEJORADO) ===
        zonas_clasificadas, zona_cerca = clasificar_zonas(opens, closes, highs, lows, emas, precio)
        
        # === DETECTAR PATRÓN (para filtro adaptativo) ===
        cuerpo = abs(closes[-1] - opens[-1])
        mecha_arriba = highs[-1] - max(opens[-1], closes[-1])
        mecha_abajo = min(opens[-1], closes[-1]) - lows[-1]
        
        tiene_patron_temp = False
        if zona_cerca and zona_cerca[1] in ["media", "fuerte"]:
            zona_nivel = zona_cerca[0]['nivel']
            if mecha_abajo > cuerpo * 2 and abs(precio - zona_nivel) / precio < 0.001:
                tiene_patron_temp = True
            elif mecha_arriba > cuerpo * 2 and abs(precio - zona_nivel) / precio < 0.001:
                tiene_patron_temp = True
        
        # === FILTRO MERCADO PELIGROSO (ADAPTATIVO) ===
        zona_fuerza_val = zona_cerca[1] if zona_cerca else "debil"
        seguro, razon_seguro, tipo_mercado = filtro_mercado_peligroso(
            opens, closes, highs, lows, rsi, atr, zona_fuerza_val, tiene_patron_temp
        )
        
        # Si es BLOQUEO, no operar
        if tipo_mercado == "BLOQUEO":
            return {
                'par': par,
                'estado_mercado': 'BLOQUEADO',
                'tipo_mercado': tipo_mercado,
                'puede_operar': False,
                'razon': razon_seguro
            }
        
        # === ESTRUCTURA ===
        estructura = analizar_estructura(closes, highs, lows)
        
        # === FILTRO CHOCH: Si hay cambio de carácter, NO OPERAR ===
        if estructura['choch_activo']:
            return {
                'par': par,
                'estado_mercado': 'CHOCH',
                'puede_operar': False,
                'razon': f"CHOCH activo: {estructura.get('choch_detalle', 'Cambio de carácter')}"
            }
        
        # === DIRECCIÓN ===
        if estructura['estructura'] == "ALCISTA":
            direccion = "CALL"
        elif estructura['estructura'] == "BAJISTA":
            direccion = "PUT"
        else:
            direccion = "CALL" if e20 > e50 else "PUT"
        
        # === ZONA FUERTE REQUERIDA ===
        # Solo operar si hay zona MEDIA o FUERTE
        if zona_cerca is None or zona_cerca[1] == "debil":
            return {
                'par': par, 'score': 0, 'puede_operar': False,
                'estado_mercado': estado,
                'razon': 'Zona muy debil o inexistente'
            }
        
        # === PATRONES ===
        cuerpo = abs(closes[-1] - opens[-1])
        mecha_arriba = highs[-1] - max(opens[-1], closes[-1])
        mecha_abajo = min(opens[-1], closes[-1]) - lows[-1]
        
        patron = "NINGUNO"
        
        # Solo buscar patrón si está en zona FUERTE o MEDIA
        if zona_cerca and zona_cerca[1] in ["media", "fuerte"]:
            zona_nivel = zona_cerca[0]['nivel']
            if mecha_abajo > cuerpo * 2 and abs(precio - zona_nivel) / precio < 0.001:
                patron = "PINBAR_CALL"
            elif mecha_arriba > cuerpo * 2 and abs(precio - zona_nivel) / precio < 0.001:
                patron = "PINBAR_PUT"
        
        vela = "CALL" if closes[-1] > opens[-1] else "PUT"
        
        # Guardar dirección de vela en memoria
        memoria.agregar_vela(vela)
        
        # === VERIFICAR FILTROS PREVIOS (ADAPTATIVOS) ===
        filtros_ok = True
        filtros_fallo = []
        
        if patron == "NINGUNO":
            filtros_ok = False
            filtros_fallo.append("Sin patron")
        if vela != direccion:
            filtros_ok = False
            filtros_fallo.append("Vela≠Direccion")
        
        # RSI: solo bloquear en casos extremos (ya交给了 filtro_mercado_peligroso)
        # Aquí solo advertimos pero permitimos
        if rsi < 20 or rsi > 80:
            filtros_ok = False
            filtros_fallo.append(f"RSI{rsi:.0f}extremo")
        
        # === FILTRO FINAL: PCR SOLO SI TODO PASÓ ===
        if filtros_ok:
            # Solo calcular PCR si todos los filtros previos pasaron
            zona_fuerza = zona_cerca[1] if zona_cerca else "debil"
            pcr_score, decision, razones_pcr = calcular_pcr_score(
                opens, closes, highs, lows, emas,
                estructura['estructura'], zona_fuerza, patron, rsi
            )
            
            puede = (decision == "OPERAR")
            errores = filtros_fallo + razones_pcr
            
            return {
                'par': par,
                'timeframe': timeframe,
                'direccion': direccion,
                'estructura': estructura['estructura'],
                'ultimo_BOS': estructura['ultimo_BOS'],
                'patron': patron,
                'rsi': rsi,
                'score': pcr_score,
                'decision': decision,  # OPERAR / DÉBIL / NO
                'razones_pcr': razones_pcr,
                'estado_mercado': estado,
                'puede_operar': puede,
                'errores': errores,
                'precio': precio
            }
        else:
            return {
                'par': par,
                'timeframe': timeframe,
                'direccion': direccion,
                'estructura': estructura['estructura'],
                'patron': patron,
                'rsi': rsi,
                'score': 0,
                'decision': "NO",
                'estado_mercado': estado,
                'puede_operar': False,
                'errores': filtros_fallo,
                'precio': precio
            }
        
    except:
        return None

# ==================== BUCLE ====================

PARES_REALES = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURGBP", "USDCAD", "EURJPY", "GBPJPY"]

class GestorSeñales:
    def __init__(self):
        self.pendientes = []
    
    def agregar(self, senal):
        self.pendientes.append({'senal': senal, 'tiempo': time.time()})
    
    def confirmar(self, iq):
        confirmadas = []
        for item in self.pendientes:
            senal = item['senal']
            par = senal['par']
            
            candles = iq.get_candles(par, 300, 2, int(time.time()))
            if len(candles) >= 2:
                closes = [x['close'] for x in candles]
                opens = [x['open'] for x in candles]
                highs = [x['max'] for x in candles]
                lows = [x['min'] for x in candles]
                
                if confirmacion_valida(opens, closes, highs, lows, senal['direccion']):
                    confirmadas.append(senal)
        
        self.pendientes = []
        return confirmadas

def log(msg):
    with open("/home/mmkd/.openclaw/workspace/otto_trading/log.txt", "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M')}] {msg}\n")
    print(msg)

log("="*60)
log("BOT V22 - SISTEMA HÍBRIDO: ESTRUCTURA + ZONA + PATRÓN + PCR")
log("PCR como FILTRO FINAL de calidad")
log("="*60)

gestor = GestorSeñales()
memoria = MemoriaContexto("/home/mmkd/.openclaw/workspace/otto_trading/contexto.json")

while True:
    ahora = int(time.time())
    segundos = ahora % 300
    
    if segundos > 30:
        log(f"⏳ Esperar ({segundos}s)")
        time.sleep(60)
        continue
    
    try:
        log("Conectando...")
        IQ = IQ_Option("rancieljarol@gmail.com", "440Harold!!!!")
        IQ.connect()
        bal = IQ.get_balance()
        log(f"Balance: ${bal}")
        
        # Verificar estado del mercado
        candles_test = IQ.get_candles("EURUSD", 300, 50, int(time.time()))
        if candles_test:
            closes_test = [x['close'] for x in candles_test]
            highs_test = [x['max'] for x in candles_test]
            lows_test = [x['min'] for x in candles_test]
            opens_test = [x['open'] for x in candles_test]
            estado = memoria.analizar_estado(closes_test, highs_test, lows_test, opens_test)
            log(f"📊 Estado del mercado: {estado}")
        
        # Confirmar señales
        confirmadas = gestor.confirmar(IQ)
        
        if confirmadas:
            for senal in confirmadas:
                try:
                    IQ.buy(1, senal['par'], senal['direccion'].lower(), 15)
                    log(f">>> OPERADO: {senal['par']} {senal['direccion']}")
                    # Registrar resultado (después de 5 min)
                except Exception as e:
                    log(f"Error: {str(e)[:40]}")
        
        # Análisis nuevo
        resultados = []
        
        for PAR in PARES_REALES:
            for tf in [300, 900]:
                r = analisis_v21(IQ, PAR, tf, memoria)
                if r and r.get('puede_operar'):
                    resultados.append(r)
        
        resultados.sort(key=lambda x: x['score'], reverse=True)
        
        if resultados:
            mejor = resultados[0]
            decision = mejor.get('decision', 'OPERAR')
            razones = mejor.get('razones_pcr', [])
            log(f"📊 Estructura: {mejor['estructura']} | Estado: {mejor['estado_mercado']}")
            log(f"📊 PCR Decision: {decision} | Score: {mejor['score']}")
            if razones:
                log(f"📊 Razones: {' | '.join(razones)}")
            log(f"📡 Señal: {mejor['par']} {mejor['direccion']}")
            gestor.agregar(mejor)
        else:
            log("Sin señales válidas o mercado bloqueado")
        
        log("Ciclo done. 10min...")
        time.sleep(600)
        
    except Exception as ex:
        log(f"Error: {ex}")
        time.sleep(60)