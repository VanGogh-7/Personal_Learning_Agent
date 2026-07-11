import { describe, expect, it } from "vitest";
import { FrontendLatencyTracker } from "./latency";

describe("FrontendLatencyTracker", () => {
  it("separates first response, stream, and render timing", () => {
    const times = [0, 120, 350, 375];
    const tracker = new FrontendLatencyTracker(() => times.shift() ?? 375);
    tracker.recordFirstChunk();
    tracker.recordLastChunk();
    expect(tracker.recordRenderComplete()).toEqual({
      frontend_ttft_ms: 120,
      frontend_stream_duration_ms: 230,
      frontend_final_render_ms: 25,
      frontend_total_ms: 375,
      streaming_enabled: true,
    });
  });

  it("treats a complete JSON response as one non-streaming chunk", () => {
    const times = [10, 210, 225];
    const tracker = new FrontendLatencyTracker(() => times.shift() ?? 225);
    tracker.recordCompleteResponse();
    expect(tracker.recordRenderComplete().streaming_enabled).toBe(false);
  });
});
