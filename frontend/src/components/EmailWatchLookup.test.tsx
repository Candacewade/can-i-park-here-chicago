import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EmailWatchLookup } from "./EmailWatchLookup";

const listWatchesByEmail = vi.fn();
vi.mock("../api", () => ({
  listWatchesByEmail: (...a: unknown[]) => listWatchesByEmail(...a),
  extendWatch: vi.fn(),
  stopWatch: vi.fn(),
}));

beforeEach(() => {
  listWatchesByEmail.mockReset();
});

describe("EmailWatchLookup", () => {
  it("starts collapsed with just the entry button", () => {
    render(<EmailWatchLookup />);
    expect(screen.getByText("Manage my parking watches")).toBeTruthy();
    expect(screen.queryByLabelText("Your email")).toBeNull();
  });

  it("opens the form, rejects an invalid email without calling the API", () => {
    render(<EmailWatchLookup />);
    fireEvent.click(screen.getByText("Manage my parking watches"));
    fireEvent.change(screen.getByLabelText("Your email"), { target: { value: "not-an-email" } });
    fireEvent.click(screen.getByRole("button", { name: "Find my watches" }));
    expect(screen.getByText(/valid email/)).toBeTruthy();
    expect(listWatchesByEmail).not.toHaveBeenCalled();
  });

  it("submits a valid email and shows the results right away -- no click required", async () => {
    listWatchesByEmail.mockResolvedValue([]);
    render(<EmailWatchLookup />);
    fireEvent.click(screen.getByText("Manage my parking watches"));
    fireEvent.change(screen.getByLabelText("Your email"), {
      target: { value: "driver@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Find my watches" }));

    await waitFor(() => expect(listWatchesByEmail).toHaveBeenCalledWith("driver@example.com"));
    expect(await screen.findByText(/No active parking watches/)).toBeTruthy();
  });

  it('"Search a different email" returns to the entry button', async () => {
    listWatchesByEmail.mockResolvedValue([]);
    render(<EmailWatchLookup />);
    fireEvent.click(screen.getByText("Manage my parking watches"));
    fireEvent.change(screen.getByLabelText("Your email"), {
      target: { value: "driver@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Find my watches" }));
    await screen.findByText(/No active parking watches/);

    fireEvent.click(screen.getByText("Search a different email"));
    expect(screen.getByText("Manage my parking watches")).toBeTruthy();
    expect(screen.queryByText(/No active parking watches/)).toBeNull();
  });
});
