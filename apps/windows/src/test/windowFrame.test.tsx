import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { WindowFrame } from "../ui/WindowFrame";
import lockIcon from "../assets/lock.svg";
import { languagePreference } from "../i18n";

const controls = vi.hoisted(() => ({
  minimize: vi.fn<() => Promise<void>>(),
  close: vi.fn<() => Promise<void>>(),
}));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => true }));
vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: () => controls,
}));
beforeEach(() => {
  controls.minimize.mockReset().mockResolvedValue(undefined);
  controls.close.mockReset().mockResolvedValue(undefined);
});
it("keeps only minimize and close available alongside the screen content", async () => {
  render(
    <WindowFrame>
      <p>screen content</p>
    </WindowFrame>,
  );
  expect(screen.getByText("screen content")).toBeVisible();
  expect(screen.getAllByRole("button")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Свернуть" }));
  await waitFor(() => expect(controls.minimize).toHaveBeenCalledOnce());
  fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
  await waitFor(() => expect(controls.close).toHaveBeenCalledOnce());
});
it("reports a failed native action without removing the screen", async () => {
  controls.minimize.mockRejectedValueOnce(new Error("native detail"));
  render(
    <WindowFrame>
      <p>screen content</p>
    </WindowFrame>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Свернуть" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось");
  expect(screen.getByText("screen content")).toBeVisible();
});

it("places the original lock and product name in the top header", () => {
  render(
    <WindowFrame>
      <p>screen content</p>
    </WindowFrame>,
  );
  const brand = screen.getByText("PrettyLisaVPN");
  expect(brand.closest("header")).not.toBeNull();
  const image = brand.parentElement?.querySelector("img");
  expect(image).toHaveAttribute("src", lockIcon);
  expect(image).toHaveAttribute("alt", "");
});

it("sets the document language before the sidebar mounts", () => {
  languagePreference.choose("en");
  render(
    <WindowFrame>
      <p>startup screen</p>
    </WindowFrame>,
  );
  expect(document.documentElement.lang).toBe("en");
  expect(screen.getByRole("button", { name: "Close" })).toBeVisible();
  act(() => languagePreference.choose("fr"));
  expect(document.documentElement.lang).toBe("fr");
  expect(screen.getByRole("button", { name: "Fermer" })).toBeVisible();
});
