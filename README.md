# Chainflip Market Making Bot

This repository contains a market making bot for Chainflip, focusing on ETH and DOT trading pairs. The bot uses the Chainflip LP API and Hyperliquid for price feeds. 
The bot is meant to be used in a cross-exchange market making strategy, where you are hedging your buys and sells on Chainflip on an external exchange. 
You can use a decentralized perps exchange like Hyperliquid or DYDX if you want to use leverage for your inventory or any centralized exchange of your choosing (IE Binance, Coinbase, ByBit, etc). 

Note: I (Chainflipgod) am a rookie at this stuff. This script and config.yaml are meant to serve as a starting point for you. Please make sure you test, test and test more. Also start with small amounts before putting significant capital at risk. 

HAPPY LPING. 

## Prerequisites

Before running the bot, ensure you have the following:

1. Python 3.7 or higher installed
2. Chainflip LP API set up and running
3. A Chainflip LP address funded with at least 10 $FLIP
4. A Telegram bot token and chat ID (optional, for notifications)

## Setup

1. Clone this repository:

git clone https://github.com/chainflipgod/Chainflip-Maker-Demo.git
cd chainflip-market-maker

2. Install the required Python packages:

pip install websockets aiohttp pyyaml

3. Set up the Chainflip LP API:
Follow the instructions in the [Chainflip Mainnet APIs repository](https://github.com/chainflip-io/chainflip-mainnet-apis) to set up the LP API in the same directory as the market maker script.

4. Configure the `config.yaml` file:
- Replace `your_chainflip_lp_address_here` with your actual Chainflip LP address
- (Optional) Add your Telegram bot token and chat ID for notifications regarding your trades 
- Adjust trading amounts and parameters as needed

## Configuration

The `config.yaml` file contains all the necessary settings for the market making bot. Here's an overview of the main sections:

- `chainflip_ws_url` and `chainflip_api_url`: WebSocket and API URLs for Chainflip
- `hyperliquid_ws_url`: WebSocket URL for Hyperliquid price feeds
- `chainflip_lp_address`: Your Chainflip LP address
- `assets`: Definitions for ETH, DOT, and USDC
- `trading_amounts`: Primary trading amounts for ETH and DOT (buy and sell)
- `telegram`: Telegram bot token and chat ID for notifications
- `trading`: Trading parameters including buy/sell factors and price change thresholds
- `lp_identifiers`: Mapping of LP addresses to names (add your own identifier)

Adjust these settings according to your trading strategy and risk tolerance.

## Running the Bot

To start the market making bot, run:

maker.py

The bot will connect to the Chainflip and Hyperliquid WebSockets, subscribe to price feeds, and start placing orders based on the configured parameters.

## Monitoring

The bot logs its activities to the console and, if configured, sends notifications via Telegram. You can monitor the bot's performance by watching these logs and messages.

## Disclaimer

This market making bot is provided as-is, without any guarantees or warranty. Use it at your own risk. The authors are not responsible for any potential losses incurred while using this bot.

## Contributing

Contributions to improve the bot are welcome. Please submit pull requests or open issues to discuss potential improvements or report bugs.

