import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi, renderApp, shellSettled, SYSTEM_INFO } from "@/test/render";

describe("Accessibility controls", () => {
  it("changes text size and contrast, and remembers them", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO) });
    renderApp("/");
    await shellSettled();
    const root = document.documentElement;
    expect(root.dataset.textScale).toBe("normal");

    await userEvent.click(screen.getByRole("button", { name: "A++ (larger text size)" }));
    expect(root.dataset.textScale).toBe("larger");
    expect(screen.getByRole("button", { name: "A++ (larger text size)" })).toHaveAttribute("aria-pressed", "true");

    const contrastToggle = screen.getByRole("button", { name: "High contrast" });
    await userEvent.click(contrastToggle);
    expect(root.dataset.contrast).toBe("high");
    expect(contrastToggle).toHaveAttribute("aria-pressed", "true");

    expect(JSON.parse(window.localStorage.getItem("dgimews.a11y")!)).toEqual({ textScale: "larger", contrast: "high" });
  });

  it("ignores corrupt stored preferences", async () => {
    window.localStorage.setItem("dgimews.a11y", "{not json");
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO) });
    renderApp("/");
    await shellSettled();
    expect(document.documentElement.dataset.textScale).toBe("normal");
    expect(document.documentElement.dataset.contrast).toBe("standard");
  });
});
