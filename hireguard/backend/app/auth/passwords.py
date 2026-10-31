"""Password policy (NIST SP 800-63B style): length and a blocklist, no composition rules."""
import secrets

MIN_LENGTH = 12
MAX_LENGTH = 256

# Common passwords of 12+ characters (shorter ones already fail the length rule), plus local favourites.
COMMON = frozenset("""
123456789012 1234567890123 12345678901234 123456123456 111111111111 000000000000 123123123123
qwertyuiopas qwertyuiop12 qwertyuiop123 qwerty123456 qwertyqwerty azertyuiop12 azertyuiop123 azerty123456
azertyazerty 1q2w3e4r5t6y 1qaz2wsx3edc zaq12wsxcde3 passwordpassword password1234 password12345
password123456 passw0rd1234 p@ssw0rd1234 p@ssword1234 motdepasse123 motdepasse1234 iloveyou1234
welcome12345 welcome123456 letmein12345 administrator admin1234567 admin12345678 adminadmin123
changeme1234 changeme12345 football1234 baseball1234 superman1234 sunshine1234 princess1234
trustno11234 monkey123456 dragon123456 abc123456789 abcdefghijkl abcdef123456 tunisie12345
tunisia12345 tunis1234567 hireguard123 hireguard1234 hireguard2026 hackathon123 hackathon2026
supcom123456 supcom2026!! correcthorsebatterystaple
""".split())


def problem(password: str, email: str = "") -> str | None:
    """None if acceptable, else a message safe to show to the user."""
    if len(password) < MIN_LENGTH:
        return f"Password must have at least {MIN_LENGTH} characters."
    if len(password) > MAX_LENGTH:
        return f"Password must have at most {MAX_LENGTH} characters."
    low = password.lower()
    if low in COMMON or len(set(low)) <= 2:
        return "This password is too common. Pick a longer phrase that is unique to you."
    local = email.split("@")[0].lower()
    if local and len(local) >= 4 and local in low:
        return "Password must not contain your email address."
    return None


def generate() -> str:
    """Temporary password for an admin reset: 20 URL-safe characters, shown once."""
    return secrets.token_urlsafe(15)
