import React, { createElement } from 'react';
import {
    Baby, Briefcase, Car, Clapperboard, Coffee, Dumbbell, Fuel, Gift, GraduationCap, HeartPulse,
    House, Landmark, Laptop, PawPrint, PiggyBank, Plane, Receipt, Repeat, ShieldCheck, ShoppingBag,
    ShoppingBasket, Smartphone, Sparkles, Tag, TrendingUp, UtensilsCrossed, Wallet, Wrench, Zap,
} from 'lucide-react';

/**
 * The icon for a category, picked from its name: users only type "Groceries" or "Gym" and get
 * a basket or a dumbbell. The first matching rule wins, so specific words come before broad
 * ones ("Coffee" before "Food"); names nothing matches get a tag.
 */
const RULES = [
    [/grocer|supermarket|vegetable|fruit|kirana|blinkit|zepto|bigbasket|dmart/, ShoppingBasket],
    [/coffee|caf[eé]|chai|\btea\b|starbucks/, Coffee],
    [/food|dining|restaurant|\beat|meal|lunch|dinner|breakfast|snack|swiggy|zomato|takeaway/, UtensilsCrossed],
    [/\brent|hous|\bhome|\bemi\b|mortgage/, House],
    [/travel|trip|flight|holiday|vacation|hotel|\btour/, Plane],
    [/fuel|petrol|diesel|\bcng\b|\bgas\b/, Fuel],
    [/transport|commute|\bcab|taxi|uber|\bola\b|metro|\bbus\b|train|parking|toll|\bcar\b|bike|vehicle/, Car],
    [/utilit|electric|power|water|\bbill/, Zap],
    [/phone|mobile|recharge|internet|wi-?fi|broadband/, Smartphone],
    [/subscri|netflix|prime|hotstar|spotify|\bott\b/, Repeat],
    [/entertain|movie|cinema|film|music|gam(e|ing)|concert|party|\bfun\b|outing/, Clapperboard],
    [/salary|income|wage|payroll|stipend|bonus|paycheck/, Briefcase],
    [/freelanc|business|client|consult/, Laptop],
    [/saving|deposit|\bfd\b|emergency fund/, PiggyBank],
    [/invest|stock|share|mutual|\bsip\b|crypto|dividend/, TrendingUp],
    [/shop|cloth|fashion|apparel|amazon|flipkart|myntra|meesho|electronic/, ShoppingBag],
    [/health|medic|doctor|hospital|pharma|clinic|dental/, HeartPulse],
    [/gym|fitness|sport|yoga|workout/, Dumbbell],
    [/educat|school|college|course|tuition|class|book|study|exam/, GraduationCap],
    [/gift|donat|charity|festival|wedding/, Gift],
    [/insur|policy|premium/, ShieldCheck],
    [/\bpet|\bdog|\bvet\b/, PawPrint],
    [/\bkid|child|baby|daycare/, Baby],
    [/loan|debt|credit|interest|repay/, Landmark],
    [/\btax|\bgst\b|\btds\b/, Receipt],
    [/beauty|salon|\bspa\b|groom|haircut|personal care|cosmetic/, Sparkles],
    [/repair|plumb|appliance|household/, Wrench],
    [/cash|\batm\b|transfer|wallet|\bupi\b/, Wallet],
];

const iconForCategory = (name = '') => {
    const text = name.toLowerCase();
    return RULES.find(([pattern]) => pattern.test(text))?.[1] ?? Tag;
};

const CategoryIcon = ({ name, color = '#64748b', className = 'h-10 w-10 rounded-xl', size = 20 }) => (
    <div
        className={`flex flex-shrink-0 items-center justify-center ${className}`}
        style={{ background: `${color}1f`, color }}
        aria-hidden="true"
    >
        {/* One of the module-level icons above, chosen by name: nothing is created per render */}
        {createElement(iconForCategory(name), { size, strokeWidth: 2.1 })}
    </div>
);

export default CategoryIcon;
