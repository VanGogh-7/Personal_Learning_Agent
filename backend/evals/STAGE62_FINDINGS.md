# Stage 62 validation status and deployment review

Date: 2026-07-12. This file distinguishes observed results from planned runs.

## Environment findings

Observed in the current development environment:

- PyMuPDF 1.28.0 imports successfully.
- Tesseract and OCRmyPDF executables are unavailable.
- NVIDIA SMI cannot communicate with an NVIDIA driver.
- PyTorch, Transformers, and `colpali-engine` are unavailable.
- No model weights were downloaded.
- The repository contains one `Analysis.pdf`, not the required independent set
  of 3–5 genuinely scanned mathematics books.

Consequently real external OCR, real ColQwen2, real GPU, real scanned-corpus
Text Hybrid, and Dual-Index measurements are **skipped**, not failed and not
replaced with fixture values. Stage 61 fixture conclusions remain in force:
Text Hybrid is the production default; fixture Dual Recall@5 did not beat Text
Hybrid; visual query p50 was about 7.5x and visual storage about 6.5x Text
Hybrid; the main fixture benefit was citation-page ranking.

## Dataset and evaluation contract

`evals/scanned_math/README.md` defines a private, checksum-verified, sealed
dataset with 3–5 books and at least 50 human-labelled queries. Development and
held-out books are separated before experiments. The evaluator rejects draft,
placeholder, incomplete, missing, or checksum-mismatched datasets. Reports
score Recall@1/3/5/10, MRR, nDCG@1/3/5/10, correct-page rate, citation-page
accuracy, p50/p95 query latency, indexing time, storage, failures, page
embedding time, multi-vector count, GPU memory, and cold start.

PostgreSQL FTS means PostgreSQL full-text search. It is **not complete BM25**.
Dual-Index uses reciprocal-rank fusion only; raw text and visual scores are
never mixed.

## Licensing and deployment findings

This is an engineering risk review, not legal advice.

- PyMuPDF is dual-licensed under GNU AGPL v3 or an Artifex commercial license.
  PLA distribution must either be demonstrably AGPL-compatible or obtain a
  commercial license before shipping PyMuPDF in a proprietary desktop build.
  Source: https://pypi.org/project/pymupdf/
- Tesseract is Apache-2.0 and uses Leptonica (BSD 2-clause), but bundled language
  data and transitive components still need a notices inventory. Source:
  https://github.com/tesseract-ocr/tesseract
- OCRmyPDF is MPL-2.0; source-level modifications to OCRmyPDF need the required
  disclosure/notices. It requires external programs including Tesseract and
  Ghostscript. Sources: https://github.com/ocrmypdf/OCRmyPDF and
  https://ocrmypdf.readthedocs.io/en/latest/installation.html
- Ghostscript is AGPL/commercial dual-licensed. Bundling it with a proprietary
  desktop distribution is a release blocker until legal review or a commercial
  license. Source: https://ghostscript.com/licensing/
- The single selected visual experiment is ColQwen2 v1.0. Its model card marks
  the model Apache-2.0, but release must preserve model notices and verify the
  exact local weight revision and all backbone/runtime licenses. Source:
  https://huggingface.co/vidore/colqwen2-v1.0
- OCRmyPDF documents Linux/macOS package-manager installation and Windows
  discovery of separately installed Tesseract and Ghostscript. A single portable
  Python-only bundle cannot be assumed.
- Tauri can bundle target-triple-specific sidecars and scope spawn permissions,
  so an OCR service sidecar is technically possible. It multiplies signing,
  architecture, native-library, model-size, update, and license obligations.
  Source: https://v2.tauri.app/develop/sidecar/
- A local ColQwen2 sidecar currently fails the product constraint that users
  should not need a high-end GPU. A remote visual service could avoid local GPU
  requirements but adds privacy, upload, operations, and model-hosting costs.

## Production recommendation

Keep **Text Hybrid default / Visual Retrieval experimental only**. There is no
real held-out quality, stability, latency, storage, or GPU evidence in this
environment, and desktop deployment plus PyMuPDF/Ghostscript licensing remain
unresolved. Do not add ANN, enable visual retrieval, distribute weights, or tune
against held-out labels.

Stage 63 is not ready for a production visual rollout. It is ready only as an
execution stage after the private sealed dataset, OCR dependencies, audited
local ColQwen2 weights, and a controlled CUDA machine are supplied. Production
consideration additionally needs at least three repeat runs with stable held-out
Recall@5 or nDCG improvement, a clear citation-page gain, acceptable cost, and
an approved desktop or remote deployment design.
