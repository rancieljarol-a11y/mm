#!/usr/bin/env python3
"""
Ejecutor Rápido - Sin IA
Se ejecuta cada 10-15 segundos
Solo ejecuta si hay señal válida de analisis_ia.py
"""
import sys
import time
import json
from datetime import datetime

sys.path.insert(0, '/home/mmkd/.local/share/Trash/files/binary-bot-master./binary-bot-master')
from iqoptionapi.stable_api import IQ_Option

LOG_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/ejecutor_log.txt"
SENAL_FILE = "/home/mmkd/.openclaw/workspace/otto_trading/senal_ia.json"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] {msg}")

def ejecutar():
    # Cargar señal del análisis
    try:
        with open(SENAL_FILE, "r") as f:
            senal = json.load(f)
    except:
        log("⏳ Sin señal del análisis")
        return
    
    # Verificar que la señal es reciente (max 5 min)
    if time.time() - senal.get('timestamp', 0) > 300:
        log("⏳ Señal vencida (>5 min)")
        return
    
    # Filtros de ejecución
    segundo = int(time.time()) % 300
    tiempo_restante = 300 - segundo
    
    # Solo ejecutar si queda tiempo suficiente
    if tiempo_restante < 20:
        log(f"⏳ Vela cerrando ({segundo}s) - esperar {tiempo_restante}s")
        return
    
    # Solo ejecutar en primeros 20 segundos de vela
    if segundo > 25:
        return
    
    try:
        IQ = IQ_Option("rancieljarol@gmail.com", "440Harold!!!!")
        IQ.connect()
    except Exception as e:
        log(f"❌ Error conexión: {str(e)[:30]}")
        return
    
    par = senal['par']
    direccion = senal['direccion']
    
    # Obtener precio actual y verificar zona válida
    try:
        candles = IQ.get_candles(par, 300, 3, int(time.time()))
        if candles and len(candles) >= 1:
            precio_actual = candles[-1]['close']
            precio_senal = senal.get('precio', precio_actual)
            
            # Verificar que el precio está cerca de la zona válida
            zona_precio = senal.get('zona_precio', 0)
            if zona_precio > 0:
                dist_zona = abs(precio_actual - zona_precio) / precio_actual
                if dist_zona > 0.005:  # Más de 0.5% de la zona
                    log(f"⚠️ Precio lejos de zona: {dist_zona*100:.2f}%")
                    return
            
            # Verificar movimiento no excesivo
            movimiento = abs(precio_actual - precio_senal) / precio_senal * 10000
            max_mov = 20  # pips
            if movimiento > max_mov:
                log(f"⚠️ Movimiento excesivo: {movimiento:.1f}p")
                return
            
            log(f"🎯 EJECUTANDO: {par} {direccion} | Score: {senal.get('score', 0)}")
            
            # Ejecutar operación
            dir_iq = 'call' if direccion == 'CALL' else 'put'
            IQ.buy(1, par, dir_iq, 15)
            log(f"✅ OPERACIÓN EXITOSA: {par} {dir_iq.upper()} $1")
            
            # Eliminar señal para no ejecutar dos veces
            try:
                import os
                os.remove(SENAL_FILE)
            except:
                pass
            
    except Exception as e:
        log(f"❌ Error ejecución: {str(e)[:40]}")

if __name__ == "__main__":
    ejecutar()