import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SupportError } from "../support/client";
import { createApiClient } from "../api/client";
import { loadConfig } from "../config/config";
import { ApplicationProvider } from "../state/application";
import { About } from "../ui/About";
import {
  supportDiagnostics,
  validateScreenshots,
  type SupportSender,
} from "../support/model";
import {
  createTestAuthenticationSession,
  createTestSessionRestoration,
  createTestVpnConnection,
} from "./fakes";

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
});

function setup(sender?: SupportSender) {
  const session = createTestAuthenticationSession();
  session.activateRestored({
    accessToken: "never-include-access-token",
    accessTokenExpiresIn: 900,
    sessionId: "123e4567-e89b-42d3-a456-426614174005",
    userId: "private-user-id",
    plan: "PREMIUM",
    profile: {
      id: "private-user-id",
      email: "reply@example.com",
      plan: "PREMIUM",
      active_device_count: 2,
    },
  });
  const vpn = createTestVpnConnection();
  const transport = vi.fn().mockRejectedValue(new Error("not configured"));
  const view = render(
    <ApplicationProvider
      value={{
        config: loadConfig({}),
        api: createApiClient("https://api.example.invalid", transport, 5000),
        desktop: { getVersion: async () => "0.7.0" },
        installationId: { getInstallationId: vi.fn() },
        session,
        sessionRestoration: createTestSessionRestoration(),
        vpnConnection: vpn,
        support: sender,
      }}
    >
      <About frontend="0.7.0" backend="0.1.0-dev" />
    </ApplicationProvider>,
  );
  return { ...view, session, vpn, transport };
}

function openForm() {
  fireEvent.click(screen.getByRole("button", { name: "написать в поддержку" }));
  return screen.getByRole("dialog", { name: "помощь и поддержка" });
}

function fillForm() {
  fireEvent.change(screen.getByRole("textbox", { name: "тема" }), {
    target: { value: "не подключается" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "описание проблемы" }), {
    target: { value: "после выбора страны возникает ошибка" },
  });
}

const png = () =>
  new File([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], "screen.png", {
    type: "image/png",
  });

