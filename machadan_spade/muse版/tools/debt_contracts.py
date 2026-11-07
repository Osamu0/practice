"""Staged Lilith contracts: payoff proofs, persistent options and target gates.

Unlocks are options for the player. They neither establish a relationship nor
waive the next contract. The existing runtime owns payment/fee/due mechanics.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import re

RULE = "staged-payoff-v1"
UNLOCK_KEYS = ("lilith_intimacy", "named_appearance_customization")
BENEFIT_BY_STAGE = {1: UNLOCK_KEYS[0], 2: UNLOCK_KEYS[1]}
_CONTRACT = re.compile(r"lilith-debt-cycle-(0|[1-9][0-9]*)\Z")
_ROMANTIC_KINDS = {"romance", "confession", "dating", "conquest", "intimacy", "private_bath",
                   "sex", "sexual", "ero", "seduction", "flirting",
                   "恋愛", "告白", "交際", "攻略", "親密", "誘惑", "特別浴場"}
_ROMANTIC_STATES = {"lover", "lovers", "dating", "romantic", "conquered", "fallen", "intimate",
                    "恋人", "恋人関係", "交際中", "攻略済み", "攻略済", "堕落済み", "陥落済み", "親密関係"}


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def principal_schedule(cycle_index):
    """Index0 is the first contract; later principals are 50k,100k,150k…"""
    if not _integer(cycle_index) or cycle_index < 0:
        raise ValueError("debt contract cycle index must be a nonnegative integer")
    return 10000 if cycle_index == 0 else 50000 * cycle_index


payoff_principal_schedule = principal_schedule


def expected_benefit(completed_stage):
    if not _integer(completed_stage) or completed_stage < 1:
        raise ValueError("completed debt stage must be a positive integer")
    return BENEFIT_BY_STAGE.get(completed_stage)


def _debt(data):
    value = data.get("debt_state") if isinstance(data, dict) else None
    return value if isinstance(value, dict) else {}


def _cycle(reference):
    matched = _CONTRACT.fullmatch(reference) if isinstance(reference, str) else None
    return int(matched.group(1)) if matched else None


def _payoff_candidate(entry):
    if not isinstance(entry, dict):
        return False
    if entry.get("event_kind") == "early_payoff":
        return True
    return (entry.get("event_kind") == "collection" and _integer(entry.get("payment"))
            and entry.get("payment") == entry.get("principal_before_payment"))


def payoff_metadata(data, completed_stage):
    """Common typed fields for scheduled and voluntary complete payments."""
    expected_benefit(completed_stage)
    return {"campaign_id": data["campaign_id"], "completed_stage": completed_stage,
            "unlocked_benefit": expected_benefit(completed_stage),
            "contract_cycle_index_before": completed_stage - 1,
            "contract_cycle_index_after": completed_stage}


def apply_payoff_unlock(data, completed_stage, transaction_id=None, day=None):
    """Update the candidate cache only; the caller must append its payoff proof."""
    benefit = expected_benefit(completed_stage)
    debt = data["debt_state"]
    debt["contract_rule"] = RULE
    flags = debt.setdefault("unlocks", {key: False for key in UNLOCK_KEYS})
    if benefit is not None:
        flags[benefit] = True
    return benefit


def _proofs(data):
    debt = _debt(data)
    ledger = debt.get("collection_ledger", [])
    errors, proofs = [], []
    if not isinstance(ledger, list):
        return proofs, ["debt collection ledger must be a list"]
    completed = 0
    running_principal = principal_schedule(0)
    for entry in ledger:
        if not isinstance(entry, dict):
            errors.append("debt proof entries must be mappings")
            continue
        principal_before = entry.get("principal_before_payment")
        if not _integer(principal_before) or principal_before != running_principal:
            errors.append("debt payoff proof must preserve the full principal/fee/payment history")
        if _cycle(entry.get("contract_id_before")) != completed:
            errors.append("debt proof entry must belong to the current consecutive contract")
        if not _payoff_candidate(entry):
            if entry.get("completed_stage") is not None or entry.get("unlocked_benefit") is not None:
                errors.append("a partial payment, charge or nonpayment cannot grant a payoff unlock")
            kind = entry.get("event_kind")
            payment, penalty = entry.get("payment", 0), entry.get("penalty", 0)
            amount = entry.get("charge_amount", 0)
            if (kind == "charge" and _integer(amount) and amount > 0
                    and entry.get("reason") in {"inn", "member_shortage", "rebirth", "crime_fine"}
                    and (entry.get("reason") != "crime_fine" or amount == 3000)
                    and isinstance(entry.get("source_id"), str) and bool(entry["source_id"])):
                running_principal += amount
            elif kind in {"payment", "collection"} and _integer(payment) and _integer(penalty) and 0 <= payment < running_principal and penalty >= 0:
                running_principal += penalty - payment
            else:
                errors.append("invalid non-payoff debt history")
            if entry.get("principal_after_resolution") != running_principal or _cycle(entry.get("contract_id_after")) != completed:
                errors.append("non-payoff debt history cannot forgive or replace its contract")
            continue
        before, after = _cycle(entry.get("contract_id_before")), _cycle(entry.get("contract_id_after"))
        stage = entry.get("completed_stage")
        payment, principal = entry.get("payment"), entry.get("principal_before_payment")
        valid = (before == completed and after == completed + 1 and stage == after and _integer(stage)
                 and entry.get("contract_cycle_index_before") == before and _integer(entry.get("contract_cycle_index_before"))
                 and entry.get("contract_cycle_index_after") == after and _integer(entry.get("contract_cycle_index_after"))
                 and _integer(payment) and _integer(principal) and principal > 0 and payment == principal
                 and entry.get("principal_after_resolution") == principal_schedule(after)
                 and entry.get("campaign_id") == data.get("campaign_id")
                 and entry.get("unlocked_benefit") == expected_benefit(after)
                 and isinstance(entry.get("transaction_id"), str) and bool(entry["transaction_id"]))
        if not valid:
            errors.append("completed contracts need consecutive, campaign-bound full-principal payoff receipts")
            continue
        proofs.append(entry)
        completed = after
        running_principal = principal_schedule(after)
    if debt.get("principal") != running_principal or debt.get("contract_cycle_index") != completed:
        errors.append("current debt principal/cycle must match its complete ledger history")
    return proofs, errors


def debt_unlocks(data):
    """Derive access from immutable validated payoff entries, never UI flags."""
    proofs, errors = _proofs(data)
    return _unlock_projection(proofs, errors)


def _unlock_projection(proofs, errors):
    if errors:
        return {key: False for key in UNLOCK_KEYS}
    stages = {entry["completed_stage"] for entry in proofs}
    return {UNLOCK_KEYS[0]: 1 in stages, UNLOCK_KEYS[1]: 2 in stages}


def _is_lilith(target):
    if isinstance(target, dict):
        for key in ("character_id", "named_id"):
            reference = target.get(key)
            if isinstance(reference, str) and reference:
                return _is_lilith(reference)
        return any(_is_lilith(target.get(key)) for key in ("english_name", "name", "char"))
    if not isinstance(target, str):
        return False
    value = target.strip().casefold()
    return value in {"リリス", "lilith", "lilith_000"}


def interaction_gate(data, target, kind):
    """Only Lilith's romance/intimacy is gated; care and other NPCs stay free."""
    normalized = kind.strip().casefold() if isinstance(kind, str) else ""
    required = _is_lilith(target) and normalized in _ROMANTIC_KINDS
    allowed = not required or debt_unlocks(data)["lilith_intimacy"]
    return {"allowed": allowed, "target": target, "interaction": kind,
            "requires_first_payoff": required,
            "reason": "第一契約の残元本と追加費用を全額返済してから選べます" if not allowed else ""}


