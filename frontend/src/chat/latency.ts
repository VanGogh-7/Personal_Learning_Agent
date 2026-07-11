export interface FrontendLatencySummary {
  frontend_first_chunk_ms: number;
  frontend_first_status_ms: number | null;
  frontend_first_activity_ms: number | null;
  frontend_ttft_ms: number;
  frontend_first_token_render_ms: number | null;
  frontend_done_ms: number | null;
  frontend_stream_duration_ms: number;
  frontend_final_render_ms: number;
  frontend_total_ms: number;
  streaming_enabled: boolean;
}

export class FrontendLatencyTracker {
  private readonly requestStartedAt: number;
  private firstChunkAt: number | null = null;
  private firstStatusAt: number | null = null;
  private firstActivityRenderedAt: number | null = null;
  private firstTokenAt: number | null = null;
  private firstTokenRenderedAt: number | null = null;
  private lastChunkAt: number | null = null;
  private doneAt: number | null = null;

  constructor(private readonly now: () => number = () => performance.now()) {
    this.requestStartedAt = this.now();
  }

  recordFirstChunk(): void {
    this.firstChunkAt ??= this.now();
  }

  recordFirstStatus(): void {
    const recordedAt = this.now();
    this.firstChunkAt ??= recordedAt;
    this.firstStatusAt ??= recordedAt;
  }

  recordFirstToken(): void {
    const recordedAt = this.now();
    this.firstChunkAt ??= recordedAt;
    this.firstTokenAt ??= recordedAt;
  }

  recordFirstActivityRender(): void {
    this.firstActivityRenderedAt ??= this.now();
  }

  recordFirstTokenRender(): void {
    this.firstTokenRenderedAt ??= this.now();
  }

  recordDone(): void {
    this.doneAt ??= this.now();
  }

  recordLastChunk(): void {
    const recordedAt = this.now();
    this.firstChunkAt ??= recordedAt;
    this.lastChunkAt = recordedAt;
  }

  recordCompleteResponse(): void {
    const receivedAt = this.now();
    this.firstChunkAt ??= receivedAt;
    this.lastChunkAt = receivedAt;
  }

  recordRenderComplete(): FrontendLatencySummary {
    const renderCompleteAt = this.now();
    const firstChunkAt = this.firstChunkAt ?? renderCompleteAt;
    const lastChunkAt = this.lastChunkAt ?? firstChunkAt;
    return {
      frontend_first_chunk_ms: round(firstChunkAt - this.requestStartedAt),
      frontend_first_status_ms:
        this.firstStatusAt === null
          ? null
          : round(this.firstStatusAt - this.requestStartedAt),
      frontend_first_activity_ms:
        this.firstActivityRenderedAt === null
          ? null
          : round(this.firstActivityRenderedAt - this.requestStartedAt),
      frontend_ttft_ms: round(
        (this.firstTokenAt ?? firstChunkAt) - this.requestStartedAt,
      ),
      frontend_first_token_render_ms:
        this.firstTokenRenderedAt === null
          ? null
          : round(this.firstTokenRenderedAt - this.requestStartedAt),
      frontend_done_ms:
        this.doneAt === null
          ? null
          : round(this.doneAt - this.requestStartedAt),
      frontend_stream_duration_ms: round(lastChunkAt - firstChunkAt),
      frontend_final_render_ms: round(renderCompleteAt - lastChunkAt),
      frontend_total_ms: round(renderCompleteAt - this.requestStartedAt),
      streaming_enabled: lastChunkAt > firstChunkAt,
    };
  }
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
