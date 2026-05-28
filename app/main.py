import os
import httpx
import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification
from app.nansen import fetch_full_intelligence

load_dotenv()
app = FastAPI(title="Sovereign Confluence Engine", version="3.2")

# --- THE INSTITUTIONAL WATCHLIST & SECTOR MAP ---
TOKEN_MAP = {
    "ETH":  {"chain": "ethereum", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "sector": "L1 / Blue-Chip"},
    "BNB":  {"chain": "bnb",      "address": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", "sector": "L1 / Exchange"},
    "SOL":  {"chain": "solana",   "address": "So11111111111111111111111111111111111111112", "sector": "L1 / Speed"},
    "HYPE": {"chain": "hyperevm", "address": "0x0d01dc56dcaaca66ad901c959b4011ec", "sector": "L1 / Perp DEX"},
    "WBTC": {"chain": "ethereum", "address": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", "sector": "Market Anchor"},
    "LINK": {"chain": "ethereum", "address": "0x514910771af9ca656af840dff83e8264ecf986ca", "sector": "Oracle / Infra"},
    "PEPE": {"chain": "ethereum", "address": "0x6982508145454ce325ddbe47a25d4ec3d2311933", "sector": "Meme / Beta"},
    "AERO": {"chain": "base",     "address": "0x94018130d51403512255c276587be09d43526f8d", "sector": "L2 / DEX"},
    "LDO":  {"chain": "ethereum", "address": "0x5a98781ae4372f810be444d32c815bc0c612b5e1", "sector": "LSD / Staking"}
}

class TradingViewPayload(BaseModel):
    ticker: str
    price: float
    direction: str
    timeframe: str
    secret_token: str

# --- SYSTEM ENDPOINTS ---

@app.get("/")
async def root():
    return {"status": "Engine Active", "port": int(os.getenv("PORT", 8080))}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "engine_version": "3.2",
        "nansen_connectivity": True if os.getenv("NANSEN_API_KEY") else False,
        "alphavantage_connectivity": True if os.getenv("ALPHA_VANTAGE_KEY") else False,
        "fmp_connectivity": True if os.getenv("FMP_API_KEY") else False
    }

# --- INTELLIGENCE LAYERS ---

async def check_forex_news_risk(symbol: str) -> dict:
    """
    Advanced Engine: Scans headlines and applies a Time-Decay (Half-Life) 
    to historical macroeconomic shocks.
    """
    api_key = os.getenv("ALPHA_VANTAGE_KEY", "FNZA72FMXYIDU7VJ")
    av_ticker = f"FX:{symbol.replace('_', '')}"
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={av_ticker}&sort=LATEST&limit=15&apikey={api_key}"
    
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                feed = res.json().get("feed", [])
                if not feed:
                    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "reason": "No historical news drag"}
                
                critical_keywords = ["fomc", "fed rate", "cpi print", "nonfarm", "nfp", "inflation shock", "ecb", "boe"]
                
                total_drag = 0.0
                latest_shock = None
                now = datetime.datetime.now()

                for article in feed:
                    pub_time_str = article.get("time_published", "")
                    if not pub_time_str:
                        continue
                        
                    try:
                        pub_time = datetime.datetime.strptime(pub_time_str, "%Y%m%dT%H%M%S")
                        days_old = (now - pub_time).days
                    except:
                        days_old = 0

                    # DECAY FORMULA: Weight drops every day
                    decay_multiplier = max(0.1, (0.8 ** days_old)) 
                    title = article.get("title", "").lower()

                    if any(kw in title for kw in critical_keywords):
                        shock_value = 10.0 * decay_multiplier
                        total_drag += shock_value
                        
                        if not latest_shock or shock_value > latest_shock['value']:
                            latest_shock = {
                                "value": shock_value, 
                                "days": days_old, 
                                "title": article.get("title")[:30]
                            }
                
                base_sentiment = feed[0].get("overall_sentiment_label", "NEUTRAL")

                if total_drag >= 8.0:
                    return {
                        "risk_score": total_drag, 
                        "sentiment": base_sentiment, 
                        "reason": f"CRITICAL OVERHANG: {latest_shock['title']}... ({latest_shock['days']} days ago) still dragging asset."
                    }
                elif total_drag >= 4.0:
                    return {
                        "risk_score": total_drag, 
                        "sentiment": base_sentiment, 
                        "reason": f"Residual Macro Drag active from {latest_shock['days']} days ago. Proceed with caution."
                    }
                else:
                    return {
                        "risk_score": total_drag, 
                        "sentiment": base_sentiment, 
                        "reason": "Historical macro timeline clear."
                    }
                    
        except Exception as e:
            print(f"⚠️ Alpha Vantage Error: {e}")
            
    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "reason": "News API timeout"}

