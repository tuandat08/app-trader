"""
Kết nối Binance qua ccxt: tải OHLCV (có cache), lọc top gainer.
Không cần API key để đọc dữ liệu công khai. Chạy trên máy có internet.
"""
import os
import time
import pandas as pd

CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def make_exchange(cfg=None):
    """Tạo đối tượng sàn. Nếu cfg có api_key -> dùng để giao dịch; testnet nếu mode='testnet'."""
    import ccxt
    params = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
    if cfg and cfg.api_key:
        params["apiKey"] = cfg.api_key
        params["secret"] = cfg.api_secret
    ex = ccxt.binance(params)
    if cfg and cfg.mode == "testnet":
        ex.set_sandbox_mode(True)   # trỏ tới Binance Testnet
    return ex


def fetch_ohlcv(symbol, timeframe, days, use_cache=True, exchange=None) -> pd.DataFrame:
    key = f"{symbol.replace('/', '')}_{timeframe}_{days}d.csv"
    path = os.path.join(CACHE_DIR, key)
    if use_cache and os.path.exists(path):
        return pd.read_csv(path, parse_dates=["time"], index_col="time")

    ex = exchange or make_exchange()
    since = ex.milliseconds() - days * 86400 * 1000
    ms_per = ex.parse_timeframe(timeframe) * 1000
    cursor, rows, limit = since, [], 1000
    while True:
        batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not batch:
            break
        rows += batch
        cursor = batch[-1][0] + ms_per
        if len(batch) < limit or cursor >= ex.milliseconds():
            break
        time.sleep(ex.rateLimit / 1000)

    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"]).drop_duplicates("ts")
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.set_index("time").drop(columns=["ts"]).sort_index()
    if use_cache:
        df.to_csv(path)
    return df


def fetch_recent(symbol, timeframe, limit=200, exchange=None) -> pd.DataFrame:
    """Lấy 'limit' nến gần nhất cho LIVE (không cache)."""
    ex = exchange or make_exchange()
    batch = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(batch, columns=["ts", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df.set_index("time").drop(columns=["ts"]).sort_index()


def top_gainers(n=10, quote="USDT", min_volume_usd=20_000_000, max_change_pct=40.0,
                exchange=None) -> list:
    """Top coin tăng 24h ĐÃ QUA bộ lọc an toàn (thanh khoản & không quá nóng)."""
    ex = exchange or make_exchange()
    tickers = ex.fetch_tickers()
    rows = []
    for sym, t in tickers.items():
        if not sym.endswith("/" + quote):
            continue
        pct, qv = t.get("percentage"), t.get("quoteVolume")
        if pct is None or qv is None:
            continue
        if qv >= min_volume_usd and 0 < pct <= max_change_pct:
            rows.append((sym, pct))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [r[0] for r in rows[:n]]


# Loại token đòn bẩy / stablecoin khỏi universe
_STABLES = {"USDC", "FDUSD", "TUSD", "DAI", "BUSD", "USDP", "EUR", "GBP", "AEUR"}
_LEVERAGED = ("UP/", "DOWN/", "BULL/", "BEAR/")


def top_symbols_by_volume(n=50, quote="USDT", exchange=None, exclude_special=True) -> list:
    """
    Lấy 'n' cặp coin có KHỐI LƯỢNG 24h lớn nhất (đại diện 'toàn thị trường' để xếp hạng
    top gainer). Bỏ stablecoin và token đòn bẩy. Đây là universe để engine chọn động.
    """
    ex = exchange or make_exchange()
    tickers = ex.fetch_tickers()
    rows = []
    for sym, t in tickers.items():
        if not sym.endswith("/" + quote):
            continue
        base = sym.split("/")[0]
        if exclude_special and (base in _STABLES or any(x in sym for x in _LEVERAGED)):
            continue
        qv = t.get("quoteVolume")
        if qv is None:
            continue
        rows.append((sym, qv))
    rows.sort(key=lambda x: x[1], reverse=True)
    return [r[0] for r in rows[:n]]
