/*
  app.js: makes the main page work.

  The big idea: the page asks the server for data, then draws it.
    - Which tab is open is remembered in the address bar (e.g. ...#KRAS),
      so refreshing the page or sharing the link opens the same tab.
    - Typing in the search box asks the server again, with the words.

  Reading guide (the parts of this file, in order):
    1. Small helpers (finding elements, making text safe)
    2. Reading the curators' text (status, spots)
    3. Drawing the tabs
    4. Drawing the ELISpot plate
    5. Drawing the records table
    6. Drawing the extra tables (other Excel tabs)
    7. Putting it all together, and listening for clicks and typing
*/

/* ---------- 1. Small helpers ---------- */

// $("id") finds the element with that id on the page. Just a shorter way to write it.
const $ = (id) => document.getElementById(id);

// Makes text safe to put inside HTML. Without this, a "<" in the data could break the page.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Is this text a web address? (Only http/https: safe to turn into a link.)
const isUrl = (s) => /^https?:\/\/\S+$/i.test(String(s ?? "").trim());

// Turns a web address into a link that opens in a new tab. The link text is the website's name.
function link(url, text) {
  const host = text || new URL(url).hostname.replace(/^www\./, "");
  return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(host)}</a>`;
}

// Shows a cell's text, or a faded "Not reported" if it is empty.
// Words like "Not reported" or "N/A" written by the curators are faded too, so gaps are easy to spot.
function show(value) {
  if (value === null || value === undefined || value === "") return '<span class="none">Not reported</span>';
  const text = esc(value);
  return /^(not (reported|specified|applicable|explicitly reported|tested|directly)|n\/?a\b|none\b)/i.test(value)
    ? `<span class="none">${text}</span>` : text;
}

// Shows a cell that may hold one or more web addresses (separated by ";"), or plain text.
function showLinks(value) {
  if (!value) return show(value);
  const parts = String(value).split(/\s*;\s*/);
  return parts.every(isUrl) ? parts.map((u) => link(u)).join("<br>") : show(value);
}


/* ---------- 2. Reading the curators' text ---------- */

// The sheet writes the result in many ways ("Immunogenic (spontaneous T cells…)", "Non-Immunogenic",
// "Weakly Immunogenic", "Not tested"). This boils it down to one of four simple words.
function statusOf(record) {
  const s = (record.immunogenic_status || "").toLowerCase();
  if (s.includes("weak")) return "weak";
  if (s.startsWith("non") || s.includes("non-immunogenic")) return "no";
  if (s.startsWith("immunogenic")) return "yes";
  return "untested";
}
const STATUS_NAME = { yes: "Immunogenic", weak: "Weakly immunogenic", no: "Non-immunogenic", untested: "Not tested / not reported" };

// How many spots a well gets. If the sheet gives a score like "0.89 (High …)", use it (0.89 → 20 spots).
// Otherwise use the status: immunogenic wells are crowded, non-immunogenic ones nearly empty.
function spotsFor(record) {
  const m = (record.immunogenicity_score || "").match(/^\s*(0?\.\d+|1(\.0+)?)\b/);
  if (m) return Math.round(parseFloat(m[1]) * 22);
  return { yes: 16, weak: 6, no: 2, untested: 0 }[statusOf(record)];
}

// A "random" number maker that always gives the same numbers for the same seed,
// so a record's spots sit in the same places every time the page loads.
function seededRandom(seed) {
  let x = seed * 9301 + 49297;
  return () => ((x = (x * 16807) % 2147483647) / 2147483647);
}

// Wells are named like a real 96-well plate: rows A to H, columns 1 to 12. Well 0 = A1, well 13 = B2.
const wellName = (i) => "ABCDEFGH"[Math.floor(i / 12)] + ((i % 12) + 1);


/* ---------- 3. Drawing the tabs ---------- */

const state = { tab: "Database", q: "", tabs: null, records: [] };

// A tiny drawing of a stained tissue section: a pink blob with dark nuclei (like H&E stain).
const TISSUE = `<svg viewBox="0 0 24 20" aria-hidden="true"><path d="M4 9c1-5 7-7 11-5s6 6 4 9-8 5-12 3-4-4-3-7z" fill="#f2a7c8"/>
  <circle cx="9" cy="8" r="1.4" fill="#0b1f4d"/><circle cx="13" cy="11" r="1.2" fill="#0b1f4d"/>
  <circle cx="15.5" cy="7" r="1.1" fill="#0b1f4d"/><circle cx="10" cy="13" r="1.1" fill="#0b1f4d"/></svg>`;

function drawTabs() {
  const t = state.tabs;
  const list = [{ name: "Database", n: t.total }, ...t.genes.map((g) => ({ name: g.name, n: g.records || "ref." }))];
  if (t.legacy) list.push({ name: "Legacy", n: state.legacyFlags ?? "!", cls: "legacy-tab" });
  // Each tab is drawn as a glass microscope slide: a frosted label (name + count) and a clear
  // glass end with a tiny stained tissue section on it (TISSUE, drawn below).
  $("tabs").innerHTML = list.map((x) =>
    `<button role="tab" class="${x.cls || ""}" aria-selected="${x.name === state.tab}" data-tab="${esc(x.name)}">
       <span class="label">${esc(x.name)} <span class="n">${esc(x.n)}</span></span><span class="glass">${TISSUE}</span></button>`).join("");
  // On a phone the tabs scroll sideways: slide the chosen one into view.
  document.querySelector('.tabs [aria-selected="true"]')?.scrollIntoView({ block: "nearest", inline: "nearest" });
}


/* ---------- 4. Drawing the ELISpot plate ---------- */

function drawPlate(records) {
  let html = '<span></span>';                                            // empty corner
  for (let c = 1; c <= 12; c++) html += `<span class="label">${c}</span>`;  // column numbers 1–12
  for (let w = 0; w < 96; w++) {
    if (w % 12 === 0) html += `<span class="label">${"ABCDEFGH"[w / 12]}</span>`;  // row letter
    const r = records[w];
    if (!r) { html += '<span class="well unused" aria-hidden="true"></span>'; continue; }  // no record here
    // Scatter the spots inside the well (positions are % so wells can be any size).
    const rnd = seededRandom(r.id);
    const spots = Array.from({ length: spotsFor(r) }, (_, k) => {
      const angle = rnd() * Math.PI * 2, dist = Math.sqrt(rnd()) * 34, size = 6 + rnd() * 9;  // % of the well
      return `<i style="width:${size}%;height:${size}%;left:${50 + Math.cos(angle) * dist - size / 2}%;` +
             `top:${50 + Math.sin(angle) * dist - size / 2}%;animation-delay:${k * 22}ms"></i>`;
    }).join("");
    html += `<button class="well ${statusOf(r)}" data-id="${r.id}" data-well="${wellName(w)}"
               aria-label="Well ${wellName(w)}: ${esc(r.gene)} ${esc(r.location || "")}, ${STATUS_NAME[statusOf(r)]}">${spots}</button>`;
  }
  $("plate").innerHTML = html;

  // The key: how many wells of each kind.
  const count = (s) => records.filter((r) => statusOf(r) === s).length;
  $("key").innerHTML = ["yes", "weak", "no", "untested"].map((s) =>
    `<li><span class="pill ${s}">${STATUS_NAME[s]}</span><b>${count(s)}</b></li>`).join("");
  $("plate-title").textContent = state.tab === "Database" ? "Plate read-out" : `${state.tab} plate read-out`;
}

