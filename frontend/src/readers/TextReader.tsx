import { useEffect, useState } from "react";
import type { Theme } from "./common";
import { THEME_BG, THEME_FG } from "./common";

export default function TextReader({
  bookId,
  fontSize,
  theme,
}: {
  bookId: number;
  fontSize: number;
  theme: Theme;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/books/${bookId}/file`)
      .then((r) => {
        if (!r.ok) throw new Error(`server returned ${r.status}`);
        return r.text();
      })
      .then(setText)
      .catch((e) =>
        setError(`Could not load this text file: ${(e as Error).message}`)
      );
  }, [bookId]);

  if (error) return <div className="reader-error">{error}</div>;
  return (
    <div
      className="text-viewport"
      style={{ background: THEME_BG[theme], color: THEME_FG[theme] }}
    >
      <pre className="text-content" style={{ fontSize: `${fontSize}%` }}>
        {text}
      </pre>
    </div>
  );
}
