"""
main.py  --  Entry point of the 8-puzzle solver (the "glue" file). (NOT search.py lol)

This file contains NO search logic and NO puzzle rules. It only:
    1. picks a start state (random, or given by the user)
    2. refuses unsolvable boards (puzzles.is_solvable)
    3. runs the chosen algorithms from search.py
    4. shows the results in a TRACEABLE format (every step drawn as a board)
    5. prints a comparison table + the Manhattan-vs-Euclidean comparison

USAGE
-----
    python main.py                          random solvable start, all algorithms
    python main.py --seed 7                 same random start every time (for the report)
    python main.py --state 1,2,5,3,4,0,6,7,8
    python main.py --algo bfs astar-manhattan
    python main.py --trace full > run.txt   print EVERY step of EVERY path to a file
    python main.py --trace none             metrics + tables only
    python main.py --gui                    hand the results to gui.py (when it exists)

WHY A TRACE MODE?
    DFS finds very long paths (thousands of moves on hard boards). Drawing every
    board of those would flood the terminal, so by default long paths show their
    first and last boards and say how many were skipped.  --trace full prints
    everything, which is what the assignment's "every step printed" asks for.
"""

import argparse
import random
import sys
import textwrap

from puzzles import (GOAL, SIZE, parse_state, random_state, is_solvable,
                     count_inversions)
from heuristics import HEURISTICS
from search import bfs, dfs, ids, astar, validate_path

# --------------------------------------------------------------------------
# Algorithm registry:  key (used on the command line) -> function(start) -> result
# --------------------------------------------------------------------------
def _astar_runner(h, label):
    """Wrap astar() so it has the same one-argument shape as bfs/dfs/ids."""
    def run(start):
        return astar(start, h, label)
    return run


ALGORITHMS = {"bfs": bfs, "dfs": dfs, "ids": ids}
for _name, _h in HEURISTICS.items():            # adds astar-manhattan, astar-euclidean
    ALGORITHMS[f"astar-{_name}"] = _astar_runner(_h, f"A* ({_name.capitalize()})")

# --------------------------------------------------------------------------
# Drawing boards
# --------------------------------------------------------------------------
BOARD_W = 4 * SIZE + 1          # width of one drawn board (13 for 3x3)
PER_ROW = 5                     # boards per line: 5*13 + 4*3 gaps = 77 columns
AUTO_FULL_LIMIT = 30            # --trace auto prints every step up to this many moves
TRACE_EDGE = 10                 # when eliding: boards kept at each end


def board_lines(state):
    """
    One board as a list of text lines:

        ┌───┬───┬───┐
        │ 1 │ 2 │ 5 │
        ├───┼───┼───┤
        │ 3 │ 4 │   │      (the blank is drawn empty)
        ├───┼───┼───┤
        │ 6 │ 7 │ 8 │
        └───┴───┴───┘
    """
    seg = "───"
    lines = ["┌" + "┬".join([seg] * SIZE) + "┐"]
    for r in range(SIZE):
        row = state[r * SIZE:(r + 1) * SIZE]
        cells = " │ ".join(" " if t == 0 else str(t) for t in row)
        lines.append("│ " + cells + " │")
        lines.append(("├" + "┼".join([seg] * SIZE) + "┤") if r < SIZE - 1
                     else ("└" + "┴".join([seg] * SIZE) + "┘"))
    return lines


def print_board_row(entries):
    """
    Draw several boards side by side, with an arrow between neighbours.
    entries = [(label, state), ...]   (at most PER_ROW of them)
    """
    blocks = [board_lines(state) for _, state in entries]
    middle = len(blocks[0]) // 2                     # the line that gets the arrow
    print("   ".join(label.center(BOARD_W) for label, _ in entries).rstrip())
    for i in range(len(blocks[0])):
        gap = " → " if i == middle else "   "
        print(gap.join(block[i] for block in blocks))


def print_boards(entries):
    """Print any number of boards, PER_ROW per line."""
    for i in range(0, len(entries), PER_ROW):
        print_board_row(entries[i:i + PER_ROW])
        print()


