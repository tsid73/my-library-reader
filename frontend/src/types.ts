export interface Entity {
  id: number;
  name: string;
  count?: number;
}

export interface BookCard {
  id: number;
  title: string;
  author: string | null;
  authors: Entity[];
  categories: Entity[];
  format: string;
  folder_path: string;
  filename: string;
  has_cover: boolean;
  is_duplicate: boolean;
  last_opened_at: string | null;
}

export interface BookDetail extends BookCard {
  abs_path: string;
  size: number;
  cleaned_title: string;
  cleaned_author: string | null;
  edited_title: string | null;
  edited_author: string | null;
}

export interface Section {
  folder: string;
  crumbs: string[];
  books: BookCard[];
}

export interface LibraryResponse {
  sections: Section[];
  total: number;
}

export interface BrowseGroup {
  id: number | null;
  name: string;
  count: number;
  books: BookCard[];
}

export interface BrowseResponse {
  groups: BrowseGroup[];
}

export interface FolderOption {
  value: string;
  label: string;
}

export interface FilterOptions {
  formats: string[];
  folders: FolderOption[];
  authors: string[];
  categories: string[];
}

export interface SyncStatus {
  running: boolean;
  run_id: number | null;
  current_folder: string;
  current_file: string;
  found: number;
  indexed: number;
  skipped: number;
  deleted: number;
  failed: number;
  errors: { file_path: string; message: string }[];
  started_at: string | null;
  finished_at: string | null;
  fatal_error: string | null;
  stopping: boolean;
  stopped: boolean;
}

export interface RootFolder {
  id: number;
  path: string;
  display_path: string;
  exists: boolean;
  rules: { id: number; kind: string; subpath: string }[];
}

export interface Bookmark {
  id: number;
  book_id: number;
  position: string;
  label: string | null;
  created_at: string;
}

export interface ProgressInfo {
  position: string | null;
  updated_at: string | null;
}

export interface BookmarkedBook {
  book: BookCard;
  bookmark_count: number;
  latest_bookmark: Bookmark;
}
