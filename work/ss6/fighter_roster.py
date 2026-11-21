"""Read src/fighter_roster.hpp, the single native list of admitted fighters.

Validators derive their per-fighter cases from this list and from the
pinned original tables instead of keeping their own copies.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_ROW = re.compile(r'\{(\d+),"([A-Z]+)",FighterPort::(\w+),\{(.*?)\},\{(-?\d+),(-?\d+)\}\}')

def _load():
    text = (ROOT/'src/fighter_roster.hpp').read_text()
    out = {}
    for m in _ROW.finditer(text):
        ranges = [(int(a), int(b)) for a, b in re.findall(r'\{(\d+),(\d+)\}', m.group(4))]
        out[int(m.group(1))] = dict(name=m.group(2), port=m.group(3), held=ranges,
                                     zero_end=[int(x) for x in m.group(5, 6) if int(x) >= 0])
    assert out, 'No fighter descriptors found'
    return out

FIGHTERS = _load()
# CharacterSelect::roster: the fully unlocked grid (column-major, eight columns of six rows).
GRID = (31,30,22,0,33,32,34,35,37,38,36,39,1,3,7,6,4,5,24,23,25,
        12,14,15,2,8,9,10,16,17,19,29,28,18,20,21,42,11,27,13,26,53,
        41,44,45,47,46,40)
COLUMNS = len(GRID)//6
# Admitted fighters the console VS selection can produce (grid cells).
# Kuroko (48) has no cell: Start switches a seat's grid to his face (12db80).
KUROKO = 48
PLAYABLE = tuple(c for c in FIGHTERS if c in GRID or c == KUROKO)
# 148df0 runs a selected id with another fighter's logic (Purple Nakoruru 42 -> Nakoruru 1).
LOGIC = {42: 1}
# Grid ids whose logic is ported; their own resource banks (graphics, voices) are packaged.
SELECTABLE = tuple(c for c in (*GRID, KUROKO) if c != 53 and LOGIC.get(c, c) in FIGHTERS)
# Admitted fighters whose banks are packaged: the selectable ones plus fighters without a grid cell
# (Makai Gaoh 43, an arcade boss), which only the debug substitution fields.
PACKAGED = SELECTABLE + tuple(c for c in FIGHTERS if c not in SELECTABLE)
SCRIPT_STUBS = tuple(c for c, d in FIGHTERS.items() if d['port'] == 'ScriptStubs')
def cursor_path(character, start=2):
    """Shortest column/row moves from the initial cell to the fighter's cell:
    ('back'|'forward'|'up'|'down', count). Columns wrap over COLUMNS, rows over 6."""
    target = GRID.index(character)
    dc = (target//6 - start//6) % COLUMNS
    cols = ('forward', dc) if dc <= COLUMNS//2 else ('back', COLUMNS - dc)
    dr = (target % 6 - start % 6) % 6
    rows = ('down', dr) if dr <= 3 else ('up', 6 - dr)
    return cols, rows
