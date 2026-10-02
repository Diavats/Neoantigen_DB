# Neoantigen Database

A curated, browsable database of cancer neoantigens: the tumour mutation, the mutant peptide it creates, the HLA molecule that presents it, the predicted binding and immunogenicity, and the experimental evidence that T cells respond. The curation was compiled by a student team from published literature.

The team curates in an Excel workbook. A Python script loads that workbook into PostgreSQL, and a FastAPI server serves both a small JSON API and the website.

## Features

- **Database tab:** every record, shown with the same 22 columns, grouped under the same five headings, as the `Database` sheet of the workbook (the sheet's row counter, S. No., is left out on purpose).
- **One tab per gene** (BRAF, EGFR, IDH1, KRAS, PIK3CA, TP53). Each shows that gene's records plus any extra reference tables the curator added (KRAS mutation catalogue, BRAF V600E frequency table, EGFR curated table, summary and column guide).
- **ELISpot plate map:** each record is one well of a 96-well plate, with spots drawn in proportion to the immunogenicity the source reported. Point at a well to read it, and click it to jump to its row.
- **Legacy tab:** an older summary table (`Sheet1`). Links that look automatically generated (each one is the link above with its last number increased by one) are flagged in red as unverified.
- **Search** across gene, mutation, location, cancer type, peptide sequences, HLA, UniProt, PMID, annotator, assay and clinical trial.
- **Record page:** the full record, grouped exactly like the sheet, with links to the source paper and PubMed.
- **Faithful values:** every value is stored as text exactly as the curators wrote it (`>1000`, `12.4 nM`, `Low (<0.2)`), never forced into a number.

## Tech stack

| Part | Technology |
|---|---|
| Database | PostgreSQL 16 (Docker container) |
| Backend | Python 3.11, FastAPI, SQLAlchemy, Uvicorn |
| Data loading | openpyxl (reads the Excel file directly, including hidden hyperlinks) |
| Frontend | Plain HTML, CSS and JavaScript, with no framework and no build step |
| Font | Atkinson Hyperlegible Next and Mono (Google Fonts), chosen so I, l, 1 and O, 0 never look alike in peptide sequences |

## Project structure

```
neoantigen-site/
├── backend/
│   ├── main.py            # FastAPI app: database tables + API + serves the frontend
│   ├── ingest.py          # loads the Excel workbook into PostgreSQL
│   ├── test_ingest.py     # self-check for the suspicious-link detector
│   ├── requirements.txt
│   └── .env.example       # optional DATABASE_URL override
├── frontend/
│   ├── index.html         # main page skeleton (header, tabs, plate, tables)
│   ├── style.css          # colours, layout, responsive rules
│   ├── app.js             # fetches data from the API and draws the page
│   └── detail.html        # single-record page
└── data/                  # put "Neoantigen data.xlsx" here (not committed)
```

## Setup

Requirements: Python 3.11, Docker Desktop.

> The pinned `psycopg2-binary==2.9.9` has no wheels for Python 3.13, so use Python 3.11.

```powershell
# 1. Start PostgreSQL in Docker (first time only: creates the container)
docker run -d --name neoantigen-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=neoantigen -p 5432:5432 -v neoantigen-pgdata:/var/lib/postgresql/data postgres:16
#    Every later time, just:
docker start neoantigen-pg

# 2. Create the Python environment and install dependencies
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 3. Put the workbook in data/ and load it
.\.venv\Scripts\python ingest.py "..\data\Neoantigen data.xlsx"

# 4. Run the server
.\.venv\Scripts\python -m uvicorn main:app --reload --port 8000
```

Open <http://127.0.0.1:8000>. Gene tabs can be opened directly, e.g. <http://127.0.0.1:8000/#KRAS>.

Run step 3 again whenever the workbook changes. It replaces the old data completely, so rows are never duplicated.

To use a different database, copy `backend/.env.example` to `backend/.env` and edit `DATABASE_URL`.

## How the workbook is read

| Sheet | Goes to |
|---|---|
| `Database` | Main records table |
| `valerie`, `Manya`, `Ehtesham` | Main records table (same 23 columns, same order); the sheet's name fills Annotator when it's empty |
| `Eshan` | KRAS tab: reference tables |
| `Abhishek` | BRAF tab: reference table |
| `Ashutosh`, `Ashutosh_Summary`, `Ashutosh_column_metadata` | EGFR tab: reference tables |
| `Sheet1` | Legacy tab, with suspicious links flagged |
| `Sheet10`, `ekta` | Skipped (empty / no table) |

Sheets that hold several small tables separated by blank rows are split into separate tables. The heading row is the first row that fills most of the table's width. Template rows (cells like `<cancer type>`) are dropped.

## API

| Endpoint | Returns |
|---|---|
| `GET /api/health` | `{"ok": true}` |
| `GET /api/tabs` | total record count, the genes with their counts, and whether a Legacy table exists |
| `GET /api/neoantigens?gene=&q=&sort=&order=&limit=&offset=` | records, optionally filtered by gene and/or search text |
| `GET /api/neoantigens/{id}` | one record |
| `GET /api/references?tab=KRAS` | the reference tables for a tab |

## Tests

```powershell
cd backend
.\.venv\Scripts\python test_ingest.py     # prints "all checks passed"
```

## Known data issues (to be checked by the curators)

- KRAS wild-type peptide `VGEGFGKK` (Database sheet) does not match the KRAS reference sequence around codon 12 (UniProt P01116).
- `Abhishek` sheet: the heading "Research Article Link" sits over the percentages column; the links are in the next, untitled column.
- `Ehtesham` sheet, row 5: columns are shifted (Evidence Type contains `P04637`, Assay Method contains `HLA-A*11`).
- Several BRAF source links carry `?utm_source=gemini`; each should be opened and checked once.
- `Sheet1`: 25 links follow a counting-up pattern and are flagged on the Legacy tab.
