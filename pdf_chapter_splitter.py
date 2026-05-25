#!/usr/bin/env python3
"""
PDF Chapter Splitter
====================
Minimal GUI to extract chapters (or page ranges) from a PDF.

Dependencies:
    pip install pypdf

Usage:
    python pdf_chapter_splitter.py
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pypdf import PdfReader, PdfWriter


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def parse_page_number(value: str, total_pages: int) -> int | None:
    """Convert string → 0-based page number. Returns None if invalid."""
    value = value.strip()
    if not value:
        return None
    try:
        n = int(value)
        if 1 <= n <= total_pages:
            return n - 1  # 0-based
    except ValueError:
        pass
    return None


def extract_pages(reader: PdfReader, start: int, end: int,
                  start_inclusive: bool, end_inclusive: bool) -> PdfWriter:
    writer = PdfWriter()
    first = start if start_inclusive else start + 1
    last  = end   if end_inclusive   else end   - 1
    for i in range(first, last + 1):
        writer.add_page(reader.pages[i])
    return writer


# ──────────────────────────────────────────────
# TOC Selection Dialog
# ──────────────────────────────────────────────

class TocDialog(tk.Toplevel):
    def __init__(self, parent, chapters: list, total_pages: int, on_import):
        super().__init__(parent)
        self.title("Detected Table of Contents")
        self.resizable(True, True)
        self.minsize(520, 420)
        self.chapters = chapters        # full list [{title, page, level}]
        self.total_pages = total_pages
        self.on_import = on_import
        self.row_vars: list[tuple[tk.BooleanVar, dict]] = []
        self._build()
        self.grab_set()

    def _build(self):
        tk.Label(self, text="Select which entries to import:",
                 font=("", 10, "bold"), pady=8).pack()

        # Filter bar
        bar = tk.Frame(self, padx=10)
        bar.pack(fill=tk.X)
        tk.Label(bar, text="Show:").pack(side=tk.LEFT)
        self.show_var = tk.StringVar(value="top")
        tk.Radiobutton(bar, text="Top-level only", variable=self.show_var,
                       value="top", command=self._refresh).pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(bar, text="All entries", variable=self.show_var,
                       value="all", command=self._refresh).pack(side=tk.LEFT, padx=4)

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6, pady=4)

        # Scrollable checklist
        outer = tk.Frame(self)
        outer.pack(fill=tk.BOTH, expand=True, padx=8, pady=2)

        self._canvas = tk.Canvas(outer, borderwidth=0, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._list_frame = tk.Frame(self._canvas)

        self._list_frame.bind("<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))

        self._canvas.create_window((0, 0), window=self._list_frame, anchor="nw")
        self._canvas.configure(yscrollcommand=sb.set)
        self._canvas.bind_all("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-1*(e.delta//120), "units"))

        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._refresh()

        # Bottom buttons
        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6, pady=4)
        btns = tk.Frame(self, padx=10, pady=6)
        btns.pack(fill=tk.X)
        tk.Button(btns, text="Select all",
                  command=lambda: self._set_all(True)).pack(side=tk.LEFT, padx=2)
        tk.Button(btns, text="Deselect all",
                  command=lambda: self._set_all(False)).pack(side=tk.LEFT, padx=2)
        tk.Button(btns, text="Cancel",
                  command=self.destroy).pack(side=tk.RIGHT, padx=2)
        tk.Button(btns, text="Import selected", bg="#2563eb", fg="white",
                  font=("", 10, "bold"), padx=10,
                  command=self._import).pack(side=tk.RIGHT, padx=4)

    def _refresh(self):
        saved = {ch["title"]: var.get() for var, ch in self.row_vars}
        for w in self._list_frame.winfo_children():
            w.destroy()
        self.row_vars.clear()

        top_only = self.show_var.get() == "top"
        for ch in self.chapters:
            if top_only and ch["level"] > 0:
                continue
            default = saved.get(ch["title"], ch["level"] == 0)
            var = tk.BooleanVar(value=default)
            self.row_vars.append((var, ch))
            indent = "    " * ch["level"]
            label = f"{indent}{ch['title']}   (p. {ch['page']})"
            tk.Checkbutton(self._list_frame, text=label, variable=var,
                           anchor="w", justify="left").pack(fill=tk.X, padx=6, pady=1)

    def _set_all(self, value: bool):
        for var, _ in self.row_vars:
            var.set(value)

    def _import(self):
        selected = [ch for var, ch in self.row_vars if var.get()]
        if not selected:
            messagebox.showwarning("Warning", "No entries selected.", parent=self)
            return

        selected.sort(key=lambda c: c["page"])

        # Use full outline start pages to infer end of each selected chapter
        all_starts = sorted({ch["page"] for ch in self.chapters})

        result = []
        for ch in selected:
            start = ch["page"]
            later = [p for p in all_starts if p > start]
            end = (later[0] - 1) if later else self.total_pages
            result.append({"title": ch["title"], "start": start, "end": end})

        self.on_import(result)
        self.destroy()


# ──────────────────────────────────────────────
# Reusable widget: a chapter row
# ──────────────────────────────────────────────

class ChapterRow(tk.Frame):
    """A row in the chapter list: name, start page, end page."""

    def __init__(self, parent, index: int, on_delete, **kw):
        super().__init__(parent, **kw)
        self.index = index

        self.selected = tk.BooleanVar(value=True)
        tk.Checkbutton(self, variable=self.selected, width=2).pack(side=tk.LEFT)

        self.name_var = tk.StringVar(value=f"Chapter {index}")
        tk.Entry(self, textvariable=self.name_var, width=22).pack(side=tk.LEFT, padx=2)

        tk.Label(self, text="From p.").pack(side=tk.LEFT)
        self.start_var = tk.StringVar()
        tk.Entry(self, textvariable=self.start_var, width=6).pack(side=tk.LEFT, padx=2)

        tk.Label(self, text="To p.").pack(side=tk.LEFT)
        self.end_var = tk.StringVar()
        tk.Entry(self, textvariable=self.end_var, width=6).pack(side=tk.LEFT, padx=2)

        self.start_inc = tk.BooleanVar(value=True)
        tk.Checkbutton(self, variable=self.start_inc,
                       text="[", font=("Courier", 11, "bold")).pack(side=tk.LEFT)

        self.end_inc = tk.BooleanVar(value=True)
        tk.Checkbutton(self, variable=self.end_inc,
                       text="]", font=("Courier", 11, "bold")).pack(side=tk.LEFT)

        tk.Button(self, text="✕", fg="red", width=2,
                  command=lambda: on_delete(self)).pack(side=tk.LEFT, padx=4)

    def get_data(self):
        return {
            "selected":   self.selected.get(),
            "name":       self.name_var.get().strip() or f"chapter_{self.index}",
            "start":      self.start_var.get(),
            "end":        self.end_var.get(),
            "start_inc":  self.start_inc.get(),
            "end_inc":    self.end_inc.get(),
        }


# ──────────────────────────────────────────────
# Main window
# ──────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Chapter Splitter")
        self.resizable(True, True)
        self.minsize(680, 400)

        self.pdf_path: str | None = None
        self.total_pages: int = 0
        self.chapter_rows: list[ChapterRow] = []

        self._build_ui()

    # ── UI ────────────────────────────────────

    def _build_ui(self):
        # ── Top: file selection ──
        top = tk.Frame(self, padx=10, pady=8)
        top.pack(fill=tk.X)

        tk.Label(top, text="PDF File:", font=("", 10, "bold")).pack(side=tk.LEFT)
        self.file_label = tk.Label(top, text="(no file)", fg="gray",
                                   anchor="w", width=50)
        self.file_label.pack(side=tk.LEFT, padx=6)
        tk.Button(top, text="Browse…", command=self._choose_file).pack(side=tk.LEFT)

        self.toc_btn = tk.Button(top, text="Detect TOC",
                                 command=self._detect_toc, state=tk.DISABLED)
        self.toc_btn.pack(side=tk.LEFT, padx=6)

        self.pages_label = tk.Label(top, text="", fg="#444")
        self.pages_label.pack(side=tk.LEFT, padx=10)

        # ── Separator ──
        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6)

        # ── Column legend ──
        legend = tk.Frame(self, padx=10, pady=4, bg="#f0f0f0")
        legend.pack(fill=tk.X)
        tk.Label(legend, text="✔", width=2, bg="#f0f0f0").pack(side=tk.LEFT)
        tk.Label(legend, text="Chapter name", width=22, bg="#f0f0f0",
                 font=("", 9, "italic")).pack(side=tk.LEFT, padx=2)
        tk.Label(legend, text="From p.", bg="#f0f0f0",
                 font=("", 9, "italic")).pack(side=tk.LEFT)
        tk.Label(legend, text="      To p.", bg="#f0f0f0",
                 font=("", 9, "italic")).pack(side=tk.LEFT)
        tk.Label(legend, text="  [ incl. start   ] incl. end",
                 bg="#f0f0f0", font=("", 9, "italic")).pack(side=tk.LEFT, padx=6)

        ttk.Separator(self, orient="horizontal").pack(fill=tk.X, padx=6)

        # ── Scrollable chapter list ──
        container = tk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.scroll_frame = tk.Frame(canvas)

        self.scroll_frame.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._main_canvas = canvas
        self._bind_main_scroll()

        # ── Bottom bar ──
        bottom = tk.Frame(self, padx=10, pady=8)
        bottom.pack(fill=tk.X)

        tk.Button(bottom, text="+ Add chapter",
                  command=self._add_chapter).pack(side=tk.LEFT, padx=4)
        tk.Button(bottom, text="Select all",
                  command=lambda: self._set_all(True)).pack(side=tk.LEFT, padx=2)
        tk.Button(bottom, text="Deselect all",
                  command=lambda: self._set_all(False)).pack(side=tk.LEFT, padx=2)

        tk.Button(bottom, text="⬇  Extract selected chapters",
                  bg="#2563eb", fg="white", font=("", 10, "bold"),
                  padx=10, pady=4,
                  command=self._extract).pack(side=tk.RIGHT, padx=4)

        # ── Status bar ──
        self.status = tk.Label(self, text="", anchor="w",
                               bd=1, relief=tk.SUNKEN, padx=6)
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    def _bind_main_scroll(self):
        c = self._main_canvas
        c.bind_all("<MouseWheel>",
                   lambda e, c=c: c.yview_scroll(-1*(e.delta//120), "units"))
        # Linux scroll bindings
        c.bind_all("<Button-4>", lambda e, c=c: c.yview_scroll(-1, "units"))
        c.bind_all("<Button-5>", lambda e, c=c: c.yview_scroll(1, "units"))

    # ── Logic ────────────────────────────────

    def _choose_file(self):
        path = filedialog.askopenfilename(
            title="Select a PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            reader = PdfReader(path)
            self.total_pages = len(reader.pages)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read PDF:\n{exc}")
            return

        self.pdf_path = path
        short = os.path.basename(path)
        self.file_label.config(text=short, fg="black")
        self.pages_label.config(text=f"({self.total_pages} pages total)")
        self.toc_btn.config(state=tk.NORMAL)
        self._set_status(f"File loaded: {short}  —  {self.total_pages} pages")

        for row in self.chapter_rows:
            row.destroy()
        self.chapter_rows.clear()

        self._add_chapter()

    def _detect_toc(self):
        if not self.pdf_path:
            return
        try:
            reader = PdfReader(self.pdf_path)
        except Exception as exc:
            messagebox.showerror("Error", f"Could not read PDF:\n{exc}")
            return

        chapters: list[dict] = []
        self._flatten_outline(reader, reader.outline, chapters, level=0)

        if not chapters:
            messagebox.showinfo(
                "No TOC found",
                "This PDF has no embedded table of contents (bookmarks).\n"
                "Please enter chapters manually.",
            )
            return

        dialog = TocDialog(self, chapters, self.total_pages, self._import_toc_chapters)
        self.wait_window(dialog)
        self._bind_main_scroll()  # restore after dialog overrides bind_all

    def _flatten_outline(self, reader: PdfReader, items, result: list, level: int):
        for item in items:
            if isinstance(item, list):
                self._flatten_outline(reader, item, result, level + 1)
            else:
                try:
                    raw = reader.get_destination_page_number(item)
                    if raw is None:
                        continue
                    page_num = raw + 1  # 1-based
                    result.append({
                        "title": item.title,
                        "page": page_num,
                        "level": level,
                    })
                except Exception:
                    pass

    def _import_toc_chapters(self, chapters: list[dict]):
        """Populate chapter rows from TOC dialog selection."""
        for row in self.chapter_rows:
            row.destroy()
        self.chapter_rows.clear()

        for ch in chapters:
            idx = len(self.chapter_rows) + 1
            row = ChapterRow(self.scroll_frame, index=idx,
                             on_delete=self._delete_chapter)
            row.name_var.set(ch["title"])
            row.start_var.set(str(ch["start"]))
            row.end_var.set(str(ch["end"]))
            row.pack(fill=tk.X, pady=2, padx=4)
            self.chapter_rows.append(row)

        self._set_status(f"{len(chapters)} chapters imported from TOC.")

    def _add_chapter(self):
        idx = len(self.chapter_rows) + 1
        row = ChapterRow(self.scroll_frame, index=idx,
                         on_delete=self._delete_chapter)
        row.pack(fill=tk.X, pady=2, padx=4)
        self.chapter_rows.append(row)

    def _delete_chapter(self, row: ChapterRow):
        row.destroy()
        self.chapter_rows.remove(row)

    def _set_all(self, value: bool):
        for row in self.chapter_rows:
            row.selected.set(value)

    def _set_status(self, msg: str):
        self.status.config(text=msg)
        self.update_idletasks()

    def _extract(self):
        if not self.pdf_path:
            messagebox.showwarning("Warning", "Please select a PDF file first.")
            return

        selected = [r for r in self.chapter_rows if r.selected.get()]
        if not selected:
            messagebox.showwarning("Warning", "No chapter selected.")
            return

        initial_dir = os.path.dirname(self.pdf_path) if self.pdf_path else None
        out_dir = filedialog.askdirectory(title="Select output folder", initialdir=initial_dir)
        if not out_dir:
            return

        reader = PdfReader(self.pdf_path)
        errors = []
        saved = 0

        for row in selected:
            data = row.get_data()
            start_0 = parse_page_number(data["start"], self.total_pages)
            end_0   = parse_page_number(data["end"],   self.total_pages)

            if start_0 is None or end_0 is None:
                errors.append(f"'{data['name']}': invalid pages "
                               f"({data['start']}–{data['end']})")
                continue

            first = start_0 if data["start_inc"] else start_0 + 1
            last  = end_0   if data["end_inc"]   else end_0   - 1

            if first > last:
                errors.append(f"'{data['name']}': empty range after "
                               "applying boundary exclusivity.")
                continue

            writer = extract_pages(reader,
                                   start_0, end_0,
                                   data["start_inc"], data["end_inc"])

            safe_name = "".join(
                c if c.isalnum() or c in " _-" else "_"
                for c in data["name"]
            ).strip()
            out_path = os.path.join(out_dir, f"{safe_name}.pdf")

            base, ext = os.path.splitext(out_path)
            counter = 1
            while os.path.exists(out_path):
                out_path = f"{base}_{counter}{ext}"
                counter += 1

            with open(out_path, "wb") as f:
                writer.write(f)
            saved += 1
            self._set_status(f"Saved: {os.path.basename(out_path)}")
            self.update()  # <-- Evita il blocco della GUI durante l'estrazione

        msg = f"{saved} files saved to:\n{out_dir}"
        if errors:
            msg += f"\n\nErrors ({len(errors)}):\n" + "\n".join(errors)
            messagebox.showwarning("Completed with warnings", msg)
        else:
            messagebox.showinfo("Completed", msg)
        self._set_status(f"Extraction complete — {saved} files saved.")


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()
