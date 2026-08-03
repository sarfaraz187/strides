import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

function Hello() {
  return <div>Strides</div>;
}

describe("smoke test", () => {
  it("renders", () => {
    render(<Hello />);
    expect(screen.getByText("Strides")).toBeInTheDocument();
  });
});
