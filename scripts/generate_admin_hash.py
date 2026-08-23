"""Génère le hash bcrypt du mot de passe admin à coller dans .env
(ADMIN_PASSWORD_HASH). Le mot de passe n'est jamais affiché ni stocké en clair.

Usage : python scripts/generate_admin_hash.py
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password  # noqa: E402


def main() -> None:
    password = getpass.getpass("Mot de passe admin : ")
    confirm = getpass.getpass("Confirmer le mot de passe : ")

    if not password:
        print("Le mot de passe ne peut pas être vide.")
        raise SystemExit(1)
    if password != confirm:
        print("Les deux mots de passe ne correspondent pas.")
        raise SystemExit(1)

    print("\nADMIN_PASSWORD_HASH=" + hash_password(password))


if __name__ == "__main__":
    main()
