import asyncio
import websockets
import json
import logging
import time
import math
import aiohttp
import re
import yaml

# Load configuration
with open('config.yaml', 'r') as file:
    config = yaml.safe_load(file)

# ANSI color codes
class Colors:
    RESET = '\033[0m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'

# Chainflip WebSocket endpoint and API URL
CHAINFLIP_WS_URL = config['chainflip_ws_url']
CHAINFLIP_API_URL = config['chainflip_api_url']

# Hyperliquid WebSocket URL - Add whatever external exchange you are using here 
HYPERLIQUID_WS_URL = config['hyperliquid_ws_url']

# Chainflip LP address
CHAINFLIP_LP_ADDRESS = config['chainflip_lp_address']

# Assets
BASE_ASSET = config['assets']['base']
DOT_ASSET = config['assets']['dot']
QUOTE_ASSET = config['assets']['quote']

# Trading amounts
ETH_SELL_AMOUNT_PRIMARY = config['trading_amounts']['eth']['sell']['primary']
ETH_BUY_AMOUNT_PRIMARY = config['trading_amounts']['eth']['buy']['primary']
DOT_SELL_AMOUNT_PRIMARY = config['trading_amounts']['dot']['sell']['primary']
DOT_BUY_AMOUNT_PRIMARY = config['trading_amounts']['dot']['buy']['primary']

# Logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Telegram setup
TELEGRAM_BOT_TOKEN = config['telegram']['bot_token']
TELEGRAM_CHAT_ID = config['telegram']['chat_id']

# File to store order fill information for Hummingbot
ORDER_FILL_FILE = config['order_fill_file']

# Initialize last_order_prices
last_order_prices = {'ETH': 0, 'DOT': 0}

# Global variable to store latest Hyperliquid prices
hyperliquid_prices = {'ETH': 0, 'DOT': 0}

