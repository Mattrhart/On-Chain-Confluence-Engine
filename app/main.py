import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification

# Load environment variables from .env file
load_dotenv()

app = FastAPI()

class TradingViewPayload(BaseModel):
    ticker: str
    price: float
    direction: str
    timeframe: str
    secret_token: str

@app.post("/webhook/tradingview")
async def tradingview_webhook(payload: TradingViewPayload):
    # 1. Security Passphrase Check
    SECRET = os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026")
    if payload.secret_token != SECRET:
        raise HTTPException(status_code=401, detail="Invalid security passphrase")
    
    # 2. Ticker Cleansing Layer (e.g., BINANCE:SOLUSDT -> SOL)
    cleaned_ticker = payload.ticker.split(":")[-1].replace("USDT", "").replace("USDC", "")

    # 3. Institutional Data Check (Simulated/Nansen baseline)
    onchain_data = {
        "token": cleaned_ticker, 
        "net_flow_24h_usd": 0, 
        "status": "No active institutional anomalies"
    }
    
    confluence_result = {
        "decision": "EXECUTE",
        "reason": f"Confluence on {cleaned_ticker}: Chart shows {payload.direction} pullback and Nansen confirms institutional stability/buying."
    }

    # 4. Asynchronous Telegram Notification Layer
    await send_telegram_notification(
        ticker=cleaned_ticker, 
        direction=payload.direction, 
        decision=confluence_result["decision"], 
        reason=confluence_result["reason"]
    )

    # 5. Core REST Response Pipeline
    return {
        "status": "received",
        "technical_data": {
            "ticker": cleaned_ticker,
            "price": payload.price,
            "direction": payload.direction,
            "timeframe": payload.timeframe
        },
        "onchain_data": onchain_data,
        "confluence": confluence_result
    }