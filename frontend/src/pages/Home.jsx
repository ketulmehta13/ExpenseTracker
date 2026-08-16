import React from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { PieChart, TrendingUp, ShieldCheck, IndianRupee, ArrowRight } from 'lucide-react';
import logoIcon from '../assets/logo-icon.png';
import { useAuth } from '../context/AuthContext';

const Home = () => {
    const navigate = useNavigate();
    const { user } = useAuth();

    return (
        <div className="h-screen w-full bg-background text-foreground flex flex-col font-sans overflow-hidden relative">
            {/* Background Decorations */}
            <div className="absolute top-[-20%] left-[-10%] w-[45%] h-[45%] rounded-full bg-gradient-to-br from-primary/25 to-secondary/15 blur-[140px] pointer-events-none" />
            <div className="absolute bottom-[-20%] right-[-10%] w-[45%] h-[45%] rounded-full bg-gradient-to-tl from-secondary/25 to-primary/15 blur-[140px] pointer-events-none" />

            {/* Header */}
            <header className="w-full px-6 md:px-12 py-3 flex justify-between items-center backdrop-blur-md bg-background/60 border-b border-border/40 z-50 flex-shrink-0">
                <div className="flex items-center gap-3">
                    <img src={logoIcon} alt="Expense Tracker" className="w-9 h-9 rounded-xl shadow-lg shadow-primary/30 object-contain" />
                    <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-primary to-secondary bg-clip-text text-transparent">
                        Expense Tracker
                    </span>
                </div>

                <div className="flex items-center gap-3">
                    {user ? (
                        <button
                            onClick={() => navigate('/dashboard')}
                            className="group px-5 py-2 bg-primary text-primary-foreground font-semibold rounded-full shadow-lg shadow-primary/25 hover:shadow-xl hover:-translate-y-0.5 transition-all duration-300 flex items-center gap-2 text-sm"
                        >
                            Dashboard
                            <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
                        </button>
                    ) : (
                        <button
                            onClick={() => navigate('/login')}
                            className="group px-5 py-2 bg-primary text-primary-foreground font-semibold rounded-full shadow-lg shadow-primary/25 hover:shadow-xl hover:-translate-y-0.5 transition-all duration-300 flex items-center gap-2 text-sm"
                        >
                            Sign In
                            <ArrowRight size={14} className="group-hover:translate-x-0.5 transition-transform" />
                        </button>
                    )}
                </div>
            </header>

            {/* Main Content - fills remaining height */}
            <main className="flex-1 flex flex-col items-center justify-center px-4 sm:px-6 lg:px-8 max-w-6xl mx-auto w-full z-10">
                <div className="flex flex-col lg:flex-row items-center justify-between gap-10 w-full">

                    {/* Left Side - Hero Text */}
                    <motion.div
                        initial={{ opacity: 0, x: -30 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ duration: 0.6 }}
                        className="flex-1 text-center lg:text-left"
                    >
                        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-display font-bold tracking-tight leading-[1.1] mb-4">
                            <span className="text-foreground">Master Your</span>
                            <br />
                            <span className="bg-gradient-to-r from-primary via-secondary to-primary bg-clip-text text-transparent">
                                Money Flow
                            </span>
                        </h1>

                        <p className="text-base sm:text-lg text-muted-foreground leading-relaxed max-w-lg mx-auto lg:mx-0 mb-6">
                            Track expenses in ₹, set budgets, analyze spending — all in one clean dashboard.
                        </p>

                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.3, duration: 0.4 }}
                            className="flex flex-col sm:flex-row gap-3 justify-center lg:justify-start"
                        >
                            <button
                                onClick={() => navigate(user ? '/dashboard' : '/register')}
                                className="group px-7 py-3.5 bg-gradient-to-r from-primary to-primary/90 text-primary-foreground text-base font-bold rounded-full shadow-xl shadow-primary/30 hover:-translate-y-0.5 hover:shadow-2xl transition-all duration-300 flex items-center justify-center gap-2"
                            >
                                <IndianRupee size={18} />
                                Get Started Free
                                <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
                            </button>
                            {!user && (
                                <button
                                    onClick={() => navigate('/login')}
                                    className="px-7 py-3.5 text-foreground text-base font-semibold rounded-full border-2 border-border hover:border-primary/30 hover:bg-primary/5 transition-all duration-300"
                                >
                                    I have an account
                                </button>
                            )}
                        </motion.div>
                    </motion.div>

                    {/* Right Side - Feature Cards */}
                    <motion.div
                        initial={{ opacity: 0, x: 30 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.3, duration: 0.6 }}
                        className="flex-1 grid grid-cols-2 gap-3 max-w-md w-full"
                    >
                        {[
                            { icon: PieChart, color: 'text-primary', bg: 'bg-primary/10', title: 'Analytics', desc: 'Visual charts & insights' },
                            { icon: TrendingUp, color: 'text-emerald-500', bg: 'bg-emerald-500/10', title: 'Track Spend', desc: 'Income & expense logs' },
                            { icon: IndianRupee, color: 'text-blue-500', bg: 'bg-blue-500/10', title: 'Budgets', desc: 'Set monthly limits' },
                            { icon: ShieldCheck, color: 'text-secondary', bg: 'bg-secondary/10', title: 'Secure', desc: 'Your data stays private' },
                        ].map((f, i) => (
                            <motion.div
                                key={i}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: 0.4 + i * 0.1, duration: 0.4 }}
                                className="group p-5 rounded-2xl bg-card/80 border border-border/50 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 backdrop-blur-sm"
                            >
                                <div className={`w-10 h-10 ${f.bg} rounded-xl flex items-center justify-center mb-3 group-hover:scale-110 transition-transform`}>
                                    <f.icon className={f.color} size={20} />
                                </div>
                                <h3 className="text-sm font-bold text-foreground mb-1">{f.title}</h3>
                                <p className="text-xs text-muted-foreground">{f.desc}</p>
                            </motion.div>
                        ))}
                    </motion.div>
                </div>
            </main>

            {/* Footer - slim */}
            <footer className="w-full py-3 border-t border-border/30 bg-card/20 backdrop-blur-sm flex-shrink-0 z-10">
                <div className="max-w-6xl mx-auto px-6 flex justify-between items-center text-xs text-muted-foreground">
                    <span>© 2026 Expense Tracker by Ketul Mehta</span>
                </div>
            </footer>
        </div>
    );
};

export default Home;
