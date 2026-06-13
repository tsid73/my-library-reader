import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

export default function App() {
  const [showScrollTop, setShowScrollTop] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowScrollTop(window.scrollY > 500);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <div className="app">
      <header className="topbar">
        <span className="logo">📚 My Library</span>
        <nav>
          <NavLink to="/" end>
            Library
          </NavLink>
          <NavLink to="/recent">Recent</NavLink>
          <NavLink to="/bookmarks">Bookmarks</NavLink>
          <NavLink to="/authors">Authors</NavLink>
          <NavLink to="/categories">Categories</NavLink>
        </nav>
      </header>
      <Outlet />
      <button
        className={`scroll-top ${showScrollTop ? "visible" : ""}`}
        type="button"
        aria-label="Scroll to top"
        title="Scroll to top"
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
          <path
            d="M12 5l-7 7h4v7h6v-7h4z"
            fill="currentColor"
          />
        </svg>
      </button>
    </div>
  );
}
