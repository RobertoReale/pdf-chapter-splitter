#!/usr/bin/env python3
"""
PDF Chapter Splitter
====================
GUI tool to extract chapters (or page ranges) from a PDF.

Dependencies:
    pip install pypdf
    pip install tkinterdnd2  # optional – enables drag-and-drop
"""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pypdf import PdfReader, PdfWriter

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    _DND = True
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    _DND = False


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def parse_page_number(value: str, total_pages: int) -> int | None:
    """Convert string → 0-based page index. Returns None if out of range or invalid."""
    value = value.strip()
    if not value:
        return None
    try:
        n = int(value)
        if 1 <= n <= total_pages:
            return n - 1
    except ValueError:
        pass
    return None


def sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-.() " else "_" for c in name).strip()


def open_folder(path: str):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ──────────────────────────────────────────────
# TOC Selection Dialog
# ──────────────────────────────────────────────

class TocDialog(tk.Toplevel):
    def __init__(self, parent, chapters: list, total_pages: int, on_import):
        super().__init__(parent)
        self.title("Detected Table of Contents")
        self.resizable(True, True)
        self.minsize(520, 420)
        self.chapters = chapters
        self.total_pages = total_pages
        self.on_import = on_import
        self.vars = [tk.BooleanVar(value=False) for _ in chapters]
        self._build()
        self.grab_set()

    def _build(self):
        tk.Label(self, text="Select entries to import:",
                 font=("", 10, "bold"), pady=8).pack()

        bar = tk.Frame(self, padx=10)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="Show:").pack(side=tk.LEFT)
        self.show_var = tk.StringVar(value="top")
        tk.Radiobutton(bar, text="Top-level only", variable=self.show_var,
                       value="top", command=self._refresh).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(bar, text="All entries", variable=self.show_var,
                       value="all", command=self._refresh).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6, pady=4)

        outer = tk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=2)

        self._canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._list_frame = tk.Frame(self._canvas)
        self._list_frame.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.create_window((0, 0), window=self._list_frame, anchor="nw")
        self._canvas.configure(yscrollcommand=sb.set)

        # Bind scroll to this canvas only — no bind_all to avoid stealing from main window
        self._canvas.bind("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        self._canvas.bind("<Button-4>", lambda e: self._canvas.yview_scroll(-1, "units"))
        self._canvas.bind("<Button-5>", lambda e: self._canvas.yview_scroll(1, "units"))

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._refresh()

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6, pady=4)
        btns = tk.Frame(self, padx=10, pady=6)
        btns.pack(fill=tk.X)
        ttk.Button(btns, text="Select all",
                   command=lambda: self._set_all(True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Deselect all",
                   command=lambda: self._set_all(False)).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Cancel",
                   command=self.destroy).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btns, text="Import selected",
                   command=self._import).pack(side=tk.RIGHT, padx=4)

    def _refresh(self):
        for w in self._list_frame.winfo_children():
            w.destroy()
        top_only = self.show_var.get() == "top"
        for i, ch in enumerate(self.chapters):
            if top_only and ch["level"] > 0:
                continue
            indent = "    " * ch["level"]
            cb = tk.Checkbutton(
                self._list_frame,
                text=f"{indent}{ch['title']}   (p. {ch['page']})",
                variable=self.vars[i],
                anchor="w", justify="left",
                command=lambda i=i: self._on_toggle(i),
            )
            cb.pack(fill=tk.X, padx=6, pady=1)
            cb.bind("<MouseWheel>",
                lambda e: self._canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    def _on_toggle(self, index):
        value = self.vars[index].get()
        level = self.chapters[index]["level"]
        for i in range(index + 1, len(self.chapters)):
            if self.chapters[i]["level"] > level:
                self.vars[i].set(value)
            else:
                break

    def _set_all(self, value: bool):
        for var in self.vars:
            var.set(value)

    def _import(self):
        selected = [i for i, v in enumerate(self.vars) if v.get()]
        if not selected:
            messagebox.showwarning("Warning", "No entries selected.", parent=self)
            return
        result = []
        for i in selected:
            ch = self.chapters[i]
            end = self.total_pages
            for j in range(i + 1, len(self.chapters)):
                if self.chapters[j]["level"] <= ch["level"]:
                    nxt = self.chapters[j]["page"]
                    if nxt > ch["page"]:
                        end = nxt - 1
                        break
            result.append({"title": ch["title"], "start": ch["page"], "end": end})
        result.sort(key=lambda x: x["start"])
        self.on_import(result)
        self.destroy()


# ──────────────────────────────────────────────
# Chapter row widget
# ──────────────────────────────────────────────

_PLACEHOLDER = "= chapter name"


class ChapterRow(tk.Frame):
    def __init__(self, parent, index: int, on_delete, total_pages_fn, **kw):
        super().__init__(parent, **kw)
        self.index = index
        self._total_pages_fn = total_pages_fn

        self.selected = tk.BooleanVar(value=True)
        tk.Checkbutton(self, variable=self.selected, width=2).pack(side=tk.LEFT)

        self.name_var = tk.StringVar(value=f"Chapter {index}")
        tk.Entry(self, textvariable=self.name_var, width=22).pack(side=tk.LEFT, padx=2)

        tk.Label(self, text="From p.").pack(side=tk.LEFT)
        self.start_var = tk.StringVar()
        self._start_e = tk.Entry(self, textvariable=self.start_var, width=6)
        self._start_e.pack(side=tk.LEFT, padx=2)

        tk.Label(self, text="To p.").pack(side=tk.LEFT)
        self.end_var = tk.StringVar()
        self._end_e = tk.Entry(self, textvariable=self.end_var, width=6)
        self._end_e.pack(side=tk.LEFT, padx=2)

        self.start_var.trace_add("write", lambda *_: self._validate(self.start_var, self._start_e))
        self.end_var.trace_add("write",   lambda *_: self._validate(self.end_var,   self._end_e))

        tk.Label(self, text="  ➔ File:").pack(side=tk.LEFT)
        self._out_e = tk.Entry(self, width=18, fg="grey")
        self._out_e.insert(0, _PLACEHOLDER)
        self._out_e.pack(side=tk.LEFT, padx=2)
        self._out_e.bind("<FocusIn>",  self._out_focus_in)
        self._out_e.bind("<FocusOut>", self._out_focus_out)

        ttk.Button(self, text="✕", width=2,
                   command=lambda: on_delete(self)).pack(side=tk.LEFT, padx=4)

    def _validate(self, var: tk.StringVar, entry: tk.Entry):
        total = self._total_pages_fn()
        val = var.get().strip()
        if not val or total == 0:
            entry.config(bg="white")
            return
        ok = parse_page_number(val, total) is not None
        entry.config(bg="#d1fae5" if ok else "#fee2e2")

    def _out_focus_in(self, _):
        if self._out_e.cget("fg") == "grey":
            self._out_e.delete(0, tk.END)
            self._out_e.config(fg="black")

    def _out_focus_out(self, _):
        if not self._out_e.get().strip():
            self._out_e.delete(0, tk.END)
            self._out_e.insert(0, _PLACEHOLDER)
            self._out_e.config(fg="grey")

    def set_output(self, val: str):
        self._out_e.delete(0, tk.END)
        if val:
            self._out_e.insert(0, val)
            self._out_e.config(fg="black")
        else:
            self._out_e.insert(0, _PLACEHOLDER)
            self._out_e.config(fg="grey")

    def get_output(self) -> str:
        if self._out_e.cget("fg") == "grey":
            return ""
        return self._out_e.get().strip()

    def get_data(self) -> dict:
        return {
            "selected": self.selected.get(),
            "name":     self.name_var.get().strip() or f"chapter_{self.index}",
            "start":    self.start_var.get(),
            "end":      self.end_var.get(),
            "output":   self.get_output(),
        }


# ──────────────────────────────────────────────
# Main window
# ──────────────────────────────────────────────

_BASE = TkinterDnD.Tk if _DND else tk.Tk  # type: ignore[union-attr]

class App(_BASE):  # type: ignore[valid-type, misc]
    def __init__(self):
        super().__init__()
        self.title("PDF Chapter Splitter")
        self.resizable(True, True)
        self.minsize(800, 420)

        self.pdf_path: str | None = None
        self.total_pages: int = 0
        self._reader: PdfReader | None = None
        self.chapter_rows: list[ChapterRow] = []

        self._build_ui()
        self.bind("<Control-o>", lambda _: self._choose_file())
        self.bind("<Control-O>", lambda _: self._choose_file())

        if _DND:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)

    # ── UI construction ───────────────────────

    def _build_ui(self):
        # Top bar: file picker
        top = tk.Frame(self, padx=10, pady=8)
        top.pack(fill=tk.X)
        tk.Label(top, text="PDF File:", font=("", 10, "bold")).pack(side=tk.LEFT)
        hint = "  (no file — Browse or drag & drop)" if _DND else "  (no file selected)"
        self.file_label = tk.Label(top, text=hint, fg="grey", anchor="w", width=46)
        self.file_label.pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Browse…", command=self._choose_file).pack(side=tk.LEFT)
        self.toc_btn = ttk.Button(top, text="Detect TOC",
                                   command=self._detect_toc, state=tk.DISABLED)
        self.toc_btn.pack(side=tk.LEFT, padx=6)
        self.pages_label = tk.Label(top, text="", fg="#555")
        self.pages_label.pack(side=tk.LEFT, padx=10)

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6)

        # Column legend
        leg = tk.Frame(self, padx=10, pady=3)
        leg.pack(fill=tk.X)
        fnt = ("", 9, "italic")
        col = "#666"
        tk.Label(leg, text="✔", width=2).pack(side=tk.LEFT)
        tk.Label(leg, text="Chapter name", width=22, font=fnt, fg=col).pack(side=tk.LEFT, padx=2)
        tk.Label(leg, text="From p.", font=fnt, fg=col).pack(side=tk.LEFT)
        tk.Label(leg, text="     To p.", font=fnt, fg=col).pack(side=tk.LEFT)
        tk.Label(leg, text="       ➔ Output file  (blank = chapter name)", font=fnt, fg=col).pack(side=tk.LEFT, padx=6)

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6)

        # Scrollable chapter list
        cont = tk.Frame(self)
        cont.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        canvas = tk.Canvas(cont, borderwidth=0, highlightthickness=0)
        sb = ttk.Scrollbar(cont, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas)
        self.scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        canvas.bind("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        # Status bar — pack first at BOTTOM so it stays at the very bottom
        self.status = tk.Label(self, text="Ready.", anchor="w",
                               bd=1, relief=tk.SUNKEN, padx=6)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

        # Progress bar — pack after status; appears above it when visible
        self._prog_var = tk.DoubleVar()
        self._prog_bar = ttk.Progressbar(self, variable=self._prog_var, maximum=100)
        # Not packed yet; shown dynamically in _set_busy()

        # Bottom action bar
        bot = tk.Frame(self, padx=10, pady=6)
        bot.pack(fill=tk.X, side=tk.BOTTOM)
        left = tk.Frame(bot)
        left.pack(side=tk.LEFT)
        ttk.Button(left, text="+ Add chapter",  command=self._add_chapter).pack(side=tk.LEFT, padx=2)
        ttk.Button(left, text="Select all",     command=lambda: self._set_all(True)).pack(side=tk.LEFT, padx=2)
        ttk.Button(left, text="Deselect all",   command=lambda: self._set_all(False)).pack(side=tk.LEFT, padx=2)
        ttk.Button(left, text="Delete all",     command=self._delete_all).pack(side=tk.LEFT, padx=4)
        right = tk.Frame(bot)
        right.pack(side=tk.RIGHT)
        self._merge_btn = tk.Button(
            right, text="⬇ Merge ALL into ONE",
            bg="#10b981", fg="white", font=("", 10, "bold"), padx=8, pady=4,
            command=self._start_merge)
        self._merge_btn.pack(side=tk.LEFT, padx=4)
        self._extract_btn = tk.Button(
            right, text="⬇ Extract (by 'File' column)",
            bg="#2563eb", fg="white", font=("", 10, "bold"), padx=8, pady=4,
            command=self._start_extract)
        self._extract_btn.pack(side=tk.LEFT, padx=4)

        # Bulk-apply bar
        bulk = tk.Frame(self, padx=10, pady=4, relief=tk.GROOVE, bd=1)
        bulk.pack(fill=tk.X, padx=6, pady=2, side=tk.BOTTOM)
        tk.Label(bulk, text="Set output file for checked rows:").pack(side=tk.LEFT)
        self.bulk_var = tk.StringVar()
        tk.Entry(bulk, textvariable=self.bulk_var, width=26).pack(side=tk.LEFT, padx=4)
        ttk.Button(bulk, text="Apply", command=self._apply_bulk).pack(side=tk.LEFT)

    # ── File loading ──────────────────────────

    def _on_drop(self, event):
        path = event.data.strip().strip("{}")
        if path.lower().endswith(".pdf"):
            self._load_pdf(path)

    def _choose_file(self):
        path = filedialog.askopenfilename(
            title="Select a PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if path:
            self._load_pdf(path)

    def _load_pdf(self, path: str):
        try:
            reader = PdfReader(path)
            total = len(reader.pages)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read PDF:\n{exc}")
            return
        self.pdf_path = path
        self._reader = reader
        self.total_pages = total
        short = os.path.basename(path)
        self.file_label.config(text=short, fg="black")
        self.pages_label.config(text=f"({total} pages)")
        self.toc_btn.config(state=tk.NORMAL)
        self._set_status(f"Loaded: {short}  —  {total} pages")
        for row in self.chapter_rows:
            row.destroy()
        self.chapter_rows.clear()

    # ── TOC detection ─────────────────────────

    def _detect_toc(self):
        if not self._reader:
            return
        chapters: list[dict] = []
        outline = self._reader.outline
        if outline:
            self._flatten_outline(self._reader, outline, chapters, 0)
        if not chapters:
            messagebox.showinfo(
                "No TOC found",
                "This PDF has no embedded table of contents.\n"
                "Please enter chapters manually.",
            )
            return
        dlg = TocDialog(self, chapters, self.total_pages, self._import_chapters)
        self.wait_window(dlg)

    def _flatten_outline(self, reader, items, result: list, level: int):
        for item in items:
            if isinstance(item, list):
                self._flatten_outline(reader, item, result, level + 1)
            else:
                try:
                    raw = reader.get_destination_page_number(item)
                    if raw is not None:
                        result.append({"title": item.title, "page": raw + 1, "level": level})
                except Exception:
                    pass

    def _import_chapters(self, chapters: list[dict]):
        for row in self.chapter_rows:
            row.selected.set(False)
        for ch in chapters:
            self._new_row(ch["title"], str(ch["start"]), str(ch["end"]))
        self._set_status(f"{len(chapters)} chapters imported from TOC.")

    # ── Chapter rows ──────────────────────────

    def _new_row(self, name: str = "", start: str = "", end: str = "") -> ChapterRow:
        idx = len(self.chapter_rows) + 1
        row = ChapterRow(
            self.scroll_frame,
            index=idx,
            on_delete=self._delete_row,
            total_pages_fn=lambda: self.total_pages,
        )
        if name:
            row.name_var.set(name)
        if start:
            row.start_var.set(start)
        if end:
            row.end_var.set(end)
        row.pack(fill=tk.X, pady=2, padx=4)
        self.chapter_rows.append(row)
        return row

    def _add_chapter(self):
        self._new_row()

    def _delete_row(self, row: ChapterRow):
        row.destroy()
        self.chapter_rows.remove(row)

    def _delete_all(self):
        if not self.chapter_rows:
            return
        if messagebox.askyesno("Confirm", "Delete all chapters?"):
            for row in self.chapter_rows:
                row.destroy()
            self.chapter_rows.clear()
            self._set_status("All chapters deleted.")

    def _set_all(self, value: bool):
        for row in self.chapter_rows:
            row.selected.set(value)

    def _apply_bulk(self):
        val = self.bulk_var.get().strip()
        count = 0
        for row in self.chapter_rows:
            if row.selected.get():
                row.set_output(val)
                count += 1
        self._set_status(f"Output file set to '{val or '(blank)'}' for {count} chapters.")

    # ── Status / progress ─────────────────────

    def _set_status(self, msg: str):
        self.status.config(text=msg)
        self.update_idletasks()

    def _set_busy(self, busy: bool):
        state = tk.DISABLED if busy else tk.NORMAL
        self._merge_btn.config(state=state)
        self._extract_btn.config(state=state)
        self.toc_btn.config(state=tk.DISABLED if (busy or not self.pdf_path) else tk.NORMAL)
        if busy:
            self._prog_var.set(0)
            self._prog_bar.pack(fill=tk.X, padx=6, side=tk.BOTTOM, after=self.status)
        else:
            self._prog_bar.pack_forget()

    def _tick(self, n: int, total: int):
        self._prog_var.set(n / total * 100)
        self.update_idletasks()

    # ── Shared validation ─────────────────────

    def _get_selected(self) -> list[ChapterRow] | None:
        if not self.pdf_path:
            messagebox.showwarning("Warning", "Please select a PDF file first.")
            return None
        rows = [r for r in self.chapter_rows if r.selected.get()]
        if not rows:
            messagebox.showwarning("Warning", "No chapters selected.")
            return None
        return rows

    def _validate_rows(self, rows: list) -> tuple[list, list]:
        """Returns (valid_chunks, errors). valid_chunks = list of (data, first_0based, last_0based)."""
        valid, errors = [], []
        for row in rows:
            d = row.get_data()
            s = parse_page_number(d["start"], self.total_pages)
            e = parse_page_number(d["end"],   self.total_pages)
            if s is None or e is None:
                errors.append(f"'{d['name']}': invalid pages ({d['start']}–{d['end']})")
            elif s > e:
                errors.append(f"'{d['name']}': start page > end page")
            else:
                valid.append((d, s, e))
        return valid, errors

    # ── Extract to separate files ─────────────

    def _start_extract(self):
        rows = self._get_selected()
        pdf_path = self.pdf_path
        if not rows or not pdf_path:
            return
        out_dir = filedialog.askdirectory(
            title="Select output folder",
            initialdir=os.path.dirname(pdf_path),
        )
        if not out_dir:
            return
        valid, errors = self._validate_rows(rows)
        if not valid:
            messagebox.showwarning("No valid chapters", "\n".join(errors))
            return

        # Group chunks into output files:
        #   • rows that share an EXPLICIT name in the File column are merged
        #     into one PDF;
        #   • rows with a blank File column each get their own PDF (named after
        #     the chapter). Duplicate filenames are made unique when writing.
        groups: list[tuple[str, list]] = []
        explicit: dict[str, list] = {}
        for d, s, e in valid:
            out = sanitize_filename(d["output"]) if d["output"].strip() else ""
            if out:
                chunks = explicit.get(out)
                if chunks is None:
                    chunks = []
                    explicit[out] = chunks
                    groups.append((out, chunks))
                chunks.append((d, s, e))
            else:
                groups.append((sanitize_filename(d["name"]) or "chapter", [(d, s, e)]))

        self._set_busy(True)

        def _worker():
            try:
                reader = PdfReader(pdf_path)
                saved, total = 0, len(groups)
                for n, (fname, chunks) in enumerate(groups, 1):
                    writer = PdfWriter()
                    for d, s, e in chunks:
                        off = len(writer.pages)
                        for i in range(s, e + 1):
                            writer.add_page(reader.pages[i])
                        writer.add_outline_item(d["name"], off)

                    path = os.path.join(out_dir, f"{fname}.pdf")
                    base, ext = os.path.splitext(path)
                    c = 1
                    while os.path.exists(path):
                        path = f"{base}_{c}{ext}"
                        c += 1
                    with open(path, "wb") as f:
                        writer.write(f)
                    saved += 1
                    self.after(0, self._set_status, f"Saved: {os.path.basename(path)}")
                    self.after(0, self._tick, n, total)

                self.after(0, self._finish, saved, out_dir, errors)
            except Exception as exc:
                self.after(0, self._finish_error, f"An error occurred during extraction:\n{exc}")

        threading.Thread(target=_worker, daemon=True).start()

    # ── Merge into one file ───────────────────

    def _start_merge(self):
        rows = self._get_selected()
        pdf_path = self.pdf_path
        if not rows or not pdf_path:
            return

        default = "Merged_Chapters.pdf"
        if len(rows) == 1:
            s = sanitize_filename(rows[0].get_data()["name"])
            if s:
                default = f"{s}.pdf"

        out_path = filedialog.asksaveasfilename(
            title="Save merged PDF as…",
            initialdir=os.path.dirname(pdf_path),
            initialfile=default,
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not out_path:
            return

        valid, errors = self._validate_rows(rows)
        if not valid:
            messagebox.showwarning("No valid chapters", "\n".join(errors))
            return

        self._set_busy(True)

        def _worker():
            try:
                reader = PdfReader(pdf_path)
                writer = PdfWriter()
                total = len(valid)
                for n, (d, s, e) in enumerate(valid, 1):
                    off = len(writer.pages)
                    for i in range(s, e + 1):
                        writer.add_page(reader.pages[i])
                    writer.add_outline_item(d["name"], off)
                    self.after(0, self._tick, n, total)

                with open(out_path, "wb") as f:
                    writer.write(f)

                self.after(0, self._set_status, f"Saved: {os.path.basename(out_path)}")
                self.after(0, self._finish, 1, os.path.dirname(out_path), errors)
            except Exception as exc:
                self.after(0, self._finish_error, f"An error occurred during merging:\n{exc}")

        threading.Thread(target=_worker, daemon=True).start()

    # ── Post-extraction callback (main thread) ─

    def _finish(self, saved: int, out_dir: str, errors: list):
        self._set_busy(False)
        title = "Completed with warnings" if errors else "Completed"
        msg = f"{saved} file(s) saved to:\n{out_dir}"
        if errors:
            msg += "\n\nWarnings:\n" + "\n".join(errors)
        msg += "\n\nOpen output folder?"
        if messagebox.askyesno(title, msg):
            open_folder(out_dir)
        self._set_status(f"Done — {saved} file(s) saved.")

    def _finish_error(self, err_msg: str):
        self._set_busy(False)
        self._set_status("Error.")
        messagebox.showerror("Error", err_msg)


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
