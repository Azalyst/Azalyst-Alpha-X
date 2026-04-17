# Azalyst Alpha X

## Description
Azalyst Alpha X is a platform designed for real-time trading signals.

## Live Deployment Status

**Production Environment:** Render Cloud

**Service Type:** Persistent Web Service (Flask + Scanner Engine)

**Current Status:** Operational

**Live Signal Dashboard:** https://azalyst-alpha-x-txx1.onrender.com

**Function:** Real-time text-based feed of all validated signals mirroring the Discord dispatch format. Auto-refreshes every 10 seconds.

**Notification Channel:** Discord Webhook Integration

**Function:** Low-latency alert dispatch for executed signals with full trade intelligence.

**Note:** As this deployment utilizes a free-tier infrastructure, latency may increase during periods of inactivity while the instance initializes.

## Infrastructure & Deployment

- **Hosting Platform:** Render Cloud (Persistent Web Service)
- **Service Type:** Flask + Scanner Engine
- **Runtime:** Python 3.10+, persistent process with Flask web server
- **Data Source:** Binance USDT-Margined Perpetuals — `fapi.binance.com` (Direct REST API)
- **Notification System:** Discord Webhook (Text-based structured alerts)
- **Web Interface:** Integrated Flask dashboard serving real-time signal history
- **State Persistence:** `paper_trades.json` — Survives restarts, maintains full trade history and balance tracking