"""
gui.py  --  Tkinter front-end for the 8-puzzle solver.

A Python port of the "8-puzzle-solver" web app (dgurkaynak/8-puzzle-solver, which
was JavaScript + vis.js). Same ideas, same layout, but it is driven by OUR code:
puzzles.py (rules), heuristics.py, and the algorithms in search.py.

WHAT YOU SEE
    left   : the board (tiles slide when a solution is replayed) + controls
    right  : the SEARCH TREE.   gray  = expanded      blue   = in the frontier
                                orange = current path  green  = solution path
             Mouse wheel = zoom, drag = pan, click a node = show that board.

HOW IT WORKS (three layers, so each can be understood and tested alone)
    1. record_search()  runs a search.py algorithm with an `observer` callback and
                        records its events: add / expand / goal / reset.
    2. TreeModel        turns a list of events into a tree (and lays it out).
                        Replaying the first k events = "the search after k steps",
                        which is what makes "Iterate one step" and "Back" trivial.
    3. BoardView / TreeView / App   the Tk widgets. They only DRAW; no search logic.

USAGE
    python gui.py                         random solvable board
    python gui.py 1,2,5,3,4,0,6,7,8       your own board
    python main.py --gui                  solve in the console first, then open this

THREADING NOTE
    The search runs in a worker thread so the window never freezes (IDS can take
    ~10 s on hard boards). Tk is NOT thread-safe, so the worker never touches a
    widget: it puts its answer in a queue that the main thread polls.
"""

import bisect
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, simpledialog, ttk

from puzzles import (GOAL, SIZE, parse_state, random_state, is_solvable,
                     count_inversions, index_to_rc)
from heuristics import HEURISTICS, manhattan, euclidean
from search import bfs, dfs, ids, astar


# ==========================================================================
# 1.  ALGORITHM REGISTRY + RECORDING  (no Tk in this section)
# ==========================================================================
def make_algorithms():
    """label -> function(start, observer=None). Labels match search.py's result names."""
    algos = {"BFS": bfs, "DFS": dfs, "IDS": ids}
    for name, h in HEURISTICS.items():
        label = f"A* ({name.capitalize()})"
        # default arguments freeze h/label for THIS iteration (classic closure trap)
        algos[label] = (lambda s, observer=None, h=h, label=label:
                        astar(s, h, label, observer=observer))
    return algos


class SearchStopped(Exception):
    """Raised inside the observer to abort a search when the user presses Stop."""


def record_search(run, start, cap=500, stop_event=None, level_aligned=False):
    """
    Run one algorithm and record what it did.

    `run(start, observer=...)` is a search.py algorithm. Its events are stored in
    a list. To keep the picture drawable, at most `cap` EXPANSIONS are recorded per
    "epoch" (an epoch is one whole search; for IDS, one depth-limit iteration).
    The search itself is never cut short: after the cap we simply stop recording,
    so the final result (cost, nodes expanded...) is still complete and exact.

    level_aligned (for BFS): when the cap cuts the recording in the middle of a tree level,
    drop that unfinished level, so the picture shows whole levels instead of a lopsided
    tree (left half of the last level expanded, right half not).

    Returns (result_dict, events, truncated, levels). `truncated` says whether the LAST
    epoch had events dropped (the drawn tree is only part of the tree). `levels` is the
    number of completely expanded levels when level alignment was applied, else None.
    """
    events = []
    state = {"recording": True, "expansions": 0, "truncated": False}

    def observer(*event):
        if stop_event is not None and stop_event.is_set():
            raise SearchStopped()
        kind = event[0]
        if kind == "reset":                       # IDS: new iteration, new tree
            state.update(recording=True, expansions=0, truncated=False)
            events.append(event)
            return
        if kind == "expand" and state["recording"]:
            if state["expansions"] >= cap:
                state["recording"] = False        # budget used up for this epoch
            else:
                state["expansions"] += 1
        if state["recording"] or kind == "goal":  # the goal event is always kept
            events.append(event)
        else:
            state["truncated"] = True

    result = run(start, observer=observer)
    levels = None
    if level_aligned and state["truncated"]:
        events, levels = trim_to_full_levels(events)
    return result, events, state["truncated"], levels


def trim_to_full_levels(events):
    """
    BFS expands level by level, so a recording cut at the cap ends in the middle of a
    level. Keep only whole levels. Returns (events, number_of_fully_expanded_levels).
    """
    expands = [i for i, ev in enumerate(events) if ev[0] == "expand"]
    if not expands:
        return events, None
    depth = events[expands[-1]][4]                    # the level the cap landed in
    added = sum(1 for ev in events if ev[0] == "add" and ev[4] == depth)
    done = sum(1 for ev in events if ev[0] == "expand" and ev[4] == depth)
    if done == added:                                 # that level happens to be complete
        return events, depth + 1
    first = next(i for i in expands if events[i][4] == depth)
    kept = events[:first] + [ev for ev in events[first:] if ev[0] == "goal"]
    return kept, depth


def step_ends(events):
    """
    Split the event list into STEPS. A step starts at every expand / goal / reset
    event (plus one initial step holding the root). Returns `ends`, where
    ends[k] = how many events have been applied after k+1 steps.
    """
    starts = [0] + [i for i, ev in enumerate(events)
                    if i and ev[0] in ("expand", "goal", "reset")]
    return starts[1:] + [len(events)]