describe("about and support", () => {
  it("shows component versions, an empty FAQ and the exact dedication", () => {
    const { container } = setup();
    expect(screen.getByText("frontend")).toBeInTheDocument();
    expect(screen.getByText("backend")).toBeInTheDocument();
    expect(screen.getByText("0.1.0-dev")).toBeInTheDocument();
    expect(screen.queryByText("окружение")).not.toBeInTheDocument();
    expect(container.querySelector(".eyebrow")).toBeNull();
    expect(screen.getByRole("region", { name: "faq" }).children).toHaveLength(
      1,
    );
    expect(
      screen.getByText("inspired by love of my life, Lisa"),
    ).toBeInTheDocument();
  });

  it("does not send or fake success when the service is not configured", () => {
    const { transport } = setup();
    const dialog = openForm();
    fillForm();
    expect(
      within(dialog).getByRole("textbox", { name: "email для ответа" }),
    ).toHaveValue("reply@example.com");
    expect(
      within(dialog).getByRole("button", { name: "отправить" }),
    ).toBeDisabled();
    expect(
      within(dialog).getByText("отправка пока недоступна"),
    ).toBeInTheDocument();
    expect(transport).not.toHaveBeenCalled();
    expect(screen.queryByText("обращение принято")).not.toBeInTheDocument();
  });

  it("validates required fields before calling a connected sender", async () => {
    const sender = { send: vi.fn() };
    setup(sender);
    openForm();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "заполните тему",
    );
    expect(sender.send).not.toHaveBeenCalled();
    fillForm();
    fireEvent.change(
      screen.getByRole("textbox", { name: "email для ответа" }),
      { target: { value: "invalid" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    expect(sender.send).not.toHaveBeenCalled();
  });

  it("allows manual screenshots and removal, while rejecting disguised files", async () => {
    setup();
    openForm();
    const input = screen.getByLabelText("прикрепить скриншоты");
    fireEvent.change(input, { target: { files: [png()] } });
    expect(await screen.findByText("screen.png")).toBeInTheDocument();
    fireEvent.change(input, {
      target: {
        files: [new File(["not an image"], "fake.png", { type: "image/png" })],
      },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "поддерживаются скриншоты",
    );
    expect(screen.getByText("screen.png")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "убрать screen.png" }));
    expect(screen.queryByText("screen.png")).not.toBeInTheDocument();
  });

  it("sends only after confirmation, with manual attachments and a backend receipt", async () => {
    const sender = {
      send: vi.fn().mockResolvedValue({ request_id: "ticket-123" }),
    };
    setup(sender);
    openForm();
    fillForm();
    fireEvent.change(screen.getByLabelText("прикрепить скриншоты"), {
      target: { files: [png()] },
    });
    await screen.findByText("screen.png");
    expect(sender.send).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "обращение принято",
    );
    const [report, token, signal] = sender.send.mock.calls[0];
    expect(report).toMatchObject({
      subject: "не подключается",
      reply_email: "reply@example.com",
      screenshots: [expect.any(File)],
      diagnostics: { frontend_version: "0.7.0", backend_version: "0.1.0-dev" },
    });
    expect(token).toBe("never-include-access-token");
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(JSON.stringify(report)).not.toContain("never-include-access-token");
  });

  it("can exclude all technical diagnostics from the submission", async () => {
    const sender = {
      send: vi.fn().mockResolvedValue({ request_id: "ticket-124" }),
    };
    setup(sender);
    openForm();
    fillForm();
    fireEvent.click(
      screen.getByRole("checkbox", { name: "приложить технические данные" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    await screen.findByRole("status");
    expect(sender.send.mock.calls[0][0].diagnostics).toBeNull();
  });

  it("blocks duplicate clicks and aborts pending work on close", async () => {
    const sender = {
      send: vi.fn<SupportSender["send"]>(
        () => new Promise<{ request_id: string }>(() => undefined),
      ),
    };
    setup(sender);
    openForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    expect(screen.getByRole("button", { name: "отправляем…" })).toBeDisabled();
    expect(sender.send).toHaveBeenCalledTimes(1);
    const signal = sender.send.mock.calls[0][2] as AbortSignal;
    fireEvent.click(screen.getByRole("button", { name: "отмена" }));
    expect(signal.aborted).toBe(true);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps the draft after failure and never claims that an email was delivered", async () => {
    const sender = {
      send: vi.fn().mockRejectedValue(new Error("secret server details")),
    };
    setup(sender);
    openForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "не удалось подтвердить отправку",
    );
    expect(screen.getByRole("textbox", { name: "тема" })).toHaveValue(
      "не подключается",
    );
    expect(screen.queryByText("обращение принято")).not.toBeInTheDocument();
    expect(screen.queryByText("secret server details")).not.toBeInTheDocument();
  });

  it("preserves UUID and complete snapshot for retry after network failure", async () => {
    const sender = {
      send: vi
        .fn()
        .mockRejectedValueOnce(new Error("network"))
        .mockResolvedValueOnce({ request_id: "ticket-retry" }),
    };
    const { vpn } = setup(sender);
    openForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    await screen.findByRole("alert");
    await act(async () => vpn.reconcile("token"));
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    await screen.findByRole("status");
    expect(sender.send.mock.calls[1][0]).toBe(sender.send.mock.calls[0][0]);
  });

  it("locks the snapshot after uncertainty even if a later POST is rejected", async () => {
    const sender = {
      send: vi
        .fn()
        .mockRejectedValueOnce(new Error("lost response"))
        .mockRejectedValueOnce(new SupportError("ATTACHMENT_REJECTED", true)),
    };
    setup(sender);
    openForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    await screen.findByRole("alert");
    expect(screen.getByRole("textbox", { name: "тема" })).toBeDisabled();
    expect(screen.getByLabelText("прикрепить скриншоты")).toBeDisabled();
    expect(
      screen.getByRole("checkbox", { name: "приложить технические данные" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    await waitFor(() => expect(sender.send).toHaveBeenCalledTimes(2));
    await screen.findByRole("alert");
    expect(sender.send.mock.calls[1][0]).toBe(sender.send.mock.calls[0][0]);
    expect(screen.getByRole("textbox", { name: "тема" })).toBeDisabled();
  });

  it("allows correction after an explicit rejection with no earlier uncertainty", async () => {
    const sender = {
      send: vi
        .fn()
        .mockRejectedValueOnce(new SupportError("ATTACHMENT_REJECTED", true))
        .mockResolvedValueOnce({ request_id: "corrected-ticket" }),
    };
    setup(sender);
    openForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    await screen.findByText(
      "скриншот не принят: проверьте формат, размер и разрешение изображения",
    );
    expect(screen.getByRole("textbox", { name: "тема" })).not.toBeDisabled();
    fireEvent.change(screen.getByRole("textbox", { name: "тема" }), {
      target: { value: "исправленное обращение" },
    });
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    await screen.findByRole("status");
    expect(sender.send.mock.calls[1][0].request_id).not.toBe(
      sender.send.mock.calls[0][0].request_id,
    );
  });

  it("shows delivery status only after backend confirmation", async () => {
    const sender = {
      send: vi
        .fn()
        .mockResolvedValue({ request_id: "ticket-status", status: "ACCEPTED" }),
      getStatus: vi
        .fn()
        .mockResolvedValue({ request_id: "ticket-status", status: "SENT" }),
    };
    setup(sender);
    openForm();
    fillForm();
    fireEvent.click(screen.getByRole("button", { name: "отправить" }));
    await screen.findByText("обращение сохранено и ожидает отправки письма");
    fireEvent.click(screen.getByRole("button", { name: "проверить статус" }));
    await screen.findByText("почтовый сервер принял письмо");
    expect(sender.getStatus.mock.calls[0][0]).toBe("ticket-status");
  });

  it("discards a popup on account change", async () => {
    const { session } = setup();
    openForm();
    fillForm();
    await act(async () => session.clear());
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
  });
});

describe("support diagnostics and attachments", () => {
  it("uses an explicit whitelist instead of serializing credentials or connection config", () => {
    const { session, vpn } = setup();
    const rawState = {
      ...vpn.current(),
      private_key: "never-include-key",
      endpoint: "never-include-ip",
    };
    const result = supportDiagnostics(
      "0.7.0",
      "недоступна",
      session.current(),
      rawState,
    );
    expect(result.backend_version).toBeNull();
    expect(result.auth_session_id).toBe(session.current()?.sessionId);
    expect(JSON.stringify(result)).not.toMatch(
      /never-include|private-user-id|reply@example/,
    );
    expect(result.vpn).toEqual({
      phase: "DISCONNECTED",
      backend: "NONE",
      tunnel: "DOWN",
      session_id: null,
      failure_code: null,
    });
  });

  it("bounds attachment count, individual size and total size", async () => {
    expect(await validateScreenshots([png(), png(), png(), png()])).toContain(
      "не более 3",
    );
    const large = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "big.png", {
      type: "image/png",
    });
    expect(await validateScreenshots([large])).toContain("5 МБ");
    const medium = new File([new Uint8Array(4 * 1024 * 1024)], "medium.png", {
      type: "image/png",
    });
    expect(await validateScreenshots([medium, medium, medium])).toContain(
      "10 МБ",
    );
  });
});
