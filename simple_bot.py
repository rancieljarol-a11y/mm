import sys, time
from datetime import datetime
sys.path.insert(0, '/home/mmkd/Escritorio/binary-bot-master./binary-bot-master')
from iqoptionapi.stable_api import IQ_Option

def log(msg):
    with open("log.txt", "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M')}] {msg}\n")
    print(msg)

PARES = ["EURUSD", "GBPUSD"]

log("Iniciando bot...")

while True:
    try:
        log("Conectando...")
        IQ = IQ_Option("rancieljarol@gmail.com", "440Harold!!!!")
        IQ.connect()
        log(f"Balance: ${IQ.get_balance()}")
        
        for PAR in PARES:
            try:
                c = IQ.get_candles(PAR, 300, 20, time.time())
                if c:
                    closes = [x['close'] for x in c]
                    e20 = sum(closes[-20:])/20
                    e50 = sum(closes[-50:])/50 if len(closes)>=50 else e20
                    dir = "CALL" if e20 > e50 else "PUT"
                    log(f"{PAR}: {dir}")
                    IQ.buy(1, PAR, "turbo", dir)
                    log(f" >>> OPERADO: {PAR} {dir}")
            except Exception as ex:
                log(f"{PAR}: {ex}")
        
        log("Ciclo completo. Dormir 10min...")
    except Exception as e:
        log(f"Error: {e}")
    
    time.sleep(600)
