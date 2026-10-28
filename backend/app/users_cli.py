"""Manage users from the command line (e.g. the first admin on a new server).

  python -m app.users_cli create <username> --roles admin [--name "Full Name"] [--password ...]
  python -m app.users_cli list
  python -m app.users_cli password <username>

Without --password you are prompted (nothing is echoed).
"""
import argparse
import getpass

from fastapi import HTTPException
from sqlalchemy import func, select

from . import auth
from .db import session_scope
from .models import User


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.users_cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("username")
    create.add_argument("--name")
    create.add_argument("--roles", default="submitter", help="comma-separated: submitter,approver,operator,admin")
    create.add_argument("--password")
    sub.add_parser("list")
    reset = sub.add_parser("password")
    reset.add_argument("username")
    reset.add_argument("--password")
    args = parser.parse_args()

    try:
        if args.command == "create":
            password = args.password or getpass.getpass("Password: ")
            user = auth.create_local_user(args.username, password, args.name, args.roles.split(","))
            print(f"Created {user['username']} with roles {', '.join(user['roles'])}")
        elif args.command == "list":
            with session_scope() as s:
                for u in s.scalars(select(User).order_by(User.username)):
                    print(f"{u.username:24} {u.auth_provider:6} {'active' if u.active else 'disabled':9} {','.join(u.roles)}")
        elif args.command == "password":
            password = args.password or getpass.getpass("New password: ")
            if len(password) < 8:
                raise SystemExit("The password must be at least 8 characters.")
            with session_scope() as s:
                user = s.scalar(select(User).where(func.lower(User.username) == args.username.lower()))
                if user is None:
                    raise SystemExit(f"No user {args.username}")
                user.password_hash = auth.hash_password(password)
            print("Password updated.")
    except HTTPException as e:
        raise SystemExit(e.detail)


if __name__ == "__main__":
    main()
