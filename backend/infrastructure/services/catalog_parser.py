"""Excel catalog parser — port of Express CatalogService + parseCatalogPreview.

Pure synchronous code. Parsing is CPU-bound; the preview query handler can
call us directly, while the upload command should run us inside a worker
thread (`asyncio.to_thread`) before publishing rows for downstream processing.

Frontend depends on the exact shape of `parse_excel_preview` — keep field
names and ordering identical to the Express version.
"""
from __future__ import annotations

import io
import logging
import math
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, BinaryIO, TypedDict, cast
from uuid import UUID

import pandas as pd

from infrastructure.settings import settings

logger = logging.getLogger("carcraft-backend")


# ---------------------------------------------------------------------------
# Mappings (Russian Excel column → DB column). Copied verbatim from
# express/services/CatalogService.js so that the upload pipeline produces
# byte-identical column sets to the legacy implementation.
# ---------------------------------------------------------------------------

OPTIONS_MAPPING: dict[str, str] = {
    "Алькантара (материал салона)": "alcantara",
    "Отделка потолка черного цвета": "black_roof",
    "Комбинированный (материал салона)": "combo_interior",
    "Декоративная подсветка салона": "decorative_interior_lighting",
    "Накладки на пороги": "door_sill_panel",
    "Электрорегулировка сиденья водителя": "driver_seat_electric",
    "Память сиденья водителя": "driver_seat_memory",
    "Сиденье водителя с поясничной поддержкой": "driver_seat_support",
    "Регулировка сиденья водителя по высоте": "driver_seat_updown",
    "Искусственная кожа (материал салона)": "eco_leather",
    "Электрорегулировка задних сидений": "electro_rear_seat",
    "Ткань (материал салона)": "fabric_seats",
    "Функция складывания спинки сиденья пассажира": "folding_front_passenger_seat",
    "Складной столик на спинках передних сидений": "folding_tables_rear",
    "Передний центральный подлокотник": "front_centre_armrest",
    "Передние сиденья с поясничной поддержкой": "front_seat_support",
    "Подогрев передних сидений": "front_seats_heat",
    "Вентиляция передних сидений": "front_seats_heat_vent",
    "Люк": "hatch",
    "Кожа (материал салона)": "leather",
    "Отделка кожей рычага КПП": "leather_gear_stick",
    "Сиденья с массажем": "massage_seats",
    "Панорамная крыша / лобовое стекло": "panorama_roof",
    "Электрорегулировка передних сидений": "passenger_seat_electric",
    "Регулировка передних сидений по высоте": "passenger_seat_updown",
    "Вентиляция задних сидений": "rear_seat_heat_vent",
    "Память задних сидений": "rear_seat_memory",
    "Подогрев задних сидений": "rear_seats_heat",
    "Солнцезащитная шторка на заднем стекле": "roller_blind_for_rear_window",
    "Солнцезащитные шторки в задних дверях": "roller_blinds_for_rear_side_windows",
    "Память передних сидений": "seat_memory",
    "Складывающееся заднее сиденье": "seat_transformation",
    "Декоративные накладки на педали": "sport_pedals",
    "Спортивные передние сиденья": "sport_seats",
    "Третий задний подголовник": "third_rear_headrest",
    "Третий ряд сидений": "third_row_seats",
    "Тонированные стекла": "tinted_glass",
    "Обогрев рулевого колеса": "wheel_heat",
    "Отделка кожей рулевого колеса": "wheel_leather",
    "Камера 360°": "camera_360",
    "Регулируемый педальный узел": "adj_pedals",
    "Адаптивный круиз-контроль": "auto_cruise",
    "Автоматическое складывание зеркал": "auto_mirrors",
    "Система автоматической парковки": "auto_park",
    "Климат-контроль 1-зонный": "climate_control_1",
    "Климат-контроль 2-зонный": "climate_control_2",
    "Бортовой компьютер": "computer",
    "Кондиционер": "condition",
    "Круиз-контроль": "cruise_control",
    "Система выбора режима движения": "drive_mode_sys",
    "Электрорегулировка руля": "e_adjustment_wheel",
    "Открытие багажника без помощи рук": "easy_trunk_opening",
    "Электропривод зеркал": "electro_mirrors",
    "Электропривод крышки багажника": "electro_trunk",
    "Электростеклоподъемники задние": "electro_window_back",
    "Электростеклоподъемники передние": "electro_window_front",
    "Электронная приборная панель": "electronic_gage_panel",
    "Камера передняя": "front_camera",
    "Система доступа без ключа": "keyless_entry",
    "Мультифункциональное рулевое колесо": "multi_wheel",
    "Климат-контроль многозонный": "multizone_climate_control",
    "Парктроник передний": "park_assist_f",
    "Парктроник задний": "park_assist_r",
    "Доводчик дверей": "power_latching_doors",
    "Программируемый предпусковой отопитель": "programmed_block_heater",
    "Проекционный дисплей": "projection_display",
    "Камера задняя": "rear_camera",
    "Дистанционный запуск двигателя": "remote_engine_start",
    "Усилитель руля": "servo",
    "Запуск двигателя с кнопки": "start_button",
    "Система «старт-стоп»": "start_stop_function",
    "Подрулевые лепестки переключения передач": "steering_wheel_gear_shift_paddles",
    "Регулировка руля по высоте": "wheel_configuration1",
    "Регулировка руля по вылету": "wheel_configuration2",
    "Рулевая колонка с памятью положения": "wheel_memory",
    "Активный усилитель руля": "wheel_power",
    "Система адаптивного освещения": "adaptive_light",
    "Автоматический корректор фар": "automatic_lighting_control",
    "Дневные ходовые огни": "drl",
    "Электрообогрев форсунок стеклоомывателей": "heated_wash_system",
    "Система управления дальним светом": "high_beam_assist",
    "Лазерные фары": "laser_lights",
    "Светодиодные фары": "led_lights",
    "Омыватель фар": "light_cleaner",
    "Датчик света": "light_sensor",
    "Электрообогрев боковых зеркал": "mirrors_heat",
    "Противотуманные фары": "ptf",
    "Датчик дождя": "rain_sensor",
    "Электрообогрев зоны стеклоочистителей": "windcleaner_heat",
    "Электрообогрев лобового стекла": "windscreen_heat",
    "Ксеноновые/биксеноновые фары": "xenon",
    "Антиблокировочная система (ABS)": "abs",
    "Подушки безопасности оконные (шторки)": "airbag_curtain",
    "Подушка безопасности водителя": "airbag_driver",
    "Подушка безопасности пассажира": "airbag_passenger",
    "Подушки безопасности боковые задние": "airbag_rear_side",
    "Подушки безопасности боковые": "airbag_side",
    "Антипробуксовочная система (ASR)": "asr",
    "Система помощи при торможении (BAS; EBD)": "bas",
    "Система контроля слепых зон": "blind_spot",
    "Система предотвращения столкновения": "collision_prevention_assist",
    "Система помощи при спуске": "dha",
    "Датчик усталости водителя": "drowsy_driver_alert_system",
    "Система стабилизации (ESP)": "esp",
    "Система предупреждения о столкновении": "feedback_alarm",
    "ЭРА-ГЛОНАСС": "glonass",
    "Система помощи при старте в гору (HSA)": "hcc",
    "Крепление детского кресла (задний ряд) ISOFIX": "isofix",
    "Крепление детского кресла (передний ряд) ISOFIX": "isofix_front",
    "Подушка безопасности для защиты коленей водителя": "knee_airbag",
    "Бронированный кузов": "laminated_safety_glass",
    "Система удержания в полосе": "lane_keeping_assist",
    "Система ночного видения": "night_vision",
    "Блокировка замков задних дверей": "power_child_locks_rear_doors",
    "Система распознавания дорожных знаков": "traffic_sign_recognition",
    "Датчик давления в шинах": "tyre_pressure",
    "Система стабилизации рулевого управления (VSM)": "vsm",
    "Сигнализация": "alarm",
    "Иммобилайзер": "immo",
    "Центральный замок": "lock_system",
    "Датчик проникновения в салон (датчик объема)": "volume_sensor",
    "Розетка 12V": "socket_12v",
    "Розетка 220V": "socket_220v",
    "Android Auto": "android_auto",
    "CarPlay": "apple_carplay",
    "Аудиоподготовка": "audiopreparation",
    "Аудиосистема": "audiosystem_cd",
    "Мультимедиа система с ЖК-экраном": "audiosystem_tv",
    "AUX": "aux",
    "Bluetooth": "bluetooth",
    "Мультимедиа система для задних пассажиров": "entertainment_system_for_rear_seat_passengers",
    "Премиальная аудиосистема": "music_super",
    "Навигационная система": "navigation",
    "USB": "usb",
    "Голосовое управление": "voice_recognition",
    "Беспроводная зарядка для смартфона": "wireless_charger",
    "Яндекс Авто": "ya_auto",
    "Активная подвеска": "activ_suspension",
    "Пневмоподвеска": "air_suspension",
    "Докатка": "reduce_spare_wheel",
    "Полноразмерное запасное колесо": "spare_wheel",
    "Спортивная подвеска": "sport_suspension",
    "Диски 14": "wheels_14_inch",
    "Диски 15": "wheels_15_inch",
    "Диски 16": "wheels_16_inch",
    "Диски 17": "wheels_17_inch",
    "Диски 18": "wheels_18_inch",
    "Диски 19": "wheels_19_inch",
    "Диски 20": "wheels_20_inch",
    "Диски 21": "wheels_21_inch",
    "Диски 22": "wheels_22_inch",
    "Обвес кузова": "body_kit",
    "Декоративные молдинги": "body_mouldings",
    "Двухцветная окраска кузова": "duo_body_color",
    "Металлик (тип краски)": "paint_metallic",
    "Рейлинги на крыше": "roof_rails",
    "Стальные диски": "steel_wheels",
}

SPECIFICATIONS_MAPPING: dict[str, str] = {
    "Задние тормоза": "back_brake",
    "Система питания двигателя": "feeding",
    # NB: Excel column "Modifikatsiya" maps to DB column `horse_power`. The
    # value is parsed via `_extract_horsepower` which strips the horsepower
    # suffix when present. Express did the same, keep behaviour identical.
    "Модификация": "horse_power",
    "Мощность (кВт)": "kvt_power",
    "Обороты макс. мощности (об/мин)": "rpm_power",
    "Тип двигателя": "engine_type",
    "Коробка передач": "transmission",
    "Тип привода": "drive",
    "Объем двигателя (л)": "volume",
    "Разгон до 100 км/ч (с)": "time_to_100",
    "Расположение цилиндров": "cylinders_order",
    "Максимальная скорость (км/ч)": "max_speed",
    "Степень сжатия": "compression",
    "Количество цилиндров": "cylinders_value",
    "Диаметр цилиндра и ход поршня (мм)": "diametr",
    "Ход поршня (мм)": "piston_stroke",
    "Расположение двигателя": "engine_order",
    "Количество передач": "gear_value",
    "Максимальный крутящий момент": "moment",
    "Марка топлива": "petrol_type",
    "Число клапанов на цилиндр": "valves",
    "Снаряженная масса (кг)": "weight",
    "Размер колёс": "wheel_size",
    "Колёсная база (мм)": "wheel_base",
    "Ширина передней колеи (мм)": "front_wheel_base",
    "Ширина задней колеи (мм)": "back_wheel_base",
    "Передние тормоза": "front_brake",
    "Тип передней подвески": "front_suspension",
    "Тип задней подвески": "back_suspension",
    "Высота (мм)": "height",
    "Ширина (мм)": "width",
    "Объём топливного бака (л)": "fuel_tank_capacity",
    "Количество мест": "seats",
    "Длина (мм)": "length",
    "Экологический класс": "emission_euro_class",
    "Объем двигателя (см³)": "volume_litres",
    "Расход топлива в смешанном цикле (л/100 км)": "consumption_mixed",
    "Клиренс (мм)": "clearance",
    "Объем багажника мин (л)": "trunks_min_capacity",
    "Объем багажника макс (л)": "trunks_max_capacity",
    "Расход топлива на трассе (л/100 км)": "consumption_hiway",
    "Расход топлива в городе (л/100 км)": "consumption_city",
    "Обороты макс. крутящего момента (об/мин)": "moment_rpm",
    "Полная масса (кг)": "full_weight",
    "Запас хода (км)": "range_distance",
    "Емкость батареи (кВт⋅ч)": "battery_capacity",
    "Выбросы CO2 (г/км)": "fuel_emission",
    "Запас хода на электричестве (км)": "electric_range",
    "Время зарядки (ч)": "charge_time",
    "Название рейтинга безопасности": "safety_rating",
    "Оценка безопасности": "safety_grade",
    "Допустимая полная масса": "full_weight",
    "Колесная формула": "wheel_formula",
    "Колесная база": "wheel_base",
    "Допустимая нагрузка на оси (передняя / задняя)": (
        "permitted_axle_loads"
    ),
    "Кабина": "cabin",
    "Экокласс": "emission_euro_class",
    "Пассажировместимость": "seats",
    "Допустимая полная масса (тягача / автопоезда)": (
        "permitted_gross_train_weight"
    ),
    "Подвеска (передняя / задняя)": "suspension",
    "Топливные баки": "fuel_tanks",
}


