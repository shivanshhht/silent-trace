"""Three deliberately different synthetic populations.

All three are fiction. Every name, number, registration, place and transaction
is invented for software testing, and the fictional currency ``SYN`` is used so
no figure here can be mistaken for a real financial record.

The populations exist to test one claim the intelligence layer has to earn:

* **A - normal network.** Families, friends and coworkers. Ordinary bridging
  exists (a person connects their household to their workplace) and *should* be
  found structurally, but it must not accumulate into a high-priority lead,
  because every crossing relationship sits in a stated family or business
  context.

* **B - coordinated network.** A hub, two intermediaries and two cells that
  barely touch each other. Value moves along a multi-step chain, communications
  cross between cells, and people from different clusters converge on one place
  in a short window. No context is stated for any of it, because a real source
  would not label it.

* **C - dense legitimate network.** A hospital where almost everyone knows
  almost everyone. It is by far the densest of the three - far more
  relationships than B - and it must produce **no** high-priority lead. This is
  the false-positive control, and it is the population that decides whether the
  engine has learned "density means suspicion".

Nothing in the intelligence layer knows these cases exist. No detector keys off
a case id, a name, or a population label; the differences it finds are the
differences in the graphs. The distinguishing structure is real: in a near
clique every route has an equally short alternative, so betweenness collapses to
zero and no intermediary can be found, whereas in B the routes between cells
genuinely pass through two people.

Construction is deterministic - fixed names, fixed dates, fixed loops, no
randomness - so seeding twice yields byte-identical cases.
"""

from datetime import datetime, timedelta, timezone

from app.schemas.investigation import SyntheticDataset


BASE = datetime(2026, 3, 2, 9, 0, tzinfo=timezone.utc)


def _stamp(day_offset: int, hour: int = 9) -> str:
    moment = BASE + timedelta(days=day_offset)
    return moment.replace(hour=hour).isoformat().replace("+00:00", "Z")


def _record(case_id: str, record_id: str, record_type: str, source: str, when: str, payload: dict) -> dict:
    return {
        "case_id": case_id,
        "record_id": record_id,
        "record_type": record_type,
        "source_record_id": source,
        "observed_at": when,
        "payload": payload,
    }


def _source_document(case_id: str, source_id: str, title: str, when: str, content: str) -> dict:
    return _record(
        case_id,
        source_id,
        "evidence_source",
        source_id,
        when,
        {
            "record_id": source_id,
            "source_type": "synthetic_report",
            "title": title,
            "collected_at": when,
            "reliability": "medium",
            "content": content,
        },
    )


def _person(case_id: str, entity_id: str, name: str, source: str, when: str) -> dict:
    return _record(
        case_id, entity_id, "person", source, when, {"entity_id": entity_id, "display_name": name}
    )


def _organization(case_id: str, entity_id: str, name: str, kind: str, source: str, when: str) -> dict:
    return _record(
        case_id,
        entity_id,
        "organization",
        source,
        when,
        {"entity_id": entity_id, "name": name, "organization_type": kind},
    )


def _location(case_id: str, entity_id: str, label: str, locality: str, source: str, when: str) -> dict:
    return _record(
        case_id,
        entity_id,
        "location",
        source,
        when,
        {"entity_id": entity_id, "label": label, "locality": locality},
    )


def _relationship(
    case_id: str,
    record_id: str,
    left: str,
    right: str,
    relationship_type: str,
    source: str,
    when: str,
    *,
    context: str | None = None,
    confidence: float = 1.0,
) -> dict:
    payload = {
        "record_id": record_id,
        "from_entity_id": left,
        "to_entity_id": right,
        "relationship_type": relationship_type,
        "source_record_id": source,
        "confidence": confidence,
        "occurred_at": when,
    }
    if context is not None:
        payload["context"] = context
    return _record(case_id, record_id, "relationship", source, when, payload)


def _communication(case_id: str, record_id: str, left: str, right: str, source: str, when: str) -> dict:
    return _record(
        case_id,
        record_id,
        "communication",
        source,
        when,
        {
            "record_id": record_id,
            "from_entity_id": left,
            "to_entity_id": right,
            "occurred_at": when,
            "channel": "call",
            "duration_seconds": 120,
        },
    )


