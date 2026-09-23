from __future__ import annotations

from datetime import date
from decimal import Decimal

from construction_os.storage.contracts_service import get_contract, set_contract


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def configure_contract(sub) -> None:
    parser = sub.add_parser("contract", help="ручной ввод условий договора")
    actions = parser.add_subparsers(dest="contract_command", required=True)
    setter = actions.add_parser("set")
    setter.add_argument("--company", required=True)
    setter.add_argument("--number", required=True)
    setter.add_argument("--signed-on", type=date.fromisoformat)
    setter.add_argument("--type", dest="contract_type", choices=("government", "commercial", "unknown"))
    setter.add_argument("--advance-pct", type=_decimal)
    setter.add_argument("--payment-delay-days", type=int)
    setter.add_argument("--security-amount", type=_decimal)
    setter.add_argument("--warranty-retention-pct", type=_decimal)
    treasury = setter.add_mutually_exclusive_group()
    treasury.add_argument("--treasury", dest="treasury_account", action="store_true")
    treasury.add_argument("--no-treasury", dest="treasury_account", action="store_false")
    setter.add_argument("--award-reduction-factor", type=_decimal)
    final = setter.add_mutually_exclusive_group()
    final.add_argument("--price-is-final", dest="price_is_final", action="store_true")
    final.add_argument("--price-not-final", dest="price_is_final", action="store_false")
    setter.set_defaults(treasury_account=None, price_is_final=None)
    setter.add_argument("--penalty-cap-pct", type=_decimal)
    setter.add_argument("--actor", default="cli")
    setter.add_argument("--reason")
    show = actions.add_parser("show")
    show.add_argument("--company", required=True)
    show.add_argument("--number", required=True)


def run_contract(args, session) -> int:
    try:
        if args.contract_command == "set":
            values = {
                name: getattr(args, name)
                for name in (
                    "signed_on",
                    "contract_type",
                    "advance_pct",
                    "payment_delay_days",
                    "security_amount",
                    "warranty_retention_pct",
                    "treasury_account",
                    "award_reduction_factor",
                    "price_is_final",
                    "penalty_cap_pct",
                    "actor",
                    "reason",
                )
            }
            contract, warnings = set_contract(
                session, args.company, args.number, **values
            )
            session.commit()
            print(f"Договор {contract.number}: условия сохранены; версия {contract.id}")
            for warning in warnings:
                print(f"ПРЕДУПРЕЖДЕНИЕ: {warning}")
        company, contract, count = get_contract(session, args.company, args.number)
        print(f"Компания: {company.name}; договор: {contract.number}; версий в истории: {count}")
        for name in (
            "contract_type",
            "signed_on",
            "advance_pct",
            "payment_delay_days",
            "security_amount",
            "warranty_retention_pct",
            "treasury_account",
            "award_reduction_factor",
            "price_is_final",
            "penalty_cap_pct",
            "valid_from",
            "valid_to",
            "replace_reason",
        ):
            value = getattr(contract, name)
            print(f"{name}: {value if value is not None else 'нет данных'}")
        return 0
    except (LookupError, ValueError) as error:
        session.rollback()
        print(str(error))
        return 2
