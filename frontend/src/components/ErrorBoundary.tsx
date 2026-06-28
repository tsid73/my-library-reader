import { Component, ReactNode } from "react";

export class ErrorBoundary extends Component<
  { children: ReactNode; fallback?: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  state: { hasError: boolean; error: Error | null } = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="page" style={{ padding: 40, textAlign: "center" }}>
            <h2>Something went wrong.</h2>
            <pre style={{ color: "red", textAlign: "left", whiteSpace: "pre-wrap" }}>
              {this.state.error?.message}
            </pre>
            <button className="btn" onClick={() => window.location.reload()}>
              Reload App
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
