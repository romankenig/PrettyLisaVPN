import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApiClient } from "../api/client";
import { loadConfig } from "../config/config";
import { createMessagesClient } from "../messages/client";
import { MessagesError, parseMessages, type AccountMessage, type MessagesClient } from "../messages/model";
import type { HttpTransport } from "../native/http";
import { ApplicationProvider } from "../state/application";
import { AccountMessages } from "../ui/AccountMessages";
import { createTestAuthenticationSession, createTestSessionRestoration, createTestVpnConnection } from "./fakes";

const rawMessage = {
  id: "88888888-8888-4888-8888-888888888888",
  revision: 1, kind: "update", title: "новости",
  blocks: [{ type: "paragraph", text: "новости PrettyLisaVPN" }, { type: "list", items: ["первое", "второе"] }],
  fallback_text: "сообщение в текстовом формате",
  dismiss_label: "понятно", expires_at: null,
  primary_action: { type: "OPEN_SUBSCRIPTION", label: "посмотреть" },
};
const envelope = (messages: unknown[] = [rawMessage]) => ({ schema_version: 1, messages });
const message = () => parseMessages(envelope())[0];
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});

function activate(session: ReturnType<typeof createTestAuthenticationSession>, suffix = "one") {
  session.activateRestored({ accessToken: `private-token-${suffix}`, accessTokenExpiresIn: 900,
    sessionId: `session-${suffix}`, userId: `user-${suffix}`, plan: "PREMIUM",
    profile: { id: `user-${suffix}`, email: "user@example.com", plan: "PREMIUM", active_device_count: 1 } });
}
function Location() {
  return <output aria-label="route">{useLocation().pathname}</output>;
}
function setup(options: { client?: MessagesClient; authenticated?: boolean; route?: string } = {}) {
  const client = options.client ?? { list: vi.fn().mockResolvedValue([message()]), acknowledge: vi.fn().mockResolvedValue(undefined) };
  const session = createTestAuthenticationSession();
  if (options.authenticated !== false) activate(session);
  const view = render(<ApplicationProvider value={{
    config: loadConfig({}), api: createApiClient("https://api.example.invalid", vi.fn(), 5000),
    desktop: { getVersion: async () => "0.8.0" }, installationId: { getInstallationId: vi.fn() },
    session, sessionRestoration: createTestSessionRestoration(), vpnConnection: createTestVpnConnection(), messages: client,
  }}><MemoryRouter initialEntries={[options.route ?? "/"]}>
    <p>приложение доступно</p><Location /><AccountMessages version="0.8.0" />
  </MemoryRouter></ApplicationProvider>);
  return { ...view, session, client };
}

