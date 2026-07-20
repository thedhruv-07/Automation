import { useRef, useState } from "react";
import { downloadClientTemplate } from "../api";

export default function ExcelSyncView({ onUpload }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [uploading, setUploading] = useState(false);
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
    if (!selectedFile) return;
    setUploading(true);
    try {
      const res = await onUpload(selectedFile);
      setResult({ type: "success", rowCount: res.row_count });
      setSelectedFile(null);
    } catch (err) {
      setResult({ type: "error", message: err.message });
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h2 className="text-2xl font-bold text-ink-primary">Excel Sync</h2>
          <p className="text-ink-secondary text-sm mt-1">
            Replace the client roster by uploading an updated spreadsheet.
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
          Must match the column headers in the downloadable template exactly.
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
        <button
          type="button"
          onClick={handleUploadClick}
          disabled={uploading}
          className="px-4 py-2 rounded-full text-sm font-semibold text-white bg-accent hover:bg-accent-dark transition-colors disabled:opacity-50"
        >
          {uploading ? "Uploading…" : "Upload and Replace Client Data"}
        </button>
      )}

      {result?.type === "success" && (
        <div className="bg-status-good/10 border border-status-good/30 rounded-lg px-4 py-2 text-sm text-ink-primary">
          Import succeeded — {result.rowCount} row{result.rowCount === 1 ? "" : "s"} loaded.
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