async def evaluate_fmp_macro_direction(symbol: str, direction: str) -> dict:
    """Dynamic Cross-Pair Macro Engine."""
    api_key = os.getenv("FMP_API_KEY", "iYdmc43pzwqT7sETRC8pwVG7mIqDTNXI")
    today = datetime.date.today().isoformat()
    url = f"https://financialmodelingprep.com/api/v3/economic_calendar?from={today}&to={today}&apikey={api_key}"
    
    base_currency, quote_currency = symbol.split("_")
    trade_dir = direction.upper()

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                events = res.json()
                
                macro_events = [
                    e for e in events 
                    if e.get("impact") == "High" 
                    and e.get("currency") in [base_currency, quote_currency]
                    and e.get("actual") is not None 
                    and e.get("estimate") is not None
                ]

                for event in macro_events:
                    try:
                        actual = float(event["actual"])
                        estimate = float(event["estimate"])
                        event_currency = event["currency"]
                        
                        is_positive_surprise = actual > estimate
                        
                        if event_currency == base_currency:
                            base_strengthened = is_positive_surprise
                            if trade_dir == "BUY" and not base_strengthened:
                                return {"action": "ABORT", "reason": f"Macro Conflict: {event['event']} weakened base {base_currency}."}
                            if trade_dir == "SHORT" and base_strengthened:
                                return {"action": "ABORT", "reason": f"Macro Conflict: {event['event']} strengthened base {base_currency}."}
                        
                        elif event_currency == quote_currency:
                            quote_strengthened = is_positive_surprise
                            if trade_dir == "BUY" and quote_strengthened:
                                return {"action": "ABORT", "reason": f"Macro Conflict: {event['event']} strengthened counter {quote_currency}."}
                            if trade_dir == "SHORT" and not quote_strengthened:
                                return {"action": "ABORT", "reason": f"Macro Conflict: {event['event']} weakened counter {quote_currency}."}
                            
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            print(f"⚠️ FMP Macro Engine Error: {e}")
            
    return {"action": "EXECUTE", "reason": "Macro context aligned"}

# --- WEBHOOK LAYER ---

