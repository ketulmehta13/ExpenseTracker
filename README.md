# 💸 Expense Tracker — Full-Stack Application

A modern, production-grade expense tracker and personal finance management system. Built with **React 18, Vite, and Tailwind CSS v4** on the frontend (deployed on **Vercel**), powered by **Supabase** (PostgreSQL, Row Level Security, and JWT Auth) as the active backend.

🌐 **Live Production App:** [https://ketul-expense-tracker.vercel.app](https://ketul-expense-tracker.vercel.app)

---

## 🏛️ System Architecture

- **Frontend:** React + Vite, Tailwind CSS v4 `@theme` design tokens, Sonner toast notifications, Recharts analytics, jsPDF reports.
- **Backend / Database:** Supabase (Managed PostgreSQL 15+).
- **Authentication:** Supabase Auth (JWT tokens, session auto-refresh, email password reset).
- **Security:** Strict PostgreSQL **Row Level Security (RLS)** on all tables (`transactions`, `categories`, `profiles`), ensuring 100% data isolation per user.
- **Hosting:**
  - Frontend: Vercel with automated CI/CD branch previews and production deployments.
  - Backend: Supabase cloud managed database & auth.

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- Node.js 18+ & npm
- A [Supabase](https://supabase.com) project

### 2. Configure Environment Variables
Copy `.env.example` to `frontend/.env.local`:
```bash
cp .env.example frontend/.env.local
```
Fill in your Supabase credentials:
```env
VITE_SUPABASE_URL=https://your-project-id.supabase.co
VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
```
> ⚠️ **Security Warning:** Only use the `anon/public` key in the frontend. Never expose the `service_role` key in client code or Git.

### 3. Apply Supabase Database Migrations
Run the SQL migration located at `supabase/migrations/20260816000000_production_hardening.sql` in your Supabase SQL Editor to establish:
1. `profiles`, `categories`, and `transactions` tables with strict constraints (`CHECK amount > 0`).
2. High-performance composite indexes (`idx_transactions_user_date`, etc.).
3. Row Level Security policies (`auth.uid() = user_id`).
4. Automatic profile provisioning trigger on user registration.
5. Default global categories seed.

### 4. Install & Run Frontend
```bash
cd frontend
npm install
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## 🛡️ Security & Row Level Security (RLS)

Every table has RLS enabled with explicit tenant isolation policies:

| Table | Operation | Policy Enforcement |
|---|---|---|
| `transactions` | `SELECT`, `INSERT`, `UPDATE`, `DELETE` | `auth.uid() = user_id` |
| `categories` | `SELECT` | `auth.uid() = user_id OR user_id IS NULL` (includes defaults) |
| `categories` | `INSERT`, `UPDATE`, `DELETE` | `auth.uid() = user_id` |
| `profiles` | `SELECT`, `INSERT`, `UPDATE`, `DELETE` | `auth.uid() = id` |

### Verifying RLS
Execute `supabase/tests/rls_security_test.sql` in the Supabase SQL editor to run the automated policy isolation test suite.

---

## 🧪 CI/CD & Production Readiness

- **Continuous Integration:** `.github/workflows/ci.yml` validates builds, verifies dependency trees, and checks migration security on every push and PR.
- **Backups:**
  - On Supabase Pro/Team tiers: Daily automated point-in-time recovery (PITR).
  - Manual backup via CLI:
    ```bash
    supabase db dump -f backup_$(date +%Y%m%d).sql
    ```
- **Staging Environment:** Create a separate Supabase project for staging and configure a Vercel preview branch deployment.

---

## 📁 Repository Structure

```
├── .github/workflows/ci.yml       # Automated CI build & migration check
├── .env.example                   # Environment variable template
├── frontend/                      # React + Vite application
│   ├── src/
│   │   ├── components/            # UI components (TransactionModal, etc.)
│   │   ├── context/               # AuthContext (Supabase auth listener)
│   │   ├── layouts/               # MainLayout (Sidebar + Mobile navigation)
│   │   ├── pages/                 # Dashboard, Transactions, Reports, Categories, Settings
│   │   └── services/              # api.js (Supabase queries & pagination)
├── supabase/
│   ├── migrations/                # Versioned SQL migrations & RLS policies
│   └── tests/                     # RLS security verification suite
└── backend/                       # Legacy Django project (kept for reference)
```

---

## 📄 License
MIT © Ketul Mehta
