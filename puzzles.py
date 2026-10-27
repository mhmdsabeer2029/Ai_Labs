"""
puzzle.py  --  The 8-puzzle "world".

This file knows everything about the PROBLEM and nothing about SEARCH 
The search algorithms (BFS, DFS, IDS, A*) will only talk to the puzzle
through the functions defined here:

    neighbors(state)   -> what states can I reach from here?
    is_goal(state)     -> am I done?
    is_solvable(state) -> is it even possible to finish from here?

STATE REPRESENTATION
--------------------
A state is a tuple of 9 integers read row by row, 0 = the blank:

        1 2 5
        3 4 _      ->   (1, 2, 5, 3, 4, 0, 6, 7, 8)
        6 7 8

Why a tuple and not a list? <<--(Hasses will be asked lol)
  * Tuples are immutable, so a state can never be changed by accident.
  * Tuples are hashable, so they can go inside a set / dict key. Search
    needs this to remember which states it has already seen.
"""

import random

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
SIZE = 3                                   # board is SIZE x SIZE
GOAL = (0, 1, 2, 3, 4, 5, 6, 7, 8)         # goal required by the assignment

# Each move describes how the BLANK moves, as (row_change, col_change).
# This matches the assignment's wording: "the blank space may be swapped
# with a component in one of the four directions Up/Down/Left/Right".
#
# The ORDER matters: it is the order in which neighbors are generated, so it
# affects which path BFS/DFS find first. The assignment lists them as
# Up, Down, Left, Right, so we keep that order (and document it in the report).
MOVES = (
    ("Up",    (-1,  0)),
    ("Down",  ( 1,  0)),
    ("Left",  ( 0, -1)),
    ("Right", ( 0,  1)),
)


# --------------------------------------------------------------------------
# Index <-> (row, col) helpers
# --------------------------------------------------------------------------
def index_to_rc(index):
    """Flat index 0..8  ->  (row, col).   e.g. 5 -> (1, 2)"""
    return divmod(index, SIZE)       #divmod(dividend, divisor) return quotient and remainder


def rc_to_index(row, col):
    """(row, col)  ->  flat index 0..8.   e.g. (1, 2) -> 5"""
    return row * SIZE + col


# --------------------------------------------------------------------------
# Core problem definition
# --------------------------------------------------------------------------
def is_goal(state):
    """True if the board is exactly the goal configuration."""
    return state == GOAL


def neighbors(state):
    """
    Return every legal move from `state` as a list of (move_name, new_state).

    How it works:
      1. Find where the blank (0) is.
      2. For each direction, compute where the blank WOULD land.
      3. If that spot is off the board, the move is illegal -> skip it.
      4. Otherwise swap the blank with the tile there -> a new state.

    A corner blank has 2 moves, an edge blank has 3, the center has 4.
    The input state is never modified; each neighbor is a brand-new tuple.
    """
    blank = state.index(0)                       # where is the blank?
    row, col = index_to_rc(blank)

    result = []
    for name, (d_row, d_col) in MOVES:
        new_row, new_col = row + d_row, col + d_col

        # Boundary check: the move is legal only if we stay on the board
        if not (0 <= new_row < SIZE and 0 <= new_col < SIZE):
            continue

        target = rc_to_index(new_row, new_col)   # tile we will swap with

        # Tuples are immutable, so copy into a list, swap, convert back.
        board = list(state)
        board[blank], board[target] = board[target], board[blank]
        result.append((name, tuple(board)))

    return result


# --------------------------------------------------------------------------
# Solvability
# --------------------------------------------------------------------------
def count_inversions(state):
    """
    An inversion is a pair of tiles (a, b) where a appears BEFORE b when the
    board is read row by row, but a > b.  The blank is ignored.

    Example: (1, 2, 5, 3, 4, 0, 6, 7, 8) -> tiles 1,2,5,3,4,6,7,8
             5 is before 3 and 4 -> 2 inversions.
    """
    tiles = [t for t in state if t != 0]         # drop the blank
    inversions = 0
    for i in range(len(tiles)):
        for j in range(i + 1, len(tiles)):
            if tiles[i] > tiles[j]:
                inversions += 1
    return inversions


def is_solvable(state):
    """
    Only HALF of all 9!... arrangements can reach the goal =181,440 states

    Why: sliding the blank left/right never changes the tile order, and
    sliding it up/down moves one tile past exactly two others (an even
    change). So the PARITY of the inversion count can never change.
    The goal has 0 inversions (even), therefore on a 3x3 board:

        solvable  <=>  inversion count is even
    """
    return count_inversions(state) % 2 == 0


# --------------------------------------------------------------------------
# Creating / validating states
# --------------------------------------------------------------------------
def is_valid(state):
    """True if state is a tuple holding each of 0..8 exactly once."""
    return (isinstance(state, tuple)
            and len(state) == SIZE * SIZE
            and sorted(state) == tuple(list(range(SIZE * SIZE))))


def parse_state(text):
    """
    Turn user input like "1,2,5,3,4,0,6,7,8" (or with spaces) into a state.
    Raises ValueError with a clear message if the input is bad.
    """
    cleaned = text.replace(",", " ").split()
    try:
        state = tuple(int(x) for x in cleaned)
    except ValueError:
        raise ValueError("State must contain only integers, e.g. 1,2,5,3,4,0,6,7,8")
    if not is_valid(state):
        raise ValueError("State must use each number 0-8 exactly once.")
    return state


def random_state(solvable=True):
    """
    Shuffle the tiles until we get a board with the requested solvability.
    About half of shuffles are solvable, so this loop ends almost instantly.
    """
    tiles = list(GOAL)
    while True:
        random.shuffle(tiles)
        state = tuple(tiles)
        if is_solvable(state) == solvable:
            return state


# --------------------------------------------------------------------------
# Display (used for the "traceable" console output the assignment asks for)
# --------------------------------------------------------------------------
def format_board(state):
    """Return the board as a 3-line string. The blank is drawn as '_'."""
    lines = []
    for row in range(SIZE):
        cells = state[row * SIZE:(row + 1) * SIZE]
        lines.append(" ".join("_" if c == 0 else str(c) for c in cells))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Quick self-test:  python puzzle.py
# --------------------------------------------------------------------------
if __name__ == "__main__":
    start = parse_state("1,2,5,3,4,0,6,7,8")      # example from the assignment PDF
    print("Start state:")
    print(format_board(start))
    print("\nLegal moves from here:")
    for move, nxt in neighbors(start):
        print(f"\n{move}:")
        print(format_board(nxt))
    print("\nInversions:", count_inversions(start), "| solvable:", is_solvable(start))