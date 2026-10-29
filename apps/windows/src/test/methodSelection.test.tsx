import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it } from "vitest";
import { AdvancedSettings } from "../ui/AdvancedSettings";
import { connectionMethods } from "../vpn/catalog";
import { createVpnConnectionManager } from "../vpn/connection";
import { createMethodPreference } from "../vpn/methodPreference";
import { createMethodSelection } from "../vpn/methodSelection";
import type { ConnectionAdapter } from "../vpn/protocol";

it("remembers a subset, rejects unknown methods and never allows an empty selection", () => {
  let stored: string | null = null;
  const storage = {
    getItem: () => stored,
    setItem: (_: string, value: string) => {
      stored = value;
    },
  };
  const preference = createMethodSelection(storage);
  expect(preference.current()).toBe(null);
  for (const method of connectionMethods)
    if (method.id !== "wireguard_relay") preference.toggle(method.id);
  preference.toggle("unknown");
  preference.toggle("wireguard_relay");
  expect(preference.current()).toEqual(["wireguard_relay"]);
  const restored = createMethodSelection(storage);
  expect(restored.current()).toEqual(["wireguard_relay"]);
  restored.all();
  expect(createMethodSelection(storage).current()).toBe(null);
});

it.each(["not json", "[]", '["removed"]', "{}"])(
  "recovers unusable stored preferences: %s",
  (raw) => {
    expect(
      createMethodSelection({
        getItem: () => raw,
        setItem: () => {},
      }).current(),
    ).toBe(null);
  },
);

it("prevents deselecting the last method and can restore all", () => {
  const preference = createMethodSelection();
  for (const method of connectionMethods)
    if (method.id !== "wireguard") preference.toggle(method.id);
  render(
    <MemoryRouter>
      <AdvancedSettings preference={preference} />
    </MemoryRouter>,
  );
  expect(screen.getByRole("checkbox", { name: "WireGuard" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "WireGuard" })).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox", { name: "WireGuard+" }));
  expect(preference.current()).toEqual(["wireguard", "wireguard_relay"]);
  fireEvent.click(screen.getByRole("checkbox", { name: "Все способы" }));
  expect(preference.current()).toBe(null);
  expect(
    screen
      .getAllByRole("checkbox")
      .every((input) => (input as HTMLInputElement).checked),
  ).toBe(true);
});

it("ignores a disabled successful method, snapshots choices and cleans up before fallback", async () => {
  const calls: string[] = [];
  let enabled = ["wireguard", "vmess"];
  const adapters: ConnectionAdapter[] = [
    "wireguard",
    "wireguard_relay",
    "vmess",
  ].map((id) => ({
    id,
    name: id,
    async connect() {
      calls.push(id);
      enabled = ["wireguard_relay"];
      return { connected: false };
    },
    async disconnect() {
      calls.push(`stop-${id}`);
    },
  }));
  const preference = createMethodPreference();
  preference.remember("wireguard_relay");
  const manager = createVpnConnectionManager(
    adapters,
    preference,
    () => enabled,
  );
  await manager.connect("", { mode: "AUTO" });
  expect(calls).toEqual(["wireguard", "stop-wireguard", "vmess", "stop-vmess"]);
  calls.length = 0;
  await manager.connect("", { mode: "AUTO" });
  expect(calls).toEqual(["wireguard_relay", "stop-wireguard_relay"]);
});
