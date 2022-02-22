import argparse
import json
import pathlib
import sys

from typing import Optional

import docuware


def parse_arguments():
    def case_insensitive_string_opt(arg: Optional[str]) -> Optional[str]:
        if arg is None:
            return None
        return arg.casefold()

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)

    parser.add_argument(
        "--config-dir",
        type=pathlib.Path,
        default=".",
        help="Directory for configuration files (default: current directory)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Output more messages"
    )

    return parser.parse_args()


def indent(n: int) -> str:
    return " " * (n*4-1)


def main():
    args = parse_arguments()
    cred_file = args.config_dir / ".credentials"
    session_file = args.config_dir / ".session"

    if not cred_file.exists() or not session_file.exists():
        print("Please log in first!", file=sys.stderr)
        exit(1)

    with open(cred_file) as f:
        credentials = json.load(f)
    with open(session_file) as f:
        session = json.load(f)

    dw = docuware.Client(credentials.get("url", "http://localhost"))
    try:
        session = dw.login(
            username=credentials.get("username"),
            password=credentials.get("password"),
            organization=credentials.get("organization"),
            cookiejar=session,
        )
    except docuware.AccountError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        exit(1)
    else:
        with open(session_file, "w") as f:
            json.dump(session, f)



if __name__ == "__main__":
    main()

# vim: set et sw=4 ts=4:
