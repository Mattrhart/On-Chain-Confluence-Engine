import os
import httpx
import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification
from app.nansen import fetch_full_intelligence

load_dotenv()
app = FastAPI(title="Sovereign Confluence Engine", version="3.4")

# --- THE INSTITUTIONAL WATCHLIST & SECTOR MAP ---
TOKEN_MAP = {
    "ETH":  {"chain": "ethereum", "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "sector": "L1 / Blue-Chip"},
    "BNB":  {"chain": "bnb",      "address": "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c", "sector": "L1 / Exchange"},
    "SOL":  {"chain": "solana",   "address": "So11111111111111111111111111111111111111112", "sector": "L1 / Speed"},
    "HYPE": {"chain": "hyperevm", "address": "0x0d01dc56dcaaca66ad901c959b4011ec", "sector": "L1 / Perp DEX"},
    "WBTC": {"chain": "ethereum", "address": "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", "sector": "Market Anchor"},
    "LINK": {"chain": "ethereum", "address": "0x514910771af9ca656af840dff83e8264ecf986ca", "sector": "Oracle / Infra"},
    "PEPE": {"chain": "ethereum", "address": "0x6982508145454ce325ddbe47a25d4ec3d2311933", "sector": "Meme / Beta"},
    "AERO": {"chain": "base",     "address": "0x94018130d41403512255c276587be09d43526f8d", "sector": "L2 / DEX"},
    "LDO":  {"chain": "ethereum", "address": "0x5a98781ae4372f810be444d32c815bc0c612b5e1", "sector": "LSD / Staking"}
}

class TradingViewPayload(BaseModel):
    ticker: str
    price: float
    direction: str
    timeframe: str
    secret_token: str

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "3.4"}

# --- PUBLIC API GUARD LAYERS ---

async def fetch_dex_liquidity_usd(chain: str, address: str) -> float:
    if chain.lower() == "solana": return 5000000.0 
    url = f"https://api.geckoterminal.com/api/v2/networks/{chain.lower()}/tokens/{address}/pools?page=1"
    headers = {"Accept": "application/json;version=20230302"}
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json().get("data", [])
                return sum([float(pool.get("attributes", {}).get("reserve_in_usd", 0.0)) for pool in data])
        except: pass
    return 1000000.0

async def check_binance_open_interest(symbol: str) -> float:
    binance_symbol = "BTCUSDT" if symbol == "WBTC" else f"{symbol}USDT"
    url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={binance_symbol}"
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200: return float(res.json().get("openInterest", 0.0))
        except: pass
    return 0.0

# --- FOREX INTELLIGENCE LAYERS ---

async def check_forex_news_risk(symbol: str) -> dict:
    api_key = os.getenv("ALPHA_VANTAGE_KEY", "FNZA72FMXYIDU7VJ")
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&topics=economy_macro&sort=LATEST&limit=25&apikey={api_key}"
    
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                feed = res.json().get("feed", [])
                if not feed:
                    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "reason": "No news data", "headline": "No recent macro articles published."}
                
                top_headline = feed[0].get("title", "Unknown Headline")
                critical_keywords = ["fomc", "fed rate", "cpi print", "nonfarm", "nfp", "inflation shock", "ecb", "boe", "powell"]
                total_drag, latest_shock, now = 0.0, None, datetime.datetime.now()

                for article in feed:
                    pub_time_str = article.get("time_published", "")
                    if not pub_time_str: continue
                    try: days_old = (now - datetime.datetime.strptime(pub_time_str, "%Y%m%dT%H%M%S")).days
                    except: days_old = 0

                    if any(kw in article.get("title", "").lower() for kw in critical_keywords):
                        shock_value = 10.0 * max(0.1, (0.8 ** days_old))
                        total_drag += shock_value
                        if not latest_shock or shock_value > latest_shock['value']:
                            latest_shock = {"value": shock_value, "days": days_old, "title": article.get("title")}
                
                base_sentiment = feed[0].get("overall_sentiment_label", "NEUTRAL")
                
                # DYNAMIC RETURN STATEMENTS
                if total_drag >= 8.0:
                    return {"risk_score": total_drag, "sentiment": base_sentiment, "headline": top_headline, "reason": f"OVERHANG: '{latest_shock['title']}' ({latest_shock['days']}d ago)"}
                elif total_drag >= 4.0:
                    return {"risk_score": total_drag, "sentiment": base_sentiment, "headline": top_headline, "reason": f"Residual Drag: '{latest_shock['title']}' ({latest_shock['days']}d ago)"}
                else:
                    return {"risk_score": total_drag, "sentiment": base_sentiment, "headline": top_headline, "reason": "No high-impact historical shocks detected."}
        except: pass
    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "reason": "News API timeout", "headline": "API Fetch Failed"}

