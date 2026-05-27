import os
import httpx

async def send_telegram_notification(message: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(url, json={
                "chat_id": chat_id, 
                "text": message, 
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            })
        except Exception as e:
            print(f"🔥 Telegram Dispatch Failed: {e}")