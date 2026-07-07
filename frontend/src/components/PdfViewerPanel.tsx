import { useEffect, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { readPdfFile } from "../tauri/pdfFiles";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

const DEFAULT_SCALE = 1;
const MIN_SCALE = 0.7;
const MAX_SCALE = 2.2;
const SCALE_STEP = 0.15;

export default function PdfViewerPanel({
  title,
  filePath,
}: {
  title: string;
  filePath: string | null;
}) {
  const [pdfData, setPdfData] = useState<Uint8Array | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState<number | null>(null);
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const documentFile = useMemo(() => {
    return pdfData ? { data: pdfData } : null;
  }, [pdfData]);

  useEffect(() => {
    let cancelled = false;
    const selectedPath = filePath?.trim();

    setPdfData(null);
    setCurrentPage(1);
    setTotalPages(null);
    setScale(DEFAULT_SCALE);
    setError(null);

    if (!selectedPath) {
      setLoading(false);
      setError("No local PDF file path is available for this Library item.");
      return () => {
        cancelled = true;
      };
    }

    setLoading(true);
    void readPdfFile(selectedPath)
      .then((data) => {
        if (!cancelled) {
          setPdfData(data);
        }
      })
      .catch((loadError) => {
        if (!cancelled) {
          setError(
            loadError instanceof Error ? loadError.message : "Could not load the selected PDF.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [filePath]);

  const canGoPrevious = currentPage > 1;
  const canGoNext = totalPages !== null && currentPage < totalPages;

  return (
    <section className="pdf-viewer-shell" aria-label={`PDF viewer for ${title}`}>
      <div className="pdf-viewer-toolbar">
        <div className="pdf-viewer-title">
          <strong>{title}</strong>
          <span>
            Page {totalPages ? currentPage : "-"} / {totalPages ?? "-"}
          </span>
        </div>
        <div className="pdf-viewer-controls" aria-label="PDF viewer controls">
          <button
            type="button"
            className="secondary-button compact-button"
            disabled={!canGoPrevious}
            onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
          >
            Previous
          </button>
          <button
            type="button"
            className="secondary-button compact-button"
            disabled={!canGoNext}
            onClick={() =>
              setCurrentPage((page) => Math.min(totalPages ?? page, page + 1))
            }
          >
            Next
          </button>
          <button
            type="button"
            className="secondary-button compact-button"
            disabled={scale <= MIN_SCALE}
            onClick={() => setScale((value) => clampScale(value - SCALE_STEP))}
          >
            Zoom out
          </button>
          <span className="pdf-zoom-label">{Math.round(scale * 100)}%</span>
          <button
            type="button"
            className="secondary-button compact-button"
            disabled={scale >= MAX_SCALE}
            onClick={() => setScale((value) => clampScale(value + SCALE_STEP))}
          >
            Zoom in
          </button>
        </div>
      </div>

      <div className="pdf-viewer-stage">
        {loading && <p className="empty-state">Loading PDF...</p>}
        {error && <p className="error compact-error">{error}</p>}
        {!loading && !error && documentFile && (
          <Document
            file={documentFile}
            loading={<p className="empty-state">Rendering PDF...</p>}
            error={<p className="error compact-error">Could not render this PDF.</p>}
            onLoadSuccess={({ numPages }) => {
              setTotalPages(numPages);
              setCurrentPage(1);
              setError(null);
            }}
            onLoadError={(loadError) => {
              setError(loadError.message || "Could not render this PDF.");
            }}
          >
            <Page
              pageNumber={currentPage}
              scale={scale}
              renderAnnotationLayer={false}
              renderTextLayer={false}
              loading={<p className="empty-state">Loading page...</p>}
              onRenderError={(renderError) => {
                setError(renderError.message || "Could not render this PDF page.");
              }}
            />
          </Document>
        )}
      </div>
    </section>
  );
}

function clampScale(value: number): number {
  return Math.min(Math.max(Number(value.toFixed(2)), MIN_SCALE), MAX_SCALE);
}