def _transaction(
    case_id: str, record_id: str, left: str, right: str, source: str, when: str, amount: float, reference: str
) -> dict:
    return _record(
        case_id,
        record_id,
        "financial_transaction",
        source,
        when,
        {
            "record_id": record_id,
            "from_entity_id": left,
            "to_entity_id": right,
            "occurred_at": when,
            "amount": amount,
            "currency": "SYN",
            "reference": reference,
        },
    )


# ---------------------------------------------------------------------------
# A. Normal network
# ---------------------------------------------------------------------------

NORMAL_CASE = "case_normal-001"


def normal_population() -> SyntheticDataset:
    case = NORMAL_CASE
    source = "src_normal-001"
    records: list[dict] = [
        _source_document(
            case,
            source,
            "Synthetic community reference notes",
            _stamp(0),
            "Fictional notes describing an ordinary household and workplace for testing.",
        )
    ]

    people = {
        "per_normal-rhea": "Rhea Alcott",
        "per_normal-sam": "Sam Alcott",
        "per_normal-tara": "Tara Alcott",
        "per_normal-umi": "Umi Fenwick",
        "per_normal-vik": "Vik Oyelaran",
        "per_normal-wren": "Wren Dabiri",
    }
    for index, (entity_id, name) in enumerate(people.items()):
        records.append(_person(case, entity_id, name, source, _stamp(index)))

    records.append(
        _organization(case, "org_normal-bakery", "Northgate Bakery", "company", source, _stamp(1))
    )
    records.append(
        _location(case, "loc_normal-bakery", "Northgate Bakery premises", "Example Town", source, _stamp(1))
    )

    # A household. Stated as family by the source, never inferred from names.
    household = [
        ("rel_normal-fam1", "per_normal-rhea", "per_normal-sam"),
        ("rel_normal-fam2", "per_normal-rhea", "per_normal-tara"),
        ("rel_normal-fam3", "per_normal-sam", "per_normal-tara"),
    ]
    for record_id, left, right in household:
        records.append(
            _relationship(case, record_id, left, right, "associated_with", source, _stamp(2), context="family")
        )

    # A workplace. Rhea is the person who links home and work - ordinary, and it
    # must stay ordinary in the output.
    for index, entity_id in enumerate(["per_normal-rhea", "per_normal-umi", "per_normal-vik"]):
        records.append(
            _relationship(
                case,
                f"rel_normal-work{index}",
                entity_id,
                "org_normal-bakery",
                "member_of",
                source,
                _stamp(3),
                context="business",
            )
        )
        records.append(
            _relationship(
                case,
                f"rel_normal-at{index}",
                entity_id,
                "loc_normal-bakery",
                "located_at",
                source,
                _stamp(3),
                context="business",
            )
        )

    records.append(
        _relationship(
            case,
            "rel_normal-colleagues",
            "per_normal-umi",
            "per_normal-vik",
            "associated_with",
            source,
            _stamp(4),
            context="business",
        )
    )
    records.append(
        _relationship(
            case,
            "rel_normal-friends",
            "per_normal-sam",
            "per_normal-wren",
            "associated_with",
            source,
            _stamp(5),
            context="community",
        )
    )

    # Steady, unremarkable contact spread evenly across several weeks.
    contact_pairs = [
        ("per_normal-rhea", "per_normal-sam"),
        ("per_normal-rhea", "per_normal-umi"),
        ("per_normal-sam", "per_normal-tara"),
        ("per_normal-sam", "per_normal-wren"),
        ("per_normal-umi", "per_normal-vik"),
    ]
    for index, (left, right) in enumerate(contact_pairs):
        for repeat in range(3):
            day = 6 + index * 3 + repeat * 7
            records.append(
                _communication(case, f"com_normal-{index}{repeat}", left, right, source, _stamp(day))
            )

    return SyntheticDataset.model_validate(
        {
            "case_id": case,
            "dataset_id": "set_normal-001",
            "description": (
                "Synthetic ordinary network: one household, one small workplace and a "
                "friendship. Entirely fictional."
            ),
            "records": records,
        }
    )


# ---------------------------------------------------------------------------
# B. Coordinated network
# ---------------------------------------------------------------------------

COORDINATED_CASE = "case_coordinated-001"


