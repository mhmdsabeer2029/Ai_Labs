"""
8 Queens Puzzle — Interactive GUI Solver
Pure black/white checker board, real queen PNG asset embedded as base64.
Ivory GUI background #E8DDD0. Eliminated cells dissolve off the board.

Requirements:
  Python 3.8+  (tkinter is included in standard Python installs)
  Pillow       (pip install Pillow)  ← for crisp image scaling
  Without Pillow the queen icon still shows but may not scale perfectly.
"""

import tkinter as tk
from tkinter import font as tkfont
import base64
import io

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except ImportError:
    PIL_OK = False

# ════════════════════════════════════════════════════════════════════════════
#  EMBEDDED QUEEN PNG  (base64 — no external files needed)
# ════════════════════════════════════════════════════════════════════════════
QUEEN_B64 = (
    "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"
    "XjPpAAAAAElFTkSuQmCC"
)

# ════════════════════════════════════════════════════════════════════════════
#  COLOR DESIGN SYSTEM  (semantic token layer)
# ════════════════════════════════════════════════════════════════════════════
C = {
    # Board
    "board-white":   "#FFFFFF",
    "board-black":   "#1A1A1A",
    "board-border":  "#111111",

    # Queen cell — cornflower blue (matches reference)
    "queen-blue":    "#4A72D4",
    "queen-blue-d":  "#3A5EBB",

    # Hover tints
    "hover-white":   "#D0DCFF",
    "hover-black":   "#2A3A7A",

    # GUI ivory
    "ivory-base":    "#E8DDD0",
    "ivory-light":   "#EDE3D8",
    "ivory-border":  "#B8A898",
    "ivory-panel":   "#DDD3C8",

    # Eliminated cell (vanishes into bg)
    "elim-fill":     "#E8DDD0",
    "elim-dot":      "#D0C8BC",

    # Text
    "text-primary":   "#1C1814",
    "text-muted":     "#8A8278",

    # Buttons
    "btn-p-bg":  "#3A5EBB",
    "btn-p-h":   "#2E4EA8",
    "btn-p-fg":  "#FFFFFF",
    "btn-s-bg":  "#D8CFC6",
    "btn-s-h":   "#C8BFB6",
    "btn-s-fg":  "#1C1814",

    # Status colours
    "s-info":  "#3A5EBB",
    "s-ok":    "#1E8C5A",
    "s-err":   "#C0392B",
    "s-idle":  "#5A5550",
}

BOARD_N = 8
CELL    = 68     # px per cell
ANIM_MS = 80     # ms per elimination step
BORDER  = 3      # board outer border thickness


