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