class Recording:
    """Everything remembered about one finished search."""
    def __init__(self, key, result, events, truncated, cap, levels=None):
        self.key = key                    # (start, algorithm label, cap): what it was run on
        self.result = result
        self.events = events
        self.truncated = truncated
        self.cap = cap
        self.levels = levels              # BFS: fully expanded levels drawn (None = not trimmed)
        self.ends = step_ends(events)
        self.resets = [i for i, ev in enumerate(events) if ev[0] == "reset"]   # IDS iterations

    def iteration_at(self, step):
        """IDS: which iteration (1, 2, 3...) is on screen after `step` steps. 0 if not IDS."""
        upto = self.ends[step - 1] if step else 0
        return bisect.bisect_left(self.resets, upto)

    @property
    def n_steps(self):
        return len(self.ends)


# ==========================================================================
# 2.  TREE MODEL  (no Tk in this section)
# ==========================================================================
class TreeModel:
    """
    The search tree as it looks after some prefix of the recorded events.

    One node per KEY. For BFS / DFS / A* the key is the state itself (a state appears once;
    if it is reached again by a different parent before it is expanded, it is re-linked to
    the newer parent: exactly the parent the algorithm itself will use). IDS sends
    search.Visit objects as keys, so every visit is its own node and nothing is re-linked.
    """
    EXPANDED, FRONTIER, PATH = "expanded", "frontier", "path"

    def __init__(self):
        self.clear()

    def clear(self):
        self.parent = {}        # state -> parent state (None for the root)
        self.move = {}          # state -> move that led here
        self.children = {}      # state -> [child states], in insertion order
        self.status = {}        # state -> EXPANDED / FRONTIER / PATH
        self.root = None
        self.current = None     # most recently expanded state
        self.goal = None

    # ---- applying events ------------------------------------------------
    def apply(self, event):
        kind = event[0]
        if kind == "reset":
            self.clear()
        elif kind == "add":
            _, state, parent, move, _depth = event
            self._link(state, parent, move)
            self.status.setdefault(state, self.FRONTIER)
        elif kind == "expand":
            _, state, parent, move, _depth = event
            self._link(state, parent, move)
            self.status[state] = self.EXPANDED
            self.current = state
        elif kind == "goal":
            self.goal = event[1]

    def _link(self, state, parent, move):
        """Attach `state` under `parent` (creating or re-parenting as needed)."""
        known = state in self.parent
        if parent is None:                       # the root
            if not known:
                self.parent[state], self.move[state] = None, None
                self.children.setdefault(state, [])
                if self.root is None:
                    self.root = state
            return
        if known and self.parent[state] == parent:
            self.move[state] = move
            return
        if known:                                # re-parenting: refuse to make a cycle
            node = parent
            while node is not None:
                if node == state:
                    return
                node = self.parent.get(node)
            old = self.parent[state]
            if old is not None and state in self.children.get(old, ()):
                self.children[old].remove(state)
        self.parent[state], self.move[state] = parent, move
        self.children.setdefault(state, [])
        self.children.setdefault(parent, []).append(state)

    def overlay_path(self, path):
        """
        Make sure every state of the solution `path` [(move, state), ...] is in the
        tree, linked in path order. Needed when recording was truncated, so the
        solution can still be drawn and replayed.

        The first state of the path IS the tree's root, whatever type its key has.
        Returns the list of node keys, aligned with `path`.
        """
        nodes, previous = [], None
        for i, (move, state) in enumerate(path):
            if i == 0 and self.root is not None:
                key = self.root
            else:
                key = state
                if key not in self.parent:
                    self.status[key] = self.PATH
                self._link(key, previous, move)
            nodes.append(key)
            previous = key
        return nodes

    def solution_nodes(self, path):
        """
        Node keys of the solution `path`, aligned with it. If the recorded tree already
        contains the whole solution (the goal's parent chain matches the path), that chain
        is used as it is. Otherwise (the recording was cut short) the path is overlaid.
        """
        chain = self.path_to(self.goal) if self.goal is not None else []
        if chain and [tuple(k) for k in chain] == [s for _, s in path]:
            return chain
        return self.overlay_path(path)

    # ---- queries ---------------------------------------------------------
    def path_to(self, state):
        """[root, ..., state] following parent links."""
        chain, seen = [], set()
        while state is not None and state not in seen and state in self.parent:
            seen.add(state)
            chain.append(state)
            state = self.parent[state]
        chain.reverse()
        return chain

    def counts(self):
        expanded = sum(1 for s in self.status.values() if s == self.EXPANDED)
        return expanded, len(self.parent) - expanded

    def layout(self):
        """
        Tidy top-down layout. Returns {state: (x, level)}: `level` is the depth in
        this tree, `x` is in "leaf slots" (each leaf gets the next free slot and a
        parent sits centered over its children).  Iterative, because a DFS tree can
        be thousands of levels deep and Python's recursion limit would be hit.
        """
        if self.root is None:
            return {}
        order, level = [], {}
        stack = [(self.root, 0)]
        while stack:                              # pre-order
            state, lv = stack.pop()
            level[state] = lv
            order.append(state)
            for child in reversed(self.children.get(state, ())):
                stack.append((child, lv + 1))
        x, slot = {}, 0
        for state in order:                       # leaves, left to right
            if not self.children.get(state):
                x[state] = slot
                slot += 1
        for state in reversed(order):             # parents after all descendants
            kids = self.children.get(state)
            if kids:
                x[state] = (x[kids[0]] + x[kids[-1]]) / 2
        return {s: (x[s], level[s]) for s in order}


