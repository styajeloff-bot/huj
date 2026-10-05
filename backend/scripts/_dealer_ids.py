#!/usr/bin/env python3
"""Shared, deterministic dealer / distributor identity derivation.

Imported by BOTH ``generate_csv.py`` (to stamp ``dealer_company_id`` onto LCA
rows) and ``generate_dealer_layer.py`` (to emit ``companies_dealers.csv`` and the
warehouse / exchange layers).  Keeping the id derivation in one place guarantees
that a vehicle, its parent application's LCA row, and the dealer company row all
agree on the SAME dealer UUID.

Everything here is a pure function of fixed seed strings, so re-running any of
the generators produces byte-identical output.

Public API
----------
    NUM_DISTRIBUTORS                 -> int (3)
    NUM_DEALERS                      -> int (12)
    DEALERS_PER_DISTRIBUTOR          -> int (4)

    distributor_id(index: int)       -> str  (stable UUID, 0..2)
    dealer_id(index: int)            -> str  (stable UUID, 0..11)

    distributor_ids()               -> list[str]   (len 3)
    dealer_ids()                    -> list[str]    (len 12)

    dealer_index_for_key(key: str)  -> int  (0..11, == hash(key) % 12)
    dealer_id_for_key(key: str)     -> str  (dealer UUID for an application_key)

    distributor_for_dealer_index(i) -> int  (which distributor owns dealer i)

    DEALERS                          -> list[dict]  (full dealer metadata)
    DISTRIBUTORS                     -> list[dict]   (full distributor metadata)
"""

from __future__ import annotations

import hashlib
import uuid

# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------

NUM_DISTRIBUTORS = 3
NUM_DEALERS = 12
DEALERS_PER_DISTRIBUTOR = NUM_DEALERS // NUM_DISTRIBUTORS  # 4

# Fixed namespace so UUIDs never change between runs / machines.
_NAMESPACE = uuid.UUID("c0ffee00-dea1-5eed-b00c-000000000001")

# Distinct seed prefixes keep the dealer and distributor id spaces disjoint.
_DISTRIBUTOR_SEED = "carcraft.distributor"
_DEALER_SEED = "carcraft.dealer"


# ---------------------------------------------------------------------------
# Deterministic primitives
# ---------------------------------------------------------------------------

def _uuid5(seed: str) -> str:
    """Stable UUID derived from a seed string (uuid5 over a fixed namespace)."""
    return str(uuid.uuid5(_NAMESPACE, seed))


def stable_hash(key: str) -> int:
    """Stable non-negative int from a string.

    Uses blake2b (not Python's salted ``hash``) so results are reproducible
    across processes and machines.  This is the SINGLE hashing function that
    every generator must route through so a vehicle and its application land on
    the same dealer.
    """
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


# ---------------------------------------------------------------------------
# Id accessors
# ---------------------------------------------------------------------------

def distributor_id(index: int) -> str:
    if not 0 <= index < NUM_DISTRIBUTORS:
        raise IndexError(f"distributor index out of range: {index}")
    return _uuid5(f"{_DISTRIBUTOR_SEED}.{index}")


def dealer_id(index: int) -> str:
    if not 0 <= index < NUM_DEALERS:
        raise IndexError(f"dealer index out of range: {index}")
    return _uuid5(f"{_DEALER_SEED}.{index}")


def dealer_user_id(index: int) -> str:
    """Stable id of the dealer-side USER account for dealer ``index``.

    Distinct from :func:`dealer_id` (the dealer COMPANY). Exchange bids
    reference ``users.id``, so bids point at this id, not the company id.
    """
    if not 0 <= index < NUM_DEALERS:
        raise IndexError(f"dealer index out of range: {index}")
    return _uuid5(f"{_DEALER_SEED}.user.{index}")


def distributor_ids() -> list[str]:
    return [distributor_id(i) for i in range(NUM_DISTRIBUTORS)]


def dealer_ids() -> list[str]:
    return [dealer_id(i) for i in range(NUM_DEALERS)]


def dealer_index_for_key(key: str) -> int:
    """Map an arbitrary stable key (application_key) -> dealer index 0..11."""
    return stable_hash(key) % NUM_DEALERS


def dealer_id_for_key(key: str) -> str:
    """Dealer UUID for an application_key (== dealers[hash(key) % 12])."""
    return dealer_id(dealer_index_for_key(key))


def distributor_for_dealer_index(dealer_idx: int) -> int:
    """Which distributor owns a given dealer (disjoint groups of 4)."""
    if not 0 <= dealer_idx < NUM_DEALERS:
        raise IndexError(f"dealer index out of range: {dealer_idx}")
    return dealer_idx // DEALERS_PER_DISTRIBUTOR


