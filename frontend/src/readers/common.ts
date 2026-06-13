export type Theme = "light" | "sepia" | "dark";

export const THEME_BG: Record<Theme, string> = {
  light: "#ffffff",
  sepia: "#f4ecd8",
  dark: "#1a1a1a",
};

export const THEME_FG: Record<Theme, string> = {
  light: "#1a1a1a",
  sepia: "#5b4636",
  dark: "#e0e0e0",
};

export interface ReaderHandle {
  // position used for progress + bookmarks (page number or CFI)
  currentPosition: () => string | null;
}