# ==========================================================================
# 3.  WIDGETS
# ==========================================================================
# Colors copied from the original web app's stylesheet.
C_HEADING, C_BORDER = "#333333", "#cccccc"
C_SEARCH, C_STOP, C_STEP, C_NEUTRAL = "#99cc00", "#ff6666", "#ffb366", "#6c757d"
C_EXPANDED, C_FRONTIER = "#eeeeee", "#97C2FC"          # vis.js defaults
C_CURRENT, C_SOLUTION = "#ffb366", "#ccff33"
C_EDGE, C_SELECT = "#999999", "#d62828"
FONT = "Arial"


def format_state(state):
    """3 text lines for a mini board; the blank is shown as a dot."""
    return "\n".join(" ".join("·" if t == 0 else str(t) for t in state[r * SIZE:(r + 1) * SIZE])
                     for r in range(SIZE))


class FlatButton(tk.Label):
    """
    A colored button. (tk.Button ignores background colors on macOS, a Label
    with a click binding looks the same everywhere.)
    """
    def __init__(self, master, text, command, bg, fg="white"):
        super().__init__(master, text=text, bg=bg, fg=fg, font=(FONT, 10, "bold"),
                         cursor="hand2", pady=4)
        self._command, self._bg, self._enabled = command, bg, True
        self.bind("<Button-1>", lambda _e: self._enabled and self._command())

    def set_enabled(self, enabled):
        self._enabled = enabled
        self.config(bg=self._bg if enabled else "#c8c8c8",
                    cursor="hand2" if enabled else "arrow")


class BoardView(tk.Canvas):
    """The 3x3 board. Tiles are canvas items that can slide to a new state."""
    TILE, BORDER = 68, 10
    C_TILE, C_TILE_OK, C_EMPTY = "#ffffff", "#d9f2c4", "#eeeeee"

    def __init__(self, master):
        size = SIZE * self.TILE + 2 * self.BORDER
        super().__init__(master, width=size, height=size, bg=C_BORDER, highlightthickness=0)
        b, span = self.BORDER, SIZE * self.TILE
        self.create_rectangle(b, b, b + span, b + span, fill=self.C_EMPTY, outline="")
        self._items, self._pos, self._anim = {}, {}, None
        for n in range(1, SIZE * SIZE):
            rect = self.create_rectangle(0, 0, 1, 1, fill=self.C_TILE, outline="black", width=2)
            text = self.create_text(0, 0, text=str(n), font=(FONT, 26, "bold"))
            self._items[n] = (rect, text)
        self.state = None

    def _cell(self, index):
        row, col = index_to_rc(index)
        return self.BORDER + col * self.TILE, self.BORDER + row * self.TILE

    def _place(self, n, x, y):
        rect, text = self._items[n]
        self.coords(rect, x + 1, y + 1, x + self.TILE - 1, y + self.TILE - 1)
        self.coords(text, x + self.TILE / 2, y + self.TILE / 2)
        self._pos[n] = (x, y)

    def _recolor(self, state):
        for index, n in enumerate(state):         # green tint = tile is home
            if n:
                self.itemconfig(self._items[n][0],
                                fill=self.C_TILE_OK if GOAL[index] == n else self.C_TILE)

    def cancel(self):
        if self._anim is not None:
            self.after_cancel(self._anim)
            self._anim = None

    def draw(self, state):
        """Jump straight to `state` (no animation)."""
        self.cancel()
        for index, n in enumerate(state):
            if n:
                self._place(n, *self._cell(index))
        self._recolor(state)
        self.state = state

    def slide_to(self, state, duration=500):
        """Animate every tile to its place in `state` (ease-in-out)."""
        self.cancel()
        start = dict(self._pos)
        end = {n: self._cell(i) for i, n in enumerate(state) if n}
        t0 = time.perf_counter()

        def frame():
            t = min(1.0, (time.perf_counter() - t0) * 1000 / max(duration, 1))
            e = t * t * (3 - 2 * t)
            for n, (ex, ey) in end.items():
                sx, sy = start[n]
                self._place(n, sx + (ex - sx) * e, sy + (ey - sy) * e)
            if t < 1:
                self._anim = self.after(16, frame)
            else:
                self._anim = None
                self._recolor(state)
        self.state = state
        frame()


