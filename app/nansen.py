import os
import httpx

NANSEN_API_BASE = "https://api.nansen.ai/api/v1"

async def fetch_full_intelligence(symbol: str, address: str, chain: str):
    """
    Unified Intelligence Engine (V4.0).
    Structurally routes EVM vs. SVM chains to prevent topology errors.
    """
    evm_chains = ["ethereum", "base", "arbitrum", "optimism", "bnb", "polygon"]
    svm_chains = ["solana"]
    
    chain_slug = chain.lower()
    
    if chain_slug in evm_chains:
        return await _fetch_evm_intelligence(symbol, address, chain_slug)
    elif chain_slug in svm_chains:
        return await _fetch_svm_intelligence(symbol, address, chain_slug)
    else:
        # Graceful return to activate the Main.py specialized app-chain exception logic
        print(f"⚠️ App-Chain routing handled via main engine: {chain_slug}")
        return None

async def _fetch_evm_intelligence(symbol: str, address: str, chain_slug: str):
    api_key = os.getenv("NANSEN_API_KEY")
    headers = {"apiKey": api_key, "Content-Type": "application/json"}

    payload = {
        "chains": [chain_slug],
        "timeframe": "24h",
        "pagination": {"page": 1, "per_page": 50},
        "filters": {"only_smart_money": True}
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.post(f"{NANSEN_API_BASE}/token-screener", json=payload, headers=headers)
            if res.status_code == 200:
                data = res.json().get("data", [])
                target_token = next((t for t in data if t.get("token_address", "").lower() == address.lower()), None)
                if target_token:
                    return {
                        "net_flow_24h": target_token.get("netflow", 0),
                        "risk_score": 5, 
                        "sm_conviction": 50, 
                        "is_institutional": True
                    }
                return None
        except Exception as e:
            print(f"⚠️ EVM Intelligence Failure: {e}")
            return None

async def _fetch_svm_intelligence(symbol: str, address: str, chain_slug: str):
    api_key = os.getenv("NANSEN_API_KEY")
    headers = {"apiKey": api_key, "Content-Type": "application/json"}
    
    url = f"{NANSEN_API_BASE}/solana/token/{address}/flows" 
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            res = await client.get(url, headers=headers)
            if res.status_code == 200:
                data = res.json()
                return {
                    "net_flow_24h": data.get("netflow_24h", 0),
                    "risk_score": 5,
                    "sm_conviction": 50,
                    "is_institutional": True
                }
            else:
                print(f"⚠️ SVM Route bypass for {symbol}. Proceeding on technical execution.")
                return {"net_flow_24h": 0, "risk_score": 5, "sm_conviction": 50, "is_institutional": False}
        except Exception as e:
            print(f"⚠️ SVM Intelligence Failure: {e}")
            return {"net_flow_24h": 0, "risk_score": 5, "sm_conviction": 50, "is_institutional": False}