"""
main.py: the web server for the Neoantigen Database.

What this file does, in plain words:
  1. It connects to the PostgreSQL database (the big filing cabinet where the data lives).
  2. It describes the two kinds of "drawers" in that cabinet (the two tables).
  3. It answers questions from the website, like "give me all KRAS records".
  4. It also hands the browser the website files (HTML, CSS, JS) from the frontend folder.

Run it with:   .venv\\Scripts\\python -m uvicorn main:app --reload --port 8000
"""
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy import JSON, Column, Integer, Text, create_engine, or_
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Read settings from a .env file if there is one (there doesn't have to be).
load_dotenv()

# The address of the database. If nobody set DATABASE_URL, use the local Docker one.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/neoantigen",
)

engine = create_engine(DATABASE_URL, future=True)              # the phone line to the database
SessionLocal = sessionmaker(bind=engine, autoflush=False)      # makes one "conversation" per request
Base = declarative_base()                                      # the parent of every table below


class Neoantigen(Base):
    """
    Drawer 1: one row = one neoantigen record.
    The columns are EXACTLY the columns of the 'Database' tab in the Excel sheet, in the same order.
    Every value is stored as text (Text), because the sheet writes things like ">1000" or
    "12.4 nM" or "Low (<0.2)". Turning those into numbers would change what the curators wrote.
    """
    __tablename__ = "neoantigens"

    id = Column(Integer, primary_key=True)        # a number the database gives each row

    # --- first columns (no group in the sheet) ---
    s_no = Column(Text)                           # S. No.
    data_source = Column(Text)                    # Data Source (usually a link to the paper)
    pmid = Column(Text)                           # PMID (PubMed ID of the paper)
    # --- group: Cancer and clinical context ---
    cancer_type = Column(Text)
    cancer_stage = Column(Text)
    treatment_response = Column(Text)
    # --- group: Mutation ---
    gene = Column(Text, index=True)               # index = a bookmark so finding by gene is fast
    mutation_type = Column(Text)
    location = Column(Text)
    hotspot_recurrent = Column(Text)
    # --- group: Peptide Information ---
    wild_type_sequence = Column(Text)
    mutant_sequence = Column(Text)
    peptide_length = Column(Text)
    source_protein_uniprot = Column(Text)
    # --- group: HLA and Predicted Data ---
    hla = Column(Text)
    predicted_binding_affinity = Column(Text)
    immunogenicity_score = Column(Text)
    tools_used = Column(Text)
    # --- group: Evidence ---
    evidence_type = Column(Text)
    assay_method = Column(Text)
    immunogenic_status = Column(Text)
    clinical_trial = Column(Text)
    # --- last column ---
    annotator = Column(Text)

    # --- two extra notes we add ourselves (not columns in the sheet) ---
    reference_link = Column(Text)                 # Ehtesham's sheet has a "Link" column; we keep its address
    source_sheet = Column(Text)                   # which Excel tab this row came from

    def to_dict(self):
        """Turn one row into a plain dictionary, so it can be sent to the browser as JSON."""
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ReferenceTable(Base):
    """
    Drawer 2: the other tabs of the Excel file (Eshan's KRAS list, Abhishek's BRAF table,
    Ashutosh's EGFR tables, and the old Sheet1). Each tab has different columns, so instead
    of a fixed shape we store each table whole: its column names plus its rows.
    """
    __tablename__ = "reference_tables"

    id = Column(Integer, primary_key=True)
    tab = Column(Text, index=True)     # which website tab shows it: "KRAS", "BRAF", "EGFR" or "Legacy"
    title = Column(Text)               # a heading for the table
    source_sheet = Column(Text)        # the Excel tab it came from
    columns = Column(JSON)             # list of column names, e.g. ["Gene", "Mutation", ...]
    rows = Column(JSON)                # list of rows; each row is a list of cells
    # A cell is either plain text, or {"text": ..., "href": link, "suspect": true/false}.
    # "suspect" marks links that look made up (see find_suspect_links in ingest.py).

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


