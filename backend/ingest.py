"""
ingest.py: copies the Excel sheet into the database.

Think of it like this: the Excel file is the notebook the team writes in.
The database is the clean copy the website reads from. Every time the notebook
changes, run this script and it throws away the old copy and makes a fresh one.

Usage:
    .venv\\Scripts\\python ingest.py "..\\data\\Neoantigen data.xlsx"

What goes where:
  * 'Database' tab                    -> main table (every row is one neoantigen record)
  * valerie / Manya / Ehtesham tabs   -> ALSO the main table (they use the same columns)
  * Eshan, Abhishek, Ashutosh tabs    -> extra tables shown on their gene's tab
  * Sheet1                            -> the 'Legacy' tab, with made-up-looking links flagged
"""
import argparse
import re
import sys

import openpyxl

from main import Base, Neoantigen, ReferenceTable, SessionLocal, engine

# The main table's columns, in the same left-to-right order as the 'Database' tab.
# Column A of the sheet goes into s_no, column B into data_source, and so on.
MAIN_COLUMNS = [
    "s_no", "data_source", "pmid",
    "cancer_type", "cancer_stage", "treatment_response",
    "gene", "mutation_type", "location", "hotspot_recurrent",
    "wild_type_sequence", "mutant_sequence", "peptide_length", "source_protein_uniprot",
    "hla", "predicted_binding_affinity", "immunogenicity_score", "tools_used",
    "evidence_type", "assay_method", "immunogenic_status", "clinical_trial",
    "annotator",
]

# Tabs that look exactly like 'Database' (same 23 columns, same order).
# The value is the person's name, used as Annotator when a row leaves it empty.
SAME_AS_DATABASE = {"Database": None, "valerie": "Valerie", "Manya": "Manya", "Ehtesham": "Ehtesham"}

# Tabs with their own layout, and the website tab each one belongs to.
REFERENCE_SHEETS = {
    "Eshan": "KRAS",
    "Abhishek": "BRAF",
    "Ashutosh": "EGFR",
    "Ashutosh_Summary": "EGFR",
    "Ashutosh_column_metadata": "EGFR",
    "Sheet1": "Legacy",
}


def cell_text(cell):
    """
    Read one Excel cell as clean text.
    Excel stores 24 as 24.0, so whole numbers lose their ".0".
    Empty cells and cells with only spaces become None (meaning "nothing here").
    """
    v = cell.value
    if v is None or not isinstance(v, (str, int, float)):   # formulas like =UNIQUE(...) are skipped
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    v = str(v).strip()
    return v or None


def cell_link(cell):
    """The web address hidden behind a cell (like Ehtesham's cells that just say 'Link'), or None."""
    return cell.hyperlink.target if cell.hyperlink and cell.hyperlink.target else None


def find_header_row(ws, must_contain):
    """Find the row number whose cells include the word `must_contain` (e.g. 'Mutant')."""
    for row in ws.iter_rows():
        if any(must_contain in (cell_text(c) or "") for c in row):
            return row[0].row
    raise ValueError(f"No header row containing {must_contain!r} in tab {ws.title!r}")


def read_main_rows(ws, default_annotator):
    """Read the records from a tab shaped like 'Database'. Returns a list of dictionaries."""
    first_data_row = find_header_row(ws, "Mutant") + 1     # data starts right under the headings
    records = []
    for row in ws.iter_rows(min_row=first_data_row):
        cells = row[: len(MAIN_COLUMNS)]
        record = {name: cell_text(c) for name, c in zip(MAIN_COLUMNS, cells)}
        if not record["gene"]:                              # a row with no gene is an empty row
            continue
        # Ehtesham's tab has "Reference Link" (a cell saying 'Link') where Database has Annotator.
        last = cells[-1] if len(cells) == len(MAIN_COLUMNS) else None
        if last is not None and cell_link(last):
            record["reference_link"] = cell_link(last)
            record["annotator"] = None
        record["annotator"] = record["annotator"] or default_annotator
        record["source_sheet"] = ws.title.strip()
        records.append(record)
    return records


def split_into_blocks(ws):
    """
    Some tabs hold more than one small table, separated by empty rows.
    This cuts a tab into those blocks. Each block is a list of rows, each row a list of cells.
    Fully empty columns are dropped so tables don't get blank stripes.
    """
    blocks, current = [], []
    for row in ws.iter_rows():
        cells = [{"text": cell_text(c), "href": cell_link(c)} for c in row]
        if any(c["text"] for c in cells):
            current.append(cells)
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    cleaned = []
    for block in blocks:
        width = max(len(r) for r in block)
        keep = [i for i in range(width) if any(i < len(r) and r[i]["text"] for r in block)]
        cleaned.append([[r[i] if i < len(r) else {"text": None, "href": None} for i in keep] for r in block])
    return cleaned


