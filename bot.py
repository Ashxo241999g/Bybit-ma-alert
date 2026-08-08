import os
import json
import requests
from datetime import datetime, timezone

BYBIT_URL = "https://api.bybit.com"

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

MA_LENGTH = 100
THRESHOLD = 0.05

STATE_FILE = "state.json"


def bybit_get(endpoint, params):
    response = requests.get(
        BYBIT_URL + endpoint,
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if data.get("retCode") != 0:
        raise Exception(data.get("retMsg", "Bybit API error"))

    return data["result"]


def get_perpetual_symbols():
    result = bybit_get(
        "/v5/market/instruments-info",
        {
            "category": "linear",
            "status": "Trading",
            "limit": 1000
        }
    )

    symbols = []

    for item in result["list"]:
        if (
            item.get("contractType") == "LinearPerpetual"
            and item.get("settleCoin") == "USDT"
        ):
            symbols.append(item["symbol"])

    return symbols


def get_100_day_ma(symbol):

    result = bybit_get(
        "/v5/market/kline",
        {
            "category": "linear",
            "symbol": symbol,
            "interval": "D",
            "limit": 102
        }
    )

    candles = result["list"]

    candles = sorted(
        candles,
        key=lambda x: int(x[0])
    )

    # Ignore today's unfinished candle
    closed_candles = candles[:-1]

    if len(closed_candles) < MA_LENGTH:
        return None

    closes = [
        float(candle[4])
        for candle in closed_candles[-MA_LENGTH:]
    ]

    return sum(closes) / MA_LENGTH


def get_current_price(symbol):

    result = bybit_get(
        "/v5/market/tickers",
        {
            "category": "linear",
            "symbol": symbol
        }
    )

    return float(result["list"][0]["lastPrice"])


def send_telegram(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        },
        timeout=20
    )


def load_state():

    if not os.path.exists(STATE_FILE):
        return {}

    try:
        with open(STATE_FILE, "r") as file:
            return json.load(file)
    except:
        return {}


def save_state(state):

    with open(STATE_FILE, "w") as file:
        json.dump(state, file, indent=2)


def main():

    state = load_state()

    symbols = get_perpetual_symbols()

    print(f"Scanning {len(symbols)} USDT perpetuals...")

    alerts = 0

    for symbol in symbols:

        try:

            ma = get_100_day_ma(symbol)

            if ma is None:
                continue

            price = get_current_price(symbol)

            distance = (price - ma) / ma

            inside_zone = abs(distance) <= THRESHOLD

            previously_inside = state.get(symbol, False)

            # Alert only when price ENTERS the ±5% zone
            if inside_zone and not previously_inside:

                direction = (
                    "ABOVE"
                    if distance >= 0
                    else "BELOW"
                )

                message = (
                    f"🔔 <b>BYBIT 100D MA ALERT</b>\n\n"
                    f"🪙 <b>{symbol}</b>\n"
                    f"💰 Price: <b>{price:,.8g}</b>\n"
                    f"📊 100D MA: <b>{ma:,.8g}</b>\n"
                    f"📏 Distance: <b>{distance * 100:+.2f}%</b>\n"
                    f"↕️ Position: <b>{direction}</b>\n"
                    f"🎯 Alert zone: ±5%\n"
                    f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                )

                send_telegram(message)

                alerts += 1

            state[symbol] = inside_zone

        except Exception as error:

            print(
                f"{symbol}: ERROR - {error}"
            )

    save_state(state)

    print(f"Alerts sent: {alerts}")


if __name__ == "__main__":
    main()
