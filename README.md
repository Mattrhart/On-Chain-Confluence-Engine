import os

def generate_readme():
    readme_content = """# 🛡️ On-Chain & Macro Confluence Engine

An institutional-grade **Quantitative Multi-Asset Pipeline** (V4.0) that filters high-probability TradingView signals through real-time on-chain analytics and global macro sentiment. 

This engine acts as an automated "Smart Filter," ensuring that technical setups (e.g., trend retests, structural expansions) are fundamentally backed by institutional capital before executing a trade decision and notifying the trader via Telegram.

---

## 🏗️ Technical Architecture

The system operates as a low-latency, event-driven microservice:

1.  **Ingestion Layer:** FastAPI Webhook listener optimized for instantaneous processing of TradingView alert payloads.
2.  **On-Chain Crypto Intelligence:** Integrates with the **Nansen API (Token Screener Pipeline)** to cross-reference crypto signals with 24h net flows, liquidity depth, and active Smart Money accumulation.
3.  **Forex Macro Telemetry:** Integrates with the **Alpha Vantage Sentiment Engine**. When an FX signal hits, the engine pulls real-time macroeconomic news feeds, sifts out equity market noise, and checks for systemic risk overhangs (FOMC, CPI prints, Non-Farm Payrolls).
4.  **Confluence Logic Matrix:** A crash-proof decision layer that runs asynchronous risk evaluation. If parameters fail safety checks (e.g., heavy whale dumping or an active macro shock), the engine triggers an immediate **ABORT** command.
5.  **Notification Layer:** Asynchronous Telegram Dispatcher utilizing FastAPI `BackgroundTasks` to send rich-text, Bloomberg-style trade alerts without hanging web server response times.

---

## 📊 Supported Asset Fields

### 1. Sovereign Crypto Assets (On-Chain Layer)
The engine queries Nansen's smart-money pipelines for the following specific asset matrix:

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

> ⚠️ **Fallback Behavior:** If an alert fires for an unmapped crypto asset, the engine gracefully bypasses the Nansen call and executes strictly on technical parameters to prevent payload crashes.

### 2. Global Forex Pairs (Macro Sentiment Layer)
For 6-character fiat tickers (e.g., `EURUSD`, `GBPUSD`), the engine automatically switches to **Macro Telemetry Mode**. It analyzes raw context from global central bank keywords (`powell`, `fed rate`, `ecb`, `boe`) and calculates a rolling risk-decay metric based on article publication age.

---

## 🛠️ Tech Stack

* **Language:** Python 3.12+
* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (High-performance ASGI framework)
* **Web Server:** Uvicorn (Configurable port binding)
* **Data Validation:** Pydantic V2 (Strict data-type compliance for incoming signals)
* **Network Client:** HTTPX (Asynchronous HTTP requests for non-blocking API interactions)
* **Environment Architecture:** Secure environmental variables handled with dynamic `.env` fallback mapping.

---

## 🔒 Security & Infrastructure Standards

* **Zero-Leak Protocols:** Strict reliance on production environment injections; zero hardcoding of sensitive parameters.
* **Authentication Handshake:** Endpoints are secured via a mandatory, customizable `secret_token` string verified before ingestion logic fires.
* **Dynamic Routing:** Automatically detects deployment ports via cloud provider assignments (e.g., Railway variables) while maintaining local testing fallbacks.

---

## 🚀 Getting Started

### 1. Prerequisites
* A Nansen API Key (Screener endpoints unlocked)
* An Alpha Vantage API Key (Free Tier supported)
* A Telegram Bot Token & Target Chat ID

### 2. Local Environment Setup
Clone the repository and build out your local `.env` profile in the root workspace directory:

```text
# Port Configuration (Defaults to 8080 locally)
PORT=8080

# Webhook Handshake Protection
TRADINGVIEW_SECRET=hype_retest_2026

# Data Provider Credentials
NANSEN_API_KEY=nsn_your_paid_key_here
ALPHA_VANTAGE_KEY=your_alphavantage_key_here

# Notification Parameters
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
TELEGRAM_CHAT_ID=-100123456789