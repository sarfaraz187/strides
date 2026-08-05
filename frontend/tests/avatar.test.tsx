import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Avatar, initialsFromName } from "@/components/avatar";

describe("initialsFromName", () => {
  it("takes the first letter of the first two words, uppercased", () => {
    expect(initialsFromName("Runner Example")).toBe("RE");
  });

  it("falls back to a single letter for a one-word name", () => {
    expect(initialsFromName("Runner")).toBe("R");
  });

  it("falls back to '?' for null", () => {
    expect(initialsFromName(null)).toBe("?");
  });
});

describe("Avatar", () => {
  it("renders an img when avatar_url is present", () => {
    render(
      <Avatar user={{ name: "Runner Example", avatar_url: "https://example.com/pic.jpg" }} size="md" />
    );

    const img = screen.getByRole("img");
    expect(img).toHaveAttribute("src", "https://example.com/pic.jpg");
  });

  it("falls back to initials when avatar_url is null", () => {
    render(<Avatar user={{ name: "Runner Example", avatar_url: null }} size="md" />);

    expect(screen.getByText("RE")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
