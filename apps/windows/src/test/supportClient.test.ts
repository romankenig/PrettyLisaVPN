import { describe, expect, it, vi } from "vitest";
import { createSupportSender } from "../support/client";
import type { SupportSubmission } from "../support/model";

const id = "11111111-1111-4111-8111-111111111111";
const draft: SupportSubmission = {
  request_id: id,
  subject: "connection issue",
  description: "please help",
  reply_email: "reply@example.com",
  diagnostics: null,
  screenshots: [
    new File(["image fixture"], "private-local-name.png", {
      type: "image/png",
    }),
  ],
};
const receipt = (status = "ACCEPTED") =>
  Response.json({ request_id: id, status });

describe("support HTTP adapter", () => {
  it("uses authenticated multipart with safe filenames and no token in report", async () => {
    const transport = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(receipt());
    const sender = createSupportSender("https://api.example.com", transport);
    expect(
      await sender.send(draft, "private-token", new AbortController().signal),
    ).toEqual({ request_id: id, status: "ACCEPTED" });
    const [url, init] = transport.mock.calls[1];
    expect(url).toBe("https://api.example.com/support/requests");
    expect(init.headers).toEqual({ authorization: "Bearer private-token" });
    expect(init.redirect).toBe("error");
    expect(init.body).toBeInstanceOf(FormData);
    expect(JSON.parse(init.body.get("report"))).toEqual({
      ...draft,
      screenshots: undefined,
    });
    expect(init.body.get("screenshots").name).toBe("screenshot-1");
    expect(init.body.get("report")).not.toContain("private-token");
    expect(init.body.get("report")).not.toContain("private-local-name");
  });

  it("recovers an accepted POST with lost response through status, without a second POST", async () => {
    const transport = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockRejectedValueOnce(new Error("lost response"))
      .mockResolvedValueOnce(receipt("SENT"));
    const sender = createSupportSender("https://api.example.com", transport);
    await expect(
      sender.send(draft, "token", new AbortController().signal),
    ).rejects.toThrow("SUPPORT_UNAVAILABLE");
    expect(
      await sender.send(draft, "token", new AbortController().signal),
    ).toEqual({ request_id: id, status: "SENT" });
    expect(
      transport.mock.calls.filter(([, init]) => init.method === "POST"),
    ).toHaveLength(1);
  });

  it("reposts the same UUID only after a definite status 404", async () => {
    const transport = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockRejectedValueOnce(new Error())
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(receipt());
    const sender = createSupportSender("https://api.example.com", transport);
    await expect(
      sender.send(draft, "token", new AbortController().signal),
    ).rejects.toThrow();
    await sender.send(draft, "token", new AbortController().signal);
    const posts = transport.mock.calls.filter(
      ([, init]) => init.method === "POST",
    );
    expect(posts).toHaveLength(2);
    expect(
      posts.map(([, init]) => JSON.parse(init.body.get("report")).request_id),
    ).toEqual([id, id]);
  });

  it("never treats failed status lookup as absence", async () => {
    const transport = vi
      .fn()
      .mockResolvedValue(new Response(null, { status: 503 }));
    await expect(
      createSupportSender("https://api.example.com", transport).send(
        draft,
        "token",
        new AbortController().signal,
      ),
    ).rejects.toThrow("SUPPORT_UNAVAILABLE");
    expect(transport).toHaveBeenCalledTimes(1);
  });

  it.each([
    receipt("UNKNOWN"),
    Response.json({ request_id: "different", status: "ACCEPTED" }),
    new Response("html", { headers: { "content-type": "text/html" } }),
  ])("rejects an invalid receipt", async (response) => {
    const sender = createSupportSender(
      "https://api.example.com",
      vi.fn().mockResolvedValue(response),
    );
    await expect(
      sender.getStatus!(id, "token", new AbortController().signal),
    ).rejects.toThrow("INVALID_RESPONSE");
  });

  it("propagates cancellation and hides raw transport errors", async () => {
    const transport = vi.fn(
      (_input, init) =>
        new Promise<Response>((_, reject) =>
          init.signal.addEventListener("abort", () =>
            reject(new Error("private transport details")),
          ),
        ),
    );
    const controller = new AbortController();
    const request = createSupportSender(
      "https://api.example.com",
      transport,
    ).send(draft, "token", controller.signal);
    controller.abort();
    await expect(request).rejects.toThrow("SUPPORT_UNAVAILABLE");
    expect(transport.mock.calls[0][1].signal.aborted).toBe(true);
  });
});
