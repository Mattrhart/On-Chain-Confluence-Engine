# 🛡️ On-Chain Confluence Engine

An institutional-grade **Quantitative Alpha Pipeline** that filters high-probability TradingView signals through real-time on-chain analytics. 

This engine acts as a "Smart Filter," ensuring that technical expansions (20/50 Ribbon Retests) on major L1s like **ETH, SOL, BNB, and HYPE** are backed by institutional Smart Money flow before notifying the trader via Telegram.

---

## 🏗️ Technical Architecture

The system is built as a modular, event-driven microservice:

1.  **Ingestion Layer:** FastAPI Webhook listener optimized for low-latency TradingView alerts.
2.  **Intelligence Layer:** Integration with **Nansen API** to cross-reference technical signals with institutional Net Flow and "Smart Money" accumulation data.
3.  **Confluence Logic:** A decision-matrix that only triggers an `EXECUTE` command if technical direction and on-chain sentiment align.
4.  **Notification Layer:** Asynchronous Telegram Dispatcher providing instant, rich-text trade alerts to mobile.

---

## 🛠️ Tech Stack

* **Language:** Python 3.11+
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (High-performance ASGI framework)
* **Web Server:** Uvicorn
* **Data Validation:** Pydantic (Strict typing for incoming TradingView payloads)
* **Network:** HTTPX (Asynchronous HTTP requests for Telegram and Nansen)
* **Environment:** Secure `.env` management with `.gitignore` shielding.

---

## 🔒 Security & Professional Standards

* **Secret Management:** Implements zero-leak protocols by utilizing environment variables for API tokens and Chat IDs.
* **Git Shielding:** Configured with robust `.gitignore` patterns to prevent exposure of sensitive institutional keys.
* **Authentication:** Webhook endpoints are protected via a unique `SECRET_TOKEN` handshake to prevent unauthorized signal injection.

---

## 🚀 Getting Started

### 1. Prerequisites
* A Nansen API Key
* A Telegram Bot Token (via @BotFather)

### 2. Configuration
Clone the repository and create a `.env` file based on the template:
```text
NANSEN_API_KEY=your_key
TRADINGVIEW_SECRET=your_custom_passphrase
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_id