describe("message schema and HTTP adapter", () => {
  it("parses a bounded document and preserves server order", () => {
    const next = { ...rawMessage, id: "99999999-9999-4999-8999-999999999999", kind: "future-kind" };
    const result = parseMessages(envelope([rawMessage, next]));
    expect(result.map((item) => item.id)).toEqual([rawMessage.id, next.id]);
    expect(result[1].kind).toBe("announcement");
  });
  it("uses fallback text for unknown blocks and drops executable or unsupported actions", () => {
    const result = parseMessages(envelope([{ ...rawMessage, blocks: [{ type: "future-block", html: "<script>bad()</script>" }], primary_action: { type: "OPEN_URL", url: "javascript:bad()" } }]))[0];
    expect(result.blocks).toEqual([{ type: "paragraph", text: rawMessage.fallback_text }]);
    expect(result.primary_action).toBeNull();
  });
  it.each([
    { schema_version: 2, messages: [rawMessage] },
    envelope([rawMessage, rawMessage]),
    envelope([{ ...rawMessage, revision: -1 }]),
    envelope([{ ...rawMessage, blocks: [{ type: "paragraph", text: "" }] }]),
    envelope([{ ...rawMessage, expires_at: "not a date" }]),
    envelope([{ ...rawMessage, title: "a".repeat(121) }]),
    envelope(Array.from({ length: 11 }, () => rawMessage)),
  ])("rejects malformed, duplicate and oversized messages", (value) => {
    expect(() => parseMessages(value)).toThrow(MessagesError);
  });
  it("authenticates requests and sends only the revision as an acknowledgement", async () => {
    const transport = vi.fn<HttpTransport>().mockResolvedValueOnce(response(envelope())).mockResolvedValueOnce(response({ id: rawMessage.id, revision: 1, acknowledged: true }));
    const client = createMessagesClient("https://api.example.invalid", transport);
    const signal = new AbortController().signal;
    await client.list("secret", { platform: "WINDOWS", app_version: "0.8.0", locale: "ru-RU", schema_version: 1 }, signal);
    const [url, init] = transport.mock.calls[0];
    expect(new URL(String(url)).searchParams.get("app_version")).toBe("0.8.0");
    expect(String(url)).not.toContain("secret");
    expect(init).toMatchObject({ credentials: "omit", cache: "no-store", redirect: "error", headers: { authorization: "Bearer secret" } });
    await client.acknowledge("secret", message(), signal);
    expect(transport.mock.calls[1][0]).toBe(`https://api.example.invalid/messages/${rawMessage.id}/acknowledgements`);
    expect(JSON.parse(String(transport.mock.calls[1][1]?.body))).toEqual({ revision: 1 });
  });
  it("rejects a receipt for a different message or revision", async () => {
    const client = createMessagesClient("https://api.example.invalid", vi.fn().mockResolvedValue(response({ id: rawMessage.id, revision: 2, acknowledged: true })));
    await expect(client.acknowledge("secret", message(), new AbortController().signal)).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });
  it.each([[404, "UNSUPPORTED"], [401, "AUTH_INVALID"], [503, "UNAVAILABLE"]])("normalizes HTTP %s without exposing response content", async (status, code) => {
    const client = createMessagesClient("https://api.example.invalid", vi.fn().mockResolvedValue(response({ secret: "private" }, Number(status))));
    await expect(client.list("token", { platform: "WINDOWS", app_version: "0.8.0", locale: "ru", schema_version: 1 }, new AbortController().signal)).rejects.toMatchObject({ code });
  });
  it("bounds stalled requests and forwards cancellation", async () => {
    const transport = vi.fn<HttpTransport>((_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new Error("private error")), { once: true });
    }));
    const client = createMessagesClient("https://api.example.invalid", transport, 10);
    await expect(client.list("token", { platform: "WINDOWS", app_version: "0.8.0", locale: "ru", schema_version: 1 }, new AbortController().signal)).rejects.toMatchObject({ code: "UNAVAILABLE" });
    expect(transport.mock.calls[0][1]?.signal?.aborted).toBe(true);
  });
});

