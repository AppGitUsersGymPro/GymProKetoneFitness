"""
Django management command to import old member records from an Excel file.

Usage:
    python manage.py import_old_members path/to/records.xlsx
    python manage.py import_old_members path/to/records.xlsx --dry-run

Expected Excel columns (case-insensitive, extra columns are ignored):
    Date | Name | Mb No | DOB | Age | Gender | Id No | Amount Paid | Package in month

Plan detection from Amount Paid (no GST on any record):
    Empty / 0          → 30-day plan (₹700), amt_paid=0, balance=700  (pending)
    0 < amt <= 700     → 30-day plan, discounted price = amt, balance=0  (paid)
    700 < amt < 2000   → 90-day plan, discounted price = amt, balance=0  (paid)
    amt >= 2000        → 90-day plan (₹2000), no discount, balance=0    (paid)

Same phone seen again → renewal, NOT a new member.
Renewal date = Date + plan.duration_days  (no renewal-date column in Excel).
"""

import re
from datetime import timedelta, date
from decimal import Decimal

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.members.models import (
    InstallmentPayment,
    Member,
    MemberPayment,
    MembershipPlan,
)
from apps.finances.models import Income


# ---------------------------------------------------------------------------
# Plan price boundaries
# ---------------------------------------------------------------------------
PLAN_30_PRICE  = Decimal("700")
PLAN_90_PRICE  = Decimal("2000")
PLAN_30_DAYS   = 30
PLAN_90_DAYS   = 90


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_phone(raw) -> str | None:
    try:
        if pd.isna(raw):
            return None
    except Exception:
        pass
    s = str(raw).strip()
    s = re.sub(r"[\s\-.()+]", "", s)
    if s.startswith("91") and len(s) == 12:
        s = s[2:]
    if s.startswith("0") and len(s) == 11:
        s = s[1:]
    if len(s) != 10 or not s.isdigit():
        return None
    return s


def _parse_date(raw) -> date | None:
    try:
        if pd.isna(raw):
            return None
    except Exception:
        pass
    if isinstance(raw, pd.Timestamp):
        return raw.date()
    if isinstance(raw, date):
        return raw

    s = str(raw).strip()
    if not s or s.lower() in ("nan", "nat", "none", ""):
        return None

    # Excel serial numbers — pandas reads date cells as integers when dtype=str.
    # Excel epoch is Dec 30, 1899. Valid range ~36526 (year 2000) to ~54789 (year 2050).
    if s.isdigit():
        serial = int(s)
        if 36526 <= serial <= 54789:
            from datetime import datetime, timedelta
            return (datetime(1899, 12, 30) + timedelta(days=serial)).date()
        # Outside sane range → genuinely corrupt cell
        return None

    # Try dd/mm/yyyy first (the stated format), then fallbacks
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y", "%m/%d/%Y"):
        try:
            return pd.to_datetime(s, format=fmt).date()
        except Exception:
            pass
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except Exception:
        return None


def _to_decimal(raw) -> Decimal | None:
    """Returns None if empty/missing, Decimal otherwise."""
    try:
        if pd.isna(raw):
            return None
    except Exception:
        pass
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", ""):
        return None
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except Exception:
        return None


def _normalize_gender(raw) -> str:
    try:
        if pd.isna(raw):
            return ""
    except Exception:
        pass
    s = str(raw).strip().lower()
    if s in ("male", "m"):
        return "Male"
    if s in ("female", "f"):
        return "Female"
    if s:
        return "Other"
    return ""


def _invoice_number(member_id: int, dt: date, suffix: str = "") -> str:
    return f"INV-{dt.year}{dt.month:02d}-M{member_id:04d}{suffix}"


def _determine_plan(amt: Decimal | None, plan_30: MembershipPlan, plan_90: MembershipPlan):
    """
    Returns (plan, plan_price, discount_amount, amt_paid, is_fully_paid).

    plan_price  = what the member owes (post-discount)
    discount    = standard_price - plan_price
    amt_paid    = what was actually paid today
    is_fully_paid = whether balance = 0
    """
    if amt is None or amt <= Decimal("0"):
        # Unpaid enrollment on the 30-day plan
        return plan_30, PLAN_30_PRICE, Decimal("0"), Decimal("0"), False

    if amt <= PLAN_30_PRICE:
        # 30-day plan; amt is the post-discount full price
        discount = max(Decimal("0"), PLAN_30_PRICE - amt)
        return plan_30, amt, discount, amt, True

    if amt < PLAN_90_PRICE:
        # 90-day plan with discount
        discount = max(Decimal("0"), PLAN_90_PRICE - amt)
        return plan_90, amt, discount, amt, True

    # amt >= 2000 → 90-day, no discount
    return plan_90, PLAN_90_PRICE, Decimal("0"), PLAN_90_PRICE, True


# ---------------------------------------------------------------------------
# Column name aliases → canonical names
# ---------------------------------------------------------------------------

COL_MAP = {
    "date":            "joining_date",
    "joining date":    "joining_date",
    "joining_date":    "joining_date",
    "join date":       "joining_date",
    "name":            "name",
    "mb no":           "phone",
    "mb. no":          "phone",
    "mobile no":       "phone",
    "mobile number":   "phone",
    "mobile":          "phone",
    "phone":           "phone",
    "phone number":    "phone",
    "dob":             "dob",
    "date of birth":   "dob",
    "age":             "age",
    "gender":          "gender",
    "id no":           "gym_member_id",
    "idno":            "gym_member_id",
    "id":              "gym_member_id",
    "member id":       "gym_member_id",
    "amount paid":     "amt_paid",
    "amt paid":        "amt_paid",
    "amount":          "amt_paid",
    # "package in month" intentionally omitted — we ignore it
}


def _rename_columns(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {col: COL_MAP[col.strip().lower()]
               for col in df.columns if col.strip().lower() in COL_MAP}
    return df.rename(columns=mapping)


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Import old member records from an Excel file (legacy data migration)"

    def add_arguments(self, parser):
        parser.add_argument("excel_file", type=str, help="Path to the .xlsx / .xls file")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and validate without writing anything to the database",
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        excel_path = options["excel_file"]
        dry_run    = options["dry_run"]
        today      = timezone.localdate()

        # ── Fetch both plans ───────────────────────────────────────────
        plan_30 = self._get_plan(PLAN_30_DAYS, PLAN_30_PRICE, "30-day")
        plan_90 = self._get_plan(PLAN_90_DAYS, PLAN_90_PRICE, "90-day")
        self.stdout.write(f"30-day plan : [{plan_30.id}] {plan_30.name}  ₹{plan_30.price}")
        self.stdout.write(f"90-day plan : [{plan_90.id}] {plan_90.name}  ₹{plan_90.price}")
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — nothing will be written."))

        # ── Read Excel ─────────────────────────────────────────────────
        try:
            df = pd.read_excel(excel_path, dtype=str)
        except FileNotFoundError:
            raise CommandError(f"File not found: {excel_path}")
        except Exception as e:
            raise CommandError(f"Could not read Excel: {e}")

        df = _rename_columns(df)
        self.stdout.write(f"Columns recognised : {[c for c in df.columns if c in COL_MAP.values()]}")
        self.stdout.write(f"Columns ignored    : {[c for c in df.columns if c not in COL_MAP.values()]}")

        required = {"joining_date", "name", "phone"}
        missing  = required - set(df.columns)
        if missing:
            raise CommandError(
                f"Missing required columns: {missing}\n"
                f"Columns in file: {list(df.columns)}"
            )

        self.stdout.write(f"Total rows in Excel: {len(df)}")

        # ── Parse rows ─────────────────────────────────────────────────
        records = []
        skipped = 0

        for idx, row in df.iterrows():
            excel_row = idx + 2  # 1-indexed + header row

            phone = _normalize_phone(row.get("phone"))
            if not phone:
                self.stderr.write(f"  Row {excel_row}: bad phone '{row.get('phone')}' — skipped")
                skipped += 1
                continue

            joining_date = _parse_date(row.get("joining_date"))
            if not joining_date:
                self.stderr.write(f"  Row {excel_row} ({phone}): bad date '{row.get('joining_date')}' — skipped")
                skipped += 1
                continue

            name = str(row.get("name", "")).strip()
            if not name:
                self.stderr.write(f"  Row {excel_row} ({phone}): empty name — skipped")
                skipped += 1
                continue

            amt_raw = _to_decimal(row.get("amt_paid"))

            # Age: try from Excel, else compute from DOB, else default 18
            age = 18
            age_raw = row.get("age")
            try:
                if age_raw and not pd.isna(age_raw):
                    age = int(float(str(age_raw).strip()))
            except Exception:
                pass

            dob = _parse_date(row.get("dob"))
            if age == 18 and dob:
                from datetime import date as _date
                age = (joining_date - dob).days // 365

            records.append({
                "phone":         phone,
                "name":          name,
                "joining_date":  joining_date,
                "dob":           dob,
                "age":           max(1, age),
                "gender":        _normalize_gender(row.get("gender")),
                "gym_member_id": str(row.get("gym_member_id", "") or "").strip(),
                "amt_raw":       amt_raw,  # None = empty cell
            })

        records.sort(key=lambda r: (r["phone"], r["joining_date"]))

        # Group by phone
        phone_groups: dict[str, list] = {}
        for rec in records:
            phone_groups.setdefault(rec["phone"], []).append(rec)

        total_renewals = sum(len(g) - 1 for g in phone_groups.values())
        self.stdout.write(f"Valid rows     : {len(records)}  ({skipped} skipped)")
        self.stdout.write(f"Unique members : {len(phone_groups)}")
        self.stdout.write(f"Renewal rows   : {total_renewals}")

        if dry_run:
            # Show a sample of plan assignments
            sample_30, sample_90, sample_pending = 0, 0, 0
            for rows in phone_groups.values():
                for rec in rows:
                    amt = rec["amt_raw"]
                    if amt is None or amt <= 0:
                        sample_pending += 1
                    elif amt <= PLAN_30_PRICE:
                        sample_30 += 1
                    else:
                        sample_90 += 1
            self.stdout.write(f"  → 30-day plan records : {sample_30}")
            self.stdout.write(f"  → 90-day plan records : {sample_90}")
            self.stdout.write(f"  → Unpaid (pending)    : {sample_pending}")
            self.stdout.write(self.style.SUCCESS("Dry run complete. Run without --dry-run to import."))
            return

        # ── Import ─────────────────────────────────────────────────────
        created_members  = 0
        created_renewals = 0
        skipped_existing = 0

        with transaction.atomic():
            for phone, rows in phone_groups.items():
                first = rows[0]

                plan, plan_price, discount, amt_paid, is_paid = _determine_plan(
                    first["amt_raw"], plan_30, plan_90
                )
                renewal_date = first["joining_date"] + timedelta(days=plan.duration_days)

                # ── Enrollment ─────────────────────────────────────────
                member, is_new = Member.objects.get_or_create(
                    phone=phone,
                    defaults={
                        "name":             first["name"],
                        "join_date":        first["joining_date"],
                        "joining_date":     first["joining_date"],
                        "dob":              first["dob"],
                        "age":              first["age"],
                        "gender":           first["gender"],
                        "gym_member_id":    first["gym_member_id"],
                        "plan":             plan,
                        "plan_type":        "basic",
                        "renewal_date":     renewal_date,
                        "status":           "active",
                        "personal_trainer": False,
                    },
                )

                if is_new:
                    created_members += 1
                    inv_no = _invoice_number(member.id, first["joining_date"])

                    # MemberPayment.save() auto-calculates balance & status
                    payment = MemberPayment(
                        member           = member,
                        plan             = plan,
                        invoice_number   = inv_no,
                        plan_price       = plan_price,
                        diet_plan_amount = Decimal("0"),
                        discount_amount  = discount,
                        gst_rate         = Decimal("0"),
                        gst_amount       = Decimal("0"),
                        total_with_gst   = plan_price,
                        amount_paid      = amt_paid,
                        paid_date        = first["joining_date"],
                        valid_from       = first["joining_date"],
                        valid_to         = renewal_date,
                        notes            = "Imported from legacy records",
                    )
                    payment.save()  # triggers balance + status auto-calc

                    if amt_paid > Decimal("0"):
                        InstallmentPayment.objects.create(
                            payment          = payment,
                            member           = member,
                            installment_type = "enrollment",
                            amount           = amt_paid,
                            balance_after    = payment.balance,
                            paid_date        = first["joining_date"],
                            mode_of_payment  = "cash",
                            notes            = "Legacy import",
                        )

                        Income.objects.create(
                            source         = f"Membership Fee — {member.name}",
                            category       = "membership",
                            base_amount    = amt_paid,
                            gst_rate       = Decimal("0"),
                            gst_amount     = Decimal("0"),
                            amount         = amt_paid,
                            date           = first["joining_date"],
                            member_id      = member.id,
                            invoice_number = inv_no,
                            notes          = f"plan_total:{plan_price} | Legacy import enrollment",
                        )
                else:
                    skipped_existing += 1
                    self.stderr.write(
                        f"  Phone {phone} already exists as M{member.id:04d} — "
                        "enrollment skipped, processing renewals only"
                    )

                # Track the latest renewal_date across all rows for this member
                latest_renewal_date = member.renewal_date or renewal_date

                # ── Renewals ───────────────────────────────────────────
                for rec in rows[1:]:
                    plan_r, plan_price_r, discount_r, amt_paid_r, _ = _determine_plan(
                        rec["amt_raw"], plan_30, plan_90
                    )
                    renewal_date_r = rec["joining_date"] + timedelta(days=plan_r.duration_days)
                    inv_no_r       = _invoice_number(member.id, rec["joining_date"], "-R")

                    if MemberPayment.objects.filter(member=member, invoice_number=inv_no_r).exists():
                        self.stderr.write(f"  Duplicate renewal {inv_no_r} — skipped")
                        continue

                    payment_r = MemberPayment(
                        member           = member,
                        plan             = plan_r,
                        invoice_number   = inv_no_r,
                        plan_price       = plan_price_r,
                        diet_plan_amount = Decimal("0"),
                        discount_amount  = discount_r,
                        gst_rate         = Decimal("0"),
                        gst_amount       = Decimal("0"),
                        total_with_gst   = plan_price_r,
                        amount_paid      = amt_paid_r,
                        paid_date        = rec["joining_date"],
                        valid_from       = rec["joining_date"],
                        valid_to         = renewal_date_r,
                        notes            = "Imported from legacy records",
                    )
                    payment_r.save()  # auto-calc balance + status

                    if amt_paid_r > Decimal("0"):
                        InstallmentPayment.objects.create(
                            payment          = payment_r,
                            member           = member,
                            installment_type = "renewal",
                            amount           = amt_paid_r,
                            balance_after    = payment_r.balance,
                            paid_date        = rec["joining_date"],
                            mode_of_payment  = "cash",
                            notes            = "Legacy import",
                        )

                        Income.objects.create(
                            source         = f"Membership Fee — {member.name}",
                            category       = "membership",
                            base_amount    = amt_paid_r,
                            gst_rate       = Decimal("0"),
                            gst_amount     = Decimal("0"),
                            amount         = amt_paid_r,
                            date           = rec["joining_date"],
                            member_id      = member.id,
                            invoice_number = inv_no_r,
                            notes          = f"plan_total:{plan_price_r} | Legacy import renewal",
                        )

                    created_renewals += 1

                    # Update member plan to the latest renewal's plan
                    member.plan = plan_r
                    if renewal_date_r > latest_renewal_date:
                        latest_renewal_date = renewal_date_r

                # ── Final member state ─────────────────────────────────
                member.renewal_date = latest_renewal_date
                member.status = "expired" if latest_renewal_date < today else "active"
                member.save(update_fields=["plan", "renewal_date", "status"])

        # ── Summary ────────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=== Import complete ==="))
        self.stdout.write(f"  Members created   : {created_members}")
        self.stdout.write(f"  Renewals created  : {created_renewals}")
        self.stdout.write(f"  Already in DB     : {skipped_existing}")
        self.stdout.write(f"  Rows skipped      : {skipped}")

    # ------------------------------------------------------------------

    def _get_plan(self, duration_days: int, price: Decimal, label: str) -> MembershipPlan:
        # Exact match on duration
        plan = (MembershipPlan.objects
                .filter(is_active=True, duration_days=duration_days)
                .order_by("id").first())
        if plan:
            return plan

        raise CommandError(
            f"No active {label} plan (duration_days={duration_days}) found in the database.\n"
            f"Create a MembershipPlan with duration_days={duration_days} and price=₹{price}, then re-run."
        )