# ---------------------------------------------------------------------------
# Realistic metadata (fixed, deterministic)
# ---------------------------------------------------------------------------

# 12 dealers across Russian cities with a brand mix.  Order is load-bearing:
# dealer index 0..11 maps to this list, and the first 4 belong to distributor 0,
# the next 4 to distributor 1, the last 4 to distributor 2.
_DEALER_META = [
    # distributor 0
    ("АвтоПрестиж Москва", "Москва", "г. Москва", "Москва", "Lada, Kia, Hyundai"),
    ("Столица Авто", "Москва", "г. Москва", "Москва", "Toyota, Lexus"),
    ("ПодмосковьеАвто", "Подольск", "Московская область", "Московская область", "Haval, Chery"),
    ("Зеленоград Моторс", "Зеленоград", "г. Москва", "Москва", "Geely, Omoda"),
    # distributor 1
    ("Нева Авто", "Санкт-Петербург", "г. Санкт-Петербург", "Санкт-Петербург", "Lada, Renault"),
    ("БалтМоторс", "Санкт-Петербург", "г. Санкт-Петербург", "Санкт-Петербург", "Skoda, Volkswagen"),
    ("Карелия Авто", "Петрозаводск", "Республика Карелия", "Республика Карелия", "UAZ, GAZ"),
    ("Калининград Драйв", "Калининград", "Калининградская область", "Калининградская область", "BMW, Mercedes-Benz"),
    # distributor 2
    ("Урал Авто", "Екатеринбург", "Свердловская область", "Свердловская область", "Lada, Haval"),
    ("Сибирь Моторс", "Новосибирск", "Новосибирская область", "Новосибирская область", "Toyota, Geely"),
    ("Кама Авто", "Казань", "Республика Татарстан", "Республика Татарстан", "Kia, Hyundai, Chery"),
    ("Дон Авто", "Ростов-на-Дону", "Ростовская область", "Ростовская область", "Lada, Omoda, Exeed"),
]

_DISTRIBUTOR_META = [
    ("ГК АвтоХолдинг Центр", "Москва", "г. Москва", "Москва"),
    ("СеверЗапад Дистрибуция", "Санкт-Петербург", "г. Санкт-Петербург", "Санкт-Петербург"),
    ("Восток Авто Дистрибуция", "Екатеринбург", "Свердловская область", "Свердловская область"),
]


def _digits(seed: str, length: int) -> str:
    """Deterministic numeric string of a given length from a seed."""
    h = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest()
    n = int.from_bytes(h, "big")
    return str(n).zfill(length)[:length]


def _inn(seed: str) -> str:
    return _digits(f"inn.{seed}", 10)


def _phone(seed: str) -> str:
    return "+7" + _digits(f"phone.{seed}", 10)


def _slug(name: str) -> str:
    """ASCII-ish slug for building emails from Cyrillic names."""
    return hashlib.blake2b(name.encode("utf-8"), digest_size=4).hexdigest()


def _build_dealers() -> list[dict]:
    out: list[dict] = []
    for i, (name, city, legal, region, brands) in enumerate(_DEALER_META):
        seed = f"{_DEALER_SEED}.{i}"
        out.append({
            "index": i,
            "id": dealer_id(i),
            "name": name,
            "inn": _inn(seed),
            "company_type": "dealer",
            "phone": _phone(seed),
            "email": f"dealer{i}.{_slug(name)}@carcraft-demo.ru",
            "legal_address": f"{legal}, {city}",
            "actual_address": f"{legal}, {city}",
            "city": city,
            "region": region,
            "brands": brands,
            "distributor_index": distributor_for_dealer_index(i),
        })
    return out


def _build_distributors() -> list[dict]:
    out: list[dict] = []
    for i, (name, city, legal, region) in enumerate(_DISTRIBUTOR_META):
        seed = f"{_DISTRIBUTOR_SEED}.{i}"
        out.append({
            "index": i,
            "id": distributor_id(i),
            "name": name,
            "inn": _inn(seed),
            "company_type": "distributor",
            "phone": _phone(seed),
            "email": f"distributor{i}.{_slug(name)}@carcraft-demo.ru",
            "legal_address": f"{legal}, {city}",
            "actual_address": f"{legal}, {city}",
            "city": city,
            "region": region,
        })
    return out


DEALERS: list[dict] = _build_dealers()
DISTRIBUTORS: list[dict] = _build_distributors()
