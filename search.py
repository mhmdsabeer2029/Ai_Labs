"""
search.py  --  BFS, DFS, Iterative-Deepening DFS and A* for the 8-puzzle.

The algorithms talk to the puzzle ONLY through puzzles.py (neighbors, is_goal)
and, for A*, through a heuristic function passed in from heuristics.py.

EVERY algorithm returns the same dict, so main.py can print/compare them alike:

    {
      "algorithm"      : str,
      "solved"         : bool,
      "path"           : [(move, state), ...]  first item is (None, start); None if unsolved
      "cost"           : int   number of moves in the path (None if unsolved)
      "nodes_expanded" : int   states popped from the frontier whose neighbors were generated
      "max_depth"      : int   deepest tree level reached by the search
      "time"           : float seconds (wall clock, perf_counter)
    }

CONVENTIONS (mention these in the report)
  * Neighbor order is Up, Down, Left, Right (from puzzles.MOVES).
  * Goal test happens when a node is POPPED, not when generated. The goal node
    itself is not counted as "expanded".
  * All four algorithms are GRAPH searches: a state is never expanded twice
    (IDS: never re-entered at an equal-or-deeper level within one iteration).
  * Ties in A* are broken first-in-first-out (a counter), so runs are repeatable.
"""

import heapq
import itertools
import time
from collections import deque

from puzzles import neighbors, is_goal


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------
def _build_path(parent, state):
    """
    Walk parent pointers back to the root.
    parent maps state -> (parent_state, move); the root maps to (None, None).
    Returns [(None, start), (move1, s1), ..., (moveN, goal)].
    """
    path = []
    while state is not None:
        prev, move = parent[state]
        path.append((move, state))
        state = prev
    path.reverse()
    return path


def _result(name, path, expanded, max_depth, t0, **extra):
    """Pack the standard result dict (plus any algorithm-specific extras)."""
    out = {
        "algorithm": name,
        "solved": path is not None,
        "path": path,
        "cost": len(path) - 1 if path is not None else None,
        "nodes_expanded": expanded,
        "max_depth": max_depth,
        "time": time.perf_counter() - t0,
    }
    out.update(extra)
    return out


# --------------------------------------------------------------------------
# 1. Breadth-First Search   (frontier = FIFO queue)
# --------------------------------------------------------------------------
def bfs(start):
    """
    Expands the shallowest node first, so the first time it pops the goal the
    path is the SHORTEST one (all moves cost 1). Complete and optimal.
    `parent` doubles as the visited set (a state is marked when first generated).
    """
    t0 = time.perf_counter()
    parent = {start: (None, None)}
    depth = {start: 0}
    frontier = deque([start])
    expanded = 0
    max_depth = 0

    while frontier:
        state = frontier.popleft()
        d = depth[state]
        max_depth = max(max_depth, d)

        if is_goal(state):
            return _result("BFS", _build_path(parent, state), expanded, max_depth, t0)

        expanded += 1
        for move, nxt in neighbors(state):
            if nxt not in parent:
                parent[nxt] = (state, move)
                depth[nxt] = d + 1
                frontier.append(nxt)

    return _result("BFS", None, expanded, max_depth, t0)


# --------------------------------------------------------------------------
# 2. Depth-First Search   (frontier = LIFO stack)
# --------------------------------------------------------------------------
def dfs(start):
    """
    Always goes deepest first. Complete here because the explored set makes the
    search finite, but NOT optimal: expect very long paths (often thousands of
    moves). A state is marked explored when POPPED, so the stack may briefly hold
    duplicates; each stack entry remembers its own parent and move.
    Neighbors are pushed in reverse so Up is tried first.
    """
    t0 = time.perf_counter()
    explored = {}                                   # state -> (parent, move)
    stack = [(start, None, None, 0)]                # (state, parent, move, depth)
    expanded = 0
    max_depth = 0

    while stack:
        state, prev, move, d = stack.pop()
        if state in explored:
            continue
        explored[state] = (prev, move)
        max_depth = max(max_depth, d)

        if is_goal(state):
            return _result("DFS", _build_path(explored, state), expanded, max_depth, t0)

        expanded += 1
        for mv, nxt in reversed(neighbors(state)):
            if nxt not in explored:
                stack.append((nxt, state, mv, d + 1))

    return _result("DFS", None, expanded, max_depth, t0)


