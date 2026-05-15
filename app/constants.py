# ~/Desktop/acropdf/app/constants.py
from enum import IntEnum, auto

class LayoutMode(IntEnum):
    SINGLE = auto()
    DOUBLE = auto()
    CONTINUOUS = auto()

class ToolMode(IntEnum):
    HAND = auto()
    SELECT = auto()
    ZOOM = auto()
    HIGHLIGHT = auto()
    UNDERLINE = auto()
    STRIKEOUT = auto()
    FREEHAND = auto()
    ERASER = auto()
    STICKY_NOTE = auto()
    TEXT_BOX = auto()
    CALLOUT = auto()
    STAMP = auto()
    SHAPE_RECT = auto()
    SHAPE_CIRCLE = auto()
    SHAPE_LINE = auto()
    SHAPE_ARROW = auto()
    SHAPE_POLYGON = auto()
    MEASURE_DIST = auto()
    MEASURE_AREA = auto()
    REDACT = auto()
    CROP = auto()
    LINK = auto()
    FORM_FIELD = auto()
    SIGNATURE = auto()
    TEXT_EDIT = auto()
    IMAGE_EDIT = auto()
    CUSTOM_STAMP = auto()
    FORM_DESIGNER = auto()
    TEXT_REFLOW = auto()

ZOOM_LEVELS = [0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0]
DEFAULT_ZOOM = 1.0
THUMBNAIL_SIZE = (120, 160)
RENDER_DPI = 150
THUMBNAIL_DPI = 72
MAX_RECENT_FILES = 10