async def evaluate_fmp_macro_direction(symbol: str, direction: str) -> dict:
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
                macro_events = [e for e in events if e.get("impact") == "High" and e.get("currency") in [base_currency, quote_currency] and e.get("actual") is not None]
                
                if not macro_events:
                    return {"action": "EXECUTE", "reason": "No High-Impact events scheduled for today.", "event_checked": "Quiet Calendar"}

                top_event = macro_events[0].get("event", "Unknown Event")

                for event in macro_events:
                    try:
                        actual, estimate = float(event["actual"]), float(event.get("estimate", event["actual"]))
                        is_positive = actual > estimate
                        
                        if event["currency"] == base_currency:
                            if trade_dir == "BUY" and not is_positive: return {"action": "ABORT", "reason": f"Conflict: {event['event']} weakened {base_currency}.", "event_checked": event['event']}
                            if trade_dir == "SHORT" and is_positive: return {"action": "ABORT", "reason": f"Conflict: {event['event']} strengthened {base_currency}.", "event_checked": event['event']}
                        elif event["currency"] == quote_currency:
                            if trade_dir == "BUY" and is_positive: return {"action": "ABORT", "reason": f"Conflict: {event['event']} strengthened {quote_currency}.", "event_checked": event['event']}
                            if trade_dir == "SHORT" and not is_positive: return {"action": "ABORT", "reason": f"Conflict: {event['event']} weakened {quote_currency}.", "event_checked": event['event']}
                    except: continue
                return {"action": "EXECUTE", "reason": "Intraday data aligned with trade direction.", "event_checked": top_event}
        except: pass
    return {"action": "EXECUTE", "reason": "FMP API timeout", "event_checked": "None"}

# --- WEBHOOK LAYER ---