class TreeView(tk.Canvas):
    """
    Draws a TreeModel with pan / zoom. Only nodes inside the window are drawn
    (culling), so a tree with thousands of nodes still redraws instantly.
    """
    NODE_W = NODE_H = 54          # node size in world units
    X_GAP, Y_GAP = 26, 56
    Y_STRETCH_MAX = 6.0           # 'Fit view' may spread the levels apart up to this factor
    MIN_SCALE, MAX_SCALE = 0.00002, 3.0  # tiny min: DFS paths can be 50,000 levels deep

    def __init__(self, master, mono_family, on_select):
        super().__init__(master, bg="white", highlightthickness=0)
        self.model = TreeModel()
        self.mono = mono_family
        self.on_select = on_select
        self.world = {}                       # state -> (world_x, world_y, level)
        self.y_stretch = 1.0                  # vertical spacing factor chosen by fit()
        self._raw = {}                        # state -> (x in leaf slots, level), from the model
        self._auto_fit = False                # True while the view is the one fit() chose
        self.scale, self.ox, self.oy = 1.0, 0.0, 0.0
        self.current_path, self.solution, self.selected = set(), set(), None
        self._drag, self._moved, self._view_anim = None, False, None
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._motion)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<MouseWheel>", self._wheel)                 # Windows / macOS
        self.bind("<Button-4>", self._wheel)                   # Linux scroll up
        self.bind("<Button-5>", self._wheel)                   # Linux scroll down
        self.bind("<Configure>", self._on_resize)

    # ---- data ------------------------------------------------------------
    def refresh(self):
        """Recompute the layout from the model, then redraw (view is kept)."""
        self._raw = self.model.layout()
        self._apply_layout()
        self.redraw()

    def _apply_layout(self):
        step_x, step_y = self.NODE_W + self.X_GAP, self.NODE_H + self.Y_GAP
        self.world = {s: (x * step_x, lv * step_y * self.y_stretch, lv)
                      for s, (x, lv) in self._raw.items()}

    def _on_resize(self, _event):
        # Window resized (e.g. maximized): if the user hasn't moved the view, refit it.
        if self._auto_fit and self.world:
            self.fit()
        else:
            self.redraw()

    def set_highlights(self, current_path=(), solution=(), selected=None):
        self.current_path, self.solution, self.selected = set(current_path), set(solution), selected
        self.redraw()

    # ---- view ------------------------------------------------------------
    def _size(self):
        return max(self.winfo_width(), 100), max(self.winfo_height(), 100)

    def fit(self):
        """
        Zoom/pan so the whole tree is visible.

        A search tree is usually much WIDER than tall (BFS: ~300 leaves but only ~10 levels),
        so fitting by width alone leaves most of the window empty and the tree a thin sliver.
        When the width is what limits the zoom, the levels are spread further apart (up to
        Y_STRETCH_MAX) so the tree also uses the height. Only the spacing between levels
        changes; nodes keep their shape.
        """
        self._stop_view_anim()
        if not self._raw:
            return
        step_x, step_y = self.NODE_W + self.X_GAP, self.NODE_H + self.Y_GAP
        w, h = self._size()
        xs = [x * step_x for x, _ in self._raw.values()]
        levels = max(lv for _, lv in self._raw.values())
        bw = max(xs) - min(xs) + self.NODE_W
        bh = levels * step_y + self.NODE_H
        by_width, by_height = (w - 40) / bw, (h - 40) / bh
        self.y_stretch = 1.0
        if levels and by_width < min(by_height, 1.0):          # width is the limit
            room = 0.9 * (h - 40) / by_width - self.NODE_H     # world height we can use
            self.y_stretch = max(1.0, min(self.Y_STRETCH_MAX, room / (levels * step_y)))
        self._apply_layout()
        bh = levels * step_y * self.y_stretch + self.NODE_H
        self.scale = max(self.MIN_SCALE, min(by_width, (h - 40) / bh, 1.0))
        self.ox = w / 2 - self.scale * (min(xs) + max(xs)) / 2
        self.oy = 24 + self.scale * self.NODE_H / 2
        self._auto_fit = True
        self.redraw()

    def focus(self, state, scale=None, animate=True):
        """Center the view on one node (optionally zooming to `scale`)."""
        if state not in self.world:
            return
        self._stop_view_anim()
        self._auto_fit = False
        if scale is not None:
            self.scale = scale
        wx, wy, _ = self.world[state]
        w, h = self._size()
        target = (w / 2 - wx * self.scale, h / 2 - wy * self.scale)
        if not animate:
            self.ox, self.oy = target
            self.redraw()
            return
        start, frames = (self.ox, self.oy), 8

        def frame(i=1):
            t = i / frames
            self.ox = start[0] + (target[0] - start[0]) * t
            self.oy = start[1] + (target[1] - start[1]) * t
            self.redraw()
            self._view_anim = self.after(20, frame, i + 1) if i < frames else None
        frame()

    def _stop_view_anim(self):
        if self._view_anim is not None:
            self.after_cancel(self._view_anim)
            self._view_anim = None

    # ---- drawing ---------------------------------------------------------
    def _screen(self, state):
        wx, wy, _ = self.world[state]
        return wx * self.scale + self.ox, wy * self.scale + self.oy

    def _color(self, state):
        if state in self.solution:
            return C_SOLUTION, "#7a9900"
        if state in self.current_path:
            return C_CURRENT, "#cc7a29"
        if self.model.status.get(state) == TreeModel.EXPANDED:
            return C_EXPANDED, "#aaaaaa"
        return C_FRONTIER, "#2B7CE9"

    def redraw(self):
        self.delete("all")
        w, h = self._size()
        if not self.world:
            self.create_text(w / 2, h / 2, fill="#999999", font=(FONT, 13), justify="center",
                             text="Press  Search  to build the tree,\nor  Iterate one step  to watch it grow.")
            return
        s, m = self.scale, 30
        nw, nh = self.NODE_W * s, self.NODE_H * s
        # edges first (so nodes paint on top)
        for state in self.world:
            parent = self.model.parent.get(state)
            if parent is None or parent not in self.world:
                continue
            x1, y1 = self._screen(parent)
            x2, y2 = self._screen(state)
            if max(x1, x2) < -m or min(x1, x2) > w + m or max(y1, y2) < -m or min(y1, y2) > h + m:
                continue
            on_path = state in self.solution and parent in self.solution
            on_cur = state in self.current_path and parent in self.current_path
            color = "#7a9900" if on_path else "#cc7a29" if on_cur else C_EDGE
            self.create_line(x1, y1 + nh / 2, x2, y2 - nh / 2, fill=color,
                             width=3 if (on_path or on_cur) else 1,
                             arrow=tk.LAST if nh > 20 else None)
            if s >= 0.9:
                self.create_text((x1 + x2) / 2, (y1 + y2) / 2, fill="#666666",
                                 font=(FONT, max(7, int(9 * s))),
                                 text=self.model.move.get(state) or "")
        # nodes
        for state in self.world:
            cx, cy = self._screen(state)
            if cx + nw / 2 < -m or cx - nw / 2 > w + m or cy + nh / 2 < -m or cy - nh / 2 > h + m:
                continue
            fill, outline = self._color(state)
            if state == self.selected:
                outline, width = C_SELECT, 3
            else:
                width = 1
            if nw < 3:                                    # too small: just a dot
                d = 1.75
                self.create_rectangle(cx - d, cy - d, cx + d, cy + d, fill=outline, outline="")
                continue
            self.create_rectangle(cx - nw / 2, cy - nh / 2, cx + nw / 2, cy + nh / 2,
                                  fill=fill, outline=outline, width=width)
            if nw >= 26:                                  # big enough to read the digits
                self.create_text(cx, cy, text=format_state(state), fill="#222222",
                                 font=(self.mono, -max(6, int(13 * s)), "bold"))

    # ---- mouse -----------------------------------------------------------
    def _press(self, e):
        self._stop_view_anim()
        self._drag, self._moved = (e.x, e.y, self.ox, self.oy), False

    def _motion(self, e):
        if self._drag is None:
            return
        x0, y0, ox0, oy0 = self._drag
        if abs(e.x - x0) + abs(e.y - y0) > 3:
            self._moved = True
        if self._moved:
            self._auto_fit = False
            self.ox, self.oy = ox0 + e.x - x0, oy0 + e.y - y0
            self.redraw()

    def _release(self, e):
        if self._drag is not None and not self._moved:        # a click, not a drag
            hit = self._hit(e.x, e.y)
            if hit is not None:
                self.on_select(hit)
        self._drag = None

    def _hit(self, px, py):
        half_w, half_h = self.NODE_W * self.scale / 2, self.NODE_H * self.scale / 2
        for state in self.world:
            cx, cy = self._screen(state)
            if abs(px - cx) <= max(half_w, 2) and abs(py - cy) <= max(half_h, 2):
                return state
        return None

    def _wheel(self, e):
        self._stop_view_anim()
        self._auto_fit = False
        zoom_in = e.num == 4 or getattr(e, "delta", 0) > 0
        factor = 1.25 if zoom_in else 1 / 1.25
        new = max(self.MIN_SCALE, min(self.MAX_SCALE, self.scale * factor))
        factor = new / self.scale
        self.ox = e.x - (e.x - self.ox) * factor              # zoom around the cursor
        self.oy = e.y - (e.y - self.oy) * factor
        self.scale = new
        self.redraw()