# New task-specific headings take precedence over their legacy equivalents when
# both are populated. Keeping aliases explicit avoids depending on dict order
# and prevents a blank preferred cell from erasing a legacy value.
SPECIFICATION_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "full_weight": ("Допустимая полная масса", "Полная масса (кг)"),
    "wheel_base": ("Колесная база", "Колёсная база (мм)"),
    "emission_euro_class": ("Экокласс", "Экологический класс"),
    "seats": ("Пассажировместимость", "Количество мест"),
}


# ---------------------------------------------------------------------------
# Output shapes
# ---------------------------------------------------------------------------


class GDriveImagesStats(TypedDict):
    total: int
    unique: int


class SampleRow(TypedDict):
    vin: str
    mark: str
    model: str
    generation: str
    price: Any
    has_vin: bool


class CatalogPreviewDict(TypedDict):
    total_rows: int
    unique_marks: int
    unique_models: int
    unique_generations: int
    vehicles_count: int
    rows_without_vin: int
    has_errors: bool
    errors: list[str]
    warnings: list[str]
    sample_data: list[SampleRow]
    gdrive_images: GDriveImagesStats


class ParsedRow(TypedDict):
    mark: dict[str, Any]
    model: dict[str, Any]
    generation: dict[str, Any]
    configuration: dict[str, Any]
    modification: dict[str, Any]
    vehicle: dict[str, Any]
    options: dict[str, Any]
    specifications: dict[str, Any]
    image_urls: list[str]
    image_filenames: list[str]
    has_options: bool
    has_specifications: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_GDRIVE_FILE_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)/")
_HORSEPOWER_RE = re.compile(r"^(\d+)\s*л\.с.")
_EMPTY_VALUES: frozenset[str] = frozenset({"", "NaN"})
DEFAULT_VEHICLE_CATEGORY = "B (Легковые автомобили)"


def _clean_value(value: Any) -> Any:
    """Mirror of Express `cleanValue`. NaN/empty/None → None; trim strings."""
    if value is None or value in _EMPTY_VALUES:
        return None
    # pandas may give us float NaN
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return None if stripped in _EMPTY_VALUES else stripped
    return value


def _clean_int(value: Any) -> int | None:
    """Coerce pandas-read values (str/int/float) to int for SMALLINT columns."""
    cleaned = _clean_value(value)
    result: int | None = None
    if cleaned is None or (isinstance(cleaned, float) and math.isnan(cleaned)):
        result = None
    elif isinstance(cleaned, bool):
        result = int(cleaned)
    elif isinstance(cleaned, int):
        result = cleaned
    elif isinstance(cleaned, float):
        result = int(cleaned)
    elif isinstance(cleaned, str):
        stripped = cleaned.strip()
        try:
            result = int(stripped)
        except ValueError:
            try:
                result = int(float(stripped))
            except (ValueError, TypeError):
                result = None
    return result


def _clean_id(value: Any) -> str | None:
    """Coerce numeric IDs from pandas to str (DB columns are VARCHAR)."""
    cleaned = _clean_value(value)
    if cleaned is None:
        return None
    if isinstance(cleaned, float):
        if cleaned.is_integer():
            return str(int(cleaned))
        return str(cleaned)
    return str(cleaned)


