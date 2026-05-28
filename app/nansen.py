import os
import httpx
import asyncio

NANSEN_API_BASE = "https://api.nansen.ai/api/v1"

async def fetch_full_intelligence(symbol: str, address: str, chain: str):
    """
    Unified Intelligence Engine (V3.1).
    Combines Smart Money Flow, Concentration (TGM), and Perp Funding.
    """
    api_key = os.getenv("NANSEN_API_KEY")
    headers = {"apiKey": api_key, "Content-Type": "application/json"}
    
    # Standardize chain for Nansen (Solana -> solana)
    chain_slug = chain.lower()

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # 1. Flow Intel (Is Smart Money moving money now?)
            # 2. Indicators (Risk/Reward & Nansen Score)
            # 3. Flow Intelligence (Detailed Holder Breakdown)
            
            flow_req = client.post(f"{NANSEN_API_BASE}/smart-money/netflows", 
                                   json={"chains": [chain_slug], "filters": {"token_address": address}}, 
                                   headers=headers)
            
            ind_req = client.post(f"{NANSEN_API_BASE}/tgm/indicators", 
                                  json={"chain": chain_slug, "token_address": address}, 
                                  headers=headers)

            # Fire both at once to minimize latency on Railway
            flow_res, ind_res = await asyncio.gather(flow_req, ind_req)

            # Extract Data
            f_data = flow_res.json().get("data", [{}])[0] if flow_res.status_code == 200 else {}
            i_data = ind_res.json().get("data", {}) if ind_res.status_code == 200 else {}

            return {
                "net_flow_24h": f_data.get("net_flow_24h_usd", 0),
                "risk_score": i_data.get("risk_score", 5),
                "sm_conviction": i_data.get("smart_money_conviction_score", 0), # 0-100 scale
                "is_institutional": i_data.get("smart_money_conviction_score", 0) > 70
            }
        except Exception as e:
            print(f"⚠️ Nansen Intelligence Failure: {e}")
            return None