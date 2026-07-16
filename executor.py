"""Thực thi lệnh Binance (Testnet/Live). dry_run=True chỉ log. Long-only, Spot."""
from dataclasses import dataclass


@dataclass
class Order:
    id: str
    symbol: str
    side: str
    qty: float
    price: float
    kind: str


class Executor:
    def __init__(self, exchange, cfg, notifier, data_ex=None):
        self.ex = exchange                    # sàn ĐẶT LỆNH (testnet/live)
        self.data_ex = data_ex or exchange    # sàn lấy GIÁ THẬT (công khai)
        self.cfg = cfg
        self.note = notifier

    def price(self, symbol) -> float:
        return float(self.data_ex.fetch_ticker(symbol)["last"])

    def free_usdt(self) -> float:
        if self.cfg.dry_run:
            return self.cfg.max_capital or self.cfg.initial_capital
        bal = self.ex.fetch_balance()
        return float(bal["free"].get("USDT", 0.0))

    def _amt(self, symbol, qty):
        try:
            return float(self.ex.amount_to_precision(symbol, qty))
        except Exception:
            return qty

    def _prc(self, symbol, price):
        try:
            return float(self.ex.price_to_precision(symbol, price))
        except Exception:
            return price

    def market_buy(self, symbol, qty) -> Order:
        qty = self._amt(symbol, qty)
        if self.cfg.dry_run:
            px = self.price(symbol)
            self.note.event(f"[DRY] MARKET BUY {symbol} qty={qty} ~${px}", alert=False)
            return Order("dry-buy", symbol, "buy", qty, px, "market_buy")
        o = self.ex.create_order(symbol, "market", "buy", qty)
        px = float(o.get("average") or o.get("price") or self.price(symbol))
        return Order(str(o.get("id")), symbol, "buy", qty, px, "market_buy")

    def place_hard_stop(self, symbol, qty, stop_price) -> Order:
        qty = self._amt(symbol, qty)
        stop_price = self._prc(symbol, stop_price)
        limit_price = self._prc(symbol, stop_price * 0.997)
        if self.cfg.dry_run or not self.cfg.hard_stop_on_exchange:
            return Order("dry-stop", symbol, "sell", qty, stop_price, "stop_loss")
        try:
            o = self.ex.create_order(symbol, "STOP_LOSS_LIMIT", "sell", qty, limit_price,
                                     {"stopPrice": stop_price})
            return Order(str(o.get("id")), symbol, "sell", qty, stop_price, "stop_loss")
        except Exception as e:
            self.note.event(f"Không đặt được STOP-LOSS sàn cho {symbol}: {e}", alert=False)
            return None

    def cancel(self, symbol, order_id):
        if self.cfg.dry_run or not order_id or str(order_id).startswith("dry"):
            return
        try:
            self.ex.cancel_order(order_id, symbol)
        except Exception as e:
            self.note.log.warning(f"Huỷ lệnh {order_id} lỗi: {e}")

    def market_sell(self, symbol, qty, reason="") -> Order:
        qty = self._amt(symbol, qty)
        if self.cfg.dry_run:
            px = self.price(symbol)
            self.note.event(f"[DRY] MARKET SELL {symbol} qty={qty} ~${px} ({reason})", alert=False)
            return Order("dry-sell", symbol, "sell", qty, px, "market_sell")
        o = self.ex.create_order(symbol, "market", "sell", qty)
        px = float(o.get("average") or o.get("price") or self.price(symbol))
        return Order(str(o.get("id")), symbol, "sell", qty, px, "market_sell")