_STATUS_ALIASES: dict[str, str] = {
    "available": "available",
    "reserved": "reserved",
    "sold": "sold",
    "в наличии": "available",
    "доступен": "available",
    "доступна": "available",
    "зарезервировано": "reserved",
    "зарезервирован": "reserved",
    "продано": "sold",
    "продан": "sold",
}


def _clean_uuid(value: Any) -> UUID | None:
    cleaned = _clean_value(value)
    if cleaned is None:
        return None
    try:
        return UUID(str(cleaned))
    except ValueError:
        return None


def _clean_datetime(value: Any) -> datetime | None:
    cleaned = _clean_value(value)
    if cleaned is None:
        return None
    if isinstance(cleaned, datetime):
        return cleaned
    try:
        return datetime.fromisoformat(str(cleaned))
    except ValueError:
        return None


def _clean_vehicle_status(row: dict[str, Any]) -> str | None:
    raw = row.get("Статус")
    if raw is None:
        raw = row.get("status")
    cleaned = _clean_value(raw)
    if cleaned is None:
        return None
    return _STATUS_ALIASES.get(str(cleaned).strip().lower())


def _clean_price_value(value: Any) -> Decimal | None:
    """Mirror of Express `cleanPriceValue`, but returns Decimal for money."""
    result: Decimal | None = None
    if value is None or value in _EMPTY_VALUES or (
        isinstance(value, float) and math.isnan(value)
    ):
        result = None
    elif isinstance(value, str):
        clean_str = re.sub(r"\s", "", value).strip()
        if clean_str:
            try:
                result = Decimal(clean_str.replace(",", "."))
            except (InvalidOperation, ValueError):
                result = None
    elif isinstance(value, int | float):
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError):
            result = None
    return result


def _extract_horsepower(value: Any) -> Any:
    """Mirror of Express `extractHorsepower`."""
    if value is None or value in _EMPTY_VALUES:
        return None
    if isinstance(value, int | float):
        if isinstance(value, float) and math.isnan(value):
            return None
        return value
    if isinstance(value, str):
        match = _HORSEPOWER_RE.match(value)
        if match:
            return int(match.group(1))
        return value
    return None


def _is_gdrive_url(url: str | None) -> bool:
    return bool(url) and "drive.google.com" in (url or "")


def _extract_gdrive_file_id(url: str) -> str | None:
    match = _GDRIVE_FILE_ID_RE.search(url)
    return match.group(1) if match else None


_IMAGE_FILE_EXTS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".webp", ".gif"}
)


def _split_image_urls(raw: Any) -> list[str]:
    """Split the `Картинка` cell into trimmed entries (urls or filenames)."""
    if raw is None:
        return []
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def _is_image_filename(entry: str) -> bool:
    """An entry is an S3 filename if it has no URL scheme and an image ext."""
    if "://" in entry:
        return False
    lower = entry.lower()
    return any(lower.endswith(ext) for ext in _IMAGE_FILE_EXTS)


def _classify_image_entries(raw: Any) -> tuple[list[str], list[str]]:
    """Return ``(urls, filenames)`` for one `Картинка` cell."""
    urls: list[str] = []
    filenames: list[str] = []
    for entry in _split_image_urls(raw):
        if _is_image_filename(entry):
            filenames.append(entry)
        else:
            urls.append(entry)
    return urls, filenames


# ---------------------------------------------------------------------------
# Core parsing
# ---------------------------------------------------------------------------


def _read_first_nonempty_sheet(
    source: bytes | io.BytesIO | BinaryIO,
) -> list[dict[str, Any]]:
    """Pick the first sheet that has at least one row, mirroring Express."""
    stream = io.BytesIO(source) if isinstance(source, bytes) else source
    excel = pd.ExcelFile(stream, engine="openpyxl")
    for sheet_name in excel.sheet_names:
        df = excel.parse(sheet_name, dtype=object)
        df = df.dropna(how="all")
        if not df.empty:
            df = df.where(pd.notna(df), None)
            return cast("list[dict[str, Any]]", df.to_dict(orient="records"))
    return []


def parse_excel_rows(source: bytes | io.BytesIO | BinaryIO) -> list[dict[str, Any]]:
    """Return raw row dicts (Russian column names preserved)."""
    return _read_first_nonempty_sheet(source)


