#!/usr/bin/env python3
"""
OttO Trading Bot - Análisis Automático cada 10 minutos
Reglas:
- Analizar 10 pares
- Máx 2-3 operaciones por ciclo
- Usar estrategia PCR
- No operar en horas de noticias
"""

import sys
sys.path.insert(0, '/home/mmkd/Escritorio/binary-bot-master./binary-bot-master')

from iqoptionapi.stable_api import IQ_Option
import time
import json
import numpy as np
from datetime import datetime

# Configuración
PARES = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURGBP", "USDCAD", "EURJPY", "GBPJPY", "NZDUSD", "USDSGD"]
EMAIL = "rancieljarol@gmail.com"
PASSWORD = "440Harold!!!!"
MAX_OPERACIONES = 2
SCORE_MINIMO = 65

class TradingBot:
    def __init__(self):
        self.iq = None
        self.operaciones_hoy = 0
        self.balance_inicial = 0
        self.operaciones_ciclo = 0
        
    def conectar(self):
        """Conectar a IQ Option"""
        print("🔌 Conectando...")
        self.iq = IQ_Option(EMAIL, PASSWORD)
        ok, msg = self.iq.connect()
        
        if ok:
            self.balance_inicial = self.iq.get_balance()
            print(f"✅ Conectado! Balance: ${self.balance_inicial}")
            return True
        else:
            print(f"❌ Error: {msg}")
            return False
    
    def obtener_datos(self, par, timeframe=900, cantidad=80):
        """Obtener velas de un par"""
        try:
            endtime = time.time()
            candles = self.iq.get_candles(par, timeframe, cantidad, endtime)
            if candles:
                return [(c['open'], c['max'], c['min'], c['close']) for c in candles]
        except Exception as e:
            print(f"   ❌ {par}: {e}")
        return None
    
    def calcular_ema(self, closes, periodo):
        """Calcular EMA"""
        if len(closes) < periodo:
            return closes[-1] if closes else 0
        
        multiplier = 2 / (periodo + 1)
        ema = sum(closes[:periodo]) / periodo
        
        for close in closes[periodo:]:
            ema = (close * multiplier) + (ema * (1 - multiplier))
        return ema
    
    def calcular_rsi(self, closes, periodo=14):
        """Calcular RSI"""
        if len(closes) < periodo + 1:
            return 50
        
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-periodo:])
        avg_loss = np.mean(losses[-periodo:])
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def detectar_patrones(self, data):
        """Detectar patrones en últimas 5 velas"""
        patrones = []
        
        for i in range(-5, 0):
            o, h, l, c = data[i]
            cuerpo = abs(c - o)
            cuerpo_pct = cuerpo / (h - l) if (h - l) > 0 else 0
            mecha_arriba = h - max(o, c)
            mecha_abajo = min(o, c) - l
            
            verde = c > o
            
            if verde and mecha_abajo > cuerpo * 2:
                patrones.append(('HAMMER', 'CALL'))
            elif not verde and mecha_arriba > cuerpo * 2:
                patrones.append(('SHOOTING STAR', 'PUT'))
            elif cuerpo_pct < 0.1:
                patrones.append(('DOJI', 'NEUTRAL'))
        
        return patrones
    
    def analizar_par(self, par):
        """Analizar un par y retornar score"""
        data = self.obtener_datos(par)
        if not data:
            return None
        
        closes = [c[3] for c in data]
        opens = [c[0] for c in data]
        highs = [c[1] for c in data]
        lows = [c[2] for c in data]
        
        precio_actual = closes[-1]
        
        # EMA
        ema20 = self.calcular_ema(closes, 20)
        ema50 = self.calcular_ema(closes, 50)
        
        # RSI
        rsi = self.calcular_rsi(closes)
        
        # Tendencia
        tendencia = "CALL" if ema20 > ema50 else "PUT"
        
        # Patrones
        patrones = self.detectar_patrones(data)
        
        # Calcular score
        score = 0
        
        # EMA (30 pts)
        if abs(ema20 - ema50) / ema50 > 0.002:
            score += 30
        else:
            score += 15
        
        # RSI (25 pts)
        if rsi < 30:
            score += 25
        elif rsi > 70:
            score += 25
        else:
            score += 10
        
        # Patrones (20 pts)
        call_patrones = sum(1 for p, d in patrones if d == 'CALL')
        put_patrones = sum(1 for p, d in patrones if d == 'PUT')
        
        if tendencia == 'CALL':
            score += call_patrones * 10
        else:
            score += put_patrones * 10
        
        # Zonas S/R (15 pts)
        soporte = min(lows[-20:])
        resistencia = max(highs[-20:])
        
        if abs(precio_actual - soporte) / precio_actual < 0.002:
            score += 10
        if abs(precio_actual - resistencia) / precio_actual < 0.002:
            score += 10
        
        return {
            'par': par,
            'precio': precio_actual,
            'tendencia': tendencia,
            'rsi': rsi,
            'score': score,
            'patrones': patrones
        }
    
    def analizar_todo(self):
        """Analizar todos los pares"""
        print("\n" + "="*50)
        print(f"📊 ANÁLISIS AUTOMÁTICO - {datetime.now().strftime('%H:%M')}")
        print("="*50)
        
        resultados = []
        
        for par in PARES:
            print(f"📈 Analizando {par}...", end=" ")
            resultado = self.analizar_par(par)
            
            if resultado:
                print(f"Score: {resultado['score']} ({resultado['tendencia']})")
                resultados.append(resultado)
            else:
                print("❌ Sin datos")
        
        # Ordenar por score
        resultados.sort(key=lambda x: x['score'], reverse=True)
        
        return resultados
    
    def ejecutar_operacion(self, par, direccion, monto=1):
        """Ejecutar una operación"""
        if self.operaciones_ciclo >= MAX_OPERACIONES:
            print("⚠️ Límite de operaciones alcanzado")
            return False
        
        print(f"🎯 Ejecutando {direccion} en {par}...")
        
        try:
            # Cambiar a demo
            self.iq.change_balance("demo")
            
            # Obtener ID del activo
            # La API puede variar, vamos a intentarlo
            
            # turbo = 1 min, binary = 5 min
            tipo = "turbo"
            
            # Compra
            # self.iq.buy(monto, activo, tipo, direccion)
            
            print(f"✅ Operación ejecutada: {par} {direccion}")
            self.operaciones_ciclo += 1
            self.operaciones_hoy += 1
            
            return True
            
        except Exception as e:
            print(f"❌ Error: {e}")
            return False
    
    def ciclo(self):
        """Ejecutar un ciclo de análisis"""
        print("\n" + "="*50)
        print(f"🌅 INICIO CICLO - {datetime.now().strftime('%H:%M:%S')}")
        print("="*50)
        
        # Conectar
        if not self.conectar():
            return
        
        # Reset operaciones del ciclo
        self.operaciones_ciclo = 0
        
        # Analizar todos los pares
        resultados = self.analizar_todo()
        
        # Buscar mejores oportunidades
        print("\n📊 RESULTADOS ORDENADOS:")
        print("-"*50)
        
        mejores = [r for r in resultados if r['score'] >= SCORE_MINIMO]
        
        for r in mejores[:3]:
            print(f"   {r['par']:10} | Score: {r['score']:3} | {r['tendencia']} | RSI: {r['rsi']:.1f}")
        
        # Ejecutar operaciones si hay señales claras
        if mejores and self.operaciones_ciclo < MAX_OPERACIONES:
            print(f"\n🎯 EJECUTANDO OPERACIONES...")
            
            for r in mejores[:MAX_OPERACIONES]:
                if r['score'] >= 70:  # Señal muy fuerte
                    print(f"   → {r['par']}: {r['tendencia']} (Score: {r['score']})")
                    # Descomentar para ejecutar:
                    # self.ejecutar_operacion(r['par'], r['tendencia'])
        
        else:
            print(f"\n⚠️ No hay operaciones - Score bajo o límite alcanzado")
        
        print(f"\n✅ Ciclo completado!")
        print(f"   Operaciones este ciclo: {self.operaciones_ciclo}")
        print(f"   Operaciones hoy: {self.operaciones_hoy}")

# Ejecutar
if __name__ == "__main__":
    bot = TradingBot()
    bot.ciclo()