def resolve_trace_mode(mode, steps):
    """'auto' means: everything for short paths, elided for long ones."""
    if mode == "auto":
        return "full" if steps <= AUTO_FULL_LIMIT else "elided"
    return mode


def print_trace(path, mode):
    """Draw the solution path: a labelled board for every step."""
    steps = len(path) - 1
    mode = resolve_trace_mode(mode, steps)
    if mode == "none":
        return
    entries = [(f"#{i} start" if move is None else f"#{i} {move}", state)
               for i, (move, state) in enumerate(path)]
    if mode == "elided" and len(entries) > 2 * TRACE_EDGE:
        skipped = len(entries) - 2 * TRACE_EDGE
        print_boards(entries[:TRACE_EDGE])
        print(f"   ... {skipped:,} steps not drawn (use --trace full to draw all) ...\n")
        print_boards(entries[-TRACE_EDGE:])
    else:
        print_boards(entries)


def moves_text(path, mode):
    """The move sequence as text:  Up → Left → Left  (elided if very long)."""
    moves = [m for m, _ in path[1:]]
    if not moves:
        return "(none - already at the goal)"
    if resolve_trace_mode(mode, len(moves)) == "elided" and len(moves) > 40:
        head, tail = " → ".join(moves[:20]), " → ".join(moves[-10:])
        return f"{head} → ... ({len(moves) - 30:,} moves not shown) ... → {tail}"
    return " → ".join(moves)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
def print_result(r, trace_mode):
    """Everything the assignment's report needs for ONE algorithm run."""
    print("═" * 78)
    print(f"  {r['algorithm']}")
    print("═" * 78)
    if not r["solved"]:
        print("  No solution found.")
        print(f"  Nodes expanded : {r['nodes_expanded']:,}")
        print(f"  Running time   : {r['time']:.5f} s\n")
        return

    print(f"  Path cost      : {r['cost']:,} moves")
    print(f"  Nodes expanded : {r['nodes_expanded']:,}")
    print(f"  Search depth   : {r['max_depth']:,}")
    if "iterations" in r:                                  # IDS only
        print(f"  Iterations     : {r['iterations']}  (depth limits 0..{r['iterations'] - 1})")
    print(f"  Running time   : {r['time']:.5f} s")
    print(f"  Path verified  : {'yes' if r['verified'] else 'NO - INVALID PATH!'}")
    print("  Moves          :")
    print(textwrap.indent(textwrap.fill(moves_text(r["path"], trace_mode), 72), "    "))
    print()
    print_trace(r["path"], trace_mode)


def print_summary(results):
    """One table comparing every algorithm that ran."""
    print("═" * 78)
    print("  SUMMARY")
    print("═" * 78)
    print(f"  {'algorithm':<16}{'solved':>7}{'cost':>8}{'expanded':>11}"
          f"{'search depth':>14}{'time (s)':>11}{'verified':>10}")
    print("  " + "─" * 77)
    for r in results:
        if r["solved"]:
            cost, verified = f"{r['cost']:,}", "yes" if r["verified"] else "NO"
        else:
            cost, verified = "-", "-"
        print(f"  {r['algorithm']:<16}{'yes' if r['solved'] else 'no':>7}{cost:>8}"
              f"{r['nodes_expanded']:>11,}{r['max_depth']:>14,}{r['time']:>11.5f}{verified:>10}")
    print()


