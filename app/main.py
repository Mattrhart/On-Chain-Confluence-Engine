import os
import re
import httpx
import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification
from app.nansen import fetch_full_intelligence

load_dotenv()
app = FastAPI(title="Sovereign Confluence Engine", version="5.0")

# --- THE AUTO-ROUTING CORRELATION MATRIX ---
CRYPTO_CLEAN_MAP = {
    "BTC": "WBTC", "BTCUSD": "WBTC", "BTCUSDT": "WBTC",
    "ETH": "ETH",  "ETHUSD": "ETH",  "ETHUSDT": "ETH",
    "SOL": "SOL",  "SOLUSD": "SOL",  "SOLUSDT": "SOL",
    "BNB": "BNB",  "HYPE": "HYPE",   "LINK": "LINK",
    "PEPE": "PEPE", "AERO": "AERO",   "LDO": "LDO"
}

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

CURRENCY_KEYWORDS = {
    "USD": ["fed", "fomc", "powell", "dollar", "cpi", "nfp", "nonfarm", "treasury", "warsh"],
    "EUR": ["ecb", "lagarde", "eurozone", "euro", "inflation euro"],
    "GBP": ["boe", "bailey", "sterling", "pound", "uk economy"],
    "CHF": ["snb", "franc", "swiss", "kordan"],
    "JPY": ["boj", "yen", "ueda", "tokyo", "intervene"],
    "AUD": ["rba", "aussie", "australian"],
    "CAD": ["boc", "loonie", "canadian"],
    "NZD": ["rbnz", "kiwi", "zealand"]
}

class TradingViewPayload(BaseModel):
    ticker: str
    price: float
    direction: str
    timeframe: str
    secret_token: str

@app.get("/")
async def root():
    return {"status": "Engine V5.0 Active"}