// When the mouse points at a well, describe it in the box beside the plate.
function describeWell(well) {
  const r = state.records.find((x) => x.id === Number(well.dataset.id));
  if (!r) return;
  $("well-info").innerHTML =
    `<strong>Well ${esc(well.dataset.well)}: ${esc(r.gene)} ${esc(r.location || r.mutation_type || "")}</strong><br>` +
    `<span class="mono">${esc(r.mutant_sequence || "No sequence reported")}</span> on ${esc(r.hla || "HLA not reported")}<br>` +
    `${esc(r.immunogenic_status || "Not tested")}`;
}


/* ---------- 5. Drawing the records table ---------- */

// One row of the table. The cells come in the SAME order as the Excel 'Database' tab
// (minus S. No., which only counted rows in the spreadsheet). Click the gene to open the full record.
function recordRow(r, i) {
  const pmid = /^\d{5,9}$/.test(r.pmid || "")                                     // a plain PubMed number?
    ? link(`https://pubmed.ncbi.nlm.nih.gov/${r.pmid}/`, r.pmid) : show(r.pmid);
  const source = isUrl(r.data_source) ? link(r.data_source) : show(r.data_source);
  const clip = (v) => `<div class="clip">${show(v)}</div>`;                       // long text: show 4 lines
  const s = statusOf(r);
  return `<tr id="row-${r.id}" data-id="${r.id}">
    <td>${source}${r.reference_link ? "<br>" + link(r.reference_link) : ""}</td>
    <td>${pmid}</td>
    <td>${clip(r.cancer_type)}</td><td>${clip(r.cancer_stage)}</td><td>${clip(r.treatment_response)}</td>
    <td class="gene"><a href="detail.html?id=${r.id}" title="Open the full record">${esc(r.gene)}</a></td><td>${clip(r.mutation_type)}</td><td>${clip(r.location)}</td><td>${clip(r.hotspot_recurrent)}</td>
    <td class="seq">${clip(r.wild_type_sequence)}</td><td class="seq">${clip(r.mutant_sequence)}</td>
    <td>${show(r.peptide_length)}</td><td>${clip(r.source_protein_uniprot)}</td>
    <td>${clip(r.hla)}</td><td>${clip(r.predicted_binding_affinity)}</td><td>${clip(r.immunogenicity_score)}</td><td>${clip(r.tools_used)}</td>
    <td>${clip(r.evidence_type)}</td><td>${clip(r.assay_method)}</td>
    <td><span class="pill ${s}">${STATUS_NAME[s]}</span><div class="clip status-text">${show(r.immunogenic_status)}</div></td>
    <td>${clip(r.clinical_trial)}</td>
    <td>${show(r.annotator)}</td>
  </tr>`;
}

