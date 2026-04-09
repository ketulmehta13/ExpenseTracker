import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Wallet, PieChart, TrendingUp, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Home = () => {
    const navigate = useNavigate();
    const { user } = useAuth();

    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col font-sans overflow-x-hidden relative">
            {/* Background Decorations */}
            <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] rounded-full bg-primary/20 blur-[120px] pointer-events-none" />
            <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] rounded-full bg-secondary/20 blur-[120px] pointer-events-none" />

            {/* Header */}
            <header className="w-full px-6 py-4 flex justify-between items-center backdrop-blur-md bg-background/50 sticky top-0 z-50 border-b border-border/50 shadow-sm">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-primary rounded-xl flex items-center justify-center shadow-lg">
                        <Wallet className="text-primary-foreground" size={24} />
                    </div>
                    <span className="text-xl font-bold tracking-tight text-primary">Expense Tracker</span>
                </div>
                
                <div className="flex items-center gap-4">
                    {user ? (
                        <button 
                            onClick={() => navigate('/dashboard')}
                            className="px-6 py-2 bg-primary text-primary-foreground font-semibold rounded-full shadow-md hover:bg-primary/90 transition-all active:scale-95 duration-200"
                        >
                            Dashboard
                        </button>
                    ) : (
                        <button 
                            onClick={() => navigate('/login')}
                            className="px-6 py-2 bg-primary text-primary-foreground font-semibold rounded-full shadow-md hover:bg-primary/90 transition-all active:scale-95 duration-200"
                        >
                            Sign In
                        </button>
                    )}
                </div>
            </header>

            {/* Hero Section */}
            <main className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto w-full z-10 py-16">
                <motion.div 
                    initial={{ opacity: 0, y: 30 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.6 }}
                    className="text-center space-y-6 max-w-3xl"
                >
                    <h1 className="text-5xl sm:text-6xl md:text-7xl font-extrabold tracking-tight text-primary leading-tight">
                        Take Control of Your <br/> <span className="text-secondary bg-clip-text text-transparent bg-gradient-to-r from-secondary to-primary drop-shadow-sm">Finances</span>
                    </h1>
                    <p className="text-lg sm:text-xl text-muted-foreground/80 leading-relaxed max-w-2xl mx-auto mt-6">
                        Track your expenses, analyze your spending habits, and achieve your financial goals with our modern, intuitive expense tracker.
                    </p>
                    
                    <motion.div 
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.4, duration: 0.5 }}
                        className="pt-8 flex gap-4 justify-center items-center"
                    >
                        <button 
                            onClick={() => navigate(user ? '/dashboard' : '/register')}
                            className="px-8 py-4 bg-primary text-primary-foreground text-lg font-semibold rounded-full shadow-xl hover:-translate-y-1 hover:shadow-2xl transition-all duration-300"
                        >
                            Get Started
                        </button>
                    </motion.div>
                </motion.div>

                {/* Features Section */}
                <motion.div 
                    initial={{ opacity: 0, y: 40 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.6, duration: 0.7 }}
                    className="mt-24 grid grid-cols-1 md:grid-cols-3 gap-8 w-full"
                >
                    <div className="p-8 rounded-[2rem] bg-card border border-border shadow-lg hover:shadow-xl transition-shadow backdrop-blur-sm bg-white/60">
                        <div className="w-14 h-14 bg-primary/10 rounded-2xl flex items-center justify-center mb-6">
                            <PieChart className="text-primary" size={28} />
                        </div>
                        <h3 className="text-2xl font-bold text-foreground mb-3">Clear Analytics</h3>
                        <p className="text-muted-foreground">Visualize your spending patterns across different categories effortlessly.</p>
                    </div>
                    
                    <div className="p-8 rounded-[2rem] bg-card border border-border shadow-lg hover:shadow-xl transition-shadow backdrop-blur-sm bg-white/60">
                        <div className="w-14 h-14 bg-secondary/10 rounded-2xl flex items-center justify-center mb-6">
                            <TrendingUp className="text-secondary" size={28} />
                        </div>
                        <h3 className="text-2xl font-bold text-foreground mb-3">Smart Tracking</h3>
                        <p className="text-muted-foreground">Monitor your financial health and observe how your savings grow over time.</p>
                    </div>
                    
                    <div className="p-8 rounded-[2rem] bg-card border border-border shadow-lg hover:shadow-xl transition-shadow backdrop-blur-sm bg-white/60">
                        <div className="w-14 h-14 bg-accent/10 rounded-2xl flex items-center justify-center mb-6">
                            <ShieldCheck className="text-accent" size={28} />
                        </div>
                        <h3 className="text-2xl font-bold text-foreground mb-3">Secure & Private</h3>
                        <p className="text-muted-foreground">Your data is yours. We implement robust security to keep your finances safe.</p>
                    </div>
                </motion.div>
            </main>
        </div>
    );
};

export default Home;
