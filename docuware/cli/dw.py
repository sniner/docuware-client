import argparse
import json
import pathlib
import sys
from typing import Any, Dict, List, Optional

import docuware
from docuware import types


def parse_arguments() -> argparse.Namespace:
    def case_insensitive_string_opt(arg: Optional[str]) -> Optional[str]:
        if arg is None:
            return None
        return arg.casefold()

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__
    )

    parser.add_argument(
        "--config-dir",
        type=pathlib.Path,
        default=".",
        help="Directory for configuration files (default: current directory)",
    )
    parser.add_argument("--verbose", action="store_true", help="Output more messages")
    parser.add_argument(
        "--ignore-certificate",
        action="store_true",
        help="Do not verify certificate integrity",
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    login_parser = subparsers.add_parser("login", description="Connect to DocuWare server")
    login_parser.add_argument(
        "--cookie-auth",
        action="store_true",
        help="Authenticate with session cookie instead of OAuth2",
    )
    login_parser.add_argument(
        "--url",
        type=case_insensitive_string_opt,
        required=True,
        help="URL of DocuWare server",
    )
    login_parser.add_argument("--username", type=str, required=True, help="Username")
    login_parser.add_argument("--password", type=str, required=True, help="Password")
    login_parser.add_argument("--organization", type=str, default=None, help="Organization")

    list_parser = subparsers.add_parser("list", description="List all assets")
    list_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        default=None,
        help="Select a file cabinet by name",
    )
    list_parser.add_argument(
        "--dialog",
        type=case_insensitive_string_opt,
        default=None,
        help="Select a dialog by name",
    )
    list_parser.add_argument(
        "--field",
        type=case_insensitive_string_opt,
        default=None,
        help="Select a field by name",
    )

    search_parser = subparsers.add_parser("search", description="Search for documents")
    search_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        default=None,
        required=True,
        help="Select a file cabinet by name",
    )
    search_parser.add_argument(
        "--download",
        default=None,
        choices=("document", "attachments", "all"),
        help="Download documents",
    )
    search_parser.add_argument(
        "--annotations",
        action="store_true",
        help="Preserve annotations on downloaded documents",
    )
    search_parser.add_argument("conditions", nargs="*", help="Search terms: FIELDNAME=VALUE")

    get_parser = subparsers.add_parser("get", description="Get a document by ID")
    get_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        required=True,
        help="Select a file cabinet by name",
    )
    get_parser.add_argument("--id", required=True, help="Document ID")
    get_parser.add_argument(
        "--attachment",
        default=None,
        help="Download attachment (document, or specific attachment ID)",
    )
    get_parser.add_argument(
        "--output",
        default=None,
        type=pathlib.Path,
        help="Output file or directory for download (defaults to stdout, or filename if directory)",
    )
    get_parser.add_argument(
        "--annotations",
        action="store_true",
        help="Preserve annotations on downloaded documents",
    )

    create_parser = subparsers.add_parser("create", description="Create a new document")
    create_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        required=True,
        help="Select a file cabinet by name",
    )
    create_parser.add_argument(
        "--file", type=pathlib.Path, required=False, help="File to upload (optional)"
    )
    create_parser.add_argument("fields", nargs="*", help="Fields: FIELDNAME=VALUE")

    update_parser = subparsers.add_parser("update", description="Update a document")
    update_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        required=True,
        help="Select a file cabinet by name",
    )
    update_parser.add_argument("--id", required=True, help="Document ID")
    update_parser.add_argument("fields", nargs="*", help="Fields: FIELDNAME=VALUE")

    attach_parser = subparsers.add_parser("attach", description="Add attachment to document")
    attach_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        required=True,
        help="Select a file cabinet by name",
    )
    attach_parser.add_argument("--id", required=True, help="Document ID")
    attach_parser.add_argument(
        "--file", type=pathlib.Path, required=True, help="File to attach"
    )

    detach_parser = subparsers.add_parser(
        "detach", description="Remove attachment from document"
    )
    detach_parser.add_argument(
        "--file-cabinet",
        type=case_insensitive_string_opt,
        required=True,
        help="Select a file cabinet by name",
    )
    detach_parser.add_argument("--id", required=True, help="Document ID")
    detach_parser.add_argument("--attachment-id", required=True, help="Attachment ID")

    # tasks_parser = subparsers.add_parser(
    #     "tasks", description="Show my tasks"
    # )

    _info_parser = subparsers.add_parser(
        "info", description="Show some information about this DocuWare installation"
    )

    return parser.parse_args()