@app.post("/webhook/tradingview")
@app.post("/webhook/tradingview/")
async def tradingview_webhook(payload: TradingViewPayload, background_tasks: BackgroundTasks):
    if payload.secret_token != os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026"):
        raise HTTPException(status_code=401)

    raw_ticker = payload.ticker.upper().replace("/", "_").replace("-", "_")
    is_forex = "_" in raw_ticker and len(raw_ticker.split("_")[0]) == 3 and len(raw_ticker.split("_")[1]) == 3
    
    decision = "EXECUTE"
    stars = "⭐⭐⭐"
    
    if is_forex:
        symbol = raw_ticker
        sector = "Global FX Market"
        
        av_intel = await check_forex_news_risk(symbol)
        fmp_intel = await evaluate_fmp_macro_direction(symbol, payload.direction)
        
        print(f"📊 [X-RAY] Alpha Vantage Intel for {symbol}: {av_intel}")
        print(f"📊 [X-RAY] FMP Macro Intel for {symbol}: {fmp_intel}")
        
        if av_intel["risk_score"] >= 8.0:
            decision = "ABORT"
            reasoning = f"🛑 {av_intel['reason']}"
            stars = "⚠️"
        elif fmp_intel["action"] == "ABORT":
            decision = "ABORT"
            reasoning = f"🛑 {fmp_intel['reason']}"
            stars = "⚠️"
        else:
            reasoning = f"Filters Clear. {av_intel['reason']} | {fmp_intel['reason']}"
            if av_intel["sentiment"] in ["BULLISH", "VERY_BULLISH"] and payload.direction.upper() == "BUY":
                stars = "⭐⭐⭐⭐⭐"
            elif av_intel["sentiment"] in ["BEARISH", "VERY_BEARISH"] and payload.direction.upper() == "SHORT":
                stars = "⭐⭐⭐⭐⭐"

        metric_display = f"AV: {av_intel['sentiment']}"

    else:
        symbol = raw_ticker.split(":")[-1].replace("USDT", "").replace("USDC", "")
        token_info = TOKEN_MAP.get(symbol)

        if token_info:
            sector = token_info.get("sector", "Independent Asset")
            metrics = await fetch_full_intelligence(
                symbol=symbol, 
                address=token_info.get("address"), 
                chain=token_info.get("chain")
            )
        else:
            sector = "Unmapped Asset"
            metrics = None

        if metrics:
            flow = metrics["net_flow_24h"]
            risk = metrics["risk_score"]
            conviction = metrics["sm_conviction"]
            direction = payload.direction.upper()

            if risk >= 8:
                decision = "ABORT"
                reasoning = f"⚠️ HIGH RISK PROFILE: Nansen smart risk score is critically high ({risk}/10)."
                stars = "⚠️"
            elif direction == "BUY" and flow < -2000000:
                decision = "ABORT"
                reasoning = f"⚠️ LIQUIDITY TRAP: Technical BUY, but Smart Money sold ${abs(flow)/1e6:.1f}M today."
                stars = "⚠️"
            elif direction == "SHORT" and flow > 2000000:
                decision = "ABORT"
                reasoning = f"⚠️ CONTRA-TREND: Technical SHORT, but Smart Money bought ${flow/1e6:.1f}M today."
                stars = "⚠️"
            elif conviction > 75 and flow > 3000000:
                reasoning = f"🔥 HIGH CONVICTION: Smart Money accumulated and conviction is at {conviction}%."
                stars = "⭐⭐⭐⭐⭐"
            else:
                reasoning = f"On-chain flow stable. Conviction: {conviction}% | Risk Score: {risk}/10"

            metric_display = f"${flow/1e6:+.1f}M Flow | Risk: {risk}"
        else:
            metric_display = "No On-Chain Analytics Available"
            reasoning = f"Trading execution based purely on raw technical signal metrics."

    # Rich Notification Engine
    price_display = f"{payload.price:,.5f}" if is_forex else f"{payload.price:,.2f}"
    
    rich_message = (
        f"{'🟩' if decision == 'EXECUTE' else '🟥'} *DECISION: {decision}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💎 *Asset:* `${symbol}`\n"
        f"🏷️ *Sector:* `{sector}`\n"
        f"📊 *TF:* `{payload.timeframe}m` | *Price:* `${price_display}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{'🌍 *MACRO & SENTIMENT TELEMETRY*' if is_forex else '🛡️ *ON-CHAIN INTELLIGENCE*'}\n"
        f"• Status: `{metric_display}`\n"
        f"• Conviction: {stars}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 *Note:* {reasoning}\n"
        f"📈 _Confluence Engine V3.2_"
    )

    background_tasks.add_task(send_telegram_notification, rich_message)
    return {"status": "success", "decision": decision}