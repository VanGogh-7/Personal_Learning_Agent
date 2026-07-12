from __future__ import annotations

import platform
from pathlib import Path
from time import perf_counter

from app.evaluation.stage62 import (
    DatasetManifest,
    RetrievalRun,
    ScannedMathQuery,
    _safe_pdf_path,
)

MODEL_FAMILY = "colqwen2"


def run_colqwen2_experiment(
    dataset_dir: Path,
    manifest: DatasetManifest,
    queries: list[ScannedMathQuery],
    *,
    local_model_path: Path,
    dpi: int = 144,
) -> tuple[list[RetrievalRun], dict[str, object]]:
    """Brute-force ColQwen2 evaluation with local weights and no ANN index."""
    if not local_model_path.is_dir():
        raise ValueError("ColQwen2 weights must be an existing local directory")
    if not 72 <= dpi <= 300:
        raise ValueError("Page rendering DPI must be between 72 and 300")
    try:
        import fitz
        import torch
        from PIL import Image
        from colpali_engine.models import ColQwen2, ColQwen2Processor
    except ImportError as exc:
        raise RuntimeError(
            "ColQwen2 experiment requires torch, Pillow, transformers, and colpali-engine"
        ) from exc
    if not torch.cuda.is_available():
        raise RuntimeError("ColQwen2 experiment requires an available CUDA GPU")

    device = "cuda:0"
    torch.cuda.reset_peak_memory_stats()
    cold_started = perf_counter()
    model = ColQwen2.from_pretrained(
        str(local_model_path),
        torch_dtype=torch.bfloat16,
        device_map=device,
        local_files_only=True,
    ).eval()
    processor = ColQwen2Processor.from_pretrained(
        str(local_model_path), local_files_only=True
    )
    cold_start_ms = (perf_counter() - cold_started) * 1000

    index_started = perf_counter()
    page_embeddings: dict[str, list[tuple[int, object]]] = {}
    storage_bytes = 0
    patch_count = 0
    page_embedding_times: list[float] = []
    for book in manifest.books:
        if book.split != "held_out":
            continue
        document = fitz.open(_safe_pdf_path(dataset_dir, book.pdf_file))
        vectors: list[tuple[int, object]] = []
        try:
            for page_index in range(document.page_count):
                pixmap = document.load_page(page_index).get_pixmap(
                    matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False
                )
                image = Image.frombytes(
                    "RGB", (pixmap.width, pixmap.height), pixmap.samples
                )
                started = perf_counter()
                batch = processor.process_images([image]).to(device)
                with torch.inference_mode():
                    embedding = model(**batch)[0].detach().cpu()
                page_embedding_times.append((perf_counter() - started) * 1000)
                storage_bytes += embedding.numel() * embedding.element_size()
                patch_count += int(embedding.shape[0])
                vectors.append((page_index + 1, embedding))
        finally:
            document.close()
        page_embeddings[book.book_id] = vectors
    indexing_ms = (perf_counter() - index_started) * 1000
    gpu_memory_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

    runs: list[RetrievalRun] = []
    run_id = f"colqwen2-{int(perf_counter() * 1000)}"
    for query in queries:
        if query.split != "held_out":
            continue
        started = perf_counter()
        batch = processor.process_queries([query.query]).to(device)
        with torch.inference_mode():
            query_embedding = model(**batch)[0].detach().cpu()
        scored = [
            (
                page_number,
                _late_interaction_tensor(query_embedding, page_embedding, torch),
            )
            for page_number, page_embedding in page_embeddings[query.book_id]
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        runs.append(
            RetrievalRun(
                run_id=run_id,
                query_id=query.query_id,
                variant="visual",
                ranked_pages=[page for page, _ in scored[:10]],
                query_ms=(perf_counter() - started) * 1000,
                indexing_ms=indexing_ms,
                storage_bytes=storage_bytes,
                page_embedding_ms=(
                    sum(page_embedding_times) / len(page_embedding_times)
                    if page_embedding_times
                    else 0
                ),
                gpu_memory_mb=gpu_memory_mb,
                cold_start_ms=cold_start_ms,
                patch_vector_count=patch_count,
            )
        )
    environment = {
        "model_family": MODEL_FAMILY,
        "model_path_name": local_model_path.name,
        "model_config_sha256": _config_digest(local_model_path),
        "colpali_engine_version": _package_version("colpali-engine"),
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "gpu_name": torch.cuda.get_device_name(0),
        "gpu_memory_total_mb": torch.cuda.get_device_properties(0).total_memory
        / (1024 * 1024),
        "gpu_memory_peak_mb": gpu_memory_mb,
        "ram_total_mb": _ram_total_mb(),
        "platform": platform.platform(),
        "render_dpi": dpi,
        "render_colorspace": "RGB",
        "index_format": "brute_force_bfloat16_multi_vector",
        "ann_index": False,
        "weights_auto_downloaded": False,
    }
    return runs, environment


def write_retrieval_runs(runs: list[RetrievalRun], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(run.model_dump_json() + "\n" for run in runs), encoding="utf-8"
    )


def _late_interaction_tensor(query, page, torch_module) -> float:
    scores = torch_module.matmul(query.float(), page.float().transpose(0, 1))
    return float(scores.max(dim=1).values.mean().item())


def _config_digest(model_path: Path) -> str | None:
    import hashlib

    config = model_path / "config.json"
    return hashlib.sha256(config.read_bytes()).hexdigest() if config.is_file() else None


def _package_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def _ram_total_mb() -> float | None:
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text("utf-8").splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])
        return values["MemTotal"] / 1024
    except (OSError, KeyError, ValueError):
        return None