@app.post("/webhook/tradingview")
@app.post("/webhook/tradingview/")
async def tradingview_webhook(payload: TradingViewPayload, background_tasks: BackgroundTasks):
    if payload.secret_token != os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026"): raise HTTPException(status_code=401)

    raw_ticker = payload.ticker.upper().replace("/", "").replace("-", "").replace(" ", "")
    is_forex = len(raw_ticker) == 6 and raw_ticker[:3] in {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"} and raw_ticker[3:] in {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"}
    symbol = f"{raw_ticker[:3]}_{raw_ticker[3:]}" if is_forex else raw_ticker

    decision, stars = "EXECUTE", "⭐⭐⭐"
    
    if is_forex:
        sector = "Global FX Market"
        av_intel = await check_forex_news_risk(symbol)
        fmp_intel = await evaluate_fmp_macro_direction(symbol, payload.direction)
        
        # DYNAMIC REASONING BUILDING
        base_note = f"📰 Latest: {av_intel['headline']}\n📅 Calendar Focus: {fmp_intel['event_checked']}"
        
        if av_intel["risk_score"] >= 8.0:
            decision, stars, reasoning = "ABORT", "⚠️", f"🛑 {av_intel['reason']}\n{base_note}"
        elif fmp_intel["action"] == "ABORT":
            decision, stars, reasoning = "ABORT", "⚠️", f"🛑 {fmp_intel['reason']}\n{base_note}"
        else:
            reasoning = f"✅ Macro Clear.\n{base_note}"
            if "BULLISH" in av_intel["sentiment"] and payload.direction.upper() == "BUY": stars = "⭐⭐⭐⭐⭐"
            if "BEARISH" in av_intel["sentiment"] and payload.direction.upper() == "SHORT": stars = "⭐⭐⭐⭐⭐"
        metric_display = f"AV: {av_intel['sentiment']}"

    else:
        crypto_root = raw_ticker.split(":")[-1].replace(".P", "")
        for stable in ["USDT", "USDC", "USD"]:
            if crypto_root.endswith(stable) and crypto_root != stable:
                crypto_root = crypto_root[:-len(stable)]
                break
        
        symbol = crypto_root
        token_info = TOKEN_MAP.get(symbol)

        if token_info:
            sector = token_info.get("sector", "Independent Asset")
            metrics = await fetch_full_intelligence(symbol=symbol, address=token_info.get("address"), chain=token_info.get("chain"))
            pool_liquidity = await fetch_dex_liquidity_usd(chain=token_info.get("chain"), address=token_info.get("address"))
            oi_usd = await check_binance_open_interest(symbol)
        else:
            sector, metrics, pool_liquidity, oi_usd = "Unmapped Asset", None, 1000000.0, 0.0

        if metrics:
            flow, risk, conv, direction = metrics["net_flow_24h"], metrics["risk_score"], metrics["sm_conviction"], payload.direction.upper()
            
            # DYNAMIC CRYPTO CONTEXT INJECTION
            base_note = f"💧 Pool Depth: ${pool_liquidity/1e3:,.0f}k | 📜 Binance OI: ${oi_usd/1e6:,.1f}M"

            if risk >= 8:
                decision, stars, reasoning = "ABORT", "⚠️", f"🛑 HIGH RISK: Nansen score critically high ({risk}/10).\n{base_note}"
            elif pool_liquidity < 250000.0:
                decision, stars, reasoning = "ABORT", "⚠️", f"🛑 ILLIQUID POOL TRAP: DEX depth too thin.\n{base_note}"
            elif direction == "BUY" and flow < -2000000:
                decision, stars, reasoning = "ABORT", "⚠️", f"🛑 LIQUIDITY TRAP: Smart Money dumping.\n{base_note}"
            elif direction == "SHORT" and flow > 2000000:
                decision, stars, reasoning = "ABORT", "⚠️", f"🛑 CONTRA-TREND: Whales accumulating.\n{base_note}"
            elif conv > 75 and flow > 3000000:
                stars, reasoning = "⭐⭐⭐⭐⭐", f"🔥 HIGH CONVICTION BUY.\n{base_note}"
            else:
                reasoning = f"✅ On-chain stable.\n{base_note}"

            metric_display = f"${flow/1e6:+.1f}M Flow | Risk: {risk}"
        else:
            metric_display, reasoning = "No On-Chain Analytics Available", "Technical execution based purely on raw metrics."

    price_display = f"{payload.price:,.5f}" if is_forex else f"{payload.price:,.2f}"
    
    rich_message = (
        f"{'🟩' if decision == 'EXECUTE' else '🟥'} *DECISION: {decision}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💎 *Asset:* `${symbol}`\n🏷️ *Sector:* `{sector}`\n📊 *TF:* `{payload.timeframe}m` | *Price:* `${price_display}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{'🌍 *MACRO TELEMETRY*' if is_forex else '🛡️ *ON-CHAIN INTELLIGENCE*'}\n"
        f"• Status: `{metric_display}`\n• Conviction: {stars}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 *Analyst Brief:*\n{reasoning.replace('_', '\\_')}\n"
        f"📈 _Confluence Engine V3.4_"
    )

    background_tasks.add_task(send_telegram_notification, rich_message)
    return {"status": "success", "decision": decision}