def remove_ansi_codes(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

async def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        clean_message = remove_ansi_codes(message)
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": clean_message
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                await response.json()
        logging.info(f"Telegram message sent: {clean_message}")
    except Exception as e:
        logging.error(f"Failed to send Telegram message: {e}")

async def log_success(message):
    success_message = f"{Colors.GREEN}💰 SUCCESS: {message}{Colors.RESET}"
    logging.info(success_message)
    await send_telegram_message(success_message)

def calculate_tick(price, base_precision, quote_precision):
    return math.floor(math.log(price * quote_precision / base_precision) / math.log(1.0001))

async def place_limit_order(session, order_type, price, primary_amount, pair, base_asset, quote_asset, order_id):
    if base_asset['asset'] == 'ETH':
        base_precision = 10**18
    elif base_asset['asset'] == 'DOT':
        base_precision = 10**10
    else:
        base_precision = 10**6

    quote_precision = 10**6  # USDC precision

    tick = calculate_tick(price, base_precision, quote_precision)

    if order_type == 'buy':
        sell_amount = int(primary_amount * price * quote_precision)  # USDC amount
    else:
        sell_amount = int(primary_amount * base_precision)

    payload = {
        "id": 1,
        "jsonrpc": "2.0",
        "method": "lp_set_limit_order",
        "params": {
            "base_asset": base_asset,
            "quote_asset": quote_asset,
            "side": order_type,
            "id": order_id,
            "tick": tick,
            "sell_amount": f"0x{sell_amount:x}"
        }
    }
    try:
        async with session.post(CHAINFLIP_API_URL, json=payload) as response:
            response.raise_for_status()
            response_data = await response.json()
            if 'result' in response_data:
                logging.info(f"Order placed: {order_type.capitalize()} {primary_amount:.8f} {base_asset['asset']} at {price:.2f} USDC")
                return True
            else:
                error_message = response_data.get('error', {}).get('message', 'Unknown error')
                logging.error(f"Failed to place {order_type} order for {pair}: {error_message}")
                return False
    except aiohttp.ClientError as e:
        logging.error(f"Error placing {order_type} order: {str(e)}")
        return False

async def write_order_fill(fill_data):
    try:
        with open(ORDER_FILL_FILE, 'a') as f:
            json.dump(fill_data, f)
            f.write('\n')
    except Exception as e:
        logging.error(f"Error writing order fill to file: {e}")

def handle_limit_order(order):
    base_asset = order["base_asset"]["asset"]
    quote_asset = order["quote_asset"]["asset"]
    side = order["side"]
    sold = int(order["sold"], 16)
    bought = int(order["bought"], 16)

    if base_asset in ["ETH", "DOT"] and quote_asset == "USDC":
        if base_asset == "ETH":
            asset_change = (-sold if side == "sell" else bought) / 1e18  # Convert from Wei to ETH
        else:  # DOT
            asset_change = (-sold if side == "sell" else bought) / 1e10  # Convert from Planck to DOT

        usdc_change = (bought if side == "sell" else -sold) / 1e6  # Convert from USDC wei to USDC

        average_price = abs(usdc_change / asset_change) if asset_change != 0 else 0

        # Calculate fee (5 basis points)
        fees_usdc = abs(usdc_change) * 0.0005
        fees_asset = fees_usdc / average_price if average_price != 0 else 0

        return {
            "base_asset": base_asset,
            "quote_asset": quote_asset,
            "side": side,
            "asset_change": asset_change,
            "usdc_change": usdc_change,
            "average_price": average_price,
            "fees_asset": fees_asset,
            "fees_usdc": fees_usdc
        }
    return None

async def handle_order_fills(result):
    fills = result.get("fills", [])
    if not fills:
        return

    for fill in fills:
        if "limit_order" in fill:
            order_data = handle_limit_order(fill["limit_order"])
            if order_data:
                success_message = (
                    f"Order filled: Swapped {abs(order_data['asset_change']):.8f} {order_data['base_asset']} "
                    f"(${abs(order_data['usdc_change']):.2f}) → {abs(order_data['usdc_change']):.2f} USDC "
                    f"at an average price of ${order_data['average_price']:.2f}. "
                    f"Fees earned: {order_data['fees_asset']:.8f} {order_data['base_asset']} (${order_data['fees_usdc']:.4f} USDC)"
                )
                await log_success(success_message)

                # Write order fill information to file for Hummingbot
                fill_data = {
                    "timestamp": int(time.time()),
                    "base_asset": order_data['base_asset'],
                    "quote_asset": order_data['quote_asset'],
                    "side": order_data['side'],
                    "amount": abs(order_data['asset_change']),
                    "price": order_data['average_price'],
                    "total": abs(order_data['usdc_change']),
                    "fees_earned_asset": order_data['fees_asset'],
                    "fees_earned_usdc": order_data['fees_usdc'],
                    "fees_asset": order_data['base_asset']
                }
                await write_order_fill(fill_data)
        else:
            logging.warning(f"Unexpected fill structure: {fill}")

async def subscribe_to_order_fills():
    while True:
        try:
            logging.info(f"Connecting to Chainflip WebSocket")
            async with websockets.connect(CHAINFLIP_WS_URL) as websocket:
                logging.info("Connected to Chainflip WebSocket")
                subscribe_message = {
                    "id": 1,
                    "jsonrpc": "2.0",
                    "method": "lp_subscribe_order_fills"
                }
                await websocket.send(json.dumps(subscribe_message))
                logging.info("Sent Chainflip subscription message")

                last_heartbeat = time.time()
                while True:
                    try:
                        response = await asyncio.wait_for(websocket.recv(), timeout=30)
                        data = json.loads(response)

                        if "method" in data and data["method"] == "lp_subscribe_order_fills":
                            if "params" in data and "result" in data["params"]:
                                result = data["params"]["result"]
                                block_number = result.get("block_number")
                                fills = result.get("fills", [])
                                if fills:
                                    logging.info(f"Received {len(fills)} order fill(s) at block {block_number}")
                                    await handle_order_fills(result)
                            else:
                                logging.warning(f"Unexpected data structure in order fill notification")
                    except asyncio.TimeoutError:
                        current_time = time.time()
                        if current_time - last_heartbeat >= 60:
                            logging.info("Waiting for order fills...")
                            last_heartbeat = current_time
        except websockets.exceptions.WebSocketException as e:
            logging.error(f"Chainflip WebSocket error: {e}. Attempting to reconnect...")
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Error in Chainflip WebSocket connection: {e}")
            await asyncio.sleep(5)

async def subscribe_to_hyperliquid_prices():
    global hyperliquid_prices
    while True:
        try:
            async with websockets.connect(HYPERLIQUID_WS_URL) as websocket:
                logging.info("Connected to Hyperliquid WebSocket")

                # Send subscription message
                subscribe_message = {
                    "method": "subscribe",
                    "subscription": {"type": "allMids"}
                }
                await websocket.send(json.dumps(subscribe_message))
                logging.info("Sent Hyperliquid subscription message")

                # Start ping-pong mechanism
                last_ping_time = time.time()

                while True:
                    try:
                        # Set a timeout for receiving messages
                        response = await asyncio.wait_for(websocket.recv(), timeout=60)
                        data = json.loads(response)

                        if "channel" in data:
                            if data["channel"] == "allMids":
                                mids = data["data"]["mids"]
                                old_eth = hyperliquid_prices["ETH"]
                                old_dot = hyperliquid_prices["DOT"]
                                hyperliquid_prices["ETH"] = float(mids.get("ETH", 0))
                                hyperliquid_prices["DOT"] = float(mids.get("DOT", 0))

                                # Only log if prices have changed significantly
                                if abs(hyperliquid_prices["ETH"] - old_eth) > 1 or abs(hyperliquid_prices["DOT"] - old_dot) > 0.1:
                                    logging.info(f"Price update: ETH: ${hyperliquid_prices['ETH']:.2f}, DOT: ${hyperliquid_prices['DOT']:.2f}")
                            elif data["channel"] == "subscriptionResponse":
                                logging.info("Hyperliquid subscription confirmed")
                            elif data["channel"] == "pong":
                                pass  # Ignore pong messages in logs
                            else:
                                logging.warning(f"Received unexpected message: {data}")
                        else:
                            logging.warning(f"Received message without channel: {data}")

                        # Send ping every 50 seconds
                        current_time = time.time()
                        if current_time - last_ping_time > 50:
                            await websocket.send(json.dumps({"method": "ping"}))
                            last_ping_time = current_time

                    except asyncio.TimeoutError:
                        logging.warning("No message received from Hyperliquid for 60 seconds. Reconnecting...")
                        break

        except websockets.exceptions.WebSocketException as e:
            logging.error(f"Hyperliquid WebSocket error: {e}. Attempting to reconnect...")
            await asyncio.sleep(5)
        except Exception as e:
            logging.error(f"Error in Hyperliquid WebSocket connection: {e}")
            await asyncio.sleep(5)

async def run_market_making_bot():
    global last_order_prices
    eth_pair = "ETH/USDC"
    dot_pair = "DOT/USDC"

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                eth_mid_price = hyperliquid_prices["ETH"]
                dot_mid_price = hyperliquid_prices["DOT"]

                if eth_mid_price == 0 or dot_mid_price == 0:
                    await asyncio.sleep(1)
                    continue

                eth_buy_price = eth_mid_price * config['trading']['eth']['buy_factor']
                eth_sell_price = eth_mid_price * config['trading']['eth']['sell_factor']

                dot_buy_price = dot_mid_price * config['trading']['dot']['buy_factor']
                dot_sell_price = dot_mid_price * config['trading']['dot']['sell_factor']

                # Check if prices have moved by more than the threshold
                eth_price_change = abs(eth_mid_price - last_order_prices['ETH']) / last_order_prices['ETH'] if last_order_prices['ETH'] != 0 else float('inf')
                dot_price_change = abs(dot_mid_price - last_order_prices['DOT']) / last_order_prices['DOT'] if last_order_prices['DOT'] != 0 else float('inf')

                tasks = []

                if (eth_price_change > config['trading']['price_change_threshold'] or last_order_prices['ETH'] == 0) and ETH_SELL_AMOUNT_PRIMARY > 0:
                    tasks.append(place_limit_order(session, 'sell', eth_sell_price, ETH_SELL_AMOUNT_PRIMARY, eth_pair, BASE_ASSET, QUOTE_ASSET, order_id=1))
                if (eth_price_change > config['trading']['price_change_threshold'] or last_order_prices['ETH'] == 0) and ETH_BUY_AMOUNT_PRIMARY > 0:
                    tasks.append(place_limit_order(session, 'buy', eth_buy_price, ETH_BUY_AMOUNT_PRIMARY, eth_pair, BASE_ASSET, QUOTE_ASSET, order_id=2))
                if tasks:
                    last_order_prices['ETH'] = eth_mid_price
                    logging.info(f"Updating ETH orders: Sell at ${eth_sell_price:.2f}, Buy at ${eth_buy_price:.2f}")

                if (dot_price_change > config['trading']['price_change_threshold'] or last_order_prices['DOT'] == 0) and DOT_SELL_AMOUNT_PRIMARY > 0:
                    tasks.append(place_limit_order(session, 'sell', dot_sell_price, DOT_SELL_AMOUNT_PRIMARY, dot_pair, DOT_ASSET, QUOTE_ASSET, order_id=5))
                if (dot_price_change > config['trading']['price_change_threshold'] or last_order_prices['DOT'] == 0) and DOT_BUY_AMOUNT_PRIMARY > 0:
                    tasks.append(place_limit_order(session, 'buy', dot_buy_price, DOT_BUY_AMOUNT_PRIMARY, dot_pair, DOT_ASSET, QUOTE_ASSET, order_id=6))
                if tasks:
                    last_order_prices['DOT'] = dot_mid_price
                    logging.info(f"Updating DOT orders: Sell at ${dot_sell_price:.2f}, Buy at ${dot_buy_price:.2f}")

                if tasks:
                    await asyncio.gather(*tasks)

                await asyncio.sleep(1)
            except Exception as e:
                logging.error(f"Error in market making bot: {e}")
                await asyncio.sleep(1)

async def main():
    try:
        logging.info("Starting market making bot...")
        await asyncio.gather(
            subscribe_to_hyperliquid_prices(),
            run_market_making_bot(),
            subscribe_to_order_fills()
        )
    except Exception as e:
        error_message = f"Critical error in main function: {str(e)}"
        logging.error(error_message)
        await send_telegram_message(error_message)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
    except Exception as e:
        error_message = f"Unhandled exception: {str(e)}"
        logging.error(error_message)
        asyncio.run(send_telegram_message(error_message))