def print_heuristic_comparison(by_key):
    """The comparison the assignment asks for: Manhattan vs Euclidean inside A*."""
    m, e = by_key.get("astar-manhattan"), by_key.get("astar-euclidean")
    if not (m and e and m["solved"] and e["solved"]):
        return
    print("  A* HEURISTIC COMPARISON")
    print("  " + "─" * 77)
    print(f"  Manhattan : expanded {m['nodes_expanded']:,} nodes, path cost {m['cost']}")
    print(f"  Euclidean : expanded {e['nodes_expanded']:,} nodes, path cost {e['cost']}")
    if m["nodes_expanded"] < e["nodes_expanded"]:
        print(f"  -> Manhattan expanded fewer nodes "
              f"(Euclidean needed {e['nodes_expanded'] / m['nodes_expanded']:.2f}x as many).")
    elif m["nodes_expanded"] > e["nodes_expanded"]:
        print("  -> Euclidean expanded fewer nodes on this board.")
    else:
        print("  -> Both expanded the same number of nodes on this board.")
    if m["cost"] == e["cost"]:
        same = "identical" if m["path"] == e["path"] else "different"
        print(f"  -> Both paths cost {m['cost']}; the move sequences are {same}.")
    else:
        print("  -> The path costs differ.")
    print()


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------
def parse_args(argv):
    p = argparse.ArgumentParser(
        description="8-puzzle solver: BFS, DFS, Iterative-Deepening DFS and A*.")
    p.add_argument("-s", "--state", metavar="TILES",
                   help='start board row by row, 0 = blank, e.g. "1,2,5,3,4,0,6,7,8" '
                        "(default: a random solvable board)")
    p.add_argument("--seed", type=int,
                   help="seed for the random start board, so a run can be repeated")
    p.add_argument("-a", "--algo", nargs="+", default=["all"],
                   choices=["all"] + list(ALGORITHMS), metavar="ALGO",
                   help="which algorithms to run: all, " + ", ".join(ALGORITHMS)
                        + "  (default: all)")
    p.add_argument("--trace", choices=["auto", "full", "none"], default="auto",
                   help="how many solution steps to draw: auto = every step for short "
                        "paths, first/last boards for long ones (default); "
                        "full = every step; none = metrics only")
    p.add_argument("--gui", action="store_true",
                   help="after solving, open gui.py to animate the results")
    return p.parse_args(argv)


def force_utf8():
    """
    The boards use box-drawing characters. When output is redirected to a file on
    Windows, Python may pick a legacy encoding that cannot store them and crash.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    force_utf8()
    args = parse_args(argv)

    # ---- 1. choose the start state --------------------------------------
    if args.state:
        try:
            start = parse_state(args.state)
        except ValueError as err:
            print(f"Invalid --state: {err}", file=sys.stderr)
            return 2
        origin = "given"
    else:
        seed = args.seed if args.seed is not None else random.randrange(1_000_000)
        random.seed(seed)
        start = random_state()
        origin = f"random, seed {seed}"

    # ---- 2. solvability check (BFS would otherwise exhaust 181,440 states) -
    inversions = count_inversions(start)
    print("8-PUZZLE SOLVER")
    print(f"Start state ({origin})  →  goal state\n")
    print_board_row([("start", start), ("goal", GOAL)])
    print()
    if not is_solvable(start):
        word = "inversion" if inversions == 1 else "inversions"
        print(f"This board is NOT solvable: it has {inversions} {word} (odd), and "
              "no sequence of moves can change that parity.")
        print("Try another --state, or omit it to get a random solvable board.")
        return 1
    print(f"Solvable: yes ({inversions} inversions, even)")
    print("Heuristic value of the start board: "
          + ", ".join(f"{name} {h(start):.2f}" for name, h in HEURISTICS.items()))
    print()

    # ---- 3. run the algorithms -----------------------------------------
    keys = list(ALGORITHMS) if "all" in args.algo else list(dict.fromkeys(args.algo))
    by_key = {}
    for key in keys:
        result = ALGORITHMS[key](start)
        result["verified"] = validate_path(start, result["path"])   # replay every move
        by_key[key] = result
        print_result(result, args.trace)

    # ---- 4. comparison ---------------------------------------------------
    results = list(by_key.values())
    print_summary(results)
    print_heuristic_comparison(by_key)

    # ---- 5. optional GUI -------------------------------------------------
    if args.gui:
        try:
            import gui                      # imported late: console use needs no Tk
        except ImportError as err:
            print(f"Cannot open the GUI ({err}). Is tkinter installed?", file=sys.stderr)
            return 1
        gui.launch(start, results)
    return 0


if __name__ == "__main__":
    sys.exit(main())