def find_suspect_links(urls):
    """
    Spot links that look made up. The tell: a link that is EXACTLY the link above it,
    except its last number is one bigger (…/13208, then …/13209, then …/13210).
    Real papers almost never sit at counting-up addresses, so every link after
    the first one in such a run is flagged. The first stays unflagged; it may be real.

    Takes a list of links (None where there is no link) and returns True/False for each.
    """
    flags = [False] * len(urls)
    for i in range(1, len(urls)):
        a, b = urls[i - 1], urls[i]
        ma = a and re.match(r"^(.*?)(\d+)(\D*)$", a)       # split into: start, last number, end
        mb = b and re.match(r"^(.*?)(\d+)(\D*)$", b)
        if ma and mb and ma.group(1) == mb.group(1) and ma.group(3) == mb.group(3) \
                and int(mb.group(2)) == int(ma.group(2)) + 1:
            flags[i] = True
    return flags


def read_reference_tables(ws, tab):
    """Turn one reference tab into ReferenceTable rows (one per block)."""
    tables = []
    for block in split_into_blocks(ws):
        filled = [sum(1 for c in r if c["text"]) for r in block]
        # The headings row is the first row that fills most of the table's width.
        # Rows above it with a single word or sentence are titles (e.g. "EGFR", "BRAF (V600E) ...").
        h = next((i for i, n in enumerate(filled) if n >= max(2, 0.6 * max(filled))), None)
        if h is None:                                       # a one-column list of notes
            title, header, rows = block[0][0]["text"], [{"text": "Notes"}], block[1:]
        else:
            titles = [next(c["text"] for c in r if c["text"]) for r, n in zip(block[:h], filled) if n == 1]
            title, header, rows = (" ".join(titles) or None), block[h], block[h + 1:]
        if not rows:                                        # a heading with no rows under it: skip
            continue
        # Ashutosh's last row is a fill-in template like "<cancer type>": not real data.
        rows = [r for r in rows if not any((c["text"] or "").startswith("<") for c in r)]
        # A column with no heading is kept as "Untitled column" so no data is hidden,
        # EXCEPT a helper list whose every value already appears in the first column
        # (Sheet1's column K is a leftover =UNIQUE() list of the gene names).
        first_col = {r[0]["text"] for r in rows}
        def is_helper(i):
            values = {r[i]["text"] for r in rows if r[i]["text"]}
            return not header[i]["text"] and values <= first_col
        keep = [i for i in range(len(header)) if not is_helper(i)]
        columns = [header[i]["text"] or "Untitled column" for i in keep]
        rows = [[r[i] for i in keep] for r in rows]
        if tab == "Legacy":                                 # flag counting-up links in the old sheet
            link_col = next((i for i, n in enumerate(columns) if "link" in n.lower()), None)
            if link_col is not None:
                urls = [r[link_col]["href"] or r[link_col]["text"] for r in rows]
                for r, bad in zip(rows, find_suspect_links(urls)):
                    r[link_col]["suspect"] = bad
        tables.append(ReferenceTable(tab=tab, title=title, source_sheet=ws.title.strip(), columns=columns, rows=rows))
    return tables


def main():
    ap = argparse.ArgumentParser(description="Load the Neoantigen Excel file into the database.")
    ap.add_argument("path", help="path to the .xlsx file")
    args = ap.parse_args()

    wb = openpyxl.load_workbook(args.path)
    sheets = {ws.title.strip(): ws for ws in wb.worksheets}   # "Manya " has a stray space; strip it

    # 1. Read everything first. If the file is broken we stop here, before touching the database.
    records = []
    for name, annotator in SAME_AS_DATABASE.items():
        if name in sheets:
            records += read_main_rows(sheets[name], annotator)
    tables = []
    for name, tab in REFERENCE_SHEETS.items():
        if name in sheets:
            tables += read_reference_tables(sheets[name], tab)
    ignored = [n for n in sheets if n not in SAME_AS_DATABASE and n not in REFERENCE_SHEETS]
    flagged = sum(1 for t in tables for r in t.rows for c in r if c.get("suspect"))   # count before saving

    # 2. Throw away the old copy and write the new one, all in one go.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.add_all(Neoantigen(**r) for r in records)
        session.add_all(tables)
        session.commit()

    print(f"main table: {len(records)} records")
    for name in SAME_AS_DATABASE:
        print(f"   from {name}: {sum(r['source_sheet'] == name for r in records)}")
    print(f"reference tables: {len(tables)} ({flagged} suspicious links flagged)")
    if ignored:
        print(f"tabs ignored (empty or unrecognised): {ignored}", file=sys.stderr)


if __name__ == "__main__":
    main()
