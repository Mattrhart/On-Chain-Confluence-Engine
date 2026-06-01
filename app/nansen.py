import os
import httpx

NANSEN_API_BASE = "https://api.nansen.ai/api/v1"

async def fetch_full_intelligence(symbol: str, address: str, chain: str):
    """
    Unified Intelligence Engine (V3.7).
    Uses the Token Screener endpoint (Smart Money Filtered) to bypass tier restrictions.
    """
    api_key = os.getenv("NANSEN_API_KEY")
    headers = {"apiKey": api_key, "Content-Type": "application/json"}
    chain_slug = chain.lower()

    payload = {
        "chains": [chain_slug],
        "timeframe": "24h",
        "pagination": {"page": 1, "per_page": 50},
        "filters": {
            "only_smart_money": True
        }
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(f"{NANSEN_API_BASE}/token-screener", json=payload, headers=headers)
            
            if res.status_code == 200:
                data = res.json().get("data", [])
                
                # Search the screener results for our specific token
                target_token = next((t for t in data if t.get("token_address", "").lower() == address.lower()), None)
                
                if target_token:
                    return {
                        "net_flow_24h": target_token.get("netflow", 0),
                        "risk_score": 5, # Screener doesn't provide TGM risk score, defaulting to neutral
                        "sm_conviction": 50, # Defaulting conviction as TGM is locked
                        "is_institutional": True
                    }
                else:
                    print(f"⚠️ {symbol} not found in Top 50 Smart Money Screener flows today.")
                    return None
            else:
                print(f"⚠️ Nansen API Error: {res.status_code} - {res.text}")
                return None
                
        except Exception as e:
            print(f"⚠️ Nansen Intelligence Failure: {e}")
            return None