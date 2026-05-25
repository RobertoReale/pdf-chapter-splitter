# PDF Chapter Splitter

A lightweight desktop GUI to extract chapters or arbitrary page ranges from a PDF into separate files.

## Features

- Browse and load any PDF file
- Define multiple named chapters with custom page ranges
- Toggle inclusive/exclusive boundaries for start and end pages
- Select/deselect individual chapters before extracting
- Automatically avoids overwriting existing files (appends a numeric suffix)
- Scrollable chapter list for PDFs with many sections

## Requirements

- Python 3.10+
- [pypdf](https://pypdf.readthedocs.io/)

## Installation

```bash
pip install pypdf
```

No other dependencies beyond the Python standard library (`tkinter` is included with most Python installations).

## Usage

```bash
python pdf_chapter_splitter.py
```

1. Click **Browse…** to open a PDF file.
2. Click **+ Add chapter** to add a row.
3. Fill in the chapter name, start page, and end page (1-based).
4. Use the **[** and **]** checkboxes to make boundaries inclusive (checked) or exclusive (unchecked).
5. Click **⬇ Extract selected chapters** and choose an output folder.

Each selected chapter is saved as a separate PDF named after the chapter name.

## License

MIT