# ==========================================================================
# 4.  THE APPLICATION
# ==========================================================================
class App:
    def __init__(self, root, start=None, results=None):
        self.root = root
        root.title("8-Puzzle Solver - search tree visualizer")
        root.geometry("1180x720")
        root.minsize(900, 720)      # the side panel needs ~720 px or the speed slider is cut off

        self.algos = make_algorithms()
        families = set(tkfont.families())
        self.mono = next((f for f in ("Consolas", "Menlo", "DejaVu Sans Mono", "Courier New")
                          if f in families), "Courier")

        self.start = start if start and is_solvable(start) else random_state()
        self.run = None                 # Recording of the last search (or None)
        self.step = 0                   # how many steps of the recording are applied
        self.model = TreeModel()
        self._queue = queue.Queue()
        self._job, self._stop_evt, self._busy, self._then = 0, threading.Event(), False, "final"
        self.replaying, self._replay_after, self._replay_i = False, None, 0
        self.sol_nodes = []             # tree nodes of the solution path (aligned with result path)

        self._build_ui(results)
        self._show_board(self.start, "Start state")
        root.protocol("WM_DELETE_WINDOW", self._close)
        root.after(50, self._poll)

    # ---- UI construction -------------------------------------------------
    def _heading(self, parent, text):
        tk.Label(parent, text=text, bg=C_HEADING, fg="white",
                 font=(FONT, 10, "bold")).pack(fill="x", pady=(8, 0))

    def _build_ui(self, results):
        side = tk.Frame(self.root, width=272)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        self.board = BoardView(side)
        self.board.pack(pady=(10, 2))
        self.caption = tk.Label(side, text="", font=(FONT, 9), fg="#444444", wraplength=250)
        self.caption.pack()

        self._heading(side, "Board")
        row = tk.Frame(side)
        row.pack(fill="x", padx=6, pady=4)
        for col, (text, cmd) in enumerate((("Randomize", self.on_randomize),
                                           ("Custom state", self.on_custom))):
            btn = FlatButton(row, text, cmd, C_NEUTRAL)
            btn.grid(row=0, column=col, sticky="ew", padx=2)
            row.columnconfigure(col, weight=1)
            setattr(self, ("btn_random", "btn_custom")[col], btn)

        self._heading(side, "Search")
        box = tk.Frame(side)
        box.pack(fill="x", padx=6, pady=2)
        tk.Label(box, text="Algorithm", font=(FONT, 8, "bold"), anchor="w").pack(fill="x")
        default = "A* (Manhattan)"
        if results:                                           # opened from main.py --gui
            labels = [r["algorithm"] for r in results if r["algorithm"] in self.algos]
            default = default if default in labels or not labels else labels[0]
        self.algo_var = tk.StringVar(value=default)
        self.algo_box = ttk.Combobox(box, textvariable=self.algo_var, state="readonly",
                                     values=list(self.algos))
        self.algo_box.pack(fill="x", pady=(0, 3))
        self.algo_box.bind("<<ComboboxSelected>>", lambda _e: self._invalidate())
        tk.Label(box, text="Tree limit (expansions drawn per run)", font=(FONT, 8, "bold"),
                 anchor="w").pack(fill="x")
        self.cap_var = tk.StringVar(value="500")
        self.cap_box = tk.Spinbox(box, from_=10, to=5000, increment=100,
                                  textvariable=self.cap_var, width=8)
        self.cap_box.pack(fill="x", pady=(0, 4))

        row = tk.Frame(box)
        row.pack(fill="x")
        self.btn_step = FlatButton(row, "Iterate one step", self.on_step, C_STEP)
        self.btn_back = FlatButton(row, "◀ Back", self.on_back, C_NEUTRAL)
        self.btn_step.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        self.btn_back.grid(row=0, column=1, sticky="ew", padx=(2, 0))
        row.columnconfigure(0, weight=3)
        row.columnconfigure(1, weight=2)
        self.slot = tk.Frame(box)                             # Search and Stop share this slot
        self.slot.pack(fill="x", pady=(3, 0))
        self.btn_search = FlatButton(self.slot, "Search", self.on_search, C_SEARCH)
        self.btn_stop = FlatButton(self.slot, "Stop", self.on_stop, C_STOP)
        self.btn_search.pack(fill="x")

        self._heading(side, "Search Result")
        self.result = tk.Label(side, text="", font=(FONT, 9), justify="left", anchor="nw",
                               wraplength=250, height=7)
        self.result.pack(fill="x", padx=8, pady=(4, 0))
        row = tk.Frame(side)
        row.pack(fill="x", padx=6)
        self.btn_replay = FlatButton(row, "Replay solution", self.on_replay, C_SEARCH)
        self.btn_replay.pack(fill="x")
        self.btn_replay.set_enabled(False)
        tk.Label(row, text="Replay: ms per move", font=(FONT, 8, "bold"),
                 anchor="w").pack(fill="x", pady=(4, 0))
        self.speed = tk.Scale(row, from_=100, to=1500, orient="horizontal", resolution=50)
        self.speed.set(1000)
        self.speed.pack(fill="x")

        # right side: legend bar + tree
        main = tk.Frame(self.root)
        main.pack(side="left", fill="both", expand=True)
        bar = tk.Frame(main, bg="#f4f4f4")
        bar.pack(fill="x")
        for color, text in ((C_EXPANDED, "expanded"), (C_FRONTIER, "frontier"),
                            (C_CURRENT, "current path"), (C_SOLUTION, "solution")):
            tk.Label(bar, text="■", fg=color if color != C_EXPANDED else "#bbbbbb",
                     bg="#f4f4f4", font=(FONT, 12)).pack(side="left", padx=(10, 0))
            tk.Label(bar, text=text, bg="#f4f4f4", font=(FONT, 9)).pack(side="left", padx=(2, 0))
        FlatButton(bar, "Fit view", lambda: self.tree.fit(), C_NEUTRAL).pack(side="right", padx=6, pady=3)
        self.info = tk.Label(main, anchor="w", font=(FONT, 9), fg="#444444", bg="#f4f4f4",
                             text="Wheel = zoom · drag = pan · click a node to show its board")
        self.info.pack(side="bottom", fill="x")
        self.tree = TreeView(main, self.mono, self._on_node_click)
        self.tree.model = self.model
        self.tree.pack(fill="both", expand=True)
        self.tree.refresh()

    # ---- small helpers ---------------------------------------------------
    def _cap(self):
        try:
            return max(10, int(self.cap_var.get()))
        except ValueError:
            self.cap_var.set("500")
            return 500

    def _show_board(self, state, caption=None):
        self.board.draw(state)
        if caption is not None:
            self.caption.config(text=caption)

    def _set_busy(self, busy):
        self._busy = busy
        for btn in (self.btn_random, self.btn_custom, self.btn_step, self.btn_back):
            btn.set_enabled(not busy)
        self.algo_box.config(state="disabled" if busy else "readonly")
        if busy:
            self.btn_search.pack_forget()
            self.btn_stop.pack(fill="x")
            self.result.config(text="Searching…")
        else:
            self.btn_stop.pack_forget()
            self.btn_search.pack(fill="x")

    def _invalidate(self):
        """Board / algorithm / limit changed: forget the old run and clear the tree."""
        self._stop_replay()
        self.run, self.step, self.sol_nodes = None, 0, []
        self.model.clear()
        self.tree.set_highlights()
        self.tree.y_stretch = 1.0
        self.tree.refresh()
        self.btn_replay.set_enabled(False)
        self.result.config(text="")
        self.info.config(text="Wheel = zoom · drag = pan · click a node to show its board")
        self._show_board(self.start, "Start state")

    # ---- board buttons ---------------------------------------------------
    def on_randomize(self):
        self.start = random_state()
        self._invalidate()

    def on_custom(self):
        text = simpledialog.askstring(
            "Custom state",
            "Enter the 9 tiles row by row, 0 = blank.\nExample: 1,2,5,3,4,0,6,7,8",
            parent=self.root)
        if not text:
            return
        try:
            state = parse_state(text)
        except ValueError as err:
            messagebox.showerror("Invalid state", str(err), parent=self.root)
            return
        if not is_solvable(state):
            n = count_inversions(state)
            messagebox.showerror(
                "Unsolvable board",
                f"This board has {n} inversion{'s' if n != 1 else ''} (odd), so no sequence "
                "of moves can ever reach the goal. Try another one.", parent=self.root)
            return
        self.start = state
        self._invalidate()

    # ---- searching -------------------------------------------------------
    def _begin(self, then):
        """Make sure a recording exists for the current settings, then continue."""
        if self._busy:
            return
        self._stop_replay()
        label, cap = self.algo_var.get(), self._cap()
        key = (self.start, label, cap)
        if self.run is not None and self.run.key == key:       # already recorded: reuse
            self._continue(then)
            return
        self.run, self.step = None, 0
        self._job += 1
        job, evt = self._job, threading.Event()
        self._stop_evt, self._then = evt, then
        run_fn, start = self.algos[label], self.start

        def worker():                                         # runs OFF the Tk thread
            try:
                result, events, truncated, levels = record_search(
                    run_fn, start, cap, evt, level_aligned=(label == "BFS"))
                self._queue.put((job, "done",
                                 Recording(key, result, events, truncated, cap, levels)))
            except SearchStopped:
                self._queue.put((job, "stopped", None))
            except Exception as exc:                          # show it instead of dying silently
                self._queue.put((job, "error", exc))
        threading.Thread(target=worker, daemon=True).start()
        self._set_busy(True)

    def _poll(self):
        try:
            while True:
                job, kind, payload = self._queue.get_nowait()
                if job != self._job:
                    continue                                  # stale answer from an older search
                self._set_busy(False)
                if kind == "done":
                    self.run, self.step = payload, 0
                    self.model.clear()
                    self._continue(self._then)
                elif kind == "stopped":
                    self.result.config(text="Search stopped.")
                else:
                    self.result.config(text="Error: " + str(payload))
                    messagebox.showerror("Search failed", str(payload), parent=self.root)
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _continue(self, then):
        if then == "final":
            self._goto(self.run.n_steps)
        else:
            self._goto(max(self.step, 0) + 1)

    def on_search(self):
        self._begin("final")

    def on_step(self):
        if self.run is not None and self.run.key == (self.start, self.algo_var.get(), self._cap()):
            if self.step >= self.run.n_steps:
                self.info.config(text="The search has finished. Use ◀ Back to review it.")
                return
            self._stop_replay()
            self._goto(self.step + 1)
        else:
            self._begin("step")

    def on_back(self):
        if self.run is not None and self.step > 0:
            self._stop_replay()
            self._goto(self.step - 1)

    def on_stop(self):
        self._stop_evt.set()

    # ---- showing a given step of the recording ---------------------------
    def _goto(self, j):
        """Show the search after `j` steps (0 = nothing yet, n_steps = finished)."""
        run = self.run
        j = max(0, min(j, run.n_steps))
        applied = self.run.ends[self.step - 1] if self.step else 0
        if j < self.step:                                     # going back: rebuild from scratch
            self.model.clear()
            applied = 0
        upto = run.ends[j - 1] if j else 0
        for event in run.events[applied:upto]:
            self.model.apply(event)
        self.step = j
        finished = j == run.n_steps
        if finished:
            self._show_finished()
            return
        current = self.model.current
        expanded, frontier = self.model.counts()
        self.tree.y_stretch = 1.0                             # stepping: normal spacing
        self.tree.refresh()
        if current is not None:
            self.tree.set_highlights(current_path=self.model.path_to(current))
            self.tree.focus(current)
            self._show_board(current, f"Expanding this node (step {j} of {run.n_steps})")
        else:
            self.tree.set_highlights()
            self._show_board(self.start, "Start state")
        self.btn_replay.set_enabled(False)
        text = f"Step {j} / {run.n_steps}\n"
        iteration = run.iteration_at(j)
        if iteration:                                         # IDS
            text += f"Iteration {iteration}  (depth limit {iteration - 1})\n"
        self.result.config(text=text + f"\nExpanded nodes: {expanded}\nFrontier nodes: {frontier}")

    def _show_finished(self):
        run, result = self.run, self.run.result
        if result["solved"]:
            self.sol_nodes = self.model.solution_nodes(result["path"])
        else:
            self.sol_nodes = []
        self.tree.refresh()
        self.tree.set_highlights(solution=self.sol_nodes)
        self.tree.fit()
        goal_state = result["path"][-1][1] if result["solved"] else self.start
        self._show_board(goal_state, "Solved!" if result["solved"] else "No solution found")
        expanded, frontier = self.model.counts()
        lines = []
        if result["solved"]:
            lines += [f"Solved!  Cost: {result['cost']:,} moves"]
        else:
            lines += ["No solution found"]
        lines += [f"Nodes expanded: {result['nodes_expanded']:,}",
                  f"Search depth: {result['max_depth']:,}",
                  f"Time: {result['time']:.4f} s  (includes tree recording)"]
        if "iterations" in result:
            lines.append(f"Iterations: {result['iterations']}")
        note = f"Tree drawn: {expanded + frontier:,} nodes"
        if run.levels is not None:
            note += f" (levels 0-{run.levels - 1} fully expanded; solution path added)"
        elif run.truncated:
            what = "of the last iteration" if "iterations" in result else ""
            note += f" (first {run.cap:,} expansions {what}; solution path added)".replace("  ", " ")
        lines.append(note)
        self.result.config(text="\n".join(lines))
        self.btn_replay.set_enabled(result["solved"])

    # ---- clicking a node -------------------------------------------------
    def _on_node_click(self, state):
        self._stop_replay()
        self._show_board(state, "Selected node")
        self.tree.set_highlights(current_path=self.tree.current_path,
                                 solution=self.tree.solution, selected=state)
        depth = self.tree.world[state][2]
        status = self.model.status.get(state, "")
        self.info.config(
            text=f"depth {depth} in tree · {status} · h(Manhattan) {manhattan(state)}"
                 f" · h(Euclidean) {euclidean(state):.2f} · move: {self.model.move.get(state) or '-'}")

    # ---- replaying the solution -----------------------------------------
    def on_replay(self):
        if self.replaying:
            self._stop_replay()
            return
        if self.run is None or not self.run.result["solved"] or self.step < self.run.n_steps:
            return
        self.replaying, self._replay_i = True, 0
        self.btn_replay.config(text="Stop replaying")
        path = self.run.result["path"]
        first = path[0][1]
        self.board.draw(first)
        self.caption.config(text=f"Replay: step 0 / {len(path) - 1}  (start)")
        self.tree.set_highlights(solution=self.tree.solution, selected=self.sol_nodes[0])
        self.tree.focus(self.sol_nodes[0], scale=0.75)
        self._replay_after = self.root.after(int(self.speed.get()), self._replay_next)

    def _replay_next(self):
        path = self.run.result["path"]
        self._replay_i += 1
        if self._replay_i >= len(path):
            self._stop_replay(finished=True)
            return
        move, state = path[self._replay_i]
        delay = int(self.speed.get())
        self.board.slide_to(state, duration=min(500, delay // 2))
        self.caption.config(text=f"Replay: step {self._replay_i} / {len(path) - 1}  ({move})")
        self.tree.set_highlights(solution=self.tree.solution, selected=self.sol_nodes[self._replay_i])
        self.tree.focus(self.sol_nodes[self._replay_i])
        self._replay_after = self.root.after(delay, self._replay_next)

    def _stop_replay(self, finished=False):
        if self._replay_after is not None:
            self.root.after_cancel(self._replay_after)
            self._replay_after = None
        if self.replaying:
            self.replaying = False
            self.btn_replay.config(text="Replay solution")
            if finished:
                self.caption.config(text="Replay finished - the board is solved")

    def _close(self):
        self._stop_evt.set()
        self._stop_replay()
        self.board.cancel()
        self.root.destroy()


# ==========================================================================
# Entry points
# ==========================================================================
def launch(start=None, results=None):
    """
    Open the GUI. main.py calls this for `--gui`:
        start   : the start state (tuple), or None for a random one
        results : optional list of result dicts from main.py (only used to pick
                  which algorithm is pre-selected; the GUI re-runs searches itself
                  because it needs the search TREE, not just the final path)
    """
    root = tk.Tk()
    App(root, start, results)
    root.mainloop()


if __name__ == "__main__":
    begin = None
    if len(sys.argv) > 1:
        try:
            begin = parse_state(sys.argv[1])
        except ValueError as err:
            sys.exit(f"Invalid state: {err}")
        if not is_solvable(begin):
            sys.exit("That board is not solvable (odd number of inversions).")
    launch(begin)