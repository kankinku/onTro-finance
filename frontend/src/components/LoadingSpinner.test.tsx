import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { LoadingSpinner } from "./LoadingSpinner";

describe("LoadingSpinner", () => {
  test("renders with default label", () => {
    render(<LoadingSpinner />);
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  test("renders with custom label", () => {
    render(<LoadingSpinner label="Fetching data..." />);
    expect(screen.getByRole("status", { name: /fetching data/i })).toBeInTheDocument();
    expect(screen.getByText("Fetching data...")).toBeInTheDocument();
  });
});
