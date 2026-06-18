/**
 * ErrorBoundary
 * -------------
 * Catches render/runtime errors in the subtree so a single component crash
 * never turns the whole app into a blank white page. Shows a friendly,
 * actionable fallback and logs the error to the console for debugging.
 *
 * Error boundaries must be class components (React has no hook equivalent).
 */
import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  /** Optional label shown in the fallback (e.g. the page name). */
  label?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Never hide errors during development — log full details.
    console.error("[ErrorBoundary] caught a render error:", error, info);
  }

  private reset = () => this.setState({ hasError: false, error: null });

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div
        role="alert"
        className="mx-auto flex max-w-md flex-col items-center justify-center gap-4 px-4 py-20 text-center"
      >
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-health-warning/15">
          <AlertTriangle className="h-7 w-7 text-health-warning" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-foreground">
            Something went wrong on this page
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {this.props.label ? `The ${this.props.label} screen ` : "This page "}
            hit an unexpected error. The rest of the app is still working —
            please refresh or go back to the Dashboard.
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-center gap-2">
          <Button
            onClick={() => {
              this.reset();
              window.location.assign("/");
            }}
          >
            Go to Dashboard
          </Button>
          <Button variant="outline" onClick={() => window.location.reload()}>
            Refresh
          </Button>
        </div>
        {import.meta.env.DEV && this.state.error && (
          <pre className="mt-2 max-h-40 w-full overflow-auto rounded-lg bg-muted p-3 text-left text-[11px] leading-relaxed text-muted-foreground">
            {this.state.error.name}: {this.state.error.message}
          </pre>
        )}
      </div>
    );
  }
}
