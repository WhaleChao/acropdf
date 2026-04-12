# ~/Desktop/acropdf/rendering/cache.py
from collections import OrderedDict
from PyQt6.QtGui import QPixmap

class PixmapCache:
    def __init__(self, max_size: int = 30):
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._max_size = max_size

    def _key(self, page_num: int, zoom: float, rotation: int) -> str:
        return f"{page_num}_{zoom:.3f}_{rotation}"

    def get(self, page_num: int, zoom: float, rotation: int) -> QPixmap | None:
        k = self._key(page_num, zoom, rotation)
        if k in self._cache:
            self._cache.move_to_end(k)
            return self._cache[k]
        return None

    def put(self, page_num: int, zoom: float, rotation: int, pm: QPixmap):
        k = self._key(page_num, zoom, rotation)
        self._cache[k] = pm
        self._cache.move_to_end(k)
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def invalidate(self, page_num: int | None = None):
        if page_num is None:
            self._cache.clear()
        else:
            keys = [k for k in self._cache if k.startswith(f"{page_num}_")]
            for k in keys:
                del self._cache[k]