def indent(n: int) -> str:
    return " " * (n * 4 - 1)


def search_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    def get_first_search_dlg(name: str) -> Optional[docuware.SearchDialog]:
        name = name.casefold()
        for org in dw.organizations:
            for fc in org.file_cabinets:
                if fc.name.casefold() == name:
                    for dlg in fc.dialogs:
                        if isinstance(dlg, docuware.SearchDialog):
                            return dlg
        return None

    if not args.conditions:
        return 0

    dlg = get_first_search_dlg(args.file_cabinet)
    if dlg is None:
        return 0

    res = dlg.search(args.conditions)

    for n, item in enumerate(res):
        doc = item.document
        print(f"{n + 1}:", doc)
        if args.download in ("document", "all"):
            data, mime, fname = doc.download(keep_annotations=args.annotations)
            saved_path = docuware.write_binary_file(data, fname)
            if args.verbose:
                print(f"Downloaded document: {saved_path}", file=sys.stderr)
        print(indent(1), "Metadata")
        for fld in doc.fields:
            if fld.value is not None:
                if not fld.internal or args.verbose:
                    print(indent(2), fld)
        print(indent(1), "Attachments")
        for att in doc.attachments:
            print(indent(2), att)
            if args.download in ("attachments", "all"):
                data, mime, fname = att.download(keep_annotations=args.annotations)
                saved_path = docuware.write_binary_file(data, fname)
                if args.verbose:
                    print(f"Downloaded attachment: {saved_path}", file=sys.stderr)


def get_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    fc = get_file_cabinet(dw, args.file_cabinet)
    if not fc:
        print(f"File cabinet '{args.file_cabinet}' not found", file=sys.stderr)
        return 1

    try:
        doc = fc.get_document(args.id)

        if args.attachment:
            # Download mode
            target_id = args.attachment

            # Helper to download and save one item
            def download_and_save(item, out_path_arg):
                data, mime, fname = item.download(keep_annotations=args.annotations)
                if out_path_arg:
                    out_path = out_path_arg
                    if out_path.is_dir():
                        out_path = out_path / fname
                else:
                    out_path = None

                if out_path:
                    saved_path = docuware.write_binary_file(data, out_path)
                    if args.verbose:
                        print(f"Downloaded {fname} to {saved_path}", file=sys.stderr)
                else:
                    try:
                        sys.stdout.buffer.write(data)
                    except AttributeError:
                        sys.stdout.write(data.decode("latin1"))

            if target_id == "*":
                # Wildcard download
                if not args.output or not args.output.is_dir():
                    print(
                        "Error: --output must be a directory when using wildcard attachment download",
                        file=sys.stderr,
                    )
                    return 1

                for att in doc.attachments:
                    download_and_save(att, args.output)
                return 0

            # Single target download
            content_object = None
            if target_id == "document":
                content_object = doc
            else:
                for att in doc.attachments:
                    if att.id == target_id:
                        content_object = att
                        break

            if not content_object:
                print(f"Attachment '{target_id}' not found", file=sys.stderr)
                return 1

            download_and_save(content_object, args.output)
            return 0

        # Info mode (default)
        print(doc)
        print(indent(1), "Metadata")
        for fld in doc.fields:
            if fld.value is not None:
                if not fld.internal or args.verbose:
                    print(indent(2), fld)

        print(indent(1), "Attachments")
        for att in doc.attachments:
            print(indent(2), att)

    except Exception as e:
        print(f"Error getting document: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1
    return 0


def parse_fields_arg(args: List[str]) -> Dict[str, Any]:
    fields = {}
    for arg in args:
        if "=" in arg:
            key, value = arg.split("=", 1)
            fields[key] = value
        else:
            print(f"Warning: Ignoring invalid field spec '{arg}'", file=sys.stderr)
    return fields


def get_file_cabinet(dw: docuware.Client, name: str) -> Optional[docuware.FileCabinet]:
    name = name.casefold()
    for org in dw.organizations:
        for fc in org.file_cabinets:
            if fc.name.casefold() == name:
                # TODO: We need to return concrete FileCabinet or verify it is one
                return fc  # type: ignore
    return None


def create_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    fc = get_file_cabinet(dw, args.file_cabinet)
    if not fc:
        print(f"File cabinet '{args.file_cabinet}' not found", file=sys.stderr)
        return 1

    fields = parse_fields_arg(args.fields)
    try:
        doc = fc.create_document(fields=fields)
        print(f"Created document: {doc}")

        if args.file:
            att = doc.upload_attachment(args.file)
            print(f"Uploaded attachment: {att}")
    except Exception as e:
        print(f"Error creating document: {e}", file=sys.stderr)
        return 1
    return 0


def update_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    fc = get_file_cabinet(dw, args.file_cabinet)
    if not fc:
        print(f"File cabinet '{args.file_cabinet}' not found", file=sys.stderr)
        return 1

    try:
        doc = fc.get_document(args.id)
        fields = parse_fields_arg(args.fields)
        if fields:
            doc.update(fields)
            print(f"Updated document: {doc}")
        else:
            print("No fields to update")
    except Exception as e:
        print(f"Error updating document: {e}", file=sys.stderr)
        return 1
    return 0


def attach_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    fc = get_file_cabinet(dw, args.file_cabinet)
    if not fc:
        print(f"File cabinet '{args.file_cabinet}' not found", file=sys.stderr)
        return 1

    try:
        doc = fc.get_document(args.id)
        att = doc.upload_attachment(args.file)
        print(f"Added attachment: {att}")
    except Exception as e:
        # Get full traceback for debugging? Use verbose?
        print(f"Error attaching file: {e}", file=sys.stderr)
        return 1
    return 0


def detach_cmd(dw: docuware.Client, args: argparse.Namespace) -> Optional[int]:
    fc = get_file_cabinet(dw, args.file_cabinet)
    if not fc:
        print(f"File cabinet '{args.file_cabinet}' not found", file=sys.stderr)
        return 1

    try:
        doc = fc.get_document(args.id)
        # Find attachment
        attachment = None
        for att in doc.attachments:
            if att.id == args.attachment_id:
                attachment = att
                break

        if attachment:
            attachment.delete()
            print(f"Deleted attachment: {attachment}")
        else:
            print(f"Attachment '{args.attachment_id}' not found", file=sys.stderr)
            return 1
    except Exception as e:
        print(f"Error detaching file: {e}", file=sys.stderr)
        return 1
    return 0


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
        print(
            indent(1),
            "Runtime:",
            org.info.get("RuntimeVersion"),
            org.info.get("OrganizationType"),
        )
    return 0


def connect(args: argparse.Namespace) -> docuware.Client:
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

            print("Login successful", file=sys.stderr)
            exit(0)

    if not cred_file.exists() or not session_file.exists():
        print("Please log in first!", file=sys.stderr)
        exit(1)

    with open(cred_file) as f:
        credentials = json.load(f)
    with open(session_file) as f:
        session = json.load(f)

    dw = docuware.Client(
        credentials.get("url", "http://localhost"),
        verify_certificate=not args.ignore_certificate,
    )
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

    return dw


COMMANDS: Dict[str, Any] = {
    "list": list_cmd,
    "search": search_cmd,
    "get": get_cmd,
    "tasks": tasks_cmd,
    "info": info_cmd,
    "create": create_cmd,
    "update": update_cmd,
    "attach": attach_cmd,
    "detach": detach_cmd,
}


def main() -> None:
    args = parse_arguments()
    dw = connect(args)
    code = None

    try:
        func = COMMANDS.get(args.subcommand)
        if func:
            code = func(dw, args)
    except BrokenPipeError:
        pass
    except KeyboardInterrupt:
        code = 255

    exit(code if code else 0)


if __name__ == "__main__":
    main()

# vim: set et sw=4 ts=4:
