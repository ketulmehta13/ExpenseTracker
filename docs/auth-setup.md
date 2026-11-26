# Sign-in setup: email codes and Google

The app's code handles both. Each needs a few settings in the Supabase dashboard (and, for
Google, in Google Cloud). Until they're done, the app still works: sign-up emails keep their
link, and the Google button stays hidden.

## How it works

- **Sign up.** Supabase emails a 6-digit code. The app asks for it, and the right code confirms
  the address and signs the user in (`verifyOtp`, type `email`). "Send a new code" is available
  after 60 seconds (`resend`, type `signup`).
- **Signing in before confirming.** The login page sends a fresh code and shows the same screen.
- **Google.** "Continue with Google" leaves for Google, which sends the user back to `/login` with
  a session, then on to the dashboard. The button appears only when Supabase reports Google as
  enabled (`GET /auth/v1/settings`), so it never leads to an error page. New Google users get a
  profile from the existing `handle_new_user` trigger (username: the part of the email before
  the @, with a suffix if it's taken). A Google sign-in with the email of an existing account
  joins that account.

Code: `frontend/src/context/AuthContext.jsx`, `frontend/src/components/auth/`,
`frontend/src/pages/Login.jsx`, `frontend/src/pages/Register.jsx`. Tests:
`frontend/e2e/auth.public.spec.js`.

## 1. An email sender (needed for real users)

Supabase's built-in email only reaches your own team's addresses and sends a few emails an hour.

1. Create a free account with an SMTP provider. Brevo (300 emails a day, no domain needed:
   verify one sender address) is the simplest; Resend needs your own domain.
2. Supabase: **Authentication > Emails > SMTP Settings**: switch on custom SMTP and enter the
   host, port, username, password, sender email and sender name from the provider.
   These stay in Supabase; never put them in the repo.

## 2. Codes instead of links

1. **Authentication > Sign In / Providers > Email**: keep **Confirm email** on. Set the email
   OTP length to 6 and the expiry to 600 seconds (10 minutes).
2. **Authentication > Emails > Templates > Confirm sign up**: put the code in the email:

   ```html
   <h2>Your Expense Tracker code</h2>
   <p>Enter this code to confirm your account:</p>
   <p style="font-size:28px;font-weight:bold;letter-spacing:6px">{{ .Token }}</p>
   <p>It expires in 10 minutes. If you didn't sign up, ignore this email.</p>
   ```

## 3. Google

1. [Google Cloud Console](https://console.cloud.google.com): create a project.
2. **APIs & Services > OAuth consent screen**: External; app name, support email; authorised
   domains `ketul-expense-tracker.vercel.app` and `supabase.co`. Publish the app so anyone can
   sign in, not only test users.
3. **Credentials > Create credentials > OAuth client ID > Web application**:
   - Authorised JavaScript origins: `https://ketul-expense-tracker.vercel.app` and
     `http://localhost:5173`
   - Authorised redirect URI: `https://<project-ref>.supabase.co/auth/v1/callback` (Supabase
     shows the exact URL on its Google provider page)
4. Supabase: **Authentication > Sign In / Providers > Google**: enable it and paste the Client ID
   and Client Secret. The secret goes only there.
5. Supabase: **Authentication > URL Configuration**: Site URL
   `https://ketul-expense-tracker.vercel.app`; add Redirect URLs
   `https://ketul-expense-tracker.vercel.app/**` and `http://localhost:5173/**`.

## Check

- Sign up with a new email: the code arrives, and entering it opens the dashboard.
- Reload `/login`: "Continue with Google" is shown, and signing in with Google opens the dashboard.
