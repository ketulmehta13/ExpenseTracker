import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Wallet, Loader2 } from 'lucide-react';
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
    const { register } = useAuth();
    const navigate = useNavigate();

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
            navigate('/');
        } catch (err) {
            // Enhanced Error Parsing for Django/DRF
            const errorData = err.response?.data;
            if (errorData && typeof errorData === 'object') {
                const messages = Object.entries(errorData).map(([key, value]) => {
                    const detail = Array.isArray(value) ? value.join(', ') : value;
                    return `${key}: ${detail}`;
                });
                setError(messages.join(' | '));
            } else {
                setError('Registration failed. Please check your connection.');
            }
            console.error("Signup error detail:", errorData);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center bg-background px-4">
            <Card className="w-full max-w-md border-border/50 shadow-2xl bg-card/50 backdrop-blur-md">
                <CardHeader className="space-y-3 text-center flex flex-col items-center pt-8">
                    <div className="bg-primary/20 p-3 rounded-full mb-2">
                        <Wallet className="h-8 w-8 text-primary" />
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
                                <Input
                                    id="password"
                                    type="password"
                                    required
                                    placeholder="Create a password (min. 6 chars)"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                />
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