def _lilith_relationship_errors(data, unlocked):
    if unlocked:
        return []
    errors = []
    entries = []
    for key in ("npc_relationship", "party", "inn_reserve"):
        if isinstance(data.get(key), list):
            entries.extend(data[key])
    for entry in entries:
        if not isinstance(entry, dict) or not _is_lilith(entry):
            continue
        relationship = entry.get("relationship")
        values = [entry, relationship] if isinstance(relationship, dict) else [entry]
        if isinstance(relationship, str) and relationship.strip().casefold() in _ROMANTIC_STATES:
            errors.append("Lilith's romantic relationship requires the first full payoff")
        for value in values:
            for key in ("status", "type", "romance_state", "intimacy_state"):
                state = value.get(key)
                if isinstance(state, str) and state.strip().casefold() in _ROMANTIC_STATES:
                    errors.append("Lilith's romantic/intimate status requires the first full payoff")
            for key in ("lover", "romance_partner", "conquered", "intimacy_consented"):
                if value.get(key) is True:
                    errors.append("Lilith's romantic/intimate flag requires the first full payoff")
            # Trust and non-romantic care belong in their own fields or notes.
            love = value.get("love_level")
            if "love_level" in value and (not _integer(love) or love < 0):
                errors.append("Lilith's love_level must be a nonnegative integer")
            elif _integer(love) and love > 0:
                errors.append("Lilith's romantic love_level requires the first full payoff")
    if isinstance(data.get("captured_girls"), list) and any(_is_lilith(entry) for entry in data["captured_girls"]):
        errors.append("Lilith cannot be recorded as conquered/captured before the first full payoff")
    return errors


