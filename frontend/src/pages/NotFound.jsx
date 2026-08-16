import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Home, ArrowLeft } from 'lucide-react';

/**
 * NotFound — custom 404 page for unmatched routes.
 */
const NotFound = () => {
    const navigate = useNavigate();

    return (
        <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4 text-center">
            {/* Decorative background blobs */}
            <div className="absolute top-[-10%] left-[-5%] w-72 h-72 rounded-full bg-income/10 blur-[100px] pointer-events-none" />
            <div className="absolute bottom-[-10%] right-[-5%] w-72 h-72 rounded-full bg-expense/10 blur-[100px] pointer-events-none" />

            <div className="relative z-10 space-y-4">
                <p className="font-display text-8xl font-bold text-foreground/10 select-none leading-none">
                    404
                </p>
                <div className="mb-6 flex h-20 w-20 mx-auto items-center justify-center rounded-2xl bg-muted text-muted-foreground">
                    <Home size={36} />
                </div>
                <h1 className="font-display text-3xl font-bold text-foreground">
                    Page not found
                </h1>
                <p className="text-muted-foreground max-w-sm mx-auto">
                    The page you're looking for doesn't exist or has been moved.
                </p>

                <div className="flex flex-col sm:flex-row gap-3 justify-center pt-4">
                    <button
                        onClick={() => navigate(-1)}
                        className="inline-flex items-center gap-2 rounded-lg border border-border px-5 py-2.5 text-sm font-semibold text-foreground transition hover:bg-muted"
                    >
                        <ArrowLeft size={16} />
                        Go back
                    </button>
                    <button
                        onClick={() => navigate('/dashboard')}
                        className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-sm transition hover:opacity-90"
                    >
                        <Home size={16} />
                        Dashboard
                    </button>
                </div>
            </div>
        </div>
    );
};

export default NotFound;