function drawRecords(records) {
  $("rows").innerHTML = records.map(recordRow).join("");
  const n = records.length;
  $("count").textContent = state.q ? `${n} record${n === 1 ? "" : "s"} matching "${state.q}"` : `${n} record${n === 1 ? "" : "s"}`;
  $("records-title").textContent = state.tab === "Database" ? "All records" : `${state.tab} records`;
  $("empty").hidden = n > 0;
  $("empty").textContent = state.q ? `Nothing matches "${state.q}". Try a gene (KRAS), an allele (A*02:01) or part of a peptide.` : "";
}


/* ---------- 6. Drawing the extra tables (other Excel tabs) ---------- */

// One cell of an extra table. A cell may carry a hidden link, and may be flagged as suspicious.
function refCell(c) {
  const url = c.href || (isUrl(c.text) ? c.text : null);
  let html = url ? link(url, c.text && !isUrl(c.text) ? c.text : null)
                 : String(c.text || "").includes(";") ? showLinks(c.text) : show(c.text);
  if (!url && String(c.text || "").length > 70) html = `<div class="clip" title="Click to read all">${html}</div>`;  // long: show 4 lines
  if (c.suspect) html += '<span class="flag">Unverified: possibly AI-generated link. Please verify.</span>';
  return `<td class="${c.suspect ? "suspect" : ""}">${html}</td>`;
}

function drawReferences(tables) {
  $("references").innerHTML = tables.map((t) => `
    <section class="ref">
      <h2>${esc(t.title || headingFor(t))}</h2>
      <p class="from">From the "${esc(t.source_sheet)}" tab of the spreadsheet: ${t.rows.length} row${t.rows.length === 1 ? "" : "s"}.</p>
      <div class="scroll"><table>
        <thead><tr>${t.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
        <tbody>${t.rows.map((r) => `<tr>${r.map(refCell).join("")}</tr>`).join("")}</tbody>
      </table></div>
    </section>`).join("");
}

