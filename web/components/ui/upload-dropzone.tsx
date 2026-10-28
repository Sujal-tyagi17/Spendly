"use client";

import { FileText, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { buttonClass } from "./button";

export function UploadDropzone({ maxMb, disabled, file, onFile }: {
  maxMb: number; disabled?: boolean; file: File | null; onFile: (file: File | null, error?: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const accept = (f: File | undefined | null) => {
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) return onFile(null, "Only PDF statements are supported.");
    if (f.size > maxMb * 1024 * 1024) return onFile(null, `That file is larger than ${maxMb} MB.`);
    onFile(f);
  };

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (!disabled) accept(e.dataTransfer.files?.[0]); }}
      className={`relative flex flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-10 text-center transition-colors duration-200 ${
        over ? "border-lime/60 bg-lime/[0.04]" : "border-line-2 bg-ink-2/60"} ${disabled ? "opacity-50" : ""}`}
    >
      <span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl border border-line bg-card text-lime">
        {file ? <FileText className="h-5 w-5" aria-hidden="true" /> : <UploadCloud className="h-5 w-5" aria-hidden="true" />}
      </span>
      {file ? (
        <>
          <p className="max-w-full truncate text-[0.95rem] font-medium text-fg">{file.name}</p>
          <p className="mt-1 text-[0.8rem] text-muted">{(file.size / 1024).toFixed(0)} KB · ready to read</p>
        </>
      ) : (
        <>
          <p className="text-[0.95rem] font-medium text-fg">Drop your statement PDF here</p>
          <p className="mt-1 text-[0.8rem] text-muted">Text-based PDF · up to {maxMb} MB · read in memory, never stored</p>
        </>
      )}
      <div className="mt-5 flex gap-2">
        <button type="button" disabled={disabled} onClick={() => input.current?.click()} className={buttonClass(file ? "secondary" : "primary", "md")}>
          {file ? "Choose another file" : "Browse files"}
        </button>
        {file ? (
          <button type="button" className={buttonClass("ghost", "md")} onClick={() => { onFile(null); if (input.current) input.current.value = ""; }}>
            Remove
          </button>
        ) : null}
      </div>
      <input ref={input} type="file" accept="application/pdf,.pdf" className="sr-only" tabIndex={-1} aria-label="Statement PDF"
        onChange={(e) => accept(e.target.files?.[0])} />
    </div>
  );
}