# ════════════════════════════════════════════════════════════════════════════
#  APP
# ════════════════════════════════════════════════════════════════════════════
class EightQueensApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("8 Queens Puzzle")
        self.root.configure(bg=C["ivory-base"])
        self.root.resizable(False, False)

        # ── State ─────────────────────────────────────────────────────────
        self.queens      = []   # [(row, col), ...]
        self.eliminated  = set()
        self.solution    = []
        self.step_index  = 0
        self.phase       = "pick"   # pick | animate | next | done
        self.anim_queue  = []
        self._hover      = None
        self._img_cache  = {}    # size -> PhotoImage (prevents GC)

        self._load_queen()
        self._build_fonts()
        self._build_ui()
        self._draw_board()
        self._set_status("Click any cell on the board to place your first queen.", C["s-info"])

    # ── Queen image ───────────────────────────────────────────────────────
    def _load_queen(self):
        raw = base64.b64decode(QUEEN_B64)
        if PIL_OK:
            self._pil_img = Image.open(io.BytesIO(raw)).convert("RGBA")
            self._tk_img  = None
        else:
            self._pil_img = None
            self._tk_img  = tk.PhotoImage(data=QUEEN_B64)

    def _queen_photo(self, size: int):
        if size in self._img_cache:
            return self._img_cache[size]
        if PIL_OK and self._pil_img:
            img   = self._pil_img.resize((size, size), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        else:
            photo = self._tk_img
        self._img_cache[size] = photo   # must hold reference — tkinter GC bug
        return photo

    # ── Fonts ─────────────────────────────────────────────────────────────
    def _build_fonts(self):
        self.f_title   = tkfont.Font(family="Georgia",   size=18, weight="bold")
        self.f_sub     = tkfont.Font(family="Helvetica", size=10)
        self.f_coord   = tkfont.Font(family="Helvetica", size=8,  weight="bold")
        self.f_status  = tkfont.Font(family="Helvetica", size=10, weight="bold")
        self.f_btn     = tkfont.Font(family="Helvetica", size=10, weight="bold")
        self.f_counter = tkfont.Font(family="Helvetica", size=9)

    # ── UI ────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root     = self.root
        board_px = CELL * BOARD_N

        # Header
        hdr = tk.Frame(root, bg=C["ivory-base"])
        hdr.pack(pady=(20, 10), padx=30)
        tk.Label(hdr, text="8 Queens Puzzle", font=self.f_title,
                 bg=C["ivory-base"], fg=C["text-primary"]).pack()
        tk.Label(hdr, text="Place all 8 queens so none can attack another.",
                 font=self.f_sub, bg=C["ivory-base"],
                 fg=C["text-muted"]).pack(pady=(3, 0))

        # Board with border frame
        bf = tk.Frame(root, bg=C["board-border"], padx=BORDER, pady=BORDER)
        bf.pack(padx=30)
        self.canvas = tk.Canvas(bf, width=board_px, height=board_px,
                                bg=C["board-white"], bd=0, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<Motion>",   self._on_hover)
        self.canvas.bind("<Leave>",    self._on_leave)

        # Rule
        tk.Frame(root, height=1, bg=C["ivory-border"]).pack(fill="x", padx=30, pady=(12, 0))

        # Status
        self.status_var = tk.StringVar()
        self.status_lbl = tk.Label(
            root, textvariable=self.status_var,
            font=self.f_status, bg=C["ivory-panel"], fg=C["text-primary"],
            wraplength=board_px - 20, justify="center", pady=10, padx=16)
        self.status_lbl.pack(fill="x", padx=30)
        tk.Frame(root, height=1, bg=C["ivory-border"]).pack(fill="x", padx=30)

        # Buttons
        br = tk.Frame(root, bg=C["ivory-base"])
        br.pack(pady=(12, 4))
        self.next_btn = self._btn(br, "▶  Next Step",
            C["btn-p-bg"], C["btn-p-h"], C["btn-p-fg"],
            self._next_step, state="disabled")
        self.next_btn.grid(row=0, column=0, padx=7)
        self.restart_btn = self._btn(br, "↺  Restart",
            C["btn-s-bg"], C["btn-s-h"], C["btn-s-fg"], self._restart)
        self.restart_btn.grid(row=0, column=1, padx=7)

        # Counter
        self.counter_var = tk.StringVar(value="0 / 8 queens placed")
        tk.Label(root, textvariable=self.counter_var,
                 font=self.f_counter, bg=C["ivory-base"],
                 fg=C["text-muted"]).pack(pady=(2, 16))

    def _btn(self, parent, text, bg, hover, fg, cmd, state="normal"):
        b = tk.Button(parent, text=text, font=self.f_btn, bg=bg, fg=fg,
                      activebackground=hover, activeforeground=fg,
                      relief="flat", cursor="hand2",
                      padx=18, pady=8, state=state, command=cmd)
        b.bind("<Enter>", lambda e: b.config(bg=hover))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
        return b

    # ── Board ─────────────────────────────────────────────────────────────
    def _is_white_cell(self, r, c):
        return (r + c) % 2 != 0      # top-left (0,0) is BLACK

    def _natural_fill(self, r, c):
        return C["board-white"] if self._is_white_cell(r, c) else C["board-black"]

    def _draw_board(self):
        self.canvas.delete("all")
        for r in range(BOARD_N):
            for c in range(BOARD_N):
                self._draw_cell(r, c)

    def _draw_cell(self, r, c):
        x1, y1 = c * CELL, r * CELL
        x2, y2 = x1 + CELL, y1 + CELL
        cx, cy = x1 + CELL // 2, y1 + CELL // 2

        is_queen = (r, c) in set(self.queens)
        is_elim  = (r, c) in self.eliminated
        is_hover = self._hover == (r, c)

        # Eliminated — cell vanishes into ivory bg
        if is_elim:
            self.canvas.create_rectangle(
                x1, y1, x2, y2, fill=C["elim-fill"], outline=C["elim-fill"])
            self.canvas.create_oval(
                cx - 2, cy - 2, cx + 2, cy + 2,
                fill=C["elim-dot"], outline="")
            return

        # Queen cell — blue fill + PNG icon
        if is_queen:
            self.canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=C["queen-blue"], outline=C["queen-blue-d"], width=2)
            size  = int(CELL * 0.70)
            photo = self._queen_photo(size)
            self.canvas.create_image(cx, cy, image=photo, anchor="center")
            return

        # Hover tint
        if is_hover and self.phase == "pick":
            fill = C["hover-white"] if self._is_white_cell(r, c) else C["hover-black"]
        else:
            fill = self._natural_fill(r, c)

        self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline="")

        # Coord labels
        if c == 0:
            fg = C["board-white"] if not self._is_white_cell(r, c) else C["text-muted"]
            self.canvas.create_text(x1 + 9, cy, text=str(r + 1),
                                    font=self.f_coord, fill=fg, anchor="center")
        if r == 0:
            fg = C["board-white"] if not self._is_white_cell(r, c) else C["text-muted"]
            self.canvas.create_text(cx, y1 + 9, text=chr(ord("A") + c),
                                    font=self.f_coord, fill=fg, anchor="center")

    # ── Solver ────────────────────────────────────────────────────────────
    def _is_safe(self, queens, row, col):
        for r, c in queens:
            if c == col or abs(r - row) == abs(c - col):
                return False
        return True

    def _solve_from(self, start_row, start_col):
        """
        Find a full solution with a queen fixed at (start_row, start_col).
        Uses backtracking: fills rows 0..BOARD_N-1 skipping start_row.
        """
        sol = [None] * BOARD_N
        sol[start_row] = start_col

        def bt(row):
            if row == BOARD_N:
                return None not in sol   # all rows filled
            if row == start_row:
                return bt(row + 1)       # skip — already fixed
            for col in range(BOARD_N):
                if self._is_safe(
                    [(r, sol[r]) for r in range(BOARD_N) if sol[r] is not None],
                    row, col
                ):
                    sol[row] = col
                    if bt(row + 1): return True
                    sol[row] = None
            return False

        return sol if bt(0) else None

    def _attacked_cells(self, queens):
        qs = set(queens)
        out = set()
        for qr, qc in queens:
            for r in range(BOARD_N):
                for c in range(BOARD_N):
                    if (r, c) in qs: continue
                    if r == qr or c == qc or abs(r - qr) == abs(c - qc):
                        out.add((r, c))
        return out

    # ── Interaction ───────────────────────────────────────────────────────
    def _on_click(self, event):
        if self.phase != "pick": return
        col = event.x // CELL
        row = event.y // CELL
        if not (0 <= row < BOARD_N and 0 <= col < BOARD_N): return
        if (row, col) in self.eliminated: return
        sol = self._solve_from(row, col)
        if sol is None:
            self._set_status("No solution from this cell — try another.", C["s-err"])
            return
        self.solution    = sol
        self.queens      = [(row, col)]
        self.eliminated  = set()
        # step_index tracks which solution rows still need to be placed
        # build the ordered list of remaining rows (all except start_row)
        self._remaining  = [r for r in range(BOARD_N) if r != row]
        self.step_index  = 0
        self._draw_board()
        self.counter_var.set("1 / 8 queens placed")
        self._set_status(
            f"Queen 1 at {chr(ord('A') + col)}{row + 1}. Removing attacked cells…",
            C["s-info"])
        self._begin_elim(self._attacked_cells(self.queens), self._ready)

    def _on_hover(self, event):
        if self.phase != "pick": return
        col = event.x // CELL
        row = event.y // CELL
        new = (row, col) if (0 <= row < BOARD_N and 0 <= col < BOARD_N) else None
        if new == self._hover: return
        old, self._hover = self._hover, new
        if old and old not in self.eliminated: self._draw_cell(*old)
        if new and new not in self.eliminated: self._draw_cell(*new)

    def _on_leave(self, event):
        if self._hover:
            old, self._hover = self._hover, None
            if old not in self.eliminated: self._draw_cell(*old)

    def _next_step(self):
        if self.phase != "next": return
        row = self._remaining[self.step_index]
        col = self.solution[row]
        self.queens.append((row, col))
        self.step_index += 1
        self._draw_cell(row, col)
        self.counter_var.set(f"{len(self.queens)} / 8 queens placed")
        self._set_status(
            f"Queen {len(self.queens)} at {chr(ord('A') + col)}{row + 1}. "
            f"Removing attacked cells…", C["s-info"])
        self._begin_elim(self._attacked_cells(self.queens), self._ready)

    # ── Elimination ───────────────────────────────────────────────────────
    def _begin_elim(self, attacked, cb):
        self.phase = "animate"
        self.next_btn.config(state="disabled")
        self.anim_queue = sorted(attacked - self.eliminated)
        self._elim_tick(cb)

    def _elim_tick(self, cb):
        if not self.anim_queue:
            self.root.after(200, cb); return
        cell = self.anim_queue.pop(0)
        self.eliminated.add(cell)
        self._draw_cell(*cell)
        self.root.after(ANIM_MS, lambda: self._elim_tick(cb))

    def _ready(self):
        if self.step_index >= len(self._remaining):
            self._finish(); return
        self.phase = "next"
        self.next_btn.config(state="normal")
        left = BOARD_N - len(self.queens)
        self._set_status(
            f"{len(self.queens)} / 8 queens placed — {left} remaining. "
            f"Press  ▶ Next Step  to continue.", C["s-idle"])

    def _finish(self):
        self.phase = "done"
        self.next_btn.config(state="disabled")
        self._draw_board()
        self._set_status(
            "🎉  Puzzle solved!  All 8 queens are safe — none can attack another.",
            C["s-ok"])
        self.counter_var.set("8 / 8 queens placed  ✓")

    def _restart(self):
        self.queens = []; self.eliminated = set()
        self.solution = []; self.step_index = 0
        self._remaining = []
        self.phase = "pick"; self.anim_queue = []
        self._hover = None
        self.next_btn.config(state="disabled")
        self.counter_var.set("0 / 8 queens placed")
        self._draw_board()
        self._set_status("Click any cell on the board to place your first queen.", C["s-info"])

    def _set_status(self, msg, color=None):
        self.status_var.set(msg)
        self.status_lbl.config(fg=color or C["text-primary"])


# ════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    EightQueensApp(root)
    root.mainloop()