from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig, load_dotenv
from .discord_webhook import DiscordWebhook
from .ftp_client import FtpLogClient
from .monitor import ArkLogMonitor, MonitorOptions
from .parser import Event, timezone_converter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll an ARK ShooterGame.log file and send timeline events to Discord."
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Path to an env file. Defaults to .env.",
    )
    parser.add_argument(
        "--local-log",
        help="Read a local ShooterGame.log instead of downloading from FTP.",
    )
    parser.add_argument(
        "--state-file",
        help="Override STATE_FILE from the environment.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one poll and exit.",
    )
    parser.add_argument(
        "--send-existing",
        action="store_true",
        help="On first run, send existing events instead of only saving a baseline.",
    )
    parser.add_argument(
        "--no-discord",
        action="store_true",
        help="Do not post to Discord. Useful for dry runs and tests.",
    )
    parser.add_argument(
        "--print-events",
        action="store_true",
        help="Print events that would be sent.",
    )
    parser.add_argument(
        "--test-discord",
        action="store_true",
        help="Send one test message to the configured Discord webhook and exit.",
    )
    parser.add_argument(
        "--find-log",
        action="store_true",
        help="Search FTP for ShooterGame.log and print matching remote paths.",
    )
    parser.add_argument(
        "--ftp-start-path",
        default="/",
        help="Remote FTP folder where --find-log should start. Defaults to /.",
    )
    parser.add_argument(
        "--ftp-max-depth",
        type=int,
        default=8,
        help="Maximum FTP folder depth for --find-log. Defaults to 8.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv(Path(args.env_file))
    config = AppConfig.from_env()

    if args.state_file:
        config.state_file = Path(args.state_file)

    try:
        timezone_converter(config.timezone_name)
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    local_log = Path(args.local_log).expanduser().resolve() if args.local_log else None
    if local_log is not None and not local_log.is_file():
        print(f"Local log not found: {local_log}", file=sys.stderr)
        return 2

    options = MonitorOptions(
        local_log=local_log,
        no_discord=args.no_discord,
        print_events=args.print_events,
        send_existing=True if args.send_existing else None,
    )
    monitor = ArkLogMonitor(config, options)

    try:
        if args.test_discord:
            if not config.discord_webhook_url:
                print("Missing DISCORD_WEBHOOK_URL.", file=sys.stderr)
                return 2
            test_event = Event(
                timestamp=datetime.now(timezone.utc),
                category="TEST",
                message="Webhook test from the ARK log bot.",
            )
            webhook = DiscordWebhook(
                url=config.discord_webhook_url,
                mention_user_id=config.discord_user_id,
            )
            webhook.send_events([test_event], config.timezone_name)
            print("Discord test message sent.")
            return 0

        if args.find_log:
            missing = config.missing_ftp_login_fields()
            if missing:
                print("Missing FTP configuration: " + ", ".join(missing), file=sys.stderr)
                return 2
            client = FtpLogClient(
                host=config.ftp_host or "",
                port=config.ftp_port,
                username=config.ftp_username or "",
                password=config.ftp_password or "",
                remote_path=config.ftp_path or "",
                use_tls=config.ftp_use_tls,
            )
            matches = client.find_files(
                "ShooterGame.log",
                start_path=args.ftp_start_path,
                max_depth=args.ftp_max_depth,
            )
            if not matches:
                print("No ShooterGame.log files found.")
                return 1
            print("Found ShooterGame.log at:")
            for match in matches:
                print(match)
            return 0

        if args.once:
            count = monitor.process_once()
            print(f"Done. {count} event(s) processed.")
        else:
            monitor.run_forever()
    except KeyboardInterrupt:
        print("Stopped.")
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
