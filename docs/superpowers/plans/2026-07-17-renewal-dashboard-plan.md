# Renewal Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `dashboard.html`, a single self-contained static file that displays `clients_certifications.xlsx` as a sortable, filterable, color-coded table, with an optional overlay showing whether a WhatsApp alert was already sent today per client.

**Architecture:** One HTML file with inline CSS/JS. Data loads via two file-picker inputs (xlsx required, sent_log.json optional) rather than `fetch()`, since a `file://` page cannot silently read other local files. Built incrementally, each task adding one layer (skeleton → raw table → computed columns → filtering/sorting → log overlay).

**Tech Stack:** Plain HTML/CSS/JS, SheetJS (`xlsx.full.min.js` via CDN) for parsing the xlsx client-side. No build step, no server.

**Deviation from standard TDD:** This repo has no JavaScript test runner, and this is a single-file, view-only, low-risk internal tool — introducing a JS test stack (npm, jsdom, a runner) solely for this file would be disproportionate (YAGNI). Each task instead specifies an exact manual verification (open in browser, perform action, confirm exact expected result) in place of an automated test step.

Spec: `docs/superpowers/specs/2026-07-17-renewal-dashboard-design.md`

---

## File Structure

```
cert_automation_scripts/
  dashboard.html   (new — single self-contained file)
```

---

### Task 1: Skeleton and xlsx file input

**Files:**
- Create: `cert_automation_scripts/dashboard.html`

- [ ] **Step 1: Create the file with page skeleton, CDN library, and file input**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Absolute Veritas — Renewal Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
<style>
  body { font-family: Arial, sans-serif; margin: 20px; background: #f4f6f9; }
  h1 { color: #1F4E79; }
  .controls { margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
</style>
</head>
<body>
<h1>Absolute Veritas — Certification Renewal Dashboard</h1>

<div class="controls">
  <label>Clients file: <input type="file" id="xlsxInput" accept=".xlsx"></label>
</div>

<script>
const RECORD_KEYS = {
  "Client ID": "client_id", "Full Name": "name", "Company": "company",
  "Certification Name": "cert_name", "Certification ID": "cert_id",
  "Expiry Date": "expiry_date", "Status": "status",
};

let clients = [];

document.getElementById("xlsxInput").addEventListener("change", function (e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function (evt) {
    const data = new Uint8Array(evt.target.result);
    const workbook = XLSX.read(data, { type: "array" });
    const sheet = workbook.Sheets[workbook.SheetNames[0]];
    const rows = XLSX.utils.sheet_to_json(sheet, { defval: "" });
    clients = rows
      .filter((r) => r["Client ID"])
      .map((r) => {
        const rec = {};
        for (const [col, key] of Object.entries(RECORD_KEYS)) {
          rec[key] = r[col];
        }
        return rec;
      });
    console.log("Parsed clients:", clients);
  };
  reader.readAsArrayBuffer(file);
});
</script>
</body>
</html>
```

- [ ] **Step 2: Manual verification**

Open `dashboard.html` directly in a browser (double-click, or drag into an open browser window). Open DevTools console (F12). Click "Clients file" and select `clients_certifications.xlsx` (the 8-row fixture from `create_dummy_data.py`).

Expected: console logs `Parsed clients:` followed by an array of 8 objects; the first object is `{client_id: "CLT001", name: "Rahul Sharma", company: "TechCorp India Pvt Ltd", cert_name: "ISO 9001:2015 Quality Management", cert_id: "ISO-2021-4521", expiry_date: "24-07-2026", status: "CRITICAL"}`. No errors in the console.

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "Add dashboard skeleton with xlsx file loading"
```

---

### Task 2: Render the table

**Files:**
- Modify: `cert_automation_scripts/dashboard.html`

- [ ] **Step 1: Add the table markup and a `render()` function**

```html
<!-- add below the .controls div with the file input -->
<table id="clientTable">
  <thead>
    <tr>
      <th>Client ID</th>
      <th>Full Name</th>
      <th>Company</th>
      <th>Certification</th>
      <th>Cert ID</th>
      <th>Expiry Date</th>
      <th>Status</th>
    </tr>
  </thead>
  <tbody id="clientTableBody"></tbody>
</table>
```

```css
/* add to the <style> block */
table { border-collapse: collapse; width: 100%; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
th, td { border: 1px solid #ddd; padding: 8px 10px; font-size: 14px; text-align: left; }
th { background: #1F4E79; color: #fff; }
```

```js
// add function to the <script> block
function render() {
  const tbody = document.getElementById("clientTableBody");
  tbody.innerHTML = "";
  clients.forEach((c) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${c.client_id}</td>
      <td>${c.name}</td>
      <td>${c.company}</td>
      <td>${c.cert_name}</td>
      <td>${c.cert_id}</td>
      <td>${c.expiry_date}</td>
      <td>${c.status}</td>
    `;
    tbody.appendChild(tr);
  });
}
```

```js
// replace the console.log("Parsed clients:", clients); line inside the file input handler with:
render();
```

- [ ] **Step 2: Manual verification**

Refresh the page, load the fixture xlsx again. Expected: a table appears with 8 rows, columns matching the header order, showing plain data (no colors/formatting yet). Row 1 shows `CLT001 | Rahul Sharma | TechCorp India Pvt Ltd | ISO 9001:2015 Quality Management | ISO-2021-4521 | 24-07-2026 | CRITICAL`.

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "Add table rendering"
```

