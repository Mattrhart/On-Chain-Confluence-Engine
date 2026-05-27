import os
import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv
from app.notifier import send_telegram_notification

load_dotenv()
app = FastAPI(title="On-Chain Confluence Engine", version="2.2")

# --- THE INSTITUTIONAL WATCHLIST & SECTOR MAP ---
# Mapped to Nansen's chain-specific contract addresses
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
    """Initial landing for basic status verification."""
    return {"status": "Engine Active", "port": 8001}

@app.get("/health")
async def health_check():
    """Professional health probe for cloud hosting platforms."""
    return {
        "status": "healthy",
        "engine_version": "2.2",
        "nansen_connectivity": True if os.getenv("NANSEN_API_KEY") else False
    }

# --- INTELLIGENCE LAYER ---

async def fetch_nansen_intelligence(symbol: str):
    """Hits Nansen API to cross-reference institutional netflow and holdings."""
    if symbol not in TOKEN_MAP:
        return None
    
    token = TOKEN_MAP[symbol]
    headers = {"apiKey": os.getenv("NANSEN_API_KEY"), "Content-Type": "application/json"}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Netflow: Tracking Smart Money USD Flow
            flow_res = await client.post("https://api.nansen.ai/api/v1/smart-money/netflow", 
                headers=headers, json={"chains": [token["chain"]], "filters": {"token_address": token["address"]}})
            flow_list = flow_res.json().get("data", [])
            f_data = flow_list[0] if flow_list else {}

            # Holdings: Tracking the number of active Smart Money Wallets
            hold_res = await client.post("https://api.nansen.ai/api/v1/smart-money/holdings", 
                headers=headers, json={"chains": [token["chain"]], "filters": {"token_address": token["address"]}})
            hold_list = hold_res.json().get("data", [])
            h_data = hold_list[0] if hold_list else {}

            return {
                "net_flow_24h": f_data.get("net_flow_24h_usd", 0),
                "sm_count": h_data.get("smart_money_trader_count", 0),
                "sm_share": h_data.get("share_of_total_sm_holdings", 0)
            }
        except Exception as e:
            print(f"⚠️ Nansen API Logic Error: {e}")
            return None

# --- WEBHOOK LAYER ---

@app.post("/webhook/tradingview")
@app.post("/webhook/tradingview/")
async def tradingview_webhook(payload: TradingViewPayload, background_tasks: BackgroundTasks):
    # 1. Security Handshake
    if payload.secret_token != os.getenv("TRADINGVIEW_SECRET", "hype_retest_2026"):
        raise HTTPException(status_code=401)

    # 2. Extract Data
    symbol = payload.ticker.split(":")[-1].replace("USDT", "").replace("USDC", "")
    metrics = await fetch_nansen_intelligence(symbol)
    
    # 3. CONFLUENCE DECISION MATRIX (The Skeptic Filter)
    decision = "EXECUTE"
    reasoning = f"Technical {payload.direction} confirms institutional flow."
    stars = "⭐⭐⭐"

    if payload.timeframe == "15" and metrics:
        flow = metrics["net_flow_24h"]
        direction = payload.direction.upper()

        # LONG Logic: Abort if Smart Money is dumping
        if direction == "BUY" and flow < -2000000:
            decision = "ABORT"
            reasoning = f"⚠️ LIQUIDITY TRAP: Technical BUY, but Smart Money sold ${abs(flow)/1e6:.1f}M today."
            stars = "⚠️"
        
        # SHORT Logic: Abort if Smart Money is accumulating
        elif direction == "SHORT" and flow > 2000000:
            decision = "ABORT"
            reasoning = f"⚠️ CONTRA-TREND: Technical SHORT, but Smart Money bought ${flow/1e6:.1f}M today."
            stars = "⚠️"
            
        # GOD MODE: Extreme conviction high-confidence alert
        elif flow > 5000000:
            stars = "⭐⭐⭐⭐⭐"

    # 4. Rich Message Formatting
    sector = TOKEN_MAP.get(symbol, {}).get("sector", "Independent Asset")
    flow_display = f"${metrics['net_flow_24h']/1e6:+.1f}M" if metrics else "No On-Chain Activity"
    
    rich_message = (
        f"{'🟩' if decision == 'EXECUTE' else '🟥'} *DECISION: {decision}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💎 *Asset:* `${symbol}`\n"
        f"🏷️ *Sector:* `{sector}`\n"
        f"📊 *TF:* `{payload.timeframe}m` | *Price:* `${payload.price:,.2f}`\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🛡️ *ON-CHAIN INTELLIGENCE*\n"
        f"• 24h Net Flow: `{flow_display}`\n"
        f"• Conviction: {stars}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📝 *Note:* {reasoning}\n"
        f"📈 _Confluence Engine V2.2_"
    )

    # 5. Dispatch
    background_tasks.add_task(send_telegram_notification, rich_message)
    return {"status": "success", "decision": decision}