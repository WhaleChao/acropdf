# ~/Desktop/acropdf/rendering/cache.py
from collections import OrderedDict
from PyQt6.QtGui import QPixmap

class PixmapCache:
    def __init__(self, max_size: int = 12, max_bytes: int = 96 * 1024 * 1024):
        self._cache: OrderedDict[str, QPixmap] = OrderedDict()
        self._max_size = max_size
        self._max_bytes = max_bytes
        self._bytes = 0

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
        if k in self._cache:
            self._bytes -= self._pixmap_bytes(self._cache[k])
        self._cache[k] = pm
        self._bytes += self._pixmap_bytes(pm)
        self._cache.move_to_end(k)
        while len(self._cache) > self._max_size or self._bytes > self._max_bytes:
            _, old = self._cache.popitem(last=False)
            self._bytes -= self._pixmap_bytes(old)

    def invalidate(self, page_num: int | None = None):
        if page_num is None:
            self._cache.clear()
            self._bytes = 0
        else:
            keys = [k for k in self._cache if k.startswith(f"{page_num}_")]
            for k in keys:
                self._bytes -= self._pixmap_bytes(self._cache[k])
                del self._cache[k]

    @staticmethod
    def _pixmap_bytes(pm: QPixmap) -> int:
        depth = max(pm.depth(), 1)
        return pm.width() * pm.height() * depth // 8
