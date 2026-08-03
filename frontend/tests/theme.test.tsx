import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

function Swatch() {
  return (
    <div>
      <div data-testid="primary" className="bg-primary text-primary-foreground">
        primary
      </div>
      <div data-testid="stat" className="font-mono">
        21.9
      </div>
    </div>
  );
}

describe("theme tokens", () => {
  it("applies primary and mono classes", () => {
    render(<Swatch />);
    expect(screen.getByTestId("primary")).toHaveClass("bg-primary");
    expect(screen.getByTestId("stat")).toHaveClass("font-mono");
  });
});
