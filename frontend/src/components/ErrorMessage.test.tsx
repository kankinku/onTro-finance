import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { ErrorMessage } from "./ErrorMessage";

describe("ErrorMessage", () => {
  test("renders the error message text", () => {
    render(<ErrorMessage message="Something went wrong." />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Something went wrong.")).toBeInTheDocument();
  });

  test("applies inline-error class", () => {
    render(<ErrorMessage message="Oops" />);
    expect(screen.getByRole("alert")).toHaveClass("inline-error");
  });
});