def coordinated_population() -> SyntheticDataset:
    case = COORDINATED_CASE
    source = "src_coord-001"
    records: list[dict] = [
        _source_document(
            case,
            source,
            "Synthetic coordination scenario notes",
            _stamp(0),
            "Fictional scenario constructed to exercise structural detectors.",
        )
    ]

    people = {
        "per_coord-marek": "Marek Idris",
        "per_coord-ines": "Ines Havel",
        "per_coord-ovid": "Ovid Strand",
        "per_coord-pax": "Pax Renn",
        "per_coord-quill": "Quill Ashby",
        "per_coord-rune": "Rune Petrov",
        "per_coord-sable": "Sable Nkemi",
    }
    for index, (entity_id, name) in enumerate(people.items()):
        records.append(_person(case, entity_id, name, source, _stamp(index)))

    records.append(
        _location(case, "loc_coord-dockside", "Dockside Lot", "Example Port", source, _stamp(1))
    )

    # Two cells that touch each other only through the two intermediaries. No
    # context is stated anywhere in this population.
    structure = [
        ("rel_coord-a1", "per_coord-marek", "per_coord-ines"),
        ("rel_coord-a2", "per_coord-marek", "per_coord-ovid"),
        ("rel_coord-b1", "per_coord-ines", "per_coord-pax"),
        ("rel_coord-b2", "per_coord-ines", "per_coord-quill"),
        ("rel_coord-b3", "per_coord-pax", "per_coord-quill"),
        ("rel_coord-c1", "per_coord-ovid", "per_coord-rune"),
        ("rel_coord-c2", "per_coord-ovid", "per_coord-sable"),
        ("rel_coord-c3", "per_coord-rune", "per_coord-sable"),
    ]
    for record_id, left, right in structure:
        records.append(
            _relationship(case, record_id, left, right, "associated_with", source, _stamp(6), confidence=0.9)
        )

    # Value moving along a multi-step route.
    chain = [
        ("txn_coord-1", "per_coord-marek", "per_coord-ines", 4200.0, "SYN transfer 1"),
        ("txn_coord-2", "per_coord-ines", "per_coord-pax", 3100.0, "SYN transfer 2"),
        ("txn_coord-3", "per_coord-pax", "per_coord-quill", 1450.0, "SYN transfer 3"),
        ("txn_coord-4", "per_coord-marek", "per_coord-ovid", 3800.0, "SYN transfer 4"),
        ("txn_coord-5", "per_coord-ovid", "per_coord-rune", 2600.0, "SYN transfer 5"),
    ]
    for index, (record_id, left, right, amount, reference) in enumerate(chain):
        records.append(
            _transaction(case, record_id, left, right, source, _stamp(8 + index), amount, reference)
        )

    # Communications that cross between the two cells.
    contacts = [
        ("per_coord-ines", "per_coord-marek"),
        ("per_coord-ovid", "per_coord-marek"),
        ("per_coord-ines", "per_coord-pax"),
        ("per_coord-ines", "per_coord-quill"),
        ("per_coord-ovid", "per_coord-rune"),
        ("per_coord-ovid", "per_coord-sable"),
        ("per_coord-ines", "per_coord-ovid"),
    ]
    for index, (left, right) in enumerate(contacts):
        records.append(_communication(case, f"com_coord-{index}", left, right, source, _stamp(14)))
    # A concentrated day of activity against an otherwise sparse baseline.
    for index, (left, right) in enumerate(contacts[:5]):
        records.append(_communication(case, f"com_coord-burst{index}", left, right, source, _stamp(15, 20)))

    # People from both cells recorded at one place inside a short window.
    for index, entity_id in enumerate(
        ["per_coord-marek", "per_coord-ines", "per_coord-ovid", "per_coord-pax"]
    ):
        records.append(
            _relationship(
                case,
                f"rel_coord-loc{index}",
                entity_id,
                "loc_coord-dockside",
                "located_at",
                source,
                _stamp(16 + index),
                confidence=0.9,
            )
        )

    return SyntheticDataset.model_validate(
        {
            "case_id": case,
            "dataset_id": "set_coordinated-001",
            "description": (
                "Synthetic coordinated network: a hub, two intermediaries and two "
                "loosely connected cells. Entirely fictional."
            ),
            "records": records,
        }
    )


