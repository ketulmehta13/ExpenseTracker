from django.contrib.auth.hashers import PBKDF2PasswordHasher


class FastPBKDF2PasswordHasher(PBKDF2PasswordHasher):
    """
    A PBKDF2 password hasher with reduced iterations for better performance
    on limited-CPU hosting (e.g., Railway free/hobby tier).

    Django 6.0 defaults to 870,000 iterations which causes 5-15 second delays
    during login/register on low-resource servers. This uses 260,000 iterations
    (the Django 4.2 default), which is still secure for most applications.
    """
    iterations = 260_000
