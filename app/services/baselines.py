# app/services/baselines.py
import json
import os
import datetime as dt
from typing import Dict

DEFAULT_FILE = os.path.join(os.path.dirname(__file__), "baselines.json")

class DailyBaselines:
    """
    Keeps the first-seen price per symbol for the current day.

    JSON schema:
    {
      "2025-08-31": {"USD/IRR": 930000, "Gold24": 32100000},
      "2025-09-01": { ... }
    }
    """
    def __init__(self, path: str = DEFAULT_FILE, keep_days: int = 7):
        self.path = path
        self.keep_days = keep_days
        self.data: Dict[str, Dict[str, float]] = {}
        self._load()

    @staticmethod
    def _today_str() -> str:
        # اگر تایم‌زون خاصی دارید همینجا اعمال کنید
        return dt.date.today().isoformat()

    def _load(self) -> None:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f) or {}
            except Exception:
                self.data = {}
        else:
            self.data = {}

    def _save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception:
            # نگذاریم شکست ذخیره، کل برنامه را خراب کند
            pass

    def reset_if_new_day(self) -> None:
        """Housekeeping: روزهای خیلی قدیمی را حذف می‌کند (اختیاری اما مفید)."""
        if not self.data:
            return
        try:
            all_days = sorted(self.data.keys())
            if len(all_days) > self.keep_days:
                for d in all_days[:-self.keep_days]:
                    self.data.pop(d, None)
                self._save()
        except Exception:
            pass

    def get_or_set(self, symbol: str, price: float) -> float:
        """
        If today's baseline for symbol exists, return it; if not, set to 'price' and return it.
        """
        day = self._today_str()
        day_map = self.data.setdefault(day, {})
        if symbol not in day_map:
            day_map[symbol] = float(price)
            self._save()
        return float(day_map[symbol])

    def clear_today(self) -> None:
        """Baselineهای امروز را پاک می‌کند (درصورت نیاز به ریست دستی)."""
        day = self._today_str()
        if day in self.data:
            self.data[day] = {}
            self._save()
