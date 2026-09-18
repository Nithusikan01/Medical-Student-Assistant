"""
Populate model_pricing.

Run from the backend directory:

    python scripts/seed_model_pricing.py --dry-run
    python scripts/seed_model_pricing.py

READ THIS BEFORE RUNNING IT.

The rates below are placeholders. They are *not* verified against either
provider's current pricing page, and they will be wrong - prices change, and
this file does not. A cost dashboard showing a confident wrong number is
worse than one showing nothing, because the wrong number gets believed and
budgeted against.

So: check each rate against the provider's pricing page, edit the table
below, and only then run this. Until it is run, estimated_cost_usd stays
NULL and the dashboard reports "not priced" rather than "$0.00" - which is
the honest state for a deployment nobody has priced yet.

Prices are USD per million tokens. Changing a price later means closing the
current row (set effective_to) and inserting a new one, not editing in
place, so historical costs stay explicable.
"""

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from backend.db.models import ModelPricing
from backend.db.session import session_scope

# model_id -> (provider, input per 1M USD, output per 1M USD, source note)
#
# VERIFY EVERY ROW. The source column exists so the next reader can re-check
# it rather than trusting it.
PLACEHOLDER_RATES: dict[str, tuple[str, str, str, str]] = {
    "gemini-flash": (
        "gemini",
        "0.10",
        "0.40",
        "PLACEHOLDER - verify at ai.google.dev/pricing",
    ),
    "groq-gpt-oss-120b": (
        "groq",
        "0.15",
        "0.75",
        "PLACEHOLDER - verify at groq.com/pricing",
    ),
    "groq-gpt-oss-20b": (
        "groq",
        "0.10",
        "0.50",
        "PLACEHOLDER - verify at groq.com/pricing",
    ),
    "groq-qwen3.8-27b": (
        "groq",
        "0.10",
        "0.50",
        "PLACEHOLDER - verify at groq.com/pricing",
    ),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would be written and exit",
    )
    parser.add_argument(
        "--i-have-verified-these-rates",
        action="store_true",
        help="required to actually write; forces you to have read the file",
    )

    args = parser.parse_args()

    now = datetime.now(UTC)

    print("Rates to insert (USD per 1M tokens):\n")

    for model_id, (provider, inp, out, source) in PLACEHOLDER_RATES.items():
        print(f"  {model_id:<20} {provider:<8} in={inp:>8}  out={out:>8}  {source}")

    if args.dry_run:
        print("\nDry run; nothing written.")
        return

    if not args.i_have_verified_these_rates:
        print(
            "\nRefusing to write unverified rates.\n"
            "Check each against the provider's pricing page, edit this file, "
            "then re-run with --i-have-verified-these-rates."
        )
        raise SystemExit(1)

    with session_scope() as session:
        for model_id, (provider, inp, out, source) in PLACEHOLDER_RATES.items():
            # Close any open rate before opening the new one, so the history
            # stays a clean sequence of non-overlapping periods.
            session.execute(
                sa.update(ModelPricing)
                .where(
                    sa.and_(
                        ModelPricing.model_id == model_id,
                        ModelPricing.effective_to.is_(None),
                    )
                )
                .values(effective_to=now)
            )

            session.add(
                ModelPricing(
                    model_id=model_id,
                    provider=provider,
                    input_cost_per_1m_usd=Decimal(inp),
                    output_cost_per_1m_usd=Decimal(out),
                    effective_from=now,
                    source=source,
                )
            )

    print(f"\nWrote {len(PLACEHOLDER_RATES)} pricing rows effective {now:%Y-%m-%d}.")


if __name__ == "__main__":
    main()
