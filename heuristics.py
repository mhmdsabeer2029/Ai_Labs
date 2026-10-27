"""
heuristics.py  --  Heuristic functions for A* on the 8-puzzle.

A heuristic h(state) ESTIMATES the number of moves left to reach the goal.
A* orders its frontier by f(n) = g(n) + h(n), where g is the path cost so far.

Both heuristics below sum a per-tile distance over tiles 1..8.
THE BLANK (0) IS IGNORED (Professor's Hint). Counting it would overestimate: one move can fix
at most one tile, so including the blank breaks admissibility.

Admissible  : h(n) <= true cost from n to the goal   (A* tree search stays optimal)
Consistent  : h(n) <= 1 + h(n') for every move n -> n'  (A* graph search with an
              explored set stays optimal; every move costs 1)

Both heuristics here are admissible AND consistent. Manhattan is the tighter one
(Manhattan >= Euclidean for every state), so A* with Manhattan expands fewer or
equal nodes. This is what the report should say about "which is more admissible":
both are admissible, Manhattan DOMINATES Euclidean, so it is the more informed one << (Note to self)

Run `python heuristics.py` for a self-test and a brute-force verification over
all 181,440 reachable states.
"""

import math
from collections import deque

from puzzles import GOAL, neighbors, index_to_rc

# --------------------------------------------------------------------------
# Precomputed goal position of every tile: {tile: (row, col)}
# Built from GOAL, so it stays correct even if GOAL is changed later.
# --------------------------------------------------------------------------
GOAL_POS = {tile: index_to_rc(i) for i, tile in enumerate(GOAL)}


def manhattan(state):
    """Sum over tiles of |row - goal_row| + |col - goal_col|. Returns an int."""
    total = 0
    for index, tile in enumerate(state):
        if tile == 0:                       # skip the blank
            continue
        row, col = index_to_rc(index)
        goal_row, goal_col = GOAL_POS[tile]
        total += abs(row - goal_row) + abs(col - goal_col)
    return total


def euclidean(state):
    """Sum over tiles of sqrt((row - goal_row)^2 + (col - goal_col)^2). Returns a float."""
    total = 0.0
    for index, tile in enumerate(state):
        if tile == 0:                       # skip the blank
            continue
        row, col = index_to_rc(index)
        goal_row, goal_col = GOAL_POS[tile]
        total += math.hypot(row - goal_row, col - goal_col)
    return total


# Name -> function, so the search/main code can pick a heuristic by string.
HEURISTICS = {
    "manhattan": manhattan,
    "euclidean": euclidean,
}


# --------------------------------------------------------------------------
# Verification (for Our report): compares each heuristic to the TRUE cost.
# Moves are reversible, so a BFS outward from GOAL gives the exact distance
# from every reachable state to the goal.
# --------------------------------------------------------------------------
def true_costs():
    """{state: exact optimal cost to GOAL} for all 181,440 solvable states."""
    dist = {GOAL: 0}
    queue = deque([GOAL])
    while queue:
        state = queue.popleft()
        for _, nxt in neighbors(state):
            if nxt not in dist:
                dist[nxt] = dist[state] + 1
                queue.append(nxt)
    return dist


def verify():
    EPS = 1e-9                              # tolerance for float rounding (Barakat Dr Tourki)
    dist = true_costs()
    print(f"States checked: {len(dist):,}\n")
    print(f"{'heuristic':<11}{'admissible':<12}{'consistent':<12}{'avg h':<9}{'avg true cost'}")
    avg_true = sum(dist.values()) / len(dist)
    for name, h in HEURISTICS.items():
        admissible = all(h(s) <= d + EPS for s, d in dist.items())
        consistent = all(h(s) <= 1 + h(n) + EPS
                         for s in dist for _, n in neighbors(s))
        avg_h = sum(h(s) for s in dist) / len(dist)
        print(f"{name:<11}{str(admissible):<12}{str(consistent):<12}{avg_h:<9.3f}{avg_true:.3f}")
    dominates = all(manhattan(s) >= euclidean(s) - EPS for s in dist)
    print(f"\nManhattan >= Euclidean on every state: {dominates}")


# --------------------------------------------------------------------------
# Quick self-test:  python heuristics.py
# --------------------------------------------------------------------------
if __name__ == "__main__":
    example = (1, 2, 5, 3, 4, 0, 6, 7, 8)   # example from the assignment PDF (3 moves)
    assert manhattan(GOAL) == 0 and euclidean(GOAL) == 0
    assert manhattan(example) == 3
    assert abs(euclidean(example) - 3.0) < 1e-9
    print("Self-test passed: h(example) = 3 for both (true cost = 3)\n")
    verify()