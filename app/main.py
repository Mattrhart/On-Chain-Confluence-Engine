import os
import httpx
import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification
# Ensure you are importing your new async intelligence layer
from app.nansen import fetch_full_intelligence

load_dotenv()
app = FastAPI(title="Sovereign Confluence Engine", version="3.1")

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
    return {"status": "Engine Active", "port": int(os.getenv("PORT", 8000))}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "engine_version": "3.1",
        "nansen_connectivity": True if os.getenv("NANSEN_API_KEY") else False,
        "alphavantage_connectivity": True if os.getenv("ALPHA_VANTAGE_KEY") else False,
        "fmp_connectivity": True if os.getenv("FMP_API_KEY") else False
    }

# --- INTELLIGENCE LAYERS ---

async def check_forex_news_risk(symbol: str) -> dict:
    """Hits Alpha Vantage to scan recent headlines for extreme event volatility."""
    api_key = os.getenv("ALPHA_VANTAGE_KEY", "FNZA72FMXYIDU7VJ")
    av_ticker = f"FX:{symbol.replace('_', '')}"
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={av_ticker}&sort=LATEST&limit=3&apikey={api_key}"
    
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                feed = res.json().get("feed", [])
                if not feed:
                    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "reason": "News sentiment stable"}
                
                critical_keywords = ["fomc", "fed rate", "cpi print", "nonfarm", "nfp", "inflation shock", "ecb", "boe"]
                for article in feed:
                    if any(kw in article.get("title", "").lower() for kw in critical_keywords):
                        return {"risk_score": 10.0, "sentiment": "NEUTRAL", "reason": f"News Shock: {article.get('title')[:40]}..."}
                
                return {"risk_score": 0.0, "sentiment": feed[0].get("overall_sentiment_label", "NEUTRAL"), "reason": "News sentiment stable"}
        except Exception as e:
            print(f"⚠️ Alpha Vantage Error: {e}")
    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "reason": "News API timeout"}

async def evaluate_fmp_macro_direction(symbol: str, direction: str) -> dict:
    """
    Dynamic Cross-Pair Macro Engine.
    Handles Majors, Minors, and Crosses dynamically based on data surprises.
    """
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
                        
                        # Macro Matrix Calculation:
                        # Positive surprise strengthens that specific currency. Negative weakens it.
                        if event_currency == base_currency:
                            base_strengthened = is_positive_surprise
                            # If we are BUYING the pair, we want base to strengthen. If it weakened instead, conflict!
                            if trade_dir == "BUY" and not base_strengthened:
                                return {"action": "ABORT", "reason": f"Macro Conflict: {event['event']} weakened base {base_currency}."}
                            if trade_dir == "SHORT" and base_strengthened:
                                return {"action": "ABORT", "reason": f"Macro Conflict: {event['event']} strengthened base {base_currency}."}
                        
                        elif event_currency == quote_currency:
                            quote_strengthened = is_positive_surprise
                            # If we are BUYING the pair, we want quote to weaken. If it strengthened, conflict!
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
    
    # Smart Asset Classification: 
    # If the string contains explicit FX structures or matches currency pair sizing, route to Forex.
    is_forex = "_" in raw_ticker and len(raw_ticker.split("_")[0]) == 3 and len(raw_ticker.split("_")[1]) == 3
    
    decision = "EXECUTE"
    stars = "⭐⭐⭐"
    
    if is_forex:
        symbol = raw_ticker
        sector = "Global FX Market"
        
        av_intel = await check_forex_news_risk(symbol)
        fmp_intel = await evaluate_fmp_macro_direction(symbol, payload.direction)
        
        if av_intel["risk_score"] >= 10.0:
            decision = "ABORT"
            reasoning = f"🛑 {av_intel['reason']}"
            stars = "⚠️"
        elif fmp_intel["action"] == "ABORT":
            decision = "ABORT"
            reasoning = f"🛑 {fmp_intel['reason']}"
            stars = "⚠️"
        else:
            reasoning = f"Filters Clear. {fmp_intel['reason']}"
            if av_intel["sentiment"] in ["BULLISH", "VERY_BULLISH"] and payload.direction.upper() == "BUY":
                stars = "⭐⭐⭐⭐⭐"
            elif av_intel["sentiment"] in ["BEARISH", "VERY_BEARISH"] and payload.direction.upper() == "SHORT":
                stars = "⭐⭐⭐⭐⭐"

        metric_display = f"AV: {av_intel['sentiment']}"

    else:
        # ==========================================
        # EXTENDED CRYPTO PIPELINE (V3.1 FINALIZE)
        # ==========================================
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

            # SKEPTIC TRAPS & CONFLUENCE MATRIX
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
    rich_message = (
        f"{'🟩' if decision == 'EXECUTE' else '🟥'} *DECISION: {decision}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💎 *Asset:* `${symbol}`\n"
        f"🏷️ *Sector:* `{sector}`\n"
        f"📊 *TF:* `{payload.timeframe}m` | *Price:* `${payload.price:,.5f if is_forex else :,.2f}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{'🌍 *MACRO & SENTIMENT TELEMETRY*' if is_forex else '🛡️ *ON-CHAIN INTELLIGENCE*'}\n"
        f"• Status: `{metric_display}`\n"
        f"• Conviction: {stars}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 *Note:* {reasoning}\n"
        f"📈 _Confluence Engine V3.1_"
    )

    background_tasks.add_task(send_telegram_notification, rich_message)
    return {"status": "success", "decision": decision}