// A sensible heading for a table that has no title of its own in the sheet.
function headingFor(t) {
  if (t.source_sheet === "Ashutosh_Summary") return "EGFR curation summary";
  if (t.source_sheet === "Ashutosh_column_metadata") return "EGFR column guide";
  if (t.source_sheet === "Sheet1") return "Legacy summary table";
  if (t.columns.length <= 2) return `${state.tab} key paper`;
  return `${state.tab} mutation catalogue`;
}


/* ---------- 7. Putting it all together ---------- */

// Ask the server for something and give back the answer (as a JavaScript object).
async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} answered ${res.status}`);
  return res.json();
}

// Draw everything for the open tab.
async function render() {
  const legacy = state.tab === "Legacy";
  drawTabs();

  // Records (not on the Legacy tab, which only has the old table).
  let records = [];
  if (!legacy) {
    const params = new URLSearchParams({ limit: 500 });
    if (state.tab !== "Database") params.set("gene", state.tab);
    if (state.q) params.set("q", state.q);
    records = (await getJSON(`/api/neoantigens?${params}`)).items;
  }
  state.records = records;
  const hasRecords = records.length > 0 || (!legacy && state.q);           // keep the table while searching
  $("bench").hidden = records.length === 0;
  $("records").hidden = !hasRecords;
  if (records.length) drawPlate(records);
  if (hasRecords) drawRecords(records);

  // Extra tables for this tab (KRAS, BRAF, EGFR, Legacy have some).
  const tables = state.tab === "Database" ? [] : await getJSON(`/api/references?tab=${encodeURIComponent(state.tab)}`);
  drawReferences(tables);
  $("legacy-note").hidden = !legacy;
  if (legacy) $("legacy-count").textContent = `${state.legacyFlags} links`;
}

// Open a tab: remember it in the address bar, then draw it.
function openTab(name) {
  state.tab = name;
  history.replaceState(null, "", name === "Database" ? location.pathname : `#${encodeURIComponent(name)}`);
  render();
}

// Clicks anywhere on the page: on a tab, on a well, or on a table row.
document.addEventListener("click", (e) => {
  const tab = e.target.closest("[data-tab]");
  if (tab) return openTab(tab.dataset.tab);

  const well = e.target.closest(".well[data-id]");
  if (well) {                                                              // jump to that record's row
    document.querySelectorAll("tr.hit").forEach((r) => r.classList.remove("hit"));
    const row = $(`row-${well.dataset.id}`);
    row.classList.add("hit");
    row.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "center" });
    return;
  }

  const clip = e.target.closest(".ref .clip");                             // a long cell in an extra table:
  if (clip) return clip.classList.toggle("open");                          // click to open / close it

  const row = e.target.closest("table.records tbody tr");
  if (row && !e.target.closest("a")) location.href = `detail.html?id=${row.dataset.id}`;  // open the full record
});

// Pointing at a well (mouse) or moving onto it (keyboard) describes it.
document.addEventListener("mouseover", (e) => { const w = e.target.closest(".well[data-id]"); if (w) describeWell(w); });
document.addEventListener("focusin", (e) => { const w = e.target.closest(".well[data-id]"); if (w) describeWell(w); });

// Typing in the search box: wait until the typing pauses for a moment, then search.
let typingTimer;
$("q").addEventListener("input", (e) => {
  clearTimeout(typingTimer);
  typingTimer = setTimeout(() => { state.q = e.target.value.trim(); render(); }, 250);
});

// Start: learn which tabs exist, count the flagged links, then open the tab named in the address bar.
(async function start() {
  try {
    state.tabs = await getJSON("/api/tabs");
    if (state.tabs.legacy) {
      const legacyTables = await getJSON("/api/references?tab=Legacy");
      state.legacyFlags = legacyTables.flatMap((t) => t.rows.flat()).filter((c) => c.suspect).length;
    }
    const wanted = decodeURIComponent(location.hash.slice(1));
    const names = ["Database", "Legacy", ...state.tabs.genes.map((g) => g.name)];
    openTab(names.includes(wanted) ? wanted : "Database");
  } catch (err) {
    $("panel").innerHTML = `<p class="empty">The database did not answer (${esc(err.message)}). Check that the server and the Postgres container are running, then reload.</p>`;
  }
})();