describe("post-authentication messages", () => {
  it("requests after restored login, without acknowledging a display", async () => {
    const { client } = setup();
    expect(screen.getByText("приложение доступно")).toBeInTheDocument();
    await screen.findByRole("dialog", { name: "новости" });
    expect(client.list).toHaveBeenCalledWith("private-token-one", expect.objectContaining({ platform: "WINDOWS", app_version: "0.8.0", schema_version: 1 }), expect.any(AbortSignal));
    expect(client.acknowledge).not.toHaveBeenCalled();
  });
  it("does not fetch while unauthenticated and starts after fresh login", async () => {
    const { session, client } = setup({ authenticated: false });
    expect(client.list).not.toHaveBeenCalled();
    act(() => activate(session));
    await screen.findByRole("dialog", { name: "новости" });
  });
  it("does not display on the email or OTP route", async () => {
    const { client } = setup({ route: "/auth/verify-otp" });
    expect(client.list).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("quietly tolerates an absent API without changing login", async () => {
    const client = { list: vi.fn().mockRejectedValue(new MessagesError("UNSUPPORTED")), acknowledge: vi.fn() };
    const { session } = setup({ client });
    await waitFor(() => expect(client.list).toHaveBeenCalled());
    expect(session.current()).not.toBeNull();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("defers until an existing modal is closed", async () => {
    const blocker = document.createElement("dialog");
    blocker.setAttribute("open", "");
    document.body.append(blocker);
    try {
      const { client } = setup();
      await waitFor(() => expect(client.list).toHaveBeenCalled());
      expect(document.querySelector(".account-message")).toBeNull();
      act(() => blocker.remove());
      await screen.findByRole("dialog", { name: "новости" });
    } finally { blocker.remove(); }
  });
  it("closes later without acknowledgement and offers it again on the next login", async () => {
    const { client, session } = setup();
    await screen.findByRole("dialog", { name: "новости" });
    fireEvent.click(screen.getByRole("button", { name: "позже" }));
    expect(client.acknowledge).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    act(() => activate(session, "new-login"));
    await screen.findByRole("dialog", { name: "новости" });
  });
  it("keeps the window after acknowledgement failure and retries the same revision", async () => {
    const client = { list: vi.fn().mockResolvedValue([message()]), acknowledge: vi.fn().mockRejectedValueOnce(new Error("private")).mockResolvedValue(undefined) };
    setup({ client });
    await screen.findByRole("dialog", { name: "новости" });
    fireEvent.click(screen.getByRole("button", { name: "понятно" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("не удалось сохранить подтверждение");
    expect(screen.queryByText("private")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "понятно" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(client.acknowledge.mock.calls.map((call) => call[1].revision)).toEqual([1, 1]);
  });
  it("blocks duplicate confirmation and navigates only after the server confirms", async () => {
    let resolve!: () => void;
    const client = { list: vi.fn().mockResolvedValue([message()]), acknowledge: vi.fn(() => new Promise<void>((done) => { resolve = done; })) };
    setup({ client });
    await screen.findByRole("dialog", { name: "новости" });
    fireEvent.click(screen.getByRole("button", { name: "посмотреть" }));
    expect(screen.getByLabelText("route")).toHaveTextContent(/^\/$/);
    expect(screen.getByRole("button", { name: "сохраняем…" })).toBeDisabled();
    expect(client.acknowledge).toHaveBeenCalledTimes(1);
    await act(async () => resolve());
    expect(screen.getByLabelText("route")).toHaveTextContent("/settings/subscription");
  });
  it("renders HTML as text and falls back instead of executing unknown content", async () => {
    const safe = parseMessages(envelope([{ ...rawMessage, blocks: [{ type: "future", html: "<img src=x>" }], fallback_text: "<script>bad()</script>", primary_action: { type: "EVAL", code: "bad()" } }]))[0];
    const { container } = setup({ client: { list: vi.fn().mockResolvedValue([safe]), acknowledge: vi.fn() } });
    expect(await screen.findByText("<script>bad()</script>")).toBeInTheDocument();
    expect(container.querySelector("script, img, iframe, a")).toBeNull();
    expect(screen.queryByRole("button", { name: "посмотреть" })).not.toBeInTheDocument();
  });
  it("shows the backend queue in order and drops expired messages", async () => {
    const expired = { ...message(), id: "77777777-7777-4777-8777-777777777777", expires_at: "2020-01-01T00:00:00Z", title: "истекло" };
    const next = { ...message(), id: "99999999-9999-4999-8999-999999999999", title: "следующее" };
    setup({ client: { list: vi.fn().mockResolvedValue([expired, message(), next]), acknowledge: vi.fn().mockResolvedValue(undefined) } });
    await screen.findByRole("dialog", { name: "новости" });
    expect(screen.queryByText("истекло")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "понятно" }));
    await screen.findByRole("dialog", { name: "следующее" });
  });
  it("ignores stale responses after an account change", async () => {
    let resolve!: (items: AccountMessage[]) => void;
    const client = { list: vi.fn<MessagesClient["list"]>().mockImplementationOnce(() => new Promise((done) => { resolve = done; })).mockResolvedValue([]), acknowledge: vi.fn() };
    const { session } = setup({ client });
    act(() => activate(session, "two"));
    await act(async () => resolve([message()]));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
  it("uses backend acknowledgements across independent device clients", async () => {
    let acknowledged = false;
    const client: MessagesClient = { list: vi.fn(async () => acknowledged ? [] : [message()]), acknowledge: vi.fn(async () => { acknowledged = true; }) };
    const first = setup({ client });
    await screen.findByRole("dialog", { name: "новости" });
    fireEvent.click(screen.getByRole("button", { name: "понятно" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    first.unmount();
    setup({ client });
    await waitFor(() => expect(client.list).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
