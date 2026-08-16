import React from 'react';

/**
 * ErrorBoundary — catches uncaught render errors and shows a branded error page.
 * Wrap around the router in App.jsx.
 */
class ErrorBoundary extends React.Component {
    constructor(props) {
        super(props);
        this.state = { hasError: false, error: null };
    }

    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }

    componentDidCatch(error, info) {
        console.error('[ErrorBoundary] Uncaught error:', error, info);
    }

    handleReset = () => {
        this.setState({ hasError: false, error: null });
        window.location.href = '/';
    };

    render() {
        if (this.state.hasError) {
            return (
                <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4 text-center">
                    <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-2xl bg-expense-muted text-expense text-4xl">
                        ⚠️
                    </div>
                    <h1 className="font-display text-3xl font-bold text-foreground mb-2">
                        Something went wrong
                    </h1>
                    <p className="text-muted-foreground mb-8 max-w-sm">
                        An unexpected error occurred. Your data is safe — please refresh or return to the dashboard.
                    </p>
                    {this.state.error && (
                        <pre className="mb-6 max-w-md rounded-lg bg-muted px-4 py-3 text-left text-xs text-muted-foreground overflow-x-auto">
                            {this.state.error.message}
                        </pre>
                    )}
                    <button
                        onClick={this.handleReset}
                        className="rounded-lg bg-primary px-6 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90"
                    >
                        Back to Dashboard
                    </button>
                </div>
            );
        }

        return this.props.children;
    }
}

export default ErrorBoundary;
