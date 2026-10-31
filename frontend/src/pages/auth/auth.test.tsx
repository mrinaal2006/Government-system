import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi, renderApp, session } from "@/test/render";

import { safeReturnPath } from "./authFlow";

const anonymous = () => jsonResponse({ error: { code: "not_authenticated", message: "Please sign in" } }, 401);

describe("Sign-in flow", () => {
  it("validates, shows the generic server error and never echoes the password", async () => {
    mockApi({
      "/api/v1/auth/me": anonymous,
      "/api/v1/auth/login": () => jsonResponse({ error: { code: "authentication_failed", message: "Invalid username or password." } }, 401),
    });
    renderApp("/login");
    await userEvent.click(await screen.findByRole("button", { name: "Sign in" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Enter your username and password.");
    await userEvent.type(screen.getByLabelText(/Username/), "officer");
    await userEvent.type(screen.getByLabelText(/Password/), "wrong-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Invalid username or password.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Password/)).toHaveAttribute("type", "password");
  });

  it("moves to MFA verification and then to the requested page", async () => {
    let me = anonymous();
    mockApi({
      "/api/v1/auth/me": () => me.clone(),
      "/api/v1/auth/login": () => jsonResponse(session([], ["district_magistrate"], "mfa_required")),
      "/api/v1/auth/mfa/verify": (_u, init) => {
        expect(JSON.parse(String(init?.body))).toEqual({ code: "123456" });
        me = jsonResponse(session());
        return jsonResponse(session());
      },
    });
    const { router } = renderApp("/login?next=%2Fsystem-status");
    await userEvent.type(await screen.findByLabelText(/Username/), "dm");
    await userEvent.type(screen.getByLabelText(/Password/), "pw");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Verify your identity" })).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Verification code/), "12a3456");
    expect(screen.getByLabelText(/Verification code/)).toHaveValue("123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/system-status"));
  });

  it("only allows safe in-app return paths", () => {
    expect(safeReturnPath("/grievances?x=1")).toBe("/grievances?x=1");
    expect(safeReturnPath("//evil.example")).toBe("/");
    expect(safeReturnPath("https://evil.example")).toBe("/");
    expect(safeReturnPath("/login")).toBe("/");
    expect(safeReturnPath(null)).toBe("/");
  });
});
