"""Command-line entry point: ``python3 -m pulsegate.cli <command> [args]``."""
from __future__ import annotations

import argparse
import json
import sys

from . import web, worker
from .core import Relay, RejectedEvent, accept_batch, accept_event
from .settings import load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pulsegate")
    parser.add_argument("--config", help="path to config.yaml (default: repository root)")
    sub = parser.add_subparsers(dest="command", required=True)
    send = sub.add_parser("send", help="queue one event given as a JSON object")
    send.add_argument("payload")
    replay = sub.add_parser("replay", help="queue every JSON line of a file")
    replay.add_argument("path")
    sub.add_parser("serve", help="run the HTTP intake server")
    sub.add_parser("drain", help="deliver queued events upstream once")
    return parser


def cmd_send(args, settings) -> int:
    relay = Relay(settings.queue_dir)
    try:
        event_id = accept_event(relay, json.loads(args.payload), source="cli")
    except (RejectedEvent, ValueError) as exc:
        print(f"rejected: {exc}", file=sys.stderr)
        return 2
    print(event_id)
    return 0


def cmd_replay(args, settings) -> int:
    relay = Relay(settings.queue_dir)
    with open(args.path, encoding="utf-8") as handle:
        payloads = [json.loads(line) for line in handle if line.strip()]
    for event_id in accept_batch(relay, payloads, source="replay"):
        print(event_id)
    return 0


def cmd_serve(args, settings) -> int:
    web.serve(settings)
    return 0


def cmd_drain(args, settings) -> int:
    delivered, failed = worker.drain(settings, Relay(settings.queue_dir))
    print(f"delivered={delivered} failed={failed}")
    return 0 if not failed else 1


COMMANDS = {"send": cmd_send, "replay": cmd_replay, "serve": cmd_serve, "drain": cmd_drain}


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    return COMMANDS[args.command](args, settings)


if __name__ == "__main__":
    sys.exit(main())
