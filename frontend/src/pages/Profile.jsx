import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { User, Loader2, Save } from 'lucide-react';
import api from '../services/api';

const Profile = () => {
    const { user } = useAuth();
    const [budget, setBudget] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchUserData = async () => {
            try {
                const res = await api.get('/auth/user/');
                if (res.data.monthly_budget !== null && res.data.monthly_budget !== undefined) {
                    setBudget(res.data.monthly_budget);
                }
            } catch (err) {
                console.error('Failed to fetch user data', err);
            }
        };
        fetchUserData();
    }, []);

    const handleUpdateBudget = async (e) => {
        e.preventDefault();
        setLoading(true);
        setMessage(null);
        setError(null);
        try {
            await api.patch('/auth/user/', { monthly_budget: budget || 0 });
            setMessage('Budget updated successfully.');
        } catch (err) {
            setError('Failed to update budget.');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="space-y-6 animate-in fade-in duration-500 max-w-2xl mx-auto pt-6">
            <div className="flex flex-col gap-1">
                <h1 className="text-3xl font-bold tracking-tight">Profile Settings</h1>
                <p className="text-muted-foreground">Manage your account preferences and goals.</p>
            </div>

            <Card className="shadow-sm">
                <CardHeader>
                    <div className="flex items-center space-x-4">
                        <div className="bg-primary/20 p-4 rounded-full">
                            <User className="h-8 w-8 text-primary" />
                        </div>
                        <div>
                            <CardTitle className="text-2xl">{user?.username}</CardTitle>
                            <CardDescription>{user?.email}</CardDescription>
                        </div>
                    </div>
                </CardHeader>
            </Card>

            <Card className="shadow-sm">
                <CardHeader>
                    <CardTitle>Financial Goals</CardTitle>
                    <CardDescription>Set a monthly budget to help track your spending</CardDescription>
                </CardHeader>
                <form onSubmit={handleUpdateBudget}>
                    <CardContent className="space-y-4">
                        {message && (
                            <div className="p-3 bg-emerald-500/15 text-emerald-500 text-sm rounded-lg border border-emerald-500/30">
                                {message}
                            </div>
                        )}
                        {error && (
                            <div className="p-3 bg-destructive/15 text-destructive text-sm rounded-lg border border-destructive/30">
                                {error}
                            </div>
                        )}
                        <div className="space-y-2">
                            <Label htmlFor="budget">Monthly Budget Limit ($)</Label>
                            <Input
                                id="budget"
                                type="number"
                                step="0.01"
                                placeholder="e.g. 2000.00"
                                value={budget}
                                onChange={(e) => setBudget(e.target.value)}
                            />
                            <p className="text-xs text-muted-foreground">
                                We will alert you on the dashboard if you exceed this budget. Setting to 0 disables warnings.
                            </p>
                        </div>
                    </CardContent>
                    <CardFooter>
                        <Button type="submit" disabled={loading}>
                            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Save className="mr-2 h-4 w-4" />}
                            Save Changes
                        </Button>
                    </CardFooter>
                </form>
            </Card>
        </div>
    );
};

export default Profile;
