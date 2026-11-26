/**
 * Map Supabase Auth error messages to messages users can act on.
 * A null replacement keeps Supabase's own wording, which is already clear.
 */
const AUTH_ERROR_MESSAGES = [
    [/invalid login credentials/i, 'Incorrect email or password.'],
    [/email not confirmed/i, 'Please confirm your email first. We sent you a code.'],
    [/token has expired or is invalid|otp.*(expired|invalid)|invalid.*otp/i, 'That code is wrong or has expired. Check it, or send a new one.'],
    [/provider is not enabled|unsupported provider/i, "Google sign-in isn't switched on yet. Please use your email and password."],
    [/user already registered/i, 'An account with this email already exists. Try signing in instead.'],
    [/database error saving new user/i, 'We could not create your account. Please try a different username.'],
    [/rate limit|too many requests|for security purposes/i, 'Too many attempts. Please wait a minute and try again.'],
    [/new password should be different/i, 'Your new password must be different from your current one.'],
    [/auth session missing/i, 'Your session has expired. Please request a new link.'],
    [/password should be at least/i, null],
];

export const getAuthErrorMessage = (err, fallback = 'Something went wrong. Please try again.') => {
    const message = err?.message || '';
    for (const [pattern, friendly] of AUTH_ERROR_MESSAGES) {
        if (pattern.test(message)) return friendly ?? message;
    }
    return message || fallback;
};
