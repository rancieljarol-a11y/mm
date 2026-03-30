#!/usr/bin/env python3
"""
OttO Trading Bot - Modo Automático
Ejecuta análisis cada 10 minutos
"""

import sys
import time
import os
from datetime import datetime

sys.path.insert(0, '/home/mmkd/Escritorio/binary-bot-master./binary-bot-master')

from iqoptionapi.stable_api import IQ_Option
import numpy as np

# Configuración
PARES = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURGBP", "USDCAD", "EURJPY", "GBPJPY", "NZDUSD", "USDSGD"]
EMAIL = "rancieljarol@gmail.com"
PASSWORD = "440Harold!!!!"
SCORE_MINIMO = 62
MAX_OPERACIONES = 2
INTERVALO = 600  # 10 minutos

class OttOBot:
    def __init__(self):
        self.iq = None
        self.balance = 0
        self.operaciones_ciclo = 0
        self.operaciones_hoy = 0
        self.log_file = "/home/mmkd/.openclaw/workspace/otto_trading/log.txt"
        
    def log(self, msg):
        """Escribir al log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.log_file, "a") as f:
            f.write(f"[{timestamp}] {msg}\n")
        print(f"[{timestamp}] {msg}")
    
    def conectar(self):
        """Conectar a IQ Option"""
        self.iq = IQ_Option(EMAIL, PASSWORD)
        ok, msg = self.iq.connect()
        
        if ok:
            self.balance = self.iq.get_balance()
            self.log(f"✅ Conectado! Balance: ${self.balance}")
            return True
        else:
            self.log(f"❌ Error conexión: {msg}")
            return False
    
    def obtener_datos(self, par, timeframe=900, cantidad=80):
        """Obtener velas"""
        try:
            endtime = time.time()
            candles = self.iq.get_candles(par, timeframe, cantidad, endtime)
            if candles:
                return [(c['open'], c['max'], c['min'], c['close']) for c in candles]
        except:
            pass
        return None
    
    def calcular_ema(self, closes, periodo):
        if len(closes) < periodo:
            return closes[-1] if closes else 0
        mult = 2 / (periodo + 1)
        ema = sum(closes[:periodo]) / periodo
        for c in closes[periodo:]:
            ema = (c * mult) + (ema * (1 - mult))
        return ema
    
    def calcular_rsi(self, closes, periodo=14):
        if len(closes) < periodo + 1:
            return 50
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-periodo:])
        avg_loss = np.mean(losses[-periodo:])
        if avg_loss == 0:
            return 100
        return 100 - (100 / (1 + avg_gain / avg_loss))
    
    def analizar_par(self, par):
        data = self.obtener_datos(par)
        if not data:
            return None
        
        closes = [c[3] for c in data]
        
        ema20 = self.calcular_ema(closes, 20)
        ema50 = self.calcular_ema(closes, 50)
        rsi = self.calcular_rsi(closes)
        
        tendencia = "CALL" if ema20 > ema50 else "PUT"
        
        score = 0
        if abs(ema20 - ema50) / ema50 > 0.002:
            score += 30
        else:
            score += 15
        
        if rsi < 30:
            score += 25
        elif rsi > 70:
            score += 25
        else:
            score += 10
        
        return {
            'par': par,
            'precio': closes[-1],
            'tendencia': tendencia,
            'rsi': rsi,
            'score': score
        }
    
    def ejecutar_operacion(self, par, direccion, monto=1):
        """Ejecutar operación (comentado por seguridad)"""
        if self.operaciones_ciclo >= MAX_OPERACIONES:
            self.log("⚠️ Límite operaciones alcanzado")
            return False
        
        try:
            self.iq.change_balance("demo")
            # self.iq.buy(monto, par, "turbo", direccion)
            self.log(f"🎯 SEÑAL: {par} {direccion} (score alto)")
            self.operaciones_ciclo += 1
            self.operaciones_hoy += 1
            return True
        except Exception as e:
            self.log(f"❌ Error operación: {e}")
            return False
    
    def ciclo(self):
        """Ejecutar un ciclo de análisis"""
        self.operaciones_ciclo = 0
        self.log("\n" + "="*50)
        self.log(f"🌅 CICLO AUTOMÁTICO - {datetime.now().strftime('%H:%M:%S')}")
        self.log("="*50)
        
        if not self.conectar():
            return
        
        resultados = []
        
        for par in PARES:
            resultado = self.analizar_par(par)
            if resultado:
                resultados.append(resultado)
                self.log(f"📊 {par}: Score {resultado['score']} | {resultado['tendencia']} | RSI {resultado['rsi']:.1f}")
        
        # Ordenar por score
        resultados.sort(key=lambda x: x['score'], reverse=True)
        
        # Ejecutar mejores señales
        mejores = [r for r in resultados if r['score'] >= SCORE_MINIMO]
        
        if mejores and self.operaciones_ciclo < MAX_OPERACIONES:
            for r in mejores[:MAX_OPERACIONES]:
                if r['score'] >= 70:  # Señal muy fuerte
                    self.ejecutar_operacion(r['par'], r['tendencia'])
        else:
            self.log("⚠️ Sin señales fuertes - No hay operaciones")
        
        self.log(f"✅ Ciclo completado | Ops ciclo: {self.operaciones_ciclo} | Ops hoy: {self.operaciones_hoy}")
    
    def iniciar(self):
        """Iniciar modo automático"""
        self.log("🚀 OttO Trading Bot INICIADO")
        self.log(f"⏰ Intervalo: 10 minutos | Score mínimo: {SCORE_MINIMO}")
        self.log(f"📊 Pares: {len(PARES)}")
        
        while True:
            try:
                self.ciclo()
            except Exception as e:
                self.log(f"❌ Error en ciclo: {e}")
            
            self.log(f"😴 Durmiendo {INTERVALO/60} minutos...")
            time.sleep(INTERVALO)

if __name__ == "__main__":
    bot = OttOBot()
    bot.iniciar()
