import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface ErrorBoundaryProps {
  children: React.ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('[ErrorBoundary] Caught error:', error);
    console.error('[ErrorBoundary] Component stack:', errorInfo.componentStack);
  }

  handleRetry = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="glass-panel p-8 flex flex-col items-center gap-6 text-center max-w-lg mx-auto mt-16">
          <div className="p-4 rounded-full bg-danger/15 border border-danger/20">
            <AlertTriangle className="w-10 h-10 text-danger" />
          </div>
          <div className="flex flex-col gap-2">
            <h2 className="text-xl font-semibold text-slate-200">
              Something went wrong
            </h2>
            <p className="text-sm text-slate-400 leading-relaxed">
              An unexpected error occurred while rendering this section.
              You can try again or refresh the page.
            </p>
          </div>
          {this.state.error && (
            <pre className="w-full text-left text-xs font-mono text-danger/80 bg-slate-900/80 border border-slate-700 rounded-lg p-4 overflow-x-auto max-h-32">
              {this.state.error.message}
            </pre>
          )}
          <button
            onClick={this.handleRetry}
            className="px-6 py-2.5 bg-primary/20 text-primary hover:bg-primary/30 rounded-lg font-medium transition-colors border border-primary/30 flex items-center gap-2"
          >
            <RefreshCw size={16} />
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
