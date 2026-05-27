# 🛡️ On-Chain Confluence Engine

An institutional-grade **Quantitative Alpha Pipeline** that filters high-probability TradingView signals through real-time on-chain analytics. 

This engine acts as a "Smart Filter," ensuring that technical expansions (20/50 Ribbon Retests) on major crypto assets are backed by institutional Smart Money flow before notifying the trader via Telegram.

---

## 🏗️ Technical Architecture

The system is built as a modular, event-driven microservice:

1.  **Ingestion Layer:** FastAPI Webhook listener optimized for low-latency TradingView alerts.
2.  **Intelligence Layer:** Integration with **Nansen API** to cross-reference technical signals with institutional Net Flow and "Smart Money" accumulation data.
3.  **Confluence Logic:** A decision-matrix that scales dynamically based on timeframe. It applies a *24h Momentum Filter* for short-term scalps (15m) and a macro *7d God Mode Accumulation Filter* for swing trades.
4.  **Notification Layer:** Asynchronous Telegram Dispatcher providing instant, Bloomberg-style rich-text trade alerts to mobile via `BackgroundTasks` to prevent server response hanging.

---

## 📊 Supported Assets & On-Chain Sectors

The Confluence Engine is explicitly configured to pull real-time institutional wallet movements from Nansen for the following asset matrix:

| Symbol | Market Sector / Role | Native Chain |
| :--- | :--- | :--- |
| **ETH** | L1 / Blue-Chip | Ethereum |
| **BNB** | L1 / Exchange Layer | BNB Chain |
| **SOL** | L1 / High-Speed Execution | Solana |
| **HYPE** | L1 / HyperEVM Ecosystem | HyperEVM |
| **WBTC** | Macro Market Anchor | Ethereum |
| **LINK** | Oracle / Infrastructure | Ethereum |
| **PEPE** | High-Volatility Meme (Beta) | Ethereum |
| **AERO** | L2 Liquidity / Base DEX | Base |
| **LDO** | Liquid Staking Derivatives | Ethereum |

### ⚠️ Fallback Behavior
If an alert fires for a symbol **not listed above**, the engine will still seamlessly process the technical breakout and dispatch a notification. However, it will bypass the Nansen API data-fetch and default to a streamlined technical layout to prevent payload errors.

---

## 🛠️ Tech Stack

* **Language:** Python 3.12+
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (High-performance ASGI framework)
* **Web Server:** Uvicorn
* **Data Validation:** Pydantic (Strict typing for incoming TradingView payloads)
* **Network:** HTTPX (Asynchronous HTTP requests for Telegram and Nansen)
* **Environment:** Secure `.env` management with `.gitignore` shielding.

---

## 🔒 Security & Professional Standards

* **Secret Management:** Implements zero-leak protocols by utilizing environment variables for API tokens and Chat IDs.
* **Git Shielding:** Configured with robust `.gitignore` patterns to prevent exposure of sensitive institutional keys.
* **Authentication:** Webhook endpoints are protected via a unique `secret_token` handshake to prevent unauthorized signal injection.

---

## 🚀 Getting Started

### 1. Prerequisites
* A Nansen API Key
* A Telegram Bot Token (via @BotFather)

### 2. Configuration
Clone the repository and create a `.env` file in the root directory:
```text
NANSEN_API_KEY=your_nansen_api_key_here
TRADINGVIEW_SECRET=hype_retest_2026
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here