# --------------------------------------------------------------------------
# 3. Iterative-Deepening DFS
# --------------------------------------------------------------------------
def ids(start, max_limit=31):
    """
    Runs depth-limited DFS with limit = 0, 1, 2, ... until the goal is found.
    Optimal like BFS, but memory is only O(depth). Upper layers are re-expanded
    every iteration, so nodes_expanded counts ALL iterations together.

    Cycle control: within one iteration a state is entered only if it has not
    been seen at an equal or shallower depth (`best`). A plain "explored" set
    would be WRONG here: a state first reached too deep could block a shallower
    route to it and make the search miss the solution.

    max_limit=31 is the longest optimal solution of any 8-puzzle, so solvable
    states are always found and unsolvable ones terminate instead of looping.
    """
    t0 = time.perf_counter()
    expanded = 0
    max_depth = 0

    def dls(state, move, depth, limit, best, path):
        nonlocal expanded, max_depth
        path.append((move, state))
        max_depth = max(max_depth, depth)

        if is_goal(state):
            return True

        if depth < limit:                           # at the limit: cut off, don't expand
            expanded += 1
            for mv, nxt in neighbors(state):
                if best.get(nxt, float("inf")) > depth + 1:
                    best[nxt] = depth + 1
                    if dls(nxt, mv, depth + 1, limit, best, path):
                        return True

        path.pop()
        return False

    for limit in range(max_limit + 1):
        path = []
        if dls(start, None, 0, limit, {start: 0}, path):
            return _result("IDS", path, expanded, max_depth, t0, iterations=limit + 1)

    return _result("IDS", None, expanded, max_depth, t0, iterations=max_limit + 1)


# --------------------------------------------------------------------------
# 4. A*   (frontier = priority queue ordered by f = g + h)
# --------------------------------------------------------------------------
def astar(start, h, name="A*"):
    """
    h is a heuristic function state -> number (see heuristics.py).
    Optimal when h is admissible; because Manhattan and Euclidean are also
    consistent, closing a state on its first pop is safe.

    Heap entries are (f, tie_counter, g, state); the counter keeps ties FIFO
    and stops Python from ever comparing two states.
    A state can be pushed more than once (cheaper route found later); stale
    entries are skipped when popped because the state is already closed.
    """
    t0 = time.perf_counter()
    counter = itertools.count()
    parent = {start: (None, None)}
    g_best = {start: 0}
    heap = [(h(start), next(counter), 0, start)]
    closed = set()
    expanded = 0
    max_depth = 0

    while heap:
        _, _, g, state = heapq.heappop(heap)
        if state in closed:
            continue
        closed.add(state)
        max_depth = max(max_depth, g)

        if is_goal(state):
            return _result(name, _build_path(parent, state), expanded, max_depth, t0)

        expanded += 1
        for move, nxt in neighbors(state):
            if nxt in closed:
                continue
            new_g = g + 1
            if new_g < g_best.get(nxt, float("inf")):
                g_best[nxt] = new_g
                parent[nxt] = (state, move)
                heapq.heappush(heap, (new_g + h(nxt), next(counter), new_g, nxt))

    return _result(name, None, expanded, max_depth, t0)


# --------------------------------------------------------------------------
# Quick self-test:  python search.py
# --------------------------------------------------------------------------
def validate_path(start, path):
    """Replay a path move by move; True if every step is legal and it ends at GOAL."""
    if path is None or path[0] != (None, start):
        return False
    for (_, prev), (move, cur) in zip(path, path[1:]):
        if (move, cur) not in neighbors(prev):
            return False
    return is_goal(path[-1][1])


if __name__ == "__main__":
    from puzzles import parse_state
    from heuristics import manhattan, euclidean

    start = parse_state("1,2,5,3,4,0,6,7,8")          # example from the assignment PDF
    runs = [
        bfs(start),
        dfs(start),
        ids(start),
        astar(start, manhattan, "A* (Manhattan)"),
        astar(start, euclidean, "A* (Euclidean)"),
    ]
    print(f"{'algorithm':<16}{'cost':>6}{'expanded':>10}{'max depth':>11}{'time (s)':>11}  valid")
    for r in runs:
        ok = validate_path(start, r["path"])
        print(f"{r['algorithm']:<16}{r['cost']:>6}{r['nodes_expanded']:>10}"
              f"{r['max_depth']:>11}{r['time']:>11.5f}  {ok}")