# 🤖 Multi-Strategy Crypto Trading Bot (Phase 1)

A production-ready algorithmic cryptocurrency trading bot built in Python. This bot runs as a lightweight FastAPI web application, designed for deployment on Render (free tier) and scheduled with `cron-job.org` to trigger market sweeps every 5 minutes. 

Phase 1 operates exclusively in **Paper Trading Mode** (fully simulated execution with live market data feeding), allowing you to validate strategy returns with zero capital risk.

---

## 🏛️ Project Architecture

```
crypto-bot/
├── main.py                    # FastAPI app, exposing /run, /status, /toggle, /
├── config.py                  # Environment configurations and trading constants
├── render.yaml                # Render Blueprint deployment specification
├── requirements.txt           # Python application package dependencies
│
├── strategies/
│   ├── __init__.py
│   ├── momentum.py            # Trend indicators strategy (RSI + MACD + EMA)
│   ├── sentiment.py           # Sentiment strategy (stub, live news in Phase 2)
│   └── arbitrage.py           # Futures/Spot premium spread strategy (stub in Phase 1)
│
├── core/
│   ├── __init__.py
│   ├── signal_combiner.py     # Weighted meta-layer strategy combiner
│   ├── risk_manager.py        # Position sizing rules, SL/TP levels, cooldowns
│   └── executor.py            # Simulated paper trade execution engine
│
├── data/
│   ├── __init__.py
│   ├── firebase_client.py     # Firestore database service integration
│   └── exchange_client.py     # ccxt Binance REST API market data facade
│
└── utils/
    ├── __init__.py
    ├── logger.py              # Custom stdout logger formatters
    └── telegram_alerts.py     # Async HTTPX Telegram Bot API notification broadcaster
```

---

## 🛠️ Step-by-Step Setup Instructions

### 1. Firebase Firestore Setup
1. Head over to the [Firebase Console](https://console.firebase.google.com/) and click **Create a project**.
2. Navigate to **Firestore Database** in the left sidebar and click **Create database**. Start in **Production mode** and choose a server location close to your region.
3. Click on the project settings gear (top left) -> **Project settings** -> **Service accounts**.
4. Choose **Python** and click **Generate new private key**. This downloads a `.json` key file.
5. Open the downloaded `.json` file and copy its entire text contents. This JSON string will be set as your `FIREBASE_CREDENTIALS` environment variable (both locally and on Render).

### 2. Binance API Credentials
1. Create a [Binance Account](https://www.binance.com/) if you do not have one.
2. Search for "API Management" in your profile drop-down menu and create a new API key.
3. For paper trading, **Read-Only (Enable Reading)** permission is sufficient. You do not need to enable Spot/Margin/Futures trading permissions.
4. Copy the **API Key** and **Secret Key**.

### 3. Telegram Bot Setup (Optional)
1. Message `@BotFather` on Telegram and send `/newbot`. Follow instructions to name your bot and receive the **HTTP API Token** (`TELEGRAM_TOKEN`).
2. Add your new bot to a Telegram channel/group or message it directly.
3. Retrieve your chat ID (`TELEGRAM_CHAT_ID`) by messaging `@userinfobot` or hitting the following endpoint in your browser:
   `https://api.telegram.org/bot<YOUR_TELEGRAM_TOKEN>/getUpdates`

### 4. Local Installation & Launch
Ensure you have Python 3.11+ installed.

1. Clone or copy this directory structure to your workspace.
2. In your terminal, navigate to the folder:
   ```bash
   cd crypto-bot
   ```
3. Create a virtual environment and activate it:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On macOS/Linux:
   source venv/bin/activate
   ```
4. Install all python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Copy `.env.example` to a new `.env` file:
   ```bash
   cp .env.example .env
   ```
6. Open `.env` and fill in your secrets (Binance keys, Firebase JSON credentials string, Telegram token/chat ID).
7. Start the FastAPI development server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```
8. Verify it works by navigating to `http://127.0.0.1:8000/` or triggering a manual run loop sweep:
   `http://127.0.0.1:8000/run`

---

## 🚀 Cloud Deployment (Render Free Tier)

Deploying on **Render** using a blueprint is incredibly easy:

1. Push your local `crypto-bot` codebase to a **private** GitHub repository.
2. Open the [Render Dashboard](https://dashboard.render.com/) and click **New** -> **Blueprint**.
3. Select your GitHub repository. Render will automatically parse the `render.yaml` file.
4. Render will prompt you to input the required environment variables:
   * `BINANCE_API_KEY`: Your Binance API key
   * `BINANCE_SECRET`: Your Binance Secret key
   * `FIREBASE_CREDENTIALS`: Paste the raw single-line or multi-line JSON string representing your Firebase service account key
   * `TELEGRAM_TOKEN`: (Optional) Your Telegram bot token
   * `TELEGRAM_CHAT_ID`: (Optional) Your Telegram chat ID
   * `ANTHROPIC_API_KEY`: (Optional, Phase 2) Your Anthropic API Key
5. Click **Apply**. Render will automatically build the service, install packages, and deploy the FastAPI server.

---

## ⏱️ Scheduler Setup (cron-job.org)

Render free tier instances sleep after 15 minutes of inactivity. To prevent this and keep the bot active, we trigger it every 5 minutes:

1. Create a free account at [cron-job.org](https://cron-job.org/).
2. Click **Create Cronjob**.
3. Fill in the parameters:
   * **Title:** `Crypto Bot Loop`
   * **URL:** `https://your-bot-name.onrender.com/run` (Replace with your actual Render URL)
   * **Request Method:** `GET`
   * **Schedule:** `Every 5 minutes` (`*/5 * * * *`)
   * **Timeout:** `30 seconds`
4. Click **Create**. This cronjob will ping the bot every 5 minutes, maintaining server warmth and triggering the quantitative scanning and paper trading execution cycle.

---

## 📈 Paper Trade Schema details

Simulated balances and orders are kept fully structured in Firestore collections:
* `/config/settings`: Overriding options (pairs list, trade environment mode toggles).
* `/paper_balance/state`: Tracks remaining USDT cash balance (initiates at $10.00).
* `/trades`: Individual trades storing entry price, quantity, active stop-loss, take-profit limits, calculated confluence scores, and win/loss PnL.
* `/performance/daily`: Performance history logs detailing win ratios and daily profit/losses.
