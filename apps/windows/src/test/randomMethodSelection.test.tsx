import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { AdvancedSettings } from "../ui/AdvancedSettings";
import { connectionMethods } from "../vpn/catalog";
import { createVpnConnectionManager } from "../vpn/connection";
import { createMethodPreference } from "../vpn/methodPreference";
import { createMethodSelection } from "../vpn/methodSelection";
import type { ConnectionAdapter } from "../vpn/protocol";

it("randomizes a nonempty ordered subset, persists it and changes it on every click", () => {
  let stored: string | null = null;
  const storage = {
    getItem: () => stored,
    setItem: (_: string, value: string) => {
      stored = value;
    },
  };
  const selection = createMethodSelection(storage);
  selection.randomize(() => 0);
  const first = selection.current()!;
  expect(first).toHaveLength(1);
  expect(connectionMethods.some((method) => method.id === first[0])).toBe(true);
  expect(createMethodSelection(storage).current()).toEqual(first);
  selection.randomize(() => 0);
  expect(selection.current()).not.toEqual(first);
  selection.randomize(() => 0.999999);
  expect(selection.current()).toHaveLength(connectionMethods.length);
  selection.randomize(() => 0.999999);
  expect(selection.current()).not.toEqual(
    connectionMethods.map((method) => method.id),
  );
  expect(new Set(selection.current()).size).toBe(connectionMethods.length);
  expect(createMethodSelection(storage).current()).toEqual(selection.current());
  selection.all();
  expect(createMethodSelection(storage).current()).toBe(null);
});

it("shows saved order and randomizes through the button", () => {
  const preference = createMethodSelection({
    getItem: () => '["vmess","wireguard","vmess","removed"]',
    setItem: () => {},
  });
  render(
    <MemoryRouter>
      <AdvancedSettings preference={preference} />
    </MemoryRouter>,
  );
  const checked = () =>
    screen
      .getAllByRole("checkbox")
      .filter((item) => (item as HTMLInputElement).checked);
  expect(checked()[0].closest("label")).toHaveTextContent("VMess");
  fireEvent.click(
    screen.getByRole("button", { name: "Случайный набор и порядок способов" }),
  );
  expect(checked().length).toBeGreaterThan(0);
  expect(preference.current()).not.toEqual(["vmess", "wireguard"]);
  expect(checked().map((input) => input.closest("label")!.textContent)).toEqual(
    preference
      .current()!
      .map((id) => connectionMethods.find((method) => method.id === id)!.name),
  );
});

it("uses saved base order while retaining successful-method priority", async () => {
  const calls: string[] = [];
  const adapters: ConnectionAdapter[] = ["wireguard", "vmess", "sstp"].map(
    (id) => ({
      id,
      name: id,
      async connect() {
        calls.push(id);
        return { connected: false };
      },
      async disconnect() {
        calls.push(`stop-${id}`);
      },
    }),
  );
  const preference = createMethodPreference();
  preference.remember("vmess");
  const manager = createVpnConnectionManager(adapters, preference, () => [
    "sstp",
    "wireguard",
    "vmess",
  ]);
  await manager.connect("", { mode: "AUTO" });
  expect(calls).toEqual([
    "vmess",
    "stop-vmess",
    "sstp",
    "stop-sstp",
    "wireguard",
    "stop-wireguard",
  ]);
  expect(preference.current()).toBe("vmess");
});