# Make the drawers if they don't exist yet (does nothing if they already do).
Base.metadata.create_all(engine)


def get_db():
    """Open a conversation with the database for one request, and always close it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="Neoantigen Database")


@app.middleware("http")
async def always_fresh(request, call_next):
    """
    Tell the browser: "before using your saved copy of a file, check with me if it changed."
    Without this, a browser can keep showing an OLD style.css or app.js after we update them.
    """
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache"
    return response

# The columns a visitor may sort by: any real column of the Neoantigen table.
SORTABLE = set(Neoantigen.__table__.columns.keys())

# The columns the search box looks inside.
SEARCHED = [
    Neoantigen.gene, Neoantigen.mutation_type, Neoantigen.location, Neoantigen.cancer_type,
    Neoantigen.mutant_sequence, Neoantigen.wild_type_sequence, Neoantigen.hla,
    Neoantigen.source_protein_uniprot, Neoantigen.pmid, Neoantigen.annotator,
    Neoantigen.assay_method, Neoantigen.clinical_trial,
]


@app.get("/api/health")
def health():
    """A tiny 'are you alive?' check."""
    return {"ok": True}


@app.get("/api/neoantigens")
def list_neoantigens(
    q: Optional[str] = None,                     # words typed in the search box
    gene: Optional[str] = None,                  # only this gene (used by the gene tabs)
    sort: str = "id",                            # which column to sort by
    order: str = Query("asc", pattern="^(asc|desc)$"),
    limit: int = Query(500, ge=1, le=500),       # at most this many rows at once
    offset: int = Query(0, ge=0),                # skip this many rows first
    db: Session = Depends(get_db),
):
    """Give back records, optionally only one gene and/or matching the search words."""
    if sort not in SORTABLE:
        raise HTTPException(400, f"cannot sort by {sort!r}")

    query = db.query(Neoantigen)
    if gene:
        query = query.filter(Neoantigen.gene == gene)
    if q:
        like = f"%{q.strip()}%"                  # % means "anything before/after"
        query = query.filter(or_(*[col.ilike(like) for col in SEARCHED]))   # ilike = ignore UPPER/lower case

    total = query.count()
    column = getattr(Neoantigen, sort)
    query = query.order_by(column.desc() if order == "desc" else column.asc(), Neoantigen.id)
    rows = query.offset(offset).limit(limit).all()
    return {"total": total, "limit": limit, "offset": offset, "items": [r.to_dict() for r in rows]}


@app.get("/api/neoantigens/{item_id}")
def get_neoantigen(item_id: int, db: Session = Depends(get_db)):
    """Give back one record by its id (used by the record page)."""
    row = db.get(Neoantigen, item_id)
    if not row:
        raise HTTPException(404, "No record with that id.")
    return row.to_dict()


@app.get("/api/tabs")
def tabs(db: Session = Depends(get_db)):
    """
    Tell the website which tabs to draw, and how many records each has.
    Genes come from the data itself, so a new gene in the sheet gets a tab automatically.
    """
    genes = [g for (g,) in db.query(Neoantigen.gene).distinct().order_by(Neoantigen.gene) if g]
    ref_tabs = [t for (t,) in db.query(ReferenceTable.tab).distinct() if t]
    names = sorted(set(genes) | {t for t in ref_tabs if t != "Legacy"})
    counts = {g: db.query(Neoantigen).filter(Neoantigen.gene == g).count() for g in names}
    return {
        "total": db.query(Neoantigen).count(),
        "genes": [{"name": g, "records": counts[g]} for g in names],
        "legacy": "Legacy" in ref_tabs,
    }


@app.get("/api/references")
def references(tab: str, db: Session = Depends(get_db)):
    """Give back the extra tables that belong to one tab (for example tab=KRAS)."""
    rows = db.query(ReferenceTable).filter(ReferenceTable.tab == tab).order_by(ReferenceTable.id).all()
    return [r.to_dict() for r in rows]


# --- the website itself ---
# Everything not starting with /api is a file from the frontend folder (index.html, style.css ...).
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