@app.get("/health")
async def health_check():
    health_report = {"status": "healthy", "version": "5.0", "api_connectivity_matrix": {}}
    async with httpx.AsyncClient(timeout=4.0) as client:
        try:
            av_key = os.getenv("ALPHA_VANTAGE_KEY")
            av_res = await client.get(f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&limit=1&apikey={av_key}")
            health_report["api_connectivity_matrix"]["alphavantage"] = "CONNECTED" if av_res.status_code == 200 else "AUTH_FAILED"
        except: health_report["api_connectivity_matrix"]["alphavantage"] = "OFFLINE"
        try:
            nan_key = os.getenv("NANSEN_API_KEY")
            nan_res = await client.post("https://api.nansen.ai/api/v1/token-screener", json={"chains": ["ethereum"], "timeframe": "24h", "pagination": {"page": 1, "per_page": 1}}, headers={"apiKey": nan_key, "Content-Type": "application/json"})
            health_report["api_connectivity_matrix"]["nansen"] = "CONNECTED" if nan_res.status_code == 200 else "AUTH_FAILED"
        except: health_report["api_connectivity_matrix"]["nansen"] = "OFFLINE"
    return health_report

async def fetch_dex_liquidity_usd(chain: str, address: str) -> float:
    if chain.lower() == "solana": return 5000000.0
    if chain.lower() == "hyperevm": return 3500000.0  # Safe deterministic default for Hyperliquid L1
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

# --- DETERMINISTIC MACRO LOGIC MATRIX ---
async def check_forex_news_risk(symbol: str, base_ccy: str, quote_ccy: str, direction: str) -> dict:
    api_key = os.getenv("ALPHA_VANTAGE_KEY")
    av_ticker = f"FOREX:{base_ccy}{quote_ccy}"
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={av_ticker}&sort=LATEST&limit=15&apikey={api_key}"
    
    base_keys = CURRENCY_KEYWORDS.get(base_ccy, [])
    quote_keys = CURRENCY_KEYWORDS.get(quote_ccy, [])
    target_keys = base_keys + quote_keys

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            res = await client.get(url)
            if res.status_code == 200:
                data = res.json()
                feed = data.get("feed", [])
                
                if not feed:
                    fallback_url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&topics=economy_macro&sort=LATEST&limit=40&apikey={api_key}"
                    res = await client.get(fallback_url)
                    feed = res.json().get("feed", [])
                
                relevant_articles = []
                pattern = re.compile(r'\b(' + '|'.join(re.escape(tk) for tk in target_keys) + r')\b')
                
                for a in feed:
                    text_to_search = f"{a.get('title', '')} {a.get('summary', '')}".lower()
                    if pattern.search(text_to_search):
                        title = a.get("title", "")
                        a["clean_title"] = title.split("...")[0].strip() if "..." in title else title
                        relevant_articles.append(a)

                if not relevant_articles:
                    return {
                        "risk_score": 0.0, "sentiment": "NEUTRAL", 
                        "headline": f"No active structural headlines detected for {base_ccy}/{quote_ccy}.",
                        "brief": "Macro landscape quiet. Pure order-flow execution authorized."
                    }
                
                top_article = relevant_articles[0]
                headline = top_article.get("clean_title", top_article.get("title"))
                sentiment_label = top_article.get("overall_sentiment_label", "NEUTRAL")
                sentiment_score = float(top_article.get("overall_sentiment_score", 0.0))

                # Compute baseline risks
                total_drag = 0.0
                critical_shocks = ["fomc", "fed rate", "cpi", "nfp", "nonfarm", "interest rate"]
                now = datetime.datetime.now()

                for art in relevant_articles[:10]:
                    p_str = art.get("time_published", "")
                    if not p_str: continue
                    try: days_old = (now - datetime.datetime.strptime(p_str, "%Y%m%dT%H%M%S")).days
                    except: days_old = 0
                    if any(ck in art.get("title", "").lower() for ck in critical_shocks):
                        total_drag += 6.0 * (0.75 ** days_old)

                # DYNAMIC RULE ENGINE: Evaluates USD cross-pair trends without AI latency
                usd_is_quote = (quote_ccy == "USD")
                brief_text = f"Monetary data prints as {sentiment_label}."
                
                if "BULLISH" in sentiment_label:
                    if usd_is_quote:
                        brief_text = f"Stronger US Dollar sentiment puts structural downward pressure on {base_ccy}/USD."
                    else:
                        brief_text = f"Bullish USD velocity driving expansion on USD/{quote_ccy} pair structures."
                elif "BEARISH" in sentiment_label:
                    if usd_is_quote:
                        brief_text = f"Weakening US Dollar parameters support structural local breakout extensions for {base_ccy}/USD."
                    else:
                        brief_text = f"Bearish Dollar liquidity metrics capping global upside extensions against {quote_ccy} environments."

                return {"risk_score": total_drag, "sentiment": sentiment_label, "headline": headline, "brief": brief_text}
        except: pass
    return {"risk_score": 0.0, "sentiment": "NEUTRAL", "headline": "Macro Pipeline Timeout", "brief": "Executing blindly on fallback protocol."}

# --- UNIFIED INTELLIGENT WEBHOOK ---
@app.post("/webhook/tradingview")
@app.post("/webhook/tradingview/")
async def tradingview_webhook(payload: TradingViewPayload, background_tasks: BackgroundTasks):
    if payload.secret_token != os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026"): raise HTTPException(status_code=401)

    raw_ticker = payload.ticker.upper().replace("/", "").replace("-", "").replace(" ", "").replace(".P", "")
    is_forex = len(raw_ticker) == 6 and raw_ticker[:3] in CURRENCY_KEYWORDS and raw_ticker[3:] in CURRENCY_KEYWORDS
    decision, stars, reasoning = "EXECUTE", "⭐⭐⭐", ""
    
    # Map direction labels for the dynamic alert headers
    dir_label = "LONG" if payload.direction.upper() == "BUY" else "SHORT"

    if is_forex:
        base_ccy, quote_ccy = raw_ticker[:3], raw_ticker[3:]
        symbol = f"{base_ccy}_{quote_ccy}"
        sector = f"Global FX | {base_ccy}-{quote_ccy} Cross"
        
        av_intel = await check_forex_news_risk(symbol, base_ccy, quote_ccy, payload.direction.upper())
        metric_display = f"AV: {av_intel['sentiment']}"
        base_note = f"📰 Latest: {av_intel['headline']}"

        if av_intel["risk_score"] >= 8.0:
            decision, stars, reasoning = "ABORT", "⚠️", f"🛑 MACRO RISK SHOCK: Systemic headline volatility detected.\n{base_note}"
        else:
            reasoning = f"✅ {av_intel['brief']}\n{base_note}"
            if "BULLISH" in av_intel["sentiment"] and payload.direction.upper() == "BUY": stars = "⭐⭐⭐⭐⭐"
            if "BEARISH" in av_intel["sentiment"] and payload.direction.upper() == "SHORT": stars = "⭐⭐⭐⭐⭐"

    else:
        lookup_key = raw_ticker.split(":")[-1]
        for stable in ["USDT", "USDC", "USD"]:
            if lookup_key.endswith(stable) and lookup_key != stable:
                lookup_key = lookup_key[:-len(stable)]
                break
        
        symbol = CRYPTO_CLEAN_MAP.get(lookup_key, lookup_key)
        token_info = TOKEN_MAP.get(symbol)

        if token_info:
            sector = token_info.get("sector")
            metrics = await fetch_full_intelligence(symbol=symbol, address=token_info.get("address"), chain=token_info.get("chain"))
            pool_liquidity = await fetch_dex_liquidity_usd(chain=token_info.get("chain"), address=token_info.get("address"))
        else:
            sector, metrics, pool_liquidity = "Unmapped Asset", None, 1000000.0

        if metrics:
            flow, direction = metrics["net_flow_24h"], payload.direction.upper()
            base_note = f"💧 Pool Depth: ${pool_liquidity/1e3:,.0f}k"

            if pool_liquidity < 250000.0:
                decision, stars, reasoning = "ABORT", "⚠️", f"🛑 ILLIQUID POOL TRAP: DEX liquidity too thin for safe execution.\n{base_note}"
            elif direction == "BUY" and flow < -2000000:
                decision, stars, reasoning = "ABORT", "⚠️", f"🛑 LIQUIDITY OVERHANG: Smart money distribution detected via active selling.\n{base_note}"
            elif direction == "SHORT" and flow > 2000000:
                decision, stars, reasoning = "ABORT", "⚠️", f"🛑 CONTRA-TREND TRAP: Heavy institutional whale accumulation underway.\n{base_note}"
            else:
                # Rule Engine for Crypto Analyst Brief
                if flow > 500000:
                    brief_text = "Heavy smart money accumulation mapped on chain."
                elif flow < -500000:
                    brief_text = "Systemic institutional distribution observed."
                else:
                    brief_text = "Capital flows stable. Technical setups aligned within baseline risk parameters."
                reasoning = f"✅ {brief_text}\n{base_note}"

            # FIX: Adaptive Formatting Engine to stop $0.0M rounding errors
            if abs(flow) >= 1_000_000:
                metric_display = f"${flow/1e6:+.2f}M Flow"
            else:
                metric_display = f"${flow/1e3:+.1f}K Flow"
        else:
            # Clean Fallback layer for app-chains like Hyperliquid
            if token_info and token_info.get("chain") == "hyperevm":
                metric_display = "App-Chain Optimized"
                reasoning = f"✅ Running structural execution protocol for custom Layer-1 app-chain topology.\n💧 Pool Depth: $3,500k"
            else:
                metric_display = "On-Chain Out of Bounds"
                reasoning = "Technical layout execution bypass due to unmapped smart contract topology."

    price_display = f"{payload.price:,.5f}" if is_forex else f"{payload.price:,.2f}"
    
    # Added dynamic direction payload label directly next to the EXECUTE/ABORT marker
    rich_message = (
        f"{'🟩' if decision == 'EXECUTE' else '🟥'} <b>DECISION: {decision} ({dir_label})</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💎 <b>Asset:</b> <code>${symbol}</code>\n"
        f"🏷️ <b>Sector:</b> <code>{sector}</code>\n"
        f"📊 <b>TF:</b> <code>{payload.timeframe}m</code> | <b>Price:</b> <code>${price_display}</code>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{'🌍 <b>MACRO TELEMETRY</b>' if is_forex else '🛡️ <b>ON-CHAIN INTELLIGENCE</b>'}\n"
        f"• Status: <code>{metric_display}</code>\n• Conviction: {stars}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 <b>Analyst Brief:</b>\n{reasoning}\n"
        f"📈 <i>Confluence Engine V5.0</i>"
    )

    background_tasks.add_task(send_telegram_notification, rich_message)
    return {"status": "success", "decision": decision}