def validate_state(data, errors):
    debt = _debt(data)
    rule = debt.get("contract_rule")
    if rule is not None and rule != RULE:
        errors.append("debt_state.contract_rule is unsupported")
    strict = rule == RULE or "unlocks" in debt
    flags = debt.get("unlocks")
    if strict and (not isinstance(flags, dict) or set(flags) != set(UNLOCK_KEYS)
                   or any(not isinstance(flags.get(key), bool) for key in UNLOCK_KEYS)):
        errors.append("debt_state.unlocks must contain exactly two boolean staged unlocks")
    proofs, proof_errors = _proofs(data)
    if strict:
        errors.extend(proof_errors)
        derived = _unlock_projection(proofs, proof_errors)
        if flags != derived:
            errors.append("debt unlock cache must match consecutive confirmed payoff receipts")
        if debt.get("contract_cycle_index") != len(proofs):
            errors.append("staged debt cycle must equal the number of completed contract receipts")
        world = data.get("world_state")
        goals = world.get("goals", {}) if isinstance(world, dict) else {}
        goals = goals if isinstance(goals, dict) else {}
        if goals.get("debt_clear") is True and not derived["lilith_intimacy"]:
            errors.append("debt_clear requires the first complete contract receipt")
    errors.extend(_lilith_relationship_errors(data, _unlock_projection(proofs, proof_errors)["lilith_intimacy"]))
    runtime = data.get("runtime_state", {})
    interaction = runtime.get("interaction") if isinstance(runtime, dict) else None
    if interaction is not None:
        if (not isinstance(interaction, dict) or not isinstance(interaction.get("target"), str)
                or not interaction["target"].strip() or not isinstance(interaction.get("kind"), str) or not interaction["kind"].strip()
                or interaction.get("status") not in {"attempt", "declined", "established"}):
            errors.append("runtime interaction requires target/kind and attempt/declined/established status")
        elif interaction["status"] == "established" and not interaction_gate(data, interaction["target"], interaction["kind"])["allowed"]:
            errors.append("Lilith's established romantic/intimate interaction requires the first full payoff")


def validate_transition(old, new, transaction_id):
    """Runs on every debt path, including no-op, charge, rebirth and benefits."""
    errors = []
    before, after = _debt(old), _debt(new)
    if before.get("contract_rule") == RULE and after.get("contract_rule") != RULE:
        errors.append("staged debt contract rule cannot be removed or changed")
    if before.get("contract_rule") == RULE or after.get("contract_rule") == RULE:
        for key in ("active_benefits", "benefit_selection"):
            if before.get(key) != after.get(key):
                errors.append("staged contracts do not add, upgrade or consume legacy enterprise benefits")
    old_flags, new_flags = debt_unlocks(old), debt_unlocks(new)
    for key in UNLOCK_KEYS:
        if old_flags[key] and not new_flags[key]:
            errors.append("earned debt unlocks cannot be revoked: " + key)
    old_ledger, new_ledger = before.get("collection_ledger", []), after.get("collection_ledger", [])
    if not isinstance(old_ledger, list) or not isinstance(new_ledger, list) or new_ledger[:len(old_ledger)] != old_ledger:
        return errors + ["debt payoff proof history is append-only"]
    added = new_ledger[len(old_ledger):]
    payoff = [entry for entry in added if _payoff_candidate(entry)]
    if payoff:
        if len(payoff) != 1 or payoff[0].get("transaction_id") != transaction_id:
            errors.append("one payoff receipt must use the current transaction ID")
        if after.get("active_benefits") != before.get("active_benefits") or after.get("benefit_selection") != before.get("benefit_selection"):
            errors.append("staged debt payoff grants no automatic enterprise benefits")
        if new.get("enterprise_state", {}).get("lilith_investments") != old.get("enterprise_state", {}).get("lilith_investments"):
            errors.append("staged debt payoff cannot add hidden enterprise investments")
    elif old_flags != new_flags:
        errors.append("debt unlocks may change only with a complete payoff receipt")
    validate_state(new, errors)
    return errors


