import os
import httpx

async def send_telegram_notification(message: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(url, json={
                "chat_id": chat_id, 
                "text": message, 
                "parse_mode": "HTML",  # Switched to HTML to prevent headline parsing crashes
                "disable_web_page_preview": True
            })
            
            if response.status_code != 200:
                print(f"🔥 TELEGRAM REJECTED MESSAGE: {response.text}")
                print(f"🔥 RAW MESSAGE ATTEMPTED:\n{message}")
            else:
                print("✅ Telegram notification sent successfully!")
                
        except Exception as e:
            print(f"🔥 Telegram Network Error: {e}")