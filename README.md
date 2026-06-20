# PDF Chapter Splitter

A robust, GUI-based Python application that allows you to easily extract chapters or specific page ranges from a PDF. You can output them into separate PDF files or merge your selected chapters into a single unified document.

## Features

- 📑 **Auto-detect Table of Contents**: Automatically reads the embedded outline/TOC of the PDF and allows you to import chapters with a single click.
- 🎯 **Manual Chapter Entry**: Add custom ranges and names if your PDF doesn't have an embedded TOC.
- 🗂️ **Extract & Merge**: 
  - **Extract**: Export all selected chapters into their own separate PDF files with customizable filenames.
  - **Merge**: Combine all selected chapters into a single PDF document.
- 🖱️ **Drag and Drop**: Simply drag a PDF onto the window to open it (requires `tkinterdnd2`).
- 🛡️ **Robust & Stable**: Multi-threaded extraction ensures the UI never freezes, even with large PDFs. Built-in exception handling safely warns you if files are locked or cannot be written.

## Prerequisites

Ensure you have Python 3.10+ installed.

Install the required dependencies via pip:

```bash
pip install pypdf
pip install tkinterdnd2  # Optional, but recommended to enable drag & drop
```

## Usage

1. Run the script:
   ```bash
   python pdf_chapter_splitter.py
   ```
2. Click **Browse...** or **drag and drop** a PDF file into the application window.
3. Click **Detect TOC** to automatically import chapters, or click **+ Add chapter** to define page ranges manually.
4. Select the chapters you want to extract using the checkboxes on the left.
5. Provide custom output filenames in the `➔ Output file` column (optional).
6. Click **⬇ Extract (by 'File' column)** to save chapters as separate files, or **⬇ Merge ALL into ONE** to bundle them together.

## Technical Details

- **Type Checked**: The codebase is 100% statically typed and verified using Pyright and Mypy.
- **Library Stack**: Pure Python using `tkinter` for the interface and `pypdf` for PDF manipulations.

## License

MIT License
