import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class ComplexPasswordValidator:
    """Enforce uppercase, lowercase, numeric, and special character requirements."""

    def validate(self, password, user=None):
        errors = []

        if not re.search(r"[A-Z]", password):
            errors.append(_("Password must contain at least one uppercase letter (A-Z)."))
        if not re.search(r"[a-z]", password):
            errors.append(_("Password must contain at least one lowercase letter (a-z)."))
        if not re.search(r"\d", password):
            errors.append(_("Password must contain at least one number (0-9)."))
        if not re.search(r"[!@#$%^&*()_+\-=[\]{};':\"\\|,.<>/?]", password):
            errors.append(_("Password must contain at least one special character."))

        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "Your password must contain at least one uppercase letter, one lowercase letter, one number, "
            "and one special character."
        )


class LenientUserAttributeSimilarityValidator:
    """
    More lenient password similarity validator that allows reasonable variations.
    Prevents overly obvious matches (e.g., exact username as password) but allows
    passwords with added symbols, numbers, or mixed casing.
    """

    def validate(self, password, user=None):
        if not user:
            return

        username = user.username.lower()
        password_lower = password.lower()

        # Check if password is exactly the username (case-insensitive)
        if password_lower == username:
            raise ValidationError(
                _("The password is too similar to the username."),
                code='password_too_similar',
            )

        # Check if password is username with only numbers appended/prepended (e.g., "dee123", "123dee")
        # Allow if it has special characters or significant modification
        if re.match(r'^\d+' + re.escape(username) + r'$', password_lower) or \
           re.match(r'^' + re.escape(username) + r'\d+$', password_lower):
            raise ValidationError(
                _("The password is too similar to the username. Please add special characters or more variation."),
                code='password_too_similar',
            )

        # Check if password is username with only common substitutions (e.g., "d33" for "dee")
        # This is a basic check - if more than 50% of characters are the same as username
        # and no special characters are present, reject it
        if not re.search(r"[!@#$%^&*()_+\-=[\]{};':\"\\|,.<>/?]", password):
            # Count matching characters
            matches = sum(1 for a, b in zip(username, password_lower) if a == b)
            similarity_ratio = matches / max(len(username), len(password_lower))
            
            # If more than 70% similar and no special chars, reject
            if similarity_ratio > 0.7:
                raise ValidationError(
                    _("The password is too similar to the username. Please add special characters or more variation."),
                    code='password_too_similar',
                )

    def get_help_text(self):
        return _(
            "Your password must not be too similar to your username. "
            "However, passwords with special characters, numbers, or mixed casing are allowed."
        )