---

### Task 3: Days-left countdown column

**Files:**
- Modify: `cert_automation_scripts/dashboard.html`

- [ ] **Step 1: Add the countdown column and computation function**

```html
<!-- add a new <th> after "Expiry Date" -->
<th>Days Left</th>
```

```js
// add function to the <script> block
function parseDate(str) {
  const [d, m, y] = String(str).split("-").map(Number);
  return new Date(y, m - 1, d);
}

function computeDaysLeft(expiryStr) {
  const expiry = parseDate(expiryStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  expiry.setHours(0, 0, 0, 0);
  const diffDays = Math.round((expiry - today) / 86400000);
  if (diffDays === 0) return "today";
  if (diffDays > 0) return `in ${diffDays} day${diffDays === 1 ? "" : "s"}`;
  return `${Math.abs(diffDays)} day${Math.abs(diffDays) === 1 ? "" : "s"} ago`;
}
```

```js
// in render(), add a new <td> between Expiry Date and Status
<td>${computeDaysLeft(c.expiry_date)}</td>
```

- [ ] **Step 2: Manual verification**

Open the browser console and run these directly to confirm the pure function logic before checking the table:

```js
computeDaysLeft("24-07-2026")   // expect: "in 7 days" (if today is 2026-07-17)
computeDaysLeft("12-07-2026")   // expect: "5 days ago"
computeDaysLeft("17-07-2026")   // expect: "today"
```

