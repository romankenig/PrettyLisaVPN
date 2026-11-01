import { afterEach, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import { readWithNetworkGrace } from "../api/readWithNetworkGrace";

afterEach(() => vi.useRealTimers());

it("hides transient network failure and returns recovery before 15 seconds", async () => {
  vi.useFakeTimers();
  const read = vi
    .fn()
    .mockRejectedValueOnce(new ApiError("NETWORK_ERROR"))
    .mockResolvedValue("online");
  const result = readWithNetworkGrace(read, new AbortController().signal);
  await vi.advanceTimersByTimeAsync(3_000);
  expect(await result).toBe("online");
  expect(read).toHaveBeenCalledTimes(2);
});

it("continuous failures surface at 15 seconds without extending the grace on retries", async () => {
  vi.useFakeTimers();
  const read = vi.fn().mockRejectedValue(new ApiError("TIMEOUT"));
  const failed = vi.fn();
  const result = readWithNetworkGrace(read, new AbortController().signal).catch(
    failed,
  );
  await vi.advanceTimersByTimeAsync(14_999);
  expect(failed).not.toHaveBeenCalled();
  await vi.advanceTimersByTimeAsync(1);
  await result;
  expect(failed).toHaveBeenCalledWith(new ApiError("TIMEOUT"));
  expect(read).toHaveBeenCalledTimes(6);
});

it("auth failures stay immediate and aborted reads never retry", async () => {
  vi.useFakeTimers();
  await expect(
    readWithNetworkGrace(
      () => Promise.reject(new ApiError("AUTH_INVALID")),
      new AbortController().signal,
    ),
  ).rejects.toMatchObject({ code: "AUTH_INVALID" });
  const controller = new AbortController();
  const read = vi.fn().mockRejectedValue(new ApiError("NETWORK_ERROR"));
  const result = readWithNetworkGrace(read, controller.signal).catch(
    (error: unknown) => error,
  );
  await vi.advanceTimersByTimeAsync(0);
  controller.abort();
  expect(await result).toBeInstanceOf(DOMException);
  await vi.advanceTimersByTimeAsync(20_000);
  expect(read).toHaveBeenCalledTimes(1);
});
