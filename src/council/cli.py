"""CLI utilities for council member inspection and model assignment."""
from __future__ import annotations

import argparse
import json
from typing import Iterable, Mapping, Optional

from src.council.service import CouncilService


class _CliDomainAdapter:
    def get_all_relations(self):
        return {}

    def get_relation(self, head_id: str, tail_id: str, relation_type: str):
        return None

    def upsert_relation(self, relation) -> None:
        return None


def build_service() -> CouncilService:
    return CouncilService(domain_adapter=_CliDomainAdapter())


def build_parser() -> argparse.ArgumentParser:
    description = (
        "Inspect council member configuration, provider health, and per-member model assignment.\n\n"
        "Model selection rules:\n"
        "  1. If `model_name` is set in `config/council_members.yaml`, that member always uses it.\n"
        "  2. If `model_name` is omitted, onTro refreshes provider health and reads available models\n"
        "     from `/models` or `/api/tags`, then distributes auto-assigned models across\n"
        "     same-provider members to reduce duplication when possible."
    )
    epilog = (
        "Examples:\n"
        "  python -m src.council.cli --help\n"
        "  python -m src.council.cli members\n"
        "  python -m src.council.cli health\n"
        "  python -m src.council.cli models --json\n\n"
        "Typical workflow:\n"
        "  1. Edit `config/council_members.yaml` and set `model_name` only for members you want fixed.\n"
        "  2. Run `python -m src.council.cli health` to confirm credentials and provider reachability.\n"
        "  3. Run `python -m src.council.cli models` to see final model assignment per member."
    )
    parser = argparse.ArgumentParser(
        prog="python -m src.council.cli",
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    members_parser = subparsers.add_parser(
        "members",
        help="Show configured council members without network calls.",
        description=(
            "List configured council members. This command only reads configuration and does not call providers.\n"
            "Use it to verify role/provider/model_name layout before health checks."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    members_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

    health_parser = subparsers.add_parser(
        "health",
        help="Run provider health checks and discover available models.",
        description=(
            "Validate council member credentials against current environment variables and call each provider\n"
            "health endpoint. Successful responses also capture available model ids when the provider returns them."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    health_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

    models_parser = subparsers.add_parser(
        "models",
        help="Show effective model assignment for each member.",
        description=(
            "Refresh provider health, discover available models, and show the final model each member will use.\n"
            "Configured `model_name` wins. Missing `model_name` is auto-assigned from discovered model lists."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    models_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

    return parser


def _members_payload(service: CouncilService) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for member in service.member_registry.list_members(enabled_only=False):
        payload.append(
            {
                "member_id": member.member_id,
                "role": member.role.value,
                "provider": member.provider.value,
                "enabled": member.enabled,
                "configured_model": member.model_name,
                "effective_model": member.effective_model_name,
            }
        )
    return payload


def _health_payload(service: CouncilService, env: Optional[Mapping[str, str]] = None) -> list[dict[str, object]]:
    statuses = service.refresh_member_availability(env=env)
    payload: list[dict[str, object]] = []
    for member in service.member_registry.list_members(enabled_only=False):
        status = statuses.get(member.member_id)
        payload.append(
            {
                "member_id": member.member_id,
                "provider": member.provider.value,
                "success": bool(status and status.success),
                "checked_url": status.checked_url if status else None,
                "missing_env": status.missing_env if status else [],
                "available_models": status.available_models if status else [],
                "effective_model": member.effective_model_name,
            }
        )
    return payload


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _print_table(rows: Iterable[dict[str, object]], columns: list[tuple[str, str]]) -> None:
    row_list = list(rows)
    widths = []
    for key, header in columns:
        cell_width = max((len(str(row.get(key, ""))) for row in row_list), default=0)
        widths.append(max(len(header), cell_width))

    header_row = "  ".join(header.ljust(widths[idx]) for idx, (_, header) in enumerate(columns))
    print(header_row)
    print("  ".join("-" * width for width in widths))
    for row in row_list:
        print(
            "  ".join(
                str(row.get(key, "")).ljust(widths[idx])
                for idx, (key, _) in enumerate(columns)
            )
        )


def _run_members(service: CouncilService, as_json: bool) -> int:
    payload = _members_payload(service)
    if as_json:
        _print_json(payload)
        return 0

    _print_table(
        payload,
        [
            ("member_id", "member_id"),
            ("role", "role"),
            ("provider", "provider"),
            ("enabled", "enabled"),
            ("configured_model", "configured_model"),
            ("effective_model", "effective_model"),
        ],
    )
    return 0


def _run_health(service: CouncilService, as_json: bool) -> int:
    payload = _health_payload(service)
    if as_json:
        _print_json(payload)
        return 0

    _print_table(
        payload,
        [
            ("member_id", "member_id"),
            ("success", "success"),
            ("effective_model", "effective_model"),
            ("available_models", "available_models"),
            ("missing_env", "missing_env"),
        ],
    )
    return 0


def _run_models(service: CouncilService, as_json: bool) -> int:
    payload = _health_payload(service)
    if as_json:
        _print_json(payload)
        return 0

    _print_table(
        payload,
        [
            ("member_id", "member_id"),
            ("provider", "provider"),
            ("effective_model", "effective_model"),
            ("available_models", "available_models"),
        ],
    )
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    service = build_service()
    if args.command == "members":
        return _run_members(service, as_json=args.json)
    if args.command == "health":
        return _run_health(service, as_json=args.json)
    if args.command == "models":
        return _run_models(service, as_json=args.json)

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