# ---------------------------------------------------------------------------
# C. Dense legitimate network (false-positive control)
# ---------------------------------------------------------------------------

DENSE_CASE = "case_dense-001"

DENSE_STAFF = [
    ("per_dense-01", "Adaeze Nwosu"),
    ("per_dense-02", "Bo Lindqvist"),
    ("per_dense-03", "Cato Meiring"),
    ("per_dense-04", "Devi Ramachandran"),
    ("per_dense-05", "Eli Thorsen"),
    ("per_dense-06", "Fen Zhao"),
    ("per_dense-07", "Gita Bhandari"),
    ("per_dense-08", "Halvor Aas"),
    ("per_dense-09", "Iva Kowalczyk"),
    ("per_dense-10", "Juno Alvarez"),
]


def dense_legitimate_population() -> SyntheticDataset:
    """A hospital: the densest population of the three, and the control.

    Every member is connected to almost every other, which is exactly what a
    working department looks like. Because no route between two staff is
    materially shorter through any particular colleague, no colleague can be a
    structural intermediary, and nothing here should be promoted into a
    high-priority lead.
    """
    case = DENSE_CASE
    source = "src_dense-001"
    records: list[dict] = [
        _source_document(
            case,
            source,
            "Synthetic hospital staff directory notes",
            _stamp(0),
            "Fictional directory of a teaching hospital department, for testing.",
        )
    ]

    for index, (entity_id, name) in enumerate(DENSE_STAFF):
        records.append(_person(case, entity_id, name, source, _stamp(index % 5)))

    records.append(
        _organization(
            case, "org_dense-hospital", "Riverside Teaching Hospital", "employer", source, _stamp(1)
        )
    )
    records.append(
        _location(case, "loc_dense-hospital", "Riverside Teaching Hospital", "Example City", source, _stamp(1))
    )

    for index, (entity_id, _) in enumerate(DENSE_STAFF):
        records.append(
            _relationship(
                case,
                f"rel_dense-member{index:02d}",
                entity_id,
                "org_dense-hospital",
                "member_of",
                source,
                _stamp(2),
                context="business",
            )
        )
        records.append(
            _relationship(
                case,
                f"rel_dense-at{index:02d}",
                entity_id,
                "loc_dense-hospital",
                "located_at",
                source,
                _stamp(2),
                context="business",
            )
        )

    # Near-complete collegial graph: every pair within three positions of each
    # other in the roster, wrapping around, which keeps degrees uniform.
    pair_index = 0
    staff_ids = [entity_id for entity_id, _ in DENSE_STAFF]
    for offset in (1, 2, 3, 4):
        for position, entity_id in enumerate(staff_ids):
            other = staff_ids[(position + offset) % len(staff_ids)]
            if entity_id >= other:
                continue
            records.append(
                _relationship(
                    case,
                    f"rel_dense-col{pair_index:03d}",
                    entity_id,
                    other,
                    "associated_with",
                    source,
                    _stamp(3),
                    context="business",
                )
            )
            pair_index += 1

    # Routine contact, spread evenly so no day stands out against any baseline.
    comm_index = 0
    for offset in (1, 2):
        for position, entity_id in enumerate(staff_ids):
            other = staff_ids[(position + offset) % len(staff_ids)]
            if entity_id >= other:
                continue
            for repeat in range(2):
                day = 5 + (comm_index % 12) + repeat * 13
                records.append(
                    _communication(case, f"com_dense-{comm_index:03d}{repeat}", entity_id, other, source, _stamp(day))
                )
            comm_index += 1

    return SyntheticDataset.model_validate(
        {
            "case_id": case,
            "dataset_id": "set_dense-001",
            "description": (
                "Synthetic dense legitimate network: one hospital department where "
                "almost everyone is connected. False-positive control. Entirely fictional."
            ),
            "records": records,
        }
    )


POPULATIONS = {
    NORMAL_CASE: normal_population,
    COORDINATED_CASE: coordinated_population,
    DENSE_CASE: dense_legitimate_population,
}


def all_populations() -> list[SyntheticDataset]:
    return [builder() for _, builder in sorted(POPULATIONS.items())]
