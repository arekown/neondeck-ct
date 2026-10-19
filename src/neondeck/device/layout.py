"""Belegung und Pixelmasse des Loupedeck CT (gemessen am Geraet).

Einzige Quelle fuer die Pixelmasse der Displays; ``render`` und der Editor importieren sie.
"""
from dataclasses import dataclass
from enum import Enum, StrEnum

# --- Pixelmasse --------------------------------------------------------------------------
STRIP_WIDTH = 60       # linke/rechte Leiste
CENTER_WIDTH = 360     # mittleres Display (4 × 3 Felder)
DISPLAY_HEIGHT = 270   # Hoehe der drei oberen Displays
FIELD_SIZE = 90        # ein Touch-Feld (und ein Leisten-Abschnitt)
WHEEL_SIZE = 240       # rundes Raddisplay (quadratisch)
SURFACE_WIDTH = 2 * STRIP_WIDTH + CENTER_WIDTH  # links + Mitte + rechts nebeneinander
RIGHT_STRIP_X = STRIP_WIDTH + CENTER_WIDTH      # rechte Leiste auf dieser Flaeche


class Display(Enum):
    LEFT = ("L", STRIP_WIDTH, DISPLAY_HEIGHT, False)
    CENTER = ("A", CENTER_WIDTH, DISPLAY_HEIGHT, False)
    RIGHT = ("R", STRIP_WIDTH, DISPLAY_HEIGHT, False)
    WHEEL = ("W", WHEEL_SIZE, WHEEL_SIZE, True)

    def __init__(self, id: str, width: int, height: int, big_endian: bool) -> None:
        self.id = id
        self.width = width
        self.height = height
        self.big_endian = big_endian


class ControlKind(StrEnum):
    """Art eines Bedienelements (``ControlRef.kind``); gleich dem Text, z. B. ``"knob"``."""
    ROUND = "round"
    SQUARE = "square"
    KNOB = "knob"
    TOUCH = "touch"
    STRIP = "strip"
    WHEEL = "wheel"


@dataclass(frozen=True)
class ControlRef:
    kind: str  # ``ControlKind`` (StrEnum, also auch als Text vergleichbar)
    index: int


ROUND_FIRST, ROUND_LAST = 7, 14
ROUND_CODES = range(ROUND_FIRST, ROUND_LAST + 1)  # Tastencodes der runden Tasten (mit LED)
KNOB_FIRST, KNOB_LAST = 1, 6
# Eckige Tasten, zeilenweise je Block: oben-links, oben-rechts, Mitte-links, ...
# Reihenfolge = Index am Geraet (``ControlRef("square", i)``).
SQUARE_CODES = (15, 18, 16, 19, 17, 20, 21, 24, 22, 25, 23, 26)
SQUARE_KEY_CODES = tuple(sorted(SQUARE_CODES))  # aufsteigend: Reihenfolge im Profil-JSON
_SQUARE_INDEX = {code: i for i, code in enumerate(SQUARE_CODES)}
TOUCH_BUTTONS = 12  # Felder im mittleren Display
ENCODERS = 6        # Drehregler

# Bedienelemente und Anzahl (Index ab 0); das Rad hat keinen Index.
CONTROL_COUNTS = {"touch": TOUCH_BUTTONS, "round": len(ROUND_CODES),
                  "square": len(SQUARE_CODES), "knob": ENCODERS, "strip": 6, "wheel": 1}


def all_controls() -> list[ControlRef]:
    """Alle Bedienelemente: Felder, Leisten, Regler, runde, eckige Tasten, Rad."""
    return [ControlRef(kind, i)
            for kind in ("touch", "strip", "knob", "round", "square", "wheel")
            for i in range(CONTROL_COUNTS[kind])]


def control_for_button(code: int) -> ControlRef:
    if ROUND_FIRST <= code <= ROUND_LAST:
        return ControlRef("round", code - ROUND_FIRST)
    if code in _SQUARE_INDEX:
        return ControlRef("square", _SQUARE_INDEX[code])
    if KNOB_FIRST <= code <= KNOB_LAST:
        return ControlRef("knob", code - KNOB_FIRST)
    raise KeyError(code)


def touch_target(x: int, y: int) -> ControlRef:
    row = max(0, min(2, y // FIELD_SIZE))
    if x < STRIP_WIDTH:
        return ControlRef("strip", row)
    if x >= RIGHT_STRIP_X:
        return ControlRef("strip", 3 + row)
    col = (x - STRIP_WIDTH) // FIELD_SIZE
    return ControlRef("touch", row * 4 + col)
