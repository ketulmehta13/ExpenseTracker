import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Wallet, PieChart, TrendingUp, ShieldCheck, IndianRupee, ArrowRight, Sparkles, BarChart3 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

const Home = () => {
    const navigate = useNavigate();
    const { user } = useAuth();

    const stats = [
        { label: 'Active Users', value: '10K+' },
        { label: 'Transactions Tracked', value: '1M+' },
        { label: 'Money Saved', value: '₹5Cr+' },
    ];

    return (
        <div className="min-h-screen bg-background text-foreground flex flex-col font-sans overflow-x-hidden relative">
            {/* Background Decorations */}
            <div className="absolute top-[-15%] left-[-15%] w-[50%] h-[50%] rounded-full bg-gradient-to-br from-primary/30 to-secondary/20 blur-[140px] pointer-events-none" />
            <div className="absolute bottom-[-15%] right-[-15%] w-[50%] h-[50%] rounded-full bg-gradient-to-tl from-secondary/30 to-primary/20 blur-[140px] pointer-events-none" />
            <div className="absolute top-[40%] right-[20%] w-[20%] h-[20%] rounded-full bg-accent/10 blur-[100px] pointer-events-none" />

            {/* Header */}
            <header className="w-full px-6 md:px-12 py-4 flex justify-between items-center backdrop-blur-md bg-background/60 sticky top-0 z-50 border-b border-border/40">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-gradient-to-br from-primary to-secondary rounded-xl flex items-center justify-center shadow-lg shadow-primary/30">
                        <Wallet className="text-white" size={22} />
                    </div>
                    <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
                        Expense Tracker
                    </span>
                </div>
                
                <div className="flex items-center gap-3">
                    {user ? (
                        <button 
                            onClick={() => navigate('/dashboard')}
                            className="group px-6 py-2.5 bg-primary text-primary-foreground font-semibold rounded-full shadow-lg shadow-primary/25 hover:shadow-xl hover:shadow-primary/30 hover:-translate-y-0.5 transition-all duration-300 flex items-center gap-2"
                        >
                            Dashboard
                            <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
                        </button>
                    ) : (
                        <>
                            <button 
                                onClick={() => navigate('/login')}
                                className="hidden sm:block px-5 py-2.5 text-primary font-semibold rounded-full border-2 border-primary/20 hover:border-primary/40 hover:bg-primary/5 transition-all duration-300"
                            >
                                Sign In
                            </button>
                            <button 
                                onClick={() => navigate('/register')}
                                className="group px-6 py-2.5 bg-primary text-primary-foreground font-semibold rounded-full shadow-lg shadow-primary/25 hover:shadow-xl hover:shadow-primary/30 hover:-translate-y-0.5 transition-all duration-300 flex items-center gap-2"
                            >
                                Get Started
                                <ArrowRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
                            </button>
                        </>
                    )}
                </div>
            </header>

            {/* Hero Section */}
            <main className="flex-1 flex flex-col items-center px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto w-full z-10">
                {/* Hero */}
                <section className="flex flex-col items-center justify-center py-20 md:py-28">
                    <motion.div 
                        initial={{ opacity: 0, y: 30 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.6 }}
                        className="text-center space-y-6 max-w-4xl"
                    >
                        <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-medium mb-4">
                            <Sparkles size={16} />
                            Smart Finance Management
                        </div>
                        
                        <h1 className="text-5xl sm:text-6xl md:text-7xl font-extrabold tracking-tight leading-[1.1]">
                            <span className="text-foreground">Master Your</span>
                            <br />
                            <span className="bg-gradient-to-r from-primary via-secondary to-primary bg-clip-text text-transparent">
                                Money Flow
                            </span>
                        </h1>
                        
                        <p className="text-lg sm:text-xl text-muted-foreground leading-relaxed max-w-2xl mx-auto">
                            Track expenses in Indian Rupees, analyze spending habits, set budgets, and take control of your finances — all in one beautiful dashboard.
                        </p>
                        
                        <motion.div 
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.4, duration: 0.5 }}
                            className="pt-6 flex flex-col sm:flex-row gap-4 justify-center items-center"
                        >
                            <button 
                                onClick={() => navigate(user ? '/dashboard' : '/register')}
                                className="group px-8 py-4 bg-gradient-to-r from-primary to-primary/90 text-primary-foreground text-lg font-bold rounded-full shadow-xl shadow-primary/30 hover:-translate-y-1 hover:shadow-2xl hover:shadow-primary/40 transition-all duration-300 flex items-center gap-2"
                            >
                                <IndianRupee size={20} />
                                Start Tracking Free
                                <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
                            </button>
                            <button 
                                onClick={() => navigate('/login')}
                                className="px-8 py-4 text-foreground text-lg font-semibold rounded-full border-2 border-border hover:border-primary/30 hover:bg-primary/5 transition-all duration-300"
                            >
                                I have an account
                            </button>
                        </motion.div>
                    </motion.div>
                </section>

                {/* Stats Bar */}
                <motion.div 
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.5, duration: 0.6 }}
                    className="w-full max-w-3xl mx-auto mb-20"
                >
                    <div className="grid grid-cols-3 gap-4 p-6 rounded-2xl bg-card/80 backdrop-blur-sm border border-border/50 shadow-lg">
                        {stats.map((stat, i) => (
                            <div key={i} className="text-center">
                                <div className="text-2xl md:text-3xl font-extrabold text-primary">{stat.value}</div>
                                <div className="text-xs md:text-sm text-muted-foreground mt-1">{stat.label}</div>
                            </div>
                        ))}
                    </div>
                </motion.div>

                {/* Features Section */}
                <motion.div 
                    initial={{ opacity: 0, y: 40 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.6, duration: 0.7 }}
                    className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 w-full pb-24"
                >
                    {[
                        { icon: PieChart, color: 'primary', title: 'Clear Analytics', desc: 'Visualize spending with interactive pie and bar charts.' },
                        { icon: TrendingUp, color: 'secondary', title: 'Smart Tracking', desc: 'Monitor income, expenses, and savings trends over time.' },
                        { icon: BarChart3, color: 'primary', title: 'Budget Goals', desc: 'Set monthly budgets and get alerts before overspending.' },
                        { icon: ShieldCheck, color: 'secondary', title: 'Secure & Private', desc: 'Your financial data is encrypted and only yours.' },
                    ].map((feature, i) => (
                        <div key={i} className="group p-6 rounded-2xl bg-card/70 border border-border/50 shadow-md hover:shadow-xl hover:-translate-y-1 transition-all duration-300 backdrop-blur-sm">
                            <div className={`w-12 h-12 bg-${feature.color}/10 rounded-xl flex items-center justify-center mb-5 group-hover:scale-110 transition-transform`}>
                                <feature.icon className={`text-${feature.color}`} size={24} />
                            </div>
                            <h3 className="text-lg font-bold text-foreground mb-2">{feature.title}</h3>
                            <p className="text-sm text-muted-foreground leading-relaxed">{feature.desc}</p>
                        </div>
                    ))}
                </motion.div>
            </main>

            {/* Footer */}
            <footer className="w-full py-6 border-t border-border/30 bg-card/30 backdrop-blur-sm">
                <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row justify-between items-center gap-3">
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <Wallet size={16} className="text-primary" />
                        <span>© 2026 Expense Tracker by Ketul</span>
                    </div>
                    <div className="text-sm text-muted-foreground">
                        Built with ❤️ in India
                    </div>
                </div>
            </footer>
        </div>
    );
};

export default Home;
