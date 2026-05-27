import os
import httpx

async def send_telegram_notification(ticker, direction, decision, reason):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    print(f"📡 [TELEGRAM] Attempting dispatch for {ticker}...")

    if not token or not chat_id:
        print("❌ [TELEGRAM] Error: Token or Chat ID is missing from .env")
        return

    emoji = "✅" if decision == "EXECUTE" else "❌"
    message = (
        f"{emoji} *TRADE SIGNAL: {decision}*\n\n"
        f"*Asset:* {ticker}\n"
        f"*Direction:* {direction}\n"
        f"*Reasoning:* {reason}\n\n"
        f"📊 _Confluence Engine Active_"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                print(f"🚀 [TELEGRAM] Success! Message sent to your phone.")
            else:
                print(f"⚠️ [TELEGRAM] API Error: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"🔥 [TELEGRAM] Connection Error: {e}")