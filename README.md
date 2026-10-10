# 📚 Archive.org Arabic PDF to Markdown Converter (`archive_arabic_to_markdown`)

[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![Zero Dependencies](https://img.shields.io/badge/dependencies-zero%20(stdlib%20only)-brightgreen.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A **zero-dependency** Python CLI tool that converts Arabic PDF books hosted on **Internet Archive (`archive.org`)** into clean, properly ordered, page-indexed **Markdown (`.md`)** in **~1.5 seconds per 500-page volume**.

---

## 🔍 Why This Tool Exists (المشكلة والحل)

When converting Arabic books from `archive.org` (such as `*_text.pdf` or scanned multi-volume books) using tools like Microsoft's `markitdown`, `pdfminer.six`, or `pymupdf4llm`, three issues commonly occur:

1. **Reversed Arabic Text (النص العربي معكوس):**  
   Archive.org embeds the invisible OCR layer inside `*_text.pdf` in **visual reversed RTL order** (e.g., `بلغوا عني ولو آية` is extracted backwards as `ةيا ولو ىنع اوغلب`).
2. **Slow Local OCR & CPU Compatibility Errors (`X86_V2`):**  
   Re-running OCR on 100MB–200MB scanned PDFs takes hours on older CPUs and crashes when libraries import **NumPy 2.x** on processors without `X86_V2` (`SSE4.2` / `POPCNT`) instructions.
3. **Diacritic (Harakat) OCR Noise Lines:**  
   Classical Arabic books contain vowel marks (*tashkeel*) that OCR engines often misinterpret as isolated garbage lines of single letters and numbers above each line.

### ✅ How This Script Solves It
Instead of parsing the broken PDF text layer or re-running heavy OCR locally:
- It automatically resolves any Archive.org `.pdf` or `_text.pdf` link to its companion **`*_djvu.xml`** structured OCR file on Archive.org.
- It extracts **logical forward-order Arabic text** organized by **Page (`OBJECT`) → Paragraph (`PARAGRAPH`) → Line (`LINE`) → Word (`WORD`)**.
- It normalizes Arabic Presentation Forms (`NFKC`, e.g., `ﻻ` → `لا`) and filters out floating diacritic/harakat noise lines while preserving footnotes and hadith/page references.
- It uses **only Python's built-in standard library** (`urllib`, `xml`, `unicodedata`, `re`, `json`, `argparse`) — **no `pip install` required!**

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>
```
*(No `pip install` needed — works out of the box on Python 3.8+ on Windows, Linux, macOS, and Google Colab.)*

---

### 2. Convert a Single Archive.org PDF URL
Pass any `*_text.pdf`, `*.pdf`, or `*_djvu.xml` URL from Archive.org:

```bash
python archive_arabic_to_markdown.py \
  --url https://ia801609.us.archive.org/23/items/alhelawy07/bn01_text.pdf
```

**Output:**
```text
[*] Fetching structured OCR XML: https://ia801609.us.archive.org/23/items/alhelawy07/bn01_djvu.xml
[+] Saved 'output_markdown/bn01.md' (522 pages, 646,277 chars in 1.34s)
```

---

### 3. Convert All Volumes of a Multi-Volume Book Automatically
Pass the Archive.org **item identifier** (the part after `archive.org/details/<item_id>`). The script queries the Archive.org Metadata API, discovers all volumes (`bn00` through `bn21`), and converts them all:

```bash
python archive_arabic_to_markdown.py --item alhelawy07 --output-dir ./al_bidaya_wal_nihaya
```

Or convert only specific volumes:

```bash
python archive_arabic_to_markdown.py --item alhelawy07 --volumes bn01 bn02 bn03
```

---

## ⚙️ Command-Line Options

| Flag | Description |
| :--- | :--- |
| `-u`, `--url <URL>` | Direct Archive.org URL to a `*_text.pdf`, `*.pdf`, or `*_djvu.xml` file. |
| `-i`, `--item <ITEM_ID>` | Archive.org item ID (e.g., `alhelawy07`) to auto-discover and convert all volumes. |
| `-v`, `--volumes <VOL ...>` | Optional space-separated list of volume prefixes to convert when using `--item` (e.g., `bn01 bn02`). |
| `-o`, `--output-dir <DIR>` | Output folder for generated `.md` files (default: `./output_markdown`). |
| `--keep-noise-lines` | Disable automatic filtering of floating harakat/diacritic noise lines. |
| `-h`, `--help` | Show help message and exit. |

---

## 📄 Sample Output (`bn01.md`)

```markdown
# bn01

## الصفحة 8

« بلغوا عنى ولو اية > وخدثوا عن ہیی إسرائیل ولا حرج » وحدثوا عنی ولا
تکذربوا على » وَمَنْ كذبَ عل متَعَمدَا يترا مَمَعَدَه مِنَ انار » . فهو محمول
على الإسرائيلياتِ المَشكوت عنا عندنا » فليس عندنا ما يصدَقَها ولا
ما يکذبها » فيجوز روايتها للاعتبار » وهذا هو الذی نستعمله فی کتابنا هذا »
...
```

---

## 📜 License

Released under the [MIT License](LICENSE).
"# archive_arabic_to_markdown" 