Then refresh, reload the fixture xlsx, and confirm the "Days Left" column shows matching values for each row (e.g. CLT001 → "in 7 days", CLT005 → "5 days ago").

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "Add days-left countdown column"
```

---

### Task 4: Status color badges

**Files:**
- Modify: `cert_automation_scripts/dashboard.html`

- [ ] **Step 1: Add the color map and badge rendering**

```css
/* add to the <style> block */
.badge { padding: 3px 10px; border-radius: 12px; color: #fff; font-weight: bold; font-size: 12px; }
```

```js
// add constant to the <script> block
const STATUS_COLORS = {
  EXPIRED: "#FF0000", CRITICAL: "#FF6600", URGENT: "#FFA500",
  "DUE SOON": "#FFD700", ACTIVE: "#00B050",
};
```

```js
// in render(), replace the plain Status <td> with:
<td><span class="badge" style="background:${STATUS_COLORS[c.status] || "#999"}">${c.status}</span></td>
```

- [ ] **Step 2: Manual verification**

Refresh, reload the fixture. Expected: each Status cell shows a colored pill — CLT001 CRITICAL in orange (`#FF6600`), CLT002/CLT007 URGENT in amber, CLT003/CLT008 DUE SOON in gold, CLT004/CLT006 ACTIVE in green, CLT005 EXPIRED in red.

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "Add status color badges"
```

---

### Task 5: Status filter tabs

**Files:**
- Modify: `cert_automation_scripts/dashboard.html`

- [ ] **Step 1: Add tab markup, styling, state, and filtering in `render()`**

```html
<!-- add inside a new .controls div, after the existing one -->
<div class="controls">
  <div class="tabs" id="statusTabs">
    <button data-status="ALL" class="active">All</button>
    <button data-status="CRITICAL">Critical</button>
    <button data-status="URGENT">Urgent</button>
    <button data-status="DUE SOON">Due Soon</button>
    <button data-status="ACTIVE">Active</button>
    <button data-status="EXPIRED">Expired</button>
  </div>
</div>
```

```css
/* add to the <style> block */
.tabs button { padding: 6px 14px; border: 1px solid #1F4E79; background: #fff; color: #1F4E79; cursor: pointer; border-radius: 4px; margin-right: 4px; }
.tabs button.active { background: #1F4E79; color: #fff; }
```

```js
// add state variable to the <script> block
let activeStatus = "ALL";

// add event listener
document.getElementById("statusTabs").addEventListener("click", function (e) {
  if (e.target.tagName !== "BUTTON") return;
  activeStatus = e.target.dataset.status;
  document.querySelectorAll("#statusTabs button").forEach((b) => b.classList.remove("active"));
  e.target.classList.add("active");
  render();
});
```

```js
// at the top of render(), before building tbody rows:
let rows = clients.slice();
if (activeStatus !== "ALL") {
  rows = rows.filter((c) => c.status === activeStatus);
}
// then change `clients.forEach` to `rows.forEach` in the existing render() body
```

- [ ] **Step 2: Manual verification**

Refresh, reload fixture. Click each tab — "Critical" shows only CLT001, "Urgent" shows CLT002 and CLT007, "Due Soon" shows CLT003 and CLT008, "Active" shows CLT004 and CLT006, "Expired" shows CLT005, "All" shows all 8 again.

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "Add status filter tabs"
```

---

### Task 6: Search box

**Files:**
- Modify: `cert_automation_scripts/dashboard.html`

- [ ] **Step 1: Add search input and filtering in `render()`**

```html
<!-- add inside the same .controls div as the status tabs -->
<input type="text" id="searchBox" placeholder="Search name or company...">
```

```css
/* add to the <style> block */
input[type="text"] { padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; min-width: 220px; }
```

```js
// add state variable
let searchTerm = "";

// add event listener
document.getElementById("searchBox").addEventListener("input", function (e) {
  searchTerm = e.target.value.toLowerCase();
  render();
});
```

```js
// in render(), after the status filter block, add:
if (searchTerm) {
  rows = rows.filter(
    (c) => c.name.toLowerCase().includes(searchTerm) || c.company.toLowerCase().includes(searchTerm)
  );
}
```

- [ ] **Step 2: Manual verification**

Refresh, reload fixture. Type "rahul" in the search box — only CLT001 shows. Type "corp" — shows clients whose company contains "corp" (case-insensitive, e.g. TechCorp, GreenEnergy Corp). Clear the box — all rows (subject to the active status tab) return.

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "Add name/company search box"
```

---

### Task 7: Column sorting

**Files:**
- Modify: `cert_automation_scripts/dashboard.html`

- [ ] **Step 1: Add `data-key` attributes, click handlers, and sort logic**

```html
<!-- update the <thead> row to add data-key to each <th> -->
<tr>
  <th data-key="client_id">Client ID</th>
  <th data-key="name">Full Name</th>
  <th data-key="company">Company</th>
  <th data-key="cert_name">Certification</th>
  <th data-key="cert_id">Cert ID</th>
  <th data-key="expiry_date">Expiry Date</th>
  <th data-key="days_left">Days Left</th>
  <th data-key="status">Status</th>
</tr>
```

```css
/* add to the th rule in <style> */
th { cursor: pointer; user-select: none; }
```

```js
// add state variables
let sortKey = null;
let sortAsc = true;

// add event listener (after the DOM table exists)
document.querySelectorAll("#clientTable th").forEach((th) => {
  th.addEventListener("click", function () {
    const key = th.dataset.key;
    if (sortKey === key) {
      sortAsc = !sortAsc;
    } else {
      sortKey = key;
      sortAsc = true;
    }
    render();
  });
});
```

```js
// in render(), after the search filter block, before building tbody rows:
if (sortKey) {
  rows.sort((a, b) => {
    const av = sortKey === "days_left" ? computeDaysLeft(a.expiry_date) : String(a[sortKey] ?? "");
    const bv = sortKey === "days_left" ? computeDaysLeft(b.expiry_date) : String(b[sortKey] ?? "");
    return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
  });
}
```

- [ ] **Step 2: Manual verification**

Refresh, reload fixture. Click "Full Name" header — rows sort alphabetically A→Z by name. Click again — sorts Z→A. Click "Company" — sorts by company. Confirm sort persists correctly when combined with an active status tab or search term.

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "Add column sorting"
```

---

### Task 8: Sent-log overlay

**Files:**
- Modify: `cert_automation_scripts/dashboard.html`

- [ ] **Step 1: Add the optional log file input and Alert Sent Today column**

```html
<!-- add to the first .controls div, next to the xlsx input -->
<label>Sent log (optional): <input type="file" id="logInput" accept=".json"></label>
```

```html
<!-- add a final <th> to the header row -->
<th>Alert Sent Today</th>
```

```js
// add state variable and constant
let sentLog = null;
const ALERT_ELIGIBLE_STATUSES = new Set(["CRITICAL", "URGENT", "DUE SOON"]);

// add functions
function todayStr() {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

function alertSentLabel(client) {
  if (!ALERT_ELIGIBLE_STATUSES.has(client.status)) return "—";
  if (!sentLog) return "—";
  const key = `${client.client_id}|${client.status}|${todayStr()}`;
  return sentLog[key] ? "✅ Sent" : "Not sent";
}

// add event listener
document.getElementById("logInput").addEventListener("change", function (e) {
  const file = e.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function (evt) {
    sentLog = JSON.parse(evt.target.result);
    render();
  };
  reader.readAsText(file);
});
```

```js
// in render(), add a final <td> to each row's innerHTML
<td>${alertSentLabel(c)}</td>
```

- [ ] **Step 2: Manual verification**

Without loading a log file: all rows show "—" in "Alert Sent Today". Create a test file `test_sent_log.json` with content `{"CLT001|CRITICAL|<today's YYYY-MM-DD>": {"message_id": "wamid.TEST"}}` (substitute today's actual date), load it via the "Sent log" picker. Expected: CLT001's row now shows "✅ Sent"; CLT002/CLT003/CLT007/CLT008 (also alert-eligible but not in the log) show "Not sent"; CLT004/CLT005/CLT006 (ACTIVE/EXPIRED) show "—" regardless of the log contents.

- [ ] **Step 3: Commit**

```bash
git add dashboard.html
git commit -m "Add sent-log overlay for Alert Sent Today column"
```

---

### Task 9: Final full walkthrough

**Files:** none (verification only)

- [ ] **Step 1: Full manual regression pass**

Open `dashboard.html` fresh. Load the 8-row fixture xlsx. Verify: all 8 rows present, correct colors, correct days-left values, all filter tabs work, search works, every column sorts both directions, and (with a test `sent_log.json`) the Alert Sent Today column behaves as in Task 8.

- [ ] **Step 2: Confirm working tree is clean**

Run: `git status`
Expected: `nothing to commit, working tree clean`
