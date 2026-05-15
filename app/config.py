# ~/Desktop/acropdf/app/config.py
from PyQt6.QtCore import QSettings
from app.constants import LayoutMode, DEFAULT_ZOOM

class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._settings = QSettings("YourOffice", "AcroPDF")
        return cls._instance

    def get(self, key: str, default=None):
        return self._settings.value(key, default)

    def set(self, key: str, value):
        self._settings.setValue(key, value)
        self._settings.sync()

    @property
    def recent_files(self) -> list[str]:
        return self._settings.value("recent_files", []) or []

    def add_recent_file(self, path: str):
        files = self.recent_files
        if path in files:
            files.remove(path)
        files.insert(0, path)
        from app.constants import MAX_RECENT_FILES
        self._settings.setValue("recent_files", files[:MAX_RECENT_FILES])
        self._settings.sync()

    @property
    def layout_mode(self) -> LayoutMode:
        v = self._settings.value("layout_mode", int(LayoutMode.CONTINUOUS))
        return LayoutMode(int(v))

    @layout_mode.setter
    def layout_mode(self, mode: LayoutMode):
        self._settings.setValue("layout_mode", int(mode))

    @property
    def theme(self) -> str:
        return self._settings.value("theme", "light") or "light"

    @theme.setter
    def theme(self, t: str):
        self._settings.setValue("theme", t)
        self._settings.sync()

    @property
    def show_rulers(self) -> bool:
        return self._settings.value("show_rulers", False) in (True, "true", "True")

    @show_rulers.setter
    def show_rulers(self, v: bool):
        self._settings.setValue("show_rulers", v)
        self._settings.sync()

    @property
    def show_grid(self) -> bool:
        return self._settings.value("show_grid", False) in (True, "true", "True")

    @show_grid.setter
    def show_grid(self, v: bool):
        self._settings.setValue("show_grid", v)
        self._settings.sync()

    @property
    def grid_spacing(self) -> int:
        try:
            return int(self._settings.value("grid_spacing", 20))
        except (ValueError, TypeError):
            return 20

    @grid_spacing.setter
    def grid_spacing(self, v: int):
        self._settings.setValue("grid_spacing", v)
        self._settings.sync()
