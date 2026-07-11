import { describe, expect, it } from "vitest";
import { FrontendLatencyTracker } from "./latency";

describe("FrontendLatencyTracker", () => {
  it("separates first response, stream, and render timing", () => {
    const times = [0, 120, 350, 375];
    const tracker = new FrontendLatencyTracker(() => times.shift() ?? 375);
    tracker.recordFirstChunk();
    tracker.recordLastChunk();
    expect(tracker.recordRenderComplete()).toEqual({
      frontend_first_chunk_ms: 120,
      frontend_first_status_ms: null,
      frontend_first_activity_ms: null,
      frontend_ttft_ms: 120,
      frontend_first_token_render_ms: null,
      frontend_done_ms: null,
      frontend_stream_duration_ms: 230,
      frontend_final_render_ms: 25,
      frontend_total_ms: 375,
      streaming_enabled: true,
    });
  });

  it("distinguishes the first visible status from the first answer token", () => {
    const times = [0, 15, 20, 80, 90, 200, 210, 220];
    const tracker = new FrontendLatencyTracker(() => times.shift() ?? 220);
    tracker.recordFirstStatus();
    tracker.recordFirstActivityRender();
    tracker.recordFirstToken();
    tracker.recordFirstTokenRender();
    tracker.recordLastChunk();
    tracker.recordDone();
    expect(tracker.recordRenderComplete()).toMatchObject({
      frontend_first_chunk_ms: 15,
      frontend_first_status_ms: 15,
      frontend_first_activity_ms: 20,
      frontend_ttft_ms: 80,
      frontend_first_token_render_ms: 90,
      frontend_done_ms: 210,
      frontend_stream_duration_ms: 185,
      frontend_final_render_ms: 20,
    });
  });

  it("treats a complete JSON response as one non-streaming chunk", () => {
    const times = [10, 210, 225];
    const tracker = new FrontendLatencyTracker(() => times.shift() ?? 225);
    tracker.recordCompleteResponse();
    expect(tracker.recordRenderComplete().streaming_enabled).toBe(false);
  });
});
