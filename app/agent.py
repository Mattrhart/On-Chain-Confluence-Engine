import os

def evaluate_trade_confluence(technical_data: dict, onchain_data: dict):
    """
    Bi-directional rule engine analyzing both LONG and SHORT setups
    against real-time Nansen data streams.
    """
    ticker = technical_data.get("ticker", "UNKNOWN").upper()
    direction = technical_data.get("direction", "BUY").upper()
    net_flow = onchain_data.get("net_flow_24h_usd", 0)
    status = onchain_data.get("status", "")
    
    # Forex Bypass Layer
    if status == "Forex Asset":
        return {
            "decision": "EXECUTE",
            "reason": f"Forex pair {ticker} detected. Bypassing blockchain data layers. Technical ribbon setup authorized."
        }

    # Timeframe-based aggression threshold
    tf = technical_data.get("timeframe", "")
    threshold_reason = ""
    is_favorable = True
    if tf == "15":
        threshold_reason = "Short-term Smart Money momentum required."
        if direction == "BUY":
            is_favorable = net_flow >= 0
        else:
            is_favorable = net_flow <= 0
    else:
        threshold_reason = "Long-term accumulation trend required."
        is_favorable = True  # Placeholder for 7-day trend logic

    if not is_favorable:
        return {
            "decision": "ABORT",
            "reason": f"Technical signal ignored: {threshold_reason}"
        }

    # Direction 1: LONG SETUPS
    if direction == "BUY":
        if net_flow < 0:
            return {
                "decision": "ABORT",
                "reason": f"Divergence on {ticker}: Chart shows LONG pullback, but Nansen shows negative institutional outflow (${net_flow:,})."
            }
        return {
            "decision": "EXECUTE",
            "reason": f"Confluence on {ticker}: Chart shows LONG pullback and Nansen confirms institutional stability/buying."
        }
        
    # Direction 2: SHORT SETUPS
    elif direction == "SELL":
        if net_flow > 0:
            return {
                "decision": "ABORT",
                "reason": f"Divergence on {ticker}: Chart shows SHORT retest, but Nansen shows positive institutional accumulation (${net_flow:,}). Whales absorbing sells."
            }
        return {
            "decision": "EXECUTE",
            "reason": f"Confluence on {ticker}: Chart shows SHORT retest and Nansen confirms heavy distribution/outflow."
        }