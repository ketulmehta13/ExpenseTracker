import React, { createContext, useContext, useEffect } from "react";

const ThemeContext = createContext({ theme: "light" });

/**
 * ThemeProvider — Enforces clean White & Green light theme across the application.
 */
export function ThemeProvider({ children }) {
    useEffect(() => {
        const root = window.document.documentElement;
        root.classList.remove("dark");
        root.classList.add("light");
        // Clear any obsolete dark mode storage
        localStorage.removeItem("et-theme");
        localStorage.removeItem("expensify-ui-theme");
    }, []);

    return (
        <ThemeContext.Provider value={{ theme: "light" }}>
            {children}
        </ThemeContext.Provider>
    );
}

export const useTheme = () => useContext(ThemeContext);
