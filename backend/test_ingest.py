"""
A tiny check for the "made-up link" detector in ingest.py.
Run it with:   .venv\\Scripts\\python test_ingest.py
If it prints "all checks passed", the detector works. If not, it stops and shows which check failed.
"""
from ingest import find_suspect_links

links = [
    "https://www.spandidos-publications.com/10.3892/ol.2022.13208",   # first of a run: could be real
    "https://www.spandidos-publications.com/10.3892/ol.2022.13209",   # +1: suspicious
    "https://www.spandidos-publications.com/10.3892/ol.2022.13210",   # +1 again: suspicious
    "https://link.springer.com/article/10.1186/s13045-019-0787-5",    # different site: new run starts
    "https://link.springer.com/article/10.1186/s13045-019-0787-6",    # +1: suspicious
    "https://www.ovid.com/jnls/cmj/fulltext/10.1097/cm9.0000000000002181",  # repeated link...
    "https://www.ovid.com/jnls/cmj/fulltext/10.1097/cm9.0000000000002181",  # ...same, not counting up
    None,                                                              # empty cell
    "https://pubmed.ncbi.nlm.nih.gov/27959684/",                       # unrelated
]
expected = [False, True, True, False, True, False, False, False, False]

assert find_suspect_links(links) == expected, find_suspect_links(links)
assert find_suspect_links([]) == []
print("all checks passed")
