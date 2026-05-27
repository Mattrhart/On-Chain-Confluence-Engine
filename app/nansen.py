import os
import requests

NANSEN_API_BASE = "https://api.nansen.ai/api/v1"

def fetch_onchain_metrics(ticker: str, chain: str = "solana"):
    """
    Queries Nansen's live Smart Money Netflow array to see if institutional 
    wallets are net accumulating or distributing assets.
    """
    api_key = os.getenv("NANSEN_API_KEY")
    if not api_key:
        return {"error": "Missing Nansen API Key"}

    headers = {
        "apiKey": api_key,
        "Content-Type": "application/json"
    }
    
    # Corrected endpoint to target Nansen's global smart money tracking array
    url = f"{NANSEN_API_BASE}/smart-money/netflow"
    
    # Nansen expects the target chains array at the root payload level
    payload = {
        "chains": [chain.lower()]
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code != 200:
            return {"error": f"Nansen API Error {response.status_code}", "details": response.text}
            
        data = response.json()
        
        # Look through the returning array to pull matching ticker metrics
        token_list = data.get("data", [])
        for token in token_list:
            if token.get("token_symbol", "").upper() == ticker.upper():
                return {
                    "token": ticker.upper(),
                    "net_flow_24h_usd": token.get("net_flow_24h_usd", 0),
                    "volume_usd": token.get("volume_usd", 0)
                }
                
        # If the token isn't in the top active list, return a clean neutral baseline
        return {"token": ticker.upper(), "net_flow_24h_usd": 0, "status": "No active institutional anomalies"}
        
    except Exception as e:
        return {"error": f"Failed to execute Nansen fetch: {str(e)}"}