def _count_gdrive_images(rows: list[dict[str, Any]]) -> GDriveImagesStats:
    unique: set[str] = set()
    total = 0
    for row in rows:
        for url in _split_image_urls(row.get("Картинка")):
            if "drive.google.com" in url:
                total += 1
                unique.add(url)
    return GDriveImagesStats(total=total, unique=len(unique))


def parse_excel_preview(source: bytes | io.BytesIO | BinaryIO) -> CatalogPreviewDict:
    """Return preview stats. Shape mirrors Express AdminService.parseCatalogPreview."""
    data = _read_first_nonempty_sheet(source)
    if not data:
        return CatalogPreviewDict(
            total_rows=0,
            unique_marks=0,
            unique_models=0,
            unique_generations=0,
            vehicles_count=0,
            rows_without_vin=0,
            has_errors=True,
            errors=["Excel файл пустой или не содержит данных"],
            warnings=[],
            sample_data=[],
            gdrive_images=GDriveImagesStats(total=0, unique=0),
        )

    unique_marks: set[Any] = set()
    unique_models: set[Any] = set()
    unique_generations: set[Any] = set()
    rows_without_vin = 0
    rows_without_price = 0

    sample_data: list[SampleRow] = []
    for row in data[: settings.catalog_preview_sample_size]:
        vin_raw = row.get("VIN")
        sample_data.append(
            SampleRow(
                vin=str(vin_raw) if vin_raw not in (None, "") else "N/A",
                mark=str(row.get("Марка") or "N/A"),
                model=str(row.get("Модель") or "N/A"),
                generation=str(row.get("Поколение") or "N/A"),
                price=row.get("Цена от") or row.get("Стоимость ") or 0,
                has_vin=bool(vin_raw and str(vin_raw).strip()),
            )
        )

    for row in data:
        if row.get("ID марки"):
            unique_marks.add(row["ID марки"])
        if row.get("ID модели"):
            unique_models.add(row["ID модели"])
        if row.get("ID поколения"):
            unique_generations.add(row["ID поколения"])
        vin = row.get("VIN")
        if not vin or not str(vin).strip():
            rows_without_vin += 1
        price = row.get("Стоимость ")
        if not price or not str(price).strip():
            rows_without_price += 1

    warnings: list[str] = []
    if rows_without_vin > 0:
        warnings.append(
            f"Найдено {rows_without_vin} строк без VIN. "
            f'Эти автомобили будут добавлены как "заказ по модели".'
        )
    if rows_without_price > 0:
        warnings.append(
            f"Найдено {rows_without_price} строк без цены. "
            f"Для этих автомобилей будет использована цена из модификации."
        )

    return CatalogPreviewDict(
        total_rows=len(data),
        unique_marks=len(unique_marks),
        unique_models=len(unique_models),
        unique_generations=len(unique_generations),
        vehicles_count=len(data),
        rows_without_vin=rows_without_vin,
        has_errors=False,
        errors=[],
        warnings=warnings,
        sample_data=sample_data,
        gdrive_images=_count_gdrive_images(data),
    )


