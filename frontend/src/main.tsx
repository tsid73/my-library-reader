import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import App from "./App";
import BookmarksPage from "./pages/BookmarksPage";
import LibraryPage from "./pages/LibraryPage";
import ManageEntitiesPage from "./pages/ManageEntitiesPage";
import ReaderPage from "./pages/ReaderPage";
import RecentPage from "./pages/RecentPage";
import "./styles.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <LibraryPage /> },
      { path: "recent", element: <RecentPage /> },
      { path: "bookmarks", element: <BookmarksPage /> },
      {
        path: "authors",
        element: <ManageEntitiesPage kind="authors" label="Author" />,
      },
      {
        path: "categories",
        element: <ManageEntitiesPage kind="categories" label="Category" />,
      },
    ],
  },
  { path: "/read/:id", element: <ReaderPage /> },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>
);
