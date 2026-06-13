import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import BookCard from "../components/BookCard";
import type { BookCard as BookCardT } from "../types";

const base: BookCardT = {
  id: 1,
  title: "The Way of Kings",
  author: "Brandon Sanderson",
  authors: [{ id: 1, name: "Brandon Sanderson" }],
  categories: [],
  format: "epub",
  folder_path: "/books",
  filename: "kings.epub",
  has_cover: false,
  is_duplicate: false,
  last_opened_at: null,
};

function renderCard(book: BookCardT) {
  return render(
    <MemoryRouter>
      <BookCard book={book} />
    </MemoryRouter>
  );
}

describe("BookCard", () => {
  it("shows the format badge and author", () => {
    renderCard(base);
    expect(screen.getByText("EPUB")).toBeInTheDocument();
    expect(screen.getByText("Brandon Sanderson")).toBeInTheDocument();
  });

  it("appends (Duplicate) when flagged", () => {
    renderCard({ ...base, is_duplicate: true });
    expect(
      screen.getByText("The Way of Kings (Duplicate)")
    ).toBeInTheDocument();
  });

  it("renders a placeholder when there is no cover", () => {
    const { container } = renderCard(base);
    expect(container.querySelector(".cover.placeholder")).toBeTruthy();
    expect(container.querySelector("img.cover")).toBeFalsy();
  });

  it("links to the reader in a new tab", () => {
    renderCard(base);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/read/1");
    expect(link).toHaveAttribute("target", "_blank");
  });
});