def _extract_options(row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    options: dict[str, Any] = {}
    has_any = False
    for excel_col, db_col in OPTIONS_MAPPING.items():
        value = _clean_value(row.get(excel_col))
        if value is not None and value not in _EMPTY_VALUES:
            has_any = True
        options[db_col] = None if value is None else str(value)
    return options, has_any


def _extract_specifications(row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    specs: dict[str, Any] = {}
    has_any = False
    for excel_col, db_col in SPECIFICATIONS_MAPPING.items():
        alias_columns = SPECIFICATION_HEADER_ALIASES.get(db_col)
        if alias_columns is not None:
            if db_col in specs:
                continue
            value = next(
                (
                    cleaned
                    for alias_column in alias_columns
                    if (cleaned := _clean_value(row.get(alias_column))) is not None
                ),
                None,
            )
        else:
            value = _clean_value(row.get(excel_col))
            if excel_col == "Модификация":
                value = _extract_horsepower(value)
        if value is not None and value not in _EMPTY_VALUES:
            has_any = True
        specs[db_col] = None if value is None else str(value)
    return specs, has_any


def extract_row_data(row: dict[str, Any]) -> ParsedRow:
    """Translate one raw Excel row into the structured ParsedRow shape."""
    mark_id = _clean_id(row.get("ID марки"))
    model_id = _clean_id(row.get("ID модели"))
    generation_id = _clean_id(row.get("ID поколения"))
    configuration_id = _clean_id(row.get("ID конфигурации"))
    modification_id = _clean_id(row.get("ID модификации"))

    mark = {
        "id": mark_id,
        "name": _clean_value(row.get("Марка")),
        "cyrillic_name": _clean_value(row.get("Марка (кириллица)")),
        "popular": 1 if _clean_value(row.get("Популярна")) else 0,
        "country": _clean_value(row.get("Страна марки")),
    }
    model = {
        "id": model_id,
        "name": _clean_value(row.get("Модель")),
        "cyrillic_name": _clean_value(row.get("Модель (кириллица)")),
        "class": _clean_value(row.get("Класс")),
        "year_from": _clean_int(row.get("Год модели от")),
        "year_to": _clean_int(row.get("Год модели до")),
        "category": (
            _clean_value(row.get("Категория транспорта"))
            or _clean_value(row.get("Категория автомобиля"))
            or DEFAULT_VEHICLE_CATEGORY
        ),
        "mark_id": mark_id,
    }
    generation = {
        "id": generation_id,
        "name": _clean_value(row.get("Поколение")),
        "year_start": _clean_int(row.get("Год поколения от")),
        "year_stop": _clean_int(row.get("Год поколения до")),
        "is_restyle": 1 if _clean_value(row.get("Рестайлинг")) else 0,
        "model_id": model_id,
    }
    configuration = {
        "id": configuration_id,
        "doors_count": _clean_int(row.get("Кол-во дверей")),
        "body_type": _clean_value(row.get("Кузов")),
        "configuration_name": _clean_value(row.get("Конфигурация")),
        "generation_id": generation_id,
    }
    modification = {
        "complectation_id": modification_id,
        "offers_price_from": _clean_price_value(row.get("Цена от")),
        "offers_price_to": _clean_price_value(row.get("Цена до")),
        "group_name": _clean_value(row.get("Группа")),
        "configuration_id": configuration_id,
    }
    # NB: trailing-space column names are intentional — the Express source
    # spreadsheets ship them as `'Стоимость '` / `'Специальная стоимость '`.
    vehicle_status = _clean_vehicle_status(row)
    vehicle = {
        "id": _clean_uuid(row.get("ID") or row.get("id")),
        "vin": _clean_id(row.get("VIN")),
        "dealer_id": _clean_uuid(row.get("dealer_id") or row.get("Дилер ID")),
        "warehouse_id": _clean_uuid(
            row.get("warehouse_id") or row.get("Склад ID")
        ),
        "mark_id": mark_id,
        "model_id": model_id,
        "generation_id": generation_id,
        "configuration_id": configuration_id,
        "complectation_id": modification_id,
        "year": _clean_int(row.get("Год выпуска")),
        "base_price": _clean_price_value(row.get("Стоимость ")),
        "special_price": (
            _clean_price_value(row.get("Специальная цена"))
            or _clean_price_value(row.get("Специальная цена "))
            or _clean_price_value(row.get("special_price"))
        ),
        "discount_price": _clean_price_value(row.get("Специальная стоимость ")),
        "color": _clean_value(row.get("Цвета")),
        "color_inter": _clean_value(row.get("Цвета салона")),
        "status": vehicle_status or "available",
        "is_available": (vehicle_status or "available") == "available",
        "created_at": _clean_datetime(
            row.get("created_at") or row.get("Дата создания") or row.get("Создано")
        ),
    }

    options, has_options = _extract_options(row)
    specs, has_specs = _extract_specifications(row)
    image_urls, image_filenames = _classify_image_entries(row.get("Картинка"))
    if image_filenames:
        vehicle["images"] = list(image_filenames)

    return ParsedRow(
        mark=mark,
        model=model,
        generation=generation,
        configuration=configuration,
        modification=modification,
        vehicle=vehicle,
        options=options,
        specifications=specs,
        image_urls=image_urls,
        image_filenames=image_filenames,
        has_options=has_options,
        has_specifications=has_specs,
    )
