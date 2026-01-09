import argparse
import json
import logging
import pathlib
import sys
from typing import Optional

import docuware


def parse_arguments() -> argparse.Namespace:
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
    parser.add_argument(
        "--ignore-certificate",
        action="store_true",
        help="Do not verify certificate integrity"
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    login_parser = subparsers.add_parser(
        "login", description="Connect to DocuWare server"
    )
    login_parser.add_argument(
        "--cookie-auth",
        action="store_true",
        help="Authenticate with session cookie instead of OAuth2"
    )
    login_parser.add_argument(
        "--url",
        type=case_insensitive_string_opt,
        required=True,
        help="URL of DocuWare server"
    )
    login_parser.add_argument(
        "--username",
        type=str,
        required=True,
        help="Username"
    )
    login_parser.add_argument(
        "--password",
        type=str,
        required=True,
        help="Password"
    )
    login_parser.add_argument(
        "--organization",
        type=str,
        default=None,
        help="Organization"
    )

    list_parser = subparsers.add_parser(
        "list", description="List all assets"
    )
    list_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        default=None,
        help="Select a file cabinet by name"
    )
    list_parser.add_argument(
        "--dialog",
        type=case_insensitive_string_opt,
        default=None,
        help="Select a dialog by name"
    )
    list_parser.add_argument(
        "--field",
        type=case_insensitive_string_opt,
        default=None,
        help="Select a field by name"
    )

    search_parser = subparsers.add_parser(
        "search", description="Search for documents"
    )
    search_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        default=None,
        required=True,
        help="Select a file cabinet by name"
    )
    search_parser.add_argument(
        "--download",
        default=None,
        choices=("document", "attachments", "all"),
        help="Download documents"
    )
    search_parser.add_argument(
        "--annotations",
        action="store_true",
        help="Preserve annotations on downloaded documents"
    )
    search_parser.add_argument(
        "conditions",
        nargs="*",
        help="Search terms: FIELDNAME=VALUE"
    )

    # tasks_parser = subparsers.add_parser(
    #     "tasks", description="Show my tasks"
    # )

    info_parser = subparsers.add_parser(
        "info", description="Show some information about this DocuWare installation"
    )

    return parser.parse_args()


def indent(n: int) -> str:
    return " " * (n * 4 - 1)


def search_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    def get_search_dlg(name: str) -> Optional[docuware.SearchDialog]:
        for org in dw.organizations:
            for fc in org.file_cabinets:
                if fc.name.casefold() == name:
                    for dlg in fc.dialogs:
                        if isinstance(dlg, docuware.SearchDialog):
                            return dlg
        return None

    if not args.conditions:
        return 0

    dlg = get_search_dlg(args.file_cabinet)
    if dlg is None:
        return 0

    res = dlg.search(args.conditions)

    for n, item in enumerate(res):
        doc = item.document
        print(f"[{n + 1}]", doc)
        if args.download in ("document", "all"):
            data, mime, fname = doc.download(keep_annotations=args.annotations)
            docuware.write_binary_file(data, fname)
        print(indent(1), "Metadata")
        for fld in doc.fields:
            if fld.value is not None:
                if fld.internal == False or args.verbose:
                    print(indent(2), fld)
        print(indent(1), "Attachments")
        for att in doc.attachments:
            print(indent(2), att)
            if args.download in ("attachments", "all"):
                data, mime, fname = att.download(keep_annotations=args.annotations)
                docuware.write_binary_file(data, fname)


def list_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    def show_field(fld: types.SearchFieldP) -> None:
        print(indent(3), fld)
        if args.field and fld.name.casefold() == args.field:
            for choice in fld.values():
                print(indent(4), choice)

    def show_searchdialog(dlg: types.SearchDialogP) -> None:
        print(indent(2), dlg)
        for fld in sorted(dlg.fields.values(), key=lambda f: f.name):
            show_field(fld)

    def show_dialog(dlg: types.DialogP) -> None:
        if args.dialog is None or dlg.name.casefold() == args.dialog:
            if isinstance(dlg, docuware.SearchDialog):
                show_searchdialog(dlg)
            else:
                print(indent(2), dlg)

    def show_filecabinet(fc: types.FileCabinetP) -> None:
        if args.file_cabinet is None or fc.name.casefold() == args.file_cabinet:
            print(indent(1), fc)
            for dlg in fc.dialogs:
                show_dialog(dlg)

    def show_org(org: types.OrganizationP) -> None:
        print(org)
        for fc in org.file_cabinets:
            show_filecabinet(fc)

    for org in dw.organizations:
        show_org(org)
    return 0


def tasks_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    for org in dw.organizations:
        print(org)
        for task in org.my_tasks:
            print(indent(1), task)
    return 0


def info_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    for org in dw.organizations:
        print(org)
        print(indent(1), "Company names:")
        for cn in org.info.get("CompanyNames") or []:
            print(indent(2), cn)
        print(indent(1), "Company address:")
        for al in org.info.get("AddressLines") or []:
            print(indent(2), al)
        print(indent(1), "Administrator:", org.info.get("Administrator"))
        print(indent(1), "Email:", org.info.get("EMail"))
        print(indent(1), "System number:", org.info.get("SystemNumber"))
        print(indent(1), "Runtime:", org.info.get("RuntimeVersion"), org.info.get("OrganizationType"))
    return 0


def main() -> None:
    args = parse_arguments()
    cred_file = args.config_dir / ".credentials"
    session_file = args.config_dir / ".session"

    if args.subcommand == "login":
        dw = docuware.Client(args.url, verify_certificate=not args.ignore_certificate)
        try:
            session = dw.login(
                username=args.username,
                password=args.password,
                organization=args.organization,
                oauth2=not args.cookie_auth,
            )
        except docuware.AccountError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            exit(1)
        else:
            credentials = {
                "username": args.username,
                "password": args.password,
                "url": args.url,
            }
            if args.organization:
                credentials["organization"] = args.organization
            with open(cred_file, "w") as f:
                json.dump(credentials, f, indent=4)
            with open(session_file, "w") as f:
                json.dump(session, f)

            print(f"Login successful", file=sys.stderr)
            exit(0)

    if not cred_file.exists() or not session_file.exists():
        print("Please log in first!", file=sys.stderr)
        exit(1)

    with open(cred_file) as f:
        credentials = json.load(f)
    with open(session_file) as f:
        session = json.load(f)

    dw = docuware.Client(credentials.get("url", "http://localhost"), verify_certificate=not args.ignore_certificate)
    try:
        session = dw.login(
            username=credentials.get("username"),
            password=credentials.get("password"),
            organization=credentials.get("organization"),
            saved_session=session,
        )
    except (docuware.AccountError, docuware.ResourceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        exit(1)
    else:
        with open(session_file, "w") as f:
            json.dump(session, f)

    code = None
    try:
        if args.subcommand == "list":
            code = list_cmd(dw, args)
        elif args.subcommand == "search":
            code = search_cmd(dw, args)
        elif args.subcommand == "tasks":
            code = tasks_cmd(dw, args)
        elif args.subcommand == "info":
            code = info_cmd(dw, args)
    except BrokenPipeError:
        pass
    except KeyboardInterrupt:
        code = 255

    exit(code if code else 0)


if __name__ == "__main__":
    main()

# vim: set et sw=4 ts=4:
