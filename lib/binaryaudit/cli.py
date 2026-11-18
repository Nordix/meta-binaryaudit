
import argparse


# Common, reusable.
arg_parser_common = argparse.ArgumentParser(add_help=False)
arg_parser_common.add_argument('-v', '--verbose', action='store_true',
                               help="Verbose output.")

# Database, reusable
arg_parser_db = argparse.ArgumentParser(add_help=False)
arg_parser_db.add_argument("--db-config", action="store", default="db_config", metavar="/path/to/file",
                           help="Path to the config file in the env format. If omited, default is 'db_config' in CWD.")


# Telemetry, reusable.
arg_parser_telemetry = argparse.ArgumentParser(add_help=False)
telemetry_args = arg_parser_telemetry.add_argument_group('telemetry arguments')
telemetry_args.add_argument('-t', '--enable-telemetry', action='store', required=False,
                            default="n", help="Enable the data storing to telemetry (default: n)")
telemetry_args.add_argument('-b', '--build-id', action='store', required=False,
                            help="Reference to the particular build.")
telemetry_args.add_argument('-d', '--product-name', action='store', required=False,
                            help="Name of the product to be tracked, e.g. a distro or a project name.")
telemetry_args.add_argument('-e', '--derivative', action='store', required=False,
                            help="Derivative name")
telemetry_args.add_argument('-u', '--buildurl', action='store', required=False,
                            help="Build URL")
telemetry_args.add_argument('-l', '--logurl', action='store', required=False,
                            help="URL of log files")


# Top level.
arg_parser = argparse.ArgumentParser(prog="binaryaudit", description="Tools for ELF audit.",
                                     parents=[arg_parser_common])
arg_parser.add_argument("--is-elf", action="store", metavar="/path/to/file",
                        help="Determine whether a file is an ELF artifact. Exit is zero if true.")


# Subcommands. If a subcommand has been called, read the name from args.cmd
arg_parser_subs = arg_parser.add_subparsers(help="Subcommands", dest="cmd")


# binaryaudit abi ...
# arg_parser_abi = arg_parser_subs.add_parser("abi", help="ABI tools.")


# binaryaudit rpm ...
arg_parser_rpm = arg_parser_subs.add_parser("rpm", help="RPM tools frontend.",
                                            parents=[arg_parser_common, arg_parser_db, arg_parser_telemetry])
arg_parser_rpm.add_argument('--list', action="store_true",
                            help="Read RPM packages in a directory and create a list grouped by SRPM.")
arg_parser_rpm.add_argument('--source-dir', action="store", help="RPM package directory.")
arg_parser_rpm.add_argument('--out-filename', action="store", help="Output filename.")


# binaryaudit db ..
arg_parser_db_cmd = arg_parser_subs.add_parser("db", help="Database CLI wrapper.",
                                               parents=[arg_parser_common, arg_parser_db])
arg_parser_db_cmd.add_argument('--check-connection', action='store_true', required=False,
                               help="Test DB connection. Exit with 0 if connection could be established.")


# binaryaudit poky ...
arg_parser_poky = arg_parser_subs.add_parser("poky", help="RPM tools frontend.",
                                             parents=[arg_parser_common, arg_parser_db, arg_parser_telemetry])
arg_parser_poky.add_argument("--compare-buildhistory", action="store_true", help="Run abicompat on two buildhistory dirs.")
arg_parser_poky.add_argument("--buildhistory-baseline", action="store", help="Baseline buildhistory directory.")
arg_parser_poky.add_argument("--buildhistory-current", action="store",
                             help="Current buildhistory directory to be compared against the baseline.")


# ##### functions #####


def validate_telemetry_args(args):
    if args.enable_telemetry:
        if not args.build_id or not args.product_name or not args.derivative:
            raise argparse.ArgumentError(None, "Options --build-id, --product-name and --derivative are required")
