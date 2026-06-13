import { afterEach, describe, expect, it, vi } from "vitest";
import { get } from "../api/client";

afterEach(() => vi.restoreAllMocks());

describe("api client", () => {
  it("returns parsed JSON on success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ ok: 1 }), { status: 200 }))
    );
    expect(await get("/x")).toEqual({ ok: 1 });
  });

  it("surfaces the backend detail message on error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "Book #9 not found." }), {
            status: 404,
          })
      )
    );
    await expect(get("/books/9")).rejects.toThrow("Book #9 not found.");
  });

  it("gives a friendly message when the backend is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      })
    );
    await expect(get("/x")).rejects.toThrow(/backend/i);
  });
});
