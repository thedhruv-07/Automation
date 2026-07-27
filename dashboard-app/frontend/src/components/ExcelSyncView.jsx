import { useRef, useState } from "react";
import { downloadClientTemplate } from "../api";

const FORMAT_LABELS = { bis_isi: "BIS ISI licence", crs: "CRS registration" };

export default function ExcelSyncView({ onUpload, onMerge }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [importFormat, setImportFormat] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [runningAction, setRunningAction] = useState(null); // "replace" | "merge" | null
  const [result, setResult] = useState(null);
  const fileInputRef = useRef(null);

  function pickFile(file) {
    if (!file) return;
    setSelectedFile(file);
    setResult(null);
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragActive(false);
    pickFile(e.dataTransfer.files?.[0]);
  }

  async function handleUploadClick() {
    if (!selectedFile || !importFormat) return;
    setRunningAction("replace");
    try {
      const res = await onUpload(selectedFile, importFormat);
      setResult({ type: "success", mode: "replace", rowCount: res.row_count, format: res.format, stats: res.stats });
      setSelectedFile(null);
      setImportFormat("");
    } catch (err) {
      setResult({ type: "error", message: err.message });
    } finally {
      setRunningAction(null);
    }
  }

  async function handleMergeClick() {
    if (!selectedFile || !importFormat) return;
    setRunningAction("merge");
    try {
      const res = await onMerge(selectedFile, importFormat);
      setResult({
        type: "success", mode: "merge", rowCount: res.row_count, format: res.format,
        stats: res.stats, added: res.added, skippedDuplicates: res.skipped_duplicates,
      });
      setSelectedFile(null);
      setImportFormat("");
    } catch (err) {
      setResult({ type: "error", message: err.message });
    } finally {
      setRunningAction(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-bold text-ink-primary">Excel Sync</h2>
          <p className="text-ink-secondary text-sm mt-1">
            Replace the client roster, or merge in new clients from an updated spreadsheet.
          </p>
        </div>
        <button
          type="button"
          onClick={downloadClientTemplate}
          className="px-4 py-2 rounded-lg text-sm font-semibold text-ink-secondary border border-line hover:text-ink-primary transition-colors"
        >
          Download Template
        </button>
      </div>

      <div>
        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-secondary mb-2">
          File format
        </label>
        <select
          value={importFormat}
          onChange={(e) => setImportFormat(e.target.value)}
          aria-label="Import format"
          className="min-w-[220px] bg-surface-page border border-line rounded-lg px-3 py-2 text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <option value="" disabled>-- Select format --</option>
          <option value="roster">Roster (dashboard template)</option>
          <option value="bis_isi">BIS ISI (raw government export)</option>
          <option value="crs">CRS (raw government export)</option>
          <option value="fmcs" disabled>FMCS (coming soon)</option>
        </select>
      </div>

      <div
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        className={`bg-surface border-2 border-dashed rounded-xl p-10 flex flex-col items-center justify-center text-center cursor-pointer transition-colors ${
          dragActive ? "border-accent bg-accent/5" : "border-line"
        }`}
      >
        <svg
          viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          strokeLinecap="round" strokeLinejoin="round" className="h-12 w-12 text-accent mb-4" aria-hidden="true"
        >
          <path d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5-5 5 5M12 5v12" />
        </svg>
        <p className="font-semibold text-ink-primary mb-1">
          {selectedFile ? selectedFile.name : "Drag and drop your .xlsx file here, or click to browse"}
        </p>
        <p className="text-xs text-ink-muted">
          Select the file's format above, then drop it here or click to browse.
        </p>
        <input
          ref={fileInputRef}
          type="file"
          accept=".xlsx"
          aria-label="Upload client spreadsheet"
          className="hidden"
          onChange={(e) => pickFile(e.target.files?.[0])}
        />
      </div>

      {selectedFile && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleUploadClick}
            disabled={runningAction !== null || !importFormat}
            className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
          >
            {runningAction === "replace" ? "Uploading…" : "Upload and Replace Client Data"}
          </button>
          <button
            type="button"
            onClick={handleMergeClick}
            disabled={runningAction !== null || !importFormat}
            className="px-4 py-2 rounded-full text-sm font-semibold text-accent border border-accent hover:bg-accent/5 transition-colors disabled:opacity-50"
          >
            {runningAction === "merge" ? "Merging…" : "Upload and Merge with Existing Data"}
          </button>
        </div>
      )}

      {result?.type === "success" && (
        <div className="bg-status-good/10 border border-status-good/30 rounded-lg px-4 py-2 text-sm text-ink-primary">
          {result.mode === "merge" ? (
            <>
              Merged{FORMAT_LABELS[result.format] ? ` (converted ${FORMAT_LABELS[result.format]} export)` : ""} —{" "}
              added {result.added} new client{result.added === 1 ? "" : "s"}, skipped{" "}
              {result.skippedDuplicates} already on file ({result.rowCount} total now).
            </>
          ) : FORMAT_LABELS[result.format] ? (
            <>
              Converted {FORMAT_LABELS[result.format]} export — {result.rowCount} row{result.rowCount === 1 ? "" : "s"} loaded
              from {result.stats?.sheets_used} sheet{result.stats?.sheets_used === 1 ? "" : "s"}
              {result.stats?.sheets_empty ? `, ${result.stats.sheets_empty} sheet(s) skipped (empty)` : ""}
              {result.stats?.rows_skipped_missing_key
                ? `, ${result.stats.rows_skipped_missing_key} row(s) skipped (missing required identifier / date)`
                : ""}.
            </>
          ) : (
            <>Import succeeded — {result.rowCount} row{result.rowCount === 1 ? "" : "s"} loaded.</>
          )}
        </div>
      )}
      {result?.type === "error" && (
        <div className="bg-status-critical/10 border border-status-critical/30 rounded-lg px-4 py-2 text-sm text-ink-primary">
          Import failed: {result.message}
        </div>
      )}
    </div>
  );
}
