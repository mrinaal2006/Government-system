import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { Alert, Breadcrumbs, Button, DataTable, SelectField, StatusBadge, TextField, type Column } from "@/design-system";

describe("TextField", () => {
  it("associates label, hint and error with the input", () => {
    render(<TextField label="Mobile number" hint="10 digits" error="Enter a valid number" required />);
    const input = screen.getByLabelText(/Mobile number/);
    expect(input).toBeRequired();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/10 digits.*Error: Enter a valid number/);
    expect(screen.getByText("(required)")).toBeInTheDocument();
  });

  it("is not marked invalid without an error", () => {
    render(<TextField label="Name" />);
    expect(screen.getByLabelText("Name")).not.toHaveAttribute("aria-invalid");
  });
});

describe("SelectField", () => {
  it("renders a placeholder and options", async () => {
    render(<SelectField label="Block" options={[{ value: "a", label: "Block A" }]} />);
    const select = screen.getByLabelText("Block");
    await userEvent.selectOptions(select, "a");
    expect(select).toHaveValue("a");
    expect(screen.getByRole("option", { name: "Select an option" })).toBeInTheDocument();
  });
});

describe("Button", () => {
  it("defaults to type=button and disables while busy", () => {
    render(
      <Button busy busyLabel="Saving…">
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Saving…" });
    expect(button).toHaveAttribute("type", "button");
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });
});

describe("Alert and StatusBadge", () => {
  it("errors use role=alert and convey tone in text", () => {
    render(<Alert tone="danger" title="Save failed" />);
    expect(screen.getByRole("alert")).toHaveTextContent("Error: Save failed");
  });
  it("informational alerts are not live by default", () => {
    render(<Alert title="Note" />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
  });
  it("badge shows its status as text", () => {
    render(<StatusBadge tone="success">Operational</StatusBadge>);
    expect(screen.getByText("Operational")).toBeInTheDocument();
  });
});

describe("Breadcrumbs", () => {
  it("marks the last item as the current page", () => {
    render(
      <MemoryRouter>
        <Breadcrumbs items={[{ label: "Home", to: "/" }, { label: "System status" }]} />
      </MemoryRouter>,
    );
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(nav).toContainElement(screen.getByRole("link", { name: "Home" }));
    expect(screen.getByText("System status")).toHaveAttribute("aria-current", "page");
  });
});

type Row = { id: string; name: string };
const columns: Column<Row>[] = [{ key: "name", header: "Name", sortable: true, render: (r) => r.name }];

describe("DataTable", () => {
  it("renders caption, headers and rows", () => {
    render(<DataTable caption="Blocks" columns={columns} rows={[{ id: "1", name: "Row one" }]} rowKey={(r) => r.id} />);
    const table = screen.getByRole("table", { name: "Blocks" });
    expect(table).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "Row one" })).toBeInTheDocument();
  });

  it("shows loading, empty and error states", () => {
    const { rerender } = render(<DataTable caption="Blocks" columns={columns} rows={undefined} rowKey={(r) => r.id} loading />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading blocks");

    rerender(<DataTable caption="Blocks" columns={columns} rows={[]} rowKey={(r) => r.id} emptyTitle="No blocks" />);
    expect(screen.getByText("No blocks")).toBeInTheDocument();

    const retry = vi.fn();
    rerender(
      <DataTable caption="Blocks" columns={columns} rows={[]} rowKey={(r) => r.id} error={{ message: "Failed", requestId: "abc123", onRetry: retry }} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Failed");
    expect(screen.getByText("abc123")).toBeInTheDocument();
  });

  it("exposes sort state and reports sort changes", async () => {
    const onSort = vi.fn();
    render(
      <DataTable
        caption="Blocks"
        columns={columns}
        rows={[{ id: "1", name: "A" }]}
        rowKey={(r) => r.id}
        sort={{ key: "name", direction: "ascending" }}
        onSortChange={onSort}
      />,
    );
    expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSort).toHaveBeenCalledWith("name", "descending");
  });
});
