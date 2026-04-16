import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader2, Eye, EyeOff, Coffee } from 'lucide-react';
import logoIcon from '../assets/logo-icon.png';
import { warmUp } from '../services/api';
import { useEffect } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';

const Register = () => {
    const [username, setUsername] = useState('');
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [showPassword, setShowPassword] = useState(false);
    const [isWakingUp, setIsWakingUp] = useState(false);
    const { register } = useAuth();
    const navigate = useNavigate();

    useEffect(() => {
        // Trigger warm-up
        warmUp();
        
        // Show subtle hint if server takes a moment to respond
        const timer = setTimeout(() => {
            setIsWakingUp(true);
        }, 1500);

        return () => clearTimeout(timer);
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);
        setIsLoading(true);

        // 1. Username Validation (Alphanumeric, @/./+/-/_ 3-20 chars)
        const usernameRegex = /^[\w.@+-]{3,20}$/;
        if (!usernameRegex.test(username)) {
            setError("Username must be 3-20 characters long and can only contain letters, numbers, and @/./+/-/_ characters.");
            setIsLoading(false);
            return;
        }

        // 2. Email Validation
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(email)) {
            setError("Please enter a valid email address.");
            setIsLoading(false);
            return;
        }

        // 3. Password Validation (min 6 chars)
        const passwordRegex = /^.{6,}$/;
        if (!passwordRegex.test(password)) {
            setError("Password must be at least 6 characters long.");
            setIsLoading(false);
            return;
        }

        try {
            await register(username, email, password);
            navigate('/dashboard');
        } catch (err) {
            // Enhanced Error Parsing for Django/DRF
            const errorData = err.response?.data;
            if (errorData && typeof errorData === 'object') {
                const messages = Object.entries(errorData).map(([key, value]) => {
                    const detail = Array.isArray(value) ? value.join(', ') : value;
                    return `${key}: ${detail}`;
                });
                setError(messages.join(' | '));
            } else if (err.request) {
                // The request was made but no response was received (Network error)
                setError('Registration failed: Backend server is unreachable. Please check the API URL configuration.');
            } else {
                setError('Registration failed: ' + (err.message || 'Unknown error'));
            }
            console.error("Signup error detail:", err);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-background px-4">
            <Card className="w-full max-w-md border-border/50 shadow-2xl bg-card/50 backdrop-blur-md">
                <CardHeader className="space-y-3 text-center flex flex-col items-center pt-8">
                    <div className="mb-2">
                        <img src={logoIcon} alt="Ketul Expense Tracker" className="h-14 w-14 rounded-xl object-contain" />
                    </div>
                    <CardTitle className="text-3xl font-extrabold tracking-tight">Create an account</CardTitle>
                    <CardDescription className="text-muted-foreground text-sm">
                        Start tracking your expenses today
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-6">
                        {error && (
                            <div className="p-3 bg-destructive/15 text-destructive text-sm rounded-lg border border-destructive/30 animate-in fade-in duration-300">
                                {error}
                            </div>
                        )}
                        {isWakingUp && !isLoading && !error && (
                            <div className="p-3 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-sm rounded-lg border border-amber-500/20 flex items-center gap-2 animate-pulse">
                                <Coffee size={16} />
                                Server is waking up from sleep...
                            </div>
                        )}
                        <div className="space-y-4">
                            <div className="space-y-2">
                                <Label htmlFor="username">Username</Label>
                                <Input
                                    id="username"
                                    type="text"
                                    required
                                    placeholder="Choose a username"
                                    value={username}
                                    onChange={(e) => setUsername(e.target.value)}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="email">Email</Label>
                                <Input
                                    id="email"
                                    type="email"
                                    required
                                    placeholder="you@example.com"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="password">Password</Label>
                                <div className="relative">
                                    <Input
                                        id="password"
                                        type={showPassword ? 'text' : 'password'}
                                        required
                                        placeholder="Create a password (min. 6 chars)"
                                        className="pr-10"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                    />
                                    <button
                                        type="button"
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                                        onClick={() => setShowPassword(v => !v)}
                                        tabIndex={-1}
                                    >
                                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                                    </button>
                                </div>
                            </div>
                        </div>

                        <Button 
                            type="submit" 
                            className="w-full h-11 text-base font-semibold" 
                            disabled={isLoading}
                        >
                            {isLoading ? (
                                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                            ) : "Sign up"}
                        </Button>
                    </form>
                </CardContent>
                <CardFooter className="justify-center pb-8 border-t border-border/40 pt-6">
                    <p className="text-sm text-muted-foreground">
                        Already have an account?{' '}
                        <Link to="/login" className="font-semibold text-primary hover:text-primary/80 transition-colors">
                            Sign in
                        </Link>
                    </p>
                </CardFooter>
            </Card>
        </div>
    );
};

export default Register;