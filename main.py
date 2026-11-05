import sys
import os
import time
import threading
import requests
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import math
import ctypes

def clean_float(val, default=0.0):
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# FUNCIONES DE INDICADORES TÉCNICOS (RSI y EMA)
# ---------------------------------------------------------
def calculate_rsi(prices, period=14):
    """Calcula el Relative Strength Index (RSI) de 14 periodos"""
    clean_prices = [clean_float(p) for p in prices if clean_float(p) is not None]
    if len(clean_prices) < period + 1:
        return 50.0  # Valor neutral por defecto si no hay suficientes datos
    
    gains = []
    losses = []
    for i in range(1, len(clean_prices)):
        change = clean_prices[i] - clean_prices[i - 1]
        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))
            
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    return clean_float(round(100.0 - (100.0 / (1.0 + rs)), 1), 50.0)

def calculate_ema(prices, period):
    """Calcula la Media Móvil Exponencial (EMA)"""
    clean_prices = [clean_float(p) for p in prices if clean_float(p) is not None]
    if len(clean_prices) < period:
        return clean_prices[-1] if clean_prices else 0.0
    k = 2 / (period + 1)
    ema = sum(clean_prices[:period]) / period
    for price in clean_prices[period:]:
        ema = (price * k) + (ema * (1 - k))
    return clean_float(ema)

def compute_technical_score(prices, change_24h):
    """
    Algoritmo de Momentum Técnico:
    Combina el RSI (14), cruce de EMA(9) vs EMA(21) y Variación de 24h.
    """
    c_change = clean_float(change_24h)
    if not prices or len(prices) < 5:
        score = round(50 + (c_change * 3), 1)
        return int(max(5, min(98, score))), 50.0

    rsi = calculate_rsi(prices)
    ema_fast = calculate_ema(prices, 9)
    ema_slow = calculate_ema(prices, 21)

    # Base de puntuación inicial basada en RSI
    if rsi >= 70:
        rsi_score = 65
    elif rsi <= 30:
        rsi_score = 35
    else:
        rsi_score = 50 + (rsi - 50) * 1.2

    ema_trend = 15 if ema_fast > ema_slow else -15
    price_momentum = c_change * 2

    final_score = int(max(5, min(98, round(rsi_score + ema_trend + price_momentum, 0))))
    return final_score, rsi

# ---------------------------------------------------------
# RUTAS DE LA API
# ---------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    html_path = get_resource_path("index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/rankings/{market}")
def get_rankings(market: str):
    now = int(time.time())
    day_seconds = 86400

    if market == "stocks":
        tickers = ["NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "GOOGL", "META", "NFLX", "AMD", "INTC"]
        results = []
        for symbol in tickers:
            try:
                stock = yf.Ticker(symbol)
                data = stock.history(period="1mo", interval="1d")
                if not data.empty and len(data) >= 5:
                    close_prices = [clean_float(p) for p in data['Close'].tolist()]
                    price = round(clean_float(close_prices[-1]), 2)
                    
                    prev_val = close_prices[-2] if len(close_prices) >= 2 else close_prices[-1]
                    if prev_val == 0:
                        change = 0.0
                    else:
                        change = round(clean_float(((close_prices[-1] - prev_val) / prev_val) * 100), 2)
                    
                    score, rsi = compute_technical_score(close_prices, change)
                    rsi = clean_float(rsi, 50.0)
                    
                    history = []
                    for i, val in enumerate(close_prices[-5:]):
                        history.append({
                            "time": now - ((5 - i) * day_seconds),
                            "value": round(clean_float(val), 2)
                        })

                    signal = "🟢 Comprar (Fuerte)" if score >= 70 else ("🟡 Mantener" if score >= 50 else "🔴 Evitar / Venta")

                    results.append({
                        "symbol": symbol,
                        "price": price,
                        "change": change,
                        "score": score,
                        "rsi": rsi,
                        "signal": signal,
                        "history": history
                    })
            except Exception as e:
                print(f"Error con acción {symbol}: {e}")
        
        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        url = "https://api.binance.com/api/v3/ticker/24hr"
        response = requests.get(url, headers=headers, timeout=10)
        tickers = response.json()
        
        usdt_pairs = [
            item for item in tickers 
            if item.get('symbol', '').endswith('USDT') 
            and 'UP' not in item['symbol'] 
            and 'DOWN' not in item['symbol']
        ]
        usdt_pairs.sort(key=lambda x: clean_float(x.get('quoteVolume')), reverse=True)
        
        top_results = []
        for pair in usdt_pairs[:10]:
            symbol = pair['symbol'].replace('USDT', '')
            price = clean_float(pair.get('lastPrice'))
            change_24h = clean_float(pair.get('priceChangePercent'))
            
            # Obtener klines históricas breves para cálculo de RSI real en Binance
            klines_url = f"https://api.binance.com/api/v3/klines?symbol={pair['symbol']}&interval=1d&limit=20"
            try:
                k_res = requests.get(klines_url, headers=headers, timeout=3).json()
            except Exception:
                k_res = []
            
            close_prices = []
            if isinstance(k_res, list) and len(k_res) > 0:
                close_prices = [clean_float(k[4]) for k in k_res]

            score, rsi = compute_technical_score(close_prices, change_24h)
            rsi = clean_float(rsi, 50.0)

            signal = "🟢 Comprar (Fuerte)" if score >= 70 else ("🟡 Mantener" if score >= 50 else "🔴 Evitar / Venta")

            top_results.append({
                "symbol": symbol,
                "price": round(price, 4 if price < 1 else 2),
                "change": round(change_24h, 2),
                "score": score,
                "rsi": rsi,
                "signal": signal,
                "history": []
            })
            
        top_results.sort(key=lambda x: x['score'], reverse=True)
        return top_results
    except Exception as e:
        print(f"Error Binance: {e}")
        return []

def run_fastapi():
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="error")

def apply_window_icon(title, icon_path):
    time.sleep(1.5)  # Espera a que la ventana se renderice por completo
    try:
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            hicon = ctypes.windll.user32.LoadImageW(
                None, icon_path, 1, 0, 0, 0x00000010
            )
            if hicon:
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 0, hicon)  # Icono pequeño (barra de título)
                ctypes.windll.user32.SendMessageW(hwnd, 0x0080, 1, hicon)  # Icono grande (barra de tareas)
    except Exception as e:
        print(f"No se pudo aplicar el icono nativo: {e}")

if __name__ == "__main__":
    import webview
    server_thread = threading.Thread(target=run_fastapi, daemon=True)
    server_thread.start()
    time.sleep(1)
    
    # Iniciar hilo para aplicar el icono MT.ico automáticamente en segundo plano
    icon_thread = threading.Thread(target=apply_window_icon, args=("Market Terminal - Live", "MT.ico"), daemon=True)
    icon_thread.start()

    window = webview.create_window(
        title="Market Terminal - Live", 
        url="http://127.0.0.1:8000/", 
        width=1280, 
        height=800
    )
    webview.start()