def payment_candidate(data, payment, transaction_id):
    """Build one voluntary payment/early payoff without touching any files."""
    debt = data["debt_state"]
    if debt.get("collection_pending") is True:
        raise ValueError("resolve the pending scheduled collection instead of a voluntary payment")
    principal, gold = debt["principal"], data["player"]["gold"]
    if not _integer(payment) or not 0 < payment <= min(principal, gold):
        raise ValueError("payment must be positive and within available gold/current principal")
    if payment % 100 and payment != principal:
        raise ValueError("payment uses 100G units except the exact final remainder")
    result = copy.deepcopy(data)
    current, player = result["debt_state"], result["player"]
    day = result["world_state"]["day"]
    player["gold"] -= payment
    paid_off = payment == principal
    if paid_off:
        current["contract_cycle_index"] += 1
        current["contract_id"] = f"lilith-debt-cycle-{current['contract_cycle_index']}"
        current["principal"] = principal_schedule(current["contract_cycle_index"])
        current["next_collection_day"] = day + 5
        current["scheduled_due"] = 500 + 250 * current["contract_cycle_index"]
        current["cycle_paid"] = 0
        current["collection_pending"] = False
        result["world_state"]["goals"]["debt_clear"] = True
        apply_payoff_unlock(result, current["contract_cycle_index"], transaction_id, day)
    else:
        current["principal"] -= payment
        current["cycle_paid"] += payment
    player["debt"] = current["principal"]
    entry = {"collection_id": "debt-payment-" + hashlib.sha256(transaction_id.encode("utf-8")).hexdigest()[:32],
             "transaction_id": transaction_id, "event_kind": "early_payoff" if paid_off else "payment",
             "collection_day": day, "contract_id_before": debt["contract_id"],
             "contract_id_after": current["contract_id"], "payment": payment,
             "principal_before_payment": principal, "principal_after_resolution": current["principal"]}
    if paid_off:
        entry.update(payoff_metadata(data, current["contract_cycle_index"]))
    current["collection_ledger"].append(entry)
    return result


def candidate_path(api, source, raw):
    supplied = Path(raw).expanduser()
    if supplied.is_symlink():
        raise api.RuntimeProblem("debt candidate must not be a symbolic link")
    output = supplied.resolve()
    if output == source or (output.exists() and source.exists() and output.samefile(source)):
        raise api.RuntimeProblem("debt resolution requires an output separate from the live save")
    root = api.ROOT.resolve()
    if output.is_relative_to(root.parent) and not output.is_relative_to(root / "state/runtime"):
        raise api.RuntimeProblem("generated debt candidates inside the game belong under state/runtime")
    for directory in (root.parent.parent / "skills", root.parent.parent / "custom-skills"):
        if output.is_relative_to(directory.resolve()):
            raise api.RuntimeProblem("debt candidates cannot overwrite skill files")
    return output


def committed_retry(api, data, output, transaction_id):
    applied = data.get("transaction", {}).get("applied_transaction_ids", [])
    if transaction_id not in applied:
        return False
    if data["transaction"].get("last_transaction_id") != transaction_id or not output.is_file():
        raise api.RuntimeProblem("debt transaction ID has already been applied")
    candidate = api.load_yaml(output)
    digest = api.sha256_bytes(api.dump_yaml(candidate).encode("utf-8"))
    if digest != data["transaction"].get("last_candidate_hash"):
        raise api.RuntimeProblem("debt retry differs from the committed candidate")
    return True


def write_candidate(api, data, candidate, output, transaction_id, *, force=False):
    errors = api._validate_debt_transition(data, candidate, transaction_id)
    state_errors, warnings = api.validate_save_data(candidate)
    if errors or state_errors:
        raise api.RuntimeProblem("invalid debt candidate: " + "; ".join([*errors, *state_errors]))
    text = api.dump_yaml(candidate)
    with api.file_locks([api.save_lock_path(output)]):
        identical = output.is_file() and output.read_text(encoding="utf-8") == text
        if output.exists() and not identical and not force:
            raise api.RuntimeProblem("refusing to overwrite a different debt candidate")
        if not identical:
            api.atomic_write(output, text)
    return identical, warnings


def resolve_payment(api, args):
    source = Path(args.save).expanduser()
    if source.is_symlink():
        raise api.RuntimeProblem("debt source must not be a symbolic link")
    source = source.resolve()
    data = api.load_yaml(source)
    errors, warnings = api.validate_save_data(data)
    if errors:
        raise api.RuntimeProblem("invalid debt save: " + "; ".join(errors))
    tx = api.safe_id(args.transaction_id)
    output = candidate_path(api, source, args.output)
    if committed_retry(api, data, output, tx):
        entry = next(item for item in data["debt_state"]["collection_ledger"] if item.get("transaction_id") == tx)
        if entry.get("event_kind") not in {"payment", "early_payoff"} or entry.get("payment") != args.payment:
            raise api.RuntimeProblem("debt transaction retry changed the payment")
        return {"ok": True, "idempotent": True, "output": str(output), "transaction_id": tx}
    try:
        candidate = payment_candidate(data, args.payment, tx)
    except ValueError as exc:
        raise api.RuntimeProblem(str(exc)) from exc
    identical, candidate_warnings = write_candidate(api, data, candidate, output, tx, force=getattr(args, "force", False))
    return {"ok": True, "idempotent": identical, "output": str(output), "transaction_id": tx,
            "payment": args.payment, "renewed": candidate["debt_state"]["contract_cycle_index"] != data["debt_state"]["contract_cycle_index"],
            "principal": candidate["debt_state"]["principal"], "unlocks": debt_unlocks(candidate),
            "warnings": [*warnings, *candidate_warnings]}
