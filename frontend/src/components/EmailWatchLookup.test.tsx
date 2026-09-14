import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { EmailWatchLookup } from "./EmailWatchLookup";

const requestWatchLookup = vi.fn();
vi.mock("../api", () => ({
  requestWatchLookup: (...a: unknown[]) => requestWatchLookup(...a),
}));

beforeEach(() => {
  requestWatchLookup.mockReset();
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
    fireEvent.click(screen.getByRole("button", { name: "Email me the link" }));
    expect(screen.getByText(/valid email/)).toBeTruthy();
    expect(requestWatchLookup).not.toHaveBeenCalled();
  });

  it("submits a valid email and shows the generic confirmation", async () => {
    requestWatchLookup.mockResolvedValue({ sent: true });
    render(<EmailWatchLookup />);
    fireEvent.click(screen.getByText("Manage my parking watches"));
    fireEvent.change(screen.getByLabelText("Your email"), {
      target: { value: "driver@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Email me the link" }));

    await waitFor(() => expect(requestWatchLookup).toHaveBeenCalledWith("driver@example.com"));
    expect(await screen.findByText(/Check your email/)).toBeTruthy();
  });

  it("API failure shows an error and stays on the form", async () => {
    requestWatchLookup.mockRejectedValue(new Error("500 boom"));
    render(<EmailWatchLookup />);
    fireEvent.click(screen.getByText("Manage my parking watches"));
    fireEvent.change(screen.getByLabelText("Your email"), {
      target: { value: "driver@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Email me the link" }));

    expect(await screen.findByText(/500 boom/)).toBeTruthy();
    expect(screen.getByLabelText("Your email")).toBeTruthy(); // still on the form
  });
});
