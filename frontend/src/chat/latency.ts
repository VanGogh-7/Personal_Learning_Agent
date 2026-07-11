export interface FrontendLatencySummary {
  frontend_ttft_ms: number;
  frontend_stream_duration_ms: number;
  frontend_final_render_ms: number;
  frontend_total_ms: number;
  streaming_enabled: boolean;
}

export class FrontendLatencyTracker {
  private readonly requestStartedAt: number;
  private firstChunkAt: number | null = null;
  private lastChunkAt: number | null = null;

  constructor(private readonly now: () => number = () => performance.now()) {
    this.requestStartedAt = this.now();
  }

  recordFirstChunk(): void {
    this.firstChunkAt ??= this.now();
  }

  recordLastChunk(): void {
    this.recordFirstChunk();
    this.lastChunkAt = this.now();
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
      frontend_ttft_ms: round(firstChunkAt - this.requestStartedAt),
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
