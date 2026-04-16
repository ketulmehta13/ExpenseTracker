from django.contrib.auth.hashers import PBKDF2PasswordHasher


class FastPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """
    A PBKDF2 password hasher with reduced iterations for better performance
    on limited-CPU hosting (e.g., Render free tier).

    Django 6.0 defaults to 870,000 iterations which causes 5-15 second delays
    during login/register on low-resource servers. 30,000 iterations with
    PBKDF2-SHA256 is still secure for a personal expense tracker.
    """
    iterations = 30_000
