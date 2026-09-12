import pandas as pd
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Optional


@dataclass
class SwingPoint:
    index: int
    price: float
    kind: str  # 'high' or 'low'
    timestamp: str


@dataclass
class StructureBreak:
    index: int
    price: float
    kind: str  # 'BOS' or 'CHoCH'
    direction: str  # 'bullish' or 'bearish'
    timestamp: str


@dataclass
class OrderBlock:
    index: int
    top: float
    bottom: float
    kind: str  # 'bullish' or 'bearish'
    mitigated: bool
    timestamp: str


@dataclass
class FVG:
    index: int
    top: float
    bottom: float
    kind: str  # 'bullish' or 'bearish'
    filled: bool
    timestamp: str


@dataclass
class LiquidityZone:
    index: int
    price: float
    kind: str  # 'buy_side' or 'sell_side'
    swept: bool
    timestamp: str


class SMCAnalyzer:
    """
    Smart Money Concepts analyzer.
    Detects: swing points, BOS/CHoCH, order blocks, FVGs, liquidity zones.
    """
    
    def __init__(self, df: pd.DataFrame, swing_lookback: int = 5):
        self.df = df.reset_index()
        # normalize timestamp column name
        time_col = None
        for c in self.df.columns:
            if c.lower() in ("date", "datetime", "index"):
                time_col = c
                break
        self.time_col = time_col
        self.swing_lookback = swing_lookback
        self.swings: List[SwingPoint] = []
        self.structure: List[StructureBreak] = []
        self.order_blocks: List[OrderBlock] = []
        self.fvgs: List[FVG] = []
        self.liquidity: List[LiquidityZone] = []
    
    def _ts(self, idx: int) -> str:
        if self.time_col is None:
            return str(idx)
        return str(self.df.loc[idx, self.time_col])
    
    # ---------- 1. Swing Points ----------
    def find_swings(self):
        n = self.swing_lookback
        highs = self.df["high"].values
        lows = self.df["low"].values
        
        for i in range(n, len(self.df) - n):
            window_h = highs[i - n:i + n + 1]
            window_l = lows[i - n:i + n + 1]
            
            if highs[i] == window_h.max() and np.sum(window_h == highs[i]) == 1:
                self.swings.append(SwingPoint(i, float(highs[i]), "high", self._ts(i)))
            if lows[i] == window_l.min() and np.sum(window_l == lows[i]) == 1:
                self.swings.append(SwingPoint(i, float(lows[i]), "low", self._ts(i)))
        
        self.swings.sort(key=lambda s: s.index)
    
    # ---------- 2. BOS / CHoCH ----------
    def detect_structure(self):
        if len(self.swings) < 2:
            return
        
        last_trend = None  # 'bullish' or 'bearish'
        last_high: Optional[SwingPoint] = None
        last_low: Optional[SwingPoint] = None
        
        for sw in self.swings:
            if sw.kind == "high":
                if last_high is not None:
                    # check break of last_high by a later close
                    broke = self._broke_level(last_high.index, last_high.price, "up")
                    if broke:
                        kind = "CHoCH" if last_trend == "bearish" else "BOS"
                        self.structure.append(StructureBreak(
                            sw.index, last_high.price, kind, "bullish", self._ts(sw.index)
                        ))
                        last_trend = "bullish"
                last_high = sw
            else:
                if last_low is not None:
                    broke = self._broke_level(last_low.index, last_low.price, "down")
                    if broke:
                        kind = "CHoCH" if last_trend == "bullish" else "BOS"
                        self.structure.append(StructureBreak(
                            sw.index, last_low.price, kind, "bearish", self._ts(sw.index)
                        ))
                        last_trend = "bearish"
                last_low = sw
    
    def _broke_level(self, from_idx: int, level: float, direction: str) -> bool:
        seg = self.df.iloc[from_idx + 1:]
        if seg.empty:
            return False
        if direction == "up":
            return bool((seg["close"] > level).any())
        return bool((seg["close"] < level).any())
    
    # ---------- 3. Order Blocks ----------
    def detect_order_blocks(self):
        """
        Last opposing candle before an impulsive move that breaks structure.
        Simplified: look for last down candle before strong bullish move (bullish OB)
        and last up candle before strong bearish move (bearish OB).
        """
        closes = self.df["close"].values
        opens = self.df["open"].values
        highs = self.df["high"].values
        lows = self.df["low"].values
        
        atr = self._atr(14)
        
        for i in range(2, len(self.df) - 3):
            body = abs(closes[i] - opens[i])
            if body < atr[i] * 0.5:
                continue
            
            # Bullish OB: bearish candle followed by strong bullish displacement
            if closes[i] < opens[i]:
                move = closes[i + 2] - highs[i]
                if move > atr[i] * 1.5 and closes[i + 1] > highs[i] and closes[i + 2] > highs[i]:
                    mitigated = bool((self.df["low"].iloc[i + 3:] <= highs[i]).any())
                    self.order_blocks.append(OrderBlock(
                        i, float(highs[i]), float(lows[i]),
                        "bullish", mitigated, self._ts(i)
                    ))
            
            # Bearish OB: bullish candle followed by strong bearish displacement
            if closes[i] > opens[i]:
                move = lows[i] - closes[i + 2]
                if move > atr[i] * 1.5 and closes[i + 1] < lows[i] and closes[i + 2] < lows[i]:
                    mitigated = bool((self.df["high"].iloc[i + 3:] >= lows[i]).any())
                    self.order_blocks.append(OrderBlock(
                        i, float(highs[i]), float(lows[i]),
                        "bearish", mitigated, self._ts(i)
                    ))
    
    # ---------- 4. Fair Value Gaps ----------
    def detect_fvgs(self):
        highs = self.df["high"].values
        lows = self.df["low"].values
        
        for i in range(2, len(self.df)):
            # Bullish FVG: low[i] > high[i-2]
            if lows[i] > highs[i - 2]:
                top, bottom = float(lows[i]), float(highs[i - 2])
                filled = bool((self.df["low"].iloc[i + 1:] <= bottom).any())
                self.fvgs.append(FVG(i, top, bottom, "bullish", filled, self._ts(i)))
            # Bearish FVG: high[i] < low[i-2]
            if highs[i] < lows[i - 2]:
                top, bottom = float(lows[i - 2]), float(highs[i])
                filled = bool((self.df["high"].iloc[i + 1:] >= top).any())
                self.fvgs.append(FVG(i, top, bottom, "bearish", filled, self._ts(i)))
    
    # ---------- 5. Liquidity Zones ----------
    def detect_liquidity(self):
        """Equal highs / equal lows = liquidity pools."""
        tolerance = float(self.df["close"].std()) * 0.05
        
        highs = [s for s in self.swings if s.kind == "high"]
        lows = [s for s in self.swings if s.kind == "low"]
        
        for i in range(len(highs) - 1):
            for j in range(i + 1, len(highs)):
                if abs(highs[i].price - highs[j].price) < tolerance:
                    swept = bool((self.df["high"].iloc[highs[j].index + 1:] >
                                  max(highs[i].price, highs[j].price) * 1.0005).any())
                    self.liquidity.append(LiquidityZone(
                        highs[j].index, float(max(highs[i].price, highs[j].price)),
                        "buy_side", swept, self._ts(highs[j].index)
                    ))
                    break
        
        for i in range(len(lows) - 1):
            for j in range(i + 1, len(lows)):
                if abs(lows[i].price - lows[j].price) < tolerance:
                    swept = bool((self.df["low"].iloc[lows[j].index + 1:] <
                                  min(lows[i].price, lows[j].price) * 0.9995).any())
                    self.liquidity.append(LiquidityZone(
                        lows[j].index, float(min(lows[i].price, lows[j].price)),
                        "sell_side", swept, self._ts(lows[j].index)
                    ))
                    break
    
    # ---------- Helpers ----------
    def _atr(self, period: int = 14) -> np.ndarray:
        high = self.df["high"]
        low = self.df["low"]
        close = self.df["close"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        return tr.rolling(period).mean().bfill().values
    
    # ---------- 6. Signal generation ----------
    def generate_signal(self) -> dict:
        if not self.swings:
            return {"bias": "neutral", "confidence": 0, "reason": "Insufficient data"}
        
        last_close = float(self.df["close"].iloc[-1])
        atr = float(self._atr(14)[-1])
        
        # Recent structure bias
        recent_structure = self.structure[-3:] if self.structure else []
        bias = "neutral"
        if recent_structure:
            last = recent_structure[-1]
            bias = last.direction
        
        # Active (unmitigated) order blocks near price
        active_obs = [ob for ob in self.order_blocks if not ob.mitigated]
        nearby_obs = [ob for ob in active_obs
                      if abs(((ob.top + ob.bottom) / 2) - last_close) < atr * 3]
        
        # Unfilled FVGs near price
        unfilled_fvgs = [f for f in self.fvgs if not f.filled]
        nearby_fvgs = [f for f in unfilled_fvgs
                       if abs(((f.top + f.bottom) / 2) - last_close) < atr * 3]
        
        # Confidence score
        score = 0
        reasons = []
        if bias == "bullish":
            score += 30
            reasons.append("Recent bullish BOS/CHoCH")
        elif bias == "bearish":
            score += 30
            reasons.append("Recent bearish BOS/CHoCH")
        
        bullish_obs = [ob for ob in nearby_obs if ob.kind == "bullish"]
        bearish_obs = [ob for ob in nearby_obs if ob.kind == "bearish"]
        if bias == "bullish" and bullish_obs:
            score += 25
            reasons.append(f"{len(bullish_obs)} bullish OB(s) below price")
        if bias == "bearish" and bearish_obs:
            score += 25
            reasons.append(f"{len(bearish_obs)} bearish OB(s) above price")
        
        if bias == "bullish" and any(f.kind == "bullish" for f in nearby_fvgs):
            score += 20
            reasons.append("Bullish FVG nearby")
        if bias == "bearish" and any(f.kind == "bearish" for f in nearby_fvgs):
            score += 20
            reasons.append("Bearish FVG nearby")
        
        # Entry / SL / TP suggestion
        entry = last_close
        if bias == "bullish":
            sl_candidates = [ob.bottom for ob in bullish_obs] or [last_close - atr * 1.5]
            sl = min(sl_candidates)
            risk = entry - sl
            tp1 = entry + risk * 2
            tp2 = entry + risk * 3
        elif bias == "bearish":
            sl_candidates = [ob.top for ob in bearish_obs] or [last_close + atr * 1.5]
            sl = max(sl_candidates)
            risk = sl - entry
            tp1 = entry - risk * 2
            tp2 = entry - risk * 3
        else:
            sl = tp1 = tp2 = None
        
        return {
            "bias": bias,
            "confidence": min(score, 95),
            "reasons": reasons,
            "entry": entry,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "risk_reward": "1:2 / 1:3" if sl else None,
            "atr": atr,
        }
    
    def analyze(self) -> dict:
        self.find_swings()
        self.detect_structure()
        self.detect_order_blocks()
        self.detect_fvgs()
        self.detect_liquidity()
        
        return {
            "candles": self._candles(),
            "swings": [asdict(s) for s in self.swings],
            "structure": [asdict(s) for s in self.structure],
            "order_blocks": [asdict(o) for o in self.order_blocks],
            "fvgs": [asdict(f) for f in self.fvgs],
            "liquidity": [asdict(l) for l in self.liquidity],
            "signal": self.generate_signal(),
        }
    
    def _candles(self) -> list:
        out = []
        for i, row in self.df.iterrows():
            out.append({
                "time": self._ts(i),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            })
        return out
