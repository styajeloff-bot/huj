"""Domain-level errors — no HTTP, no infrastructure concepts."""

import uuid
from uuid import UUID


class DomainError(Exception):
    """Base for all domain errors."""


class OrderNotFoundError(DomainError):
    def __init__(self, msg: str = "Заказ не найден"):
        super().__init__(msg)


class VehicleNotFoundError(DomainError):
    def __init__(self, vehicle_id: UUID):
        super().__init__(f"Автомобиль {vehicle_id} не найден")
        self.vehicle_id = vehicle_id


class VehicleNotAvailableError(DomainError):
    def __init__(self, vehicle_id: uuid.UUID):
        super().__init__(f"Автомобиль {vehicle_id} недоступен для покупки")
        self.vehicle_id = vehicle_id


class InsufficientVehiclesError(DomainError):
    def __init__(self, requested: int, available: int):
        super().__init__(
            f"Недостаточно автомобилей данной комплектации."
            f" Запрошено: {requested}, доступно: {available}"
        )


class InvalidOrderStatusError(DomainError):
    """Order status does not allow the requested operation."""


class AccessDeniedError(DomainError):
    def __init__(self, msg: str = "Нет доступа к данному заказу"):
        super().__init__(msg)


class PaymentNotFoundError(DomainError):
    def __init__(self, msg: str = "Платеж не найден"):
        super().__init__(msg)


class ScheduleItemNotFoundError(DomainError):
    def __init__(self, msg: str = "Платеж по графику не найден"):
        super().__init__(msg)


class ScheduleItemMismatchError(DomainError):
    def __init__(self) -> None:
        super().__init__("Платеж не относится к данному заказу")


class ScheduleItemAlreadyPaidError(DomainError):
    def __init__(self) -> None:
        super().__init__("Платеж уже оплачен")


class PriceUnavailableError(DomainError):
    def __init__(self, vehicle_id: UUID):
        super().__init__(f"Не удалось определить цену для автомобиля {vehicle_id}")


class PaymentGatewayError(DomainError):
    """Payment gateway configuration or communication error."""


class InvalidSignatureError(DomainError):
    def __init__(self) -> None:
        super().__init__("Неверная подпись webhook")


class UserNotFoundError(DomainError):
    def __init__(self, msg: str = "Пользователь не найден"):
        super().__init__(msg)


class UserAlreadyExistsError(DomainError):
    def __init__(
        self, msg: str = "Введеный номер уже зарегистрирован на платформе"
    ) -> None:
        super().__init__(msg)


class InvalidVerificationCodeError(DomainError):
    def __init__(self) -> None:
        super().__init__("Неверный код или код истёк")


class CodeAlreadySentError(DomainError):
    def __init__(self) -> None:
        super().__init__("Код подтверждения уже отправлен. Попробуйте через минуту.")


class UserDeactivatedError(DomainError):
    def __init__(self) -> None:
        super().__init__("Пользователь деактивирован")


class InvalidImageError(DomainError):
    def __init__(self, msg: str = "Некорректный файл изображения"):
        super().__init__(msg)


class ImageNotFoundError(DomainError):
    def __init__(self, msg: str = "Изображение не найдено"):
        super().__init__(msg)


class ObjectStorageUnavailableError(DomainError):
    def __init__(self, msg: str = "Хранилище объектов недоступно"):
        super().__init__(msg)


class NotificationNotFoundError(DomainError):
    def __init__(self, msg: str = "Уведомление не найдено"):
        super().__init__(msg)


class CompanyLookupUnavailableError(DomainError):
    """External company-lookup provider is misconfigured or unreachable."""

    def __init__(self, msg: str = "Сервис поиска компаний недоступен"):
        super().__init__(msg)


class SopdSignerResolutionError(DomainError):
    """A management-company chain cannot resolve to a SOPD signer."""

    def __init__(
        self,
        msg: str = "Не удалось определить директора управляющей компании",
    ):
        super().__init__(msg)


class AccountingProviderUnavailableError(DomainError):
    """External accounting-report provider is misconfigured or unreachable."""

    def __init__(self, msg: str = "Сервис бухгалтерской отчётности недоступен"):
        super().__init__(msg)


class AccountingDataNotFoundError(DomainError):
    """ФНС does not publish bookkeeping reports for this company."""

    def __init__(self, msg: str = "Бухгалтерская отчётность не найдена"):
        super().__init__(msg)


class CompensationNotFoundError(DomainError):
    def __init__(self, compensation_id: UUID | None = None):
        msg = f"Компенсация {compensation_id} не найдена" if compensation_id else "Компенсация не найдена"
        super().__init__(msg)


class InvalidCompensationStatusError(DomainError):
    """Compensation status does not allow the requested operation."""


class InvalidCompensationValueError(DomainError):
    """Compensation value or bounds are invalid."""


class CompensationDocumentsRequiredError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Невозможно отметить компенсацию оплаченной без подтверждающих документов"
        )


class ZeroCalculationBaseError(DomainError):
    def __init__(self) -> None:
        super().__init__("Невозможно создать компенсацию: база расчёта равна нулю")


class TooManyCompensationsError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Максимальное количество компенсаций на программу поддержки — 4"
        )


class SupportNotFoundError(DomainError):
    def __init__(self, support_id: UUID | None = None):
        msg = (
            f"Программа поддержки {support_id} не найдена"
            if support_id
            else "Программа поддержки не найдена"
        )
        super().__init__(msg)


class CompanyNotFoundError(DomainError):
    def __init__(self, msg: str = "Компания не найдена"):
        super().__init__(msg)


class CompanyAccessDeniedError(DomainError):
    def __init__(self, msg: str = "Недостаточно прав доступа к компании"):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Calculator domain
# ---------------------------------------------------------------------------


class CalculatorError(DomainError):
    """Base for calculator domain errors."""


class InvalidCalculationParamsError(CalculatorError):
    """Calculator inputs violate a domain invariant (e.g. avans > total)."""


class LeasingRatesNotConfiguredError(CalculatorError):
    def __init__(self) -> None:
        super().__init__("Ставки лизинга не настроены")


# ---------------------------------------------------------------------------
# Support programs / dealer groups admin domain (A6)
# ---------------------------------------------------------------------------


class SupportProgramNotFoundError(DomainError):
    def __init__(self, program_id: UUID | None = None):
        msg = (
            f"Программа поддержки {program_id} не найдена"
            if program_id is not None
            else "Программа поддержки не найдена"
        )
        super().__init__(msg)


class InvalidSupportProgramError(DomainError):
    """Domain validation failed for a support program."""


class DealerGroupNotFoundError(DomainError):
    def __init__(self, group_id: UUID | None = None):
        msg = (
            f"Группа дилеров {group_id} не найдена"
            if group_id is not None
            else "Группа дилеров не найдена"
        )
        super().__init__(msg)


class InvalidDealerGroupError(DomainError):
    """Domain validation failed for a dealer group."""


class DealerGroupAlreadyExistsError(DomainError):
    def __init__(self, name: str):
        super().__init__(f"Группа дилеров с именем '{name}' уже существует")
        self.name = name


class LeasingCompanyNotFoundError(DomainError):
    def __init__(self, leasing_company_id: UUID | None = None):
        msg = (
            f"Лизинговая компания {leasing_company_id} не найдена"
            if leasing_company_id is not None
            else "Лизинговая компания не найдена"
        )
        super().__init__(msg)


class DistributorNotFoundError(DomainError):
    def __init__(self, distributor_id: UUID | None = None):
        msg = (
            f"Дистрибьютор {distributor_id} не найден"
            if distributor_id is not None
            else "Дистрибьютор не найден"
        )
        super().__init__(msg)


class InvalidUploadError(DomainError):
    """Uploaded file failed validation (size / type / empty)."""

    def __init__(self, msg: str = "Некорректный файл"):
        super().__init__(msg)


class BillOfLadingFileNotFoundError(DomainError):
    def __init__(self, file_id: UUID | None = None):
        msg = (
            f"Файл накладной {file_id} не найден"
            if file_id is not None
            else "Файл накладной не найден"
        )
        super().__init__(msg)


class DealerNotFoundError(DomainError):
    def __init__(self, dealer_id: UUID | None = None, msg: str | None = None):
        if msg is not None:
            super().__init__(msg)
            return
        msg = (
            f"Дилер {dealer_id} не найден"
            if dealer_id is not None
            else "Дилер не найден"
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Warehouses / cities / dealer options admin domain (A4)
# ---------------------------------------------------------------------------


class CityNotFoundError(DomainError):
    def __init__(self, city_id: UUID | None = None):
        msg = (
            f"Город {city_id} не найден"
            if city_id is not None
            else "Город не найден"
        )
        super().__init__(msg)


class CityAlreadyExistsError(DomainError):
    def __init__(self, name: str):
        super().__init__(f"Город с названием '{name}' уже существует")
        self.name = name


class InvalidCityError(DomainError):
    """Domain validation failed for a city."""


class WarehouseNotFoundError(DomainError):
    def __init__(self, warehouse_id: UUID | None = None):
        msg = (
            f"Склад {warehouse_id} не найден"
            if warehouse_id is not None
            else "Склад не найден"
        )
        super().__init__(msg)


class InvalidWarehouseError(DomainError):
    """Domain validation failed for a warehouse."""


class WarehouseCascadeConfirmationInvalidError(DomainError):
    def __init__(
        self,
        msg: str = 'Для подтверждения каскадного удаления необходимо ввести "УДАЛИТЬ"',
    ):
        super().__init__(msg)


class WarehouseCascadePreviewStaleError(DomainError):
    def __init__(
        self,
        msg: str = "Данные каталога изменились с момента формирования предпросмотра. Пожалуйста, подтвердите операцию заново.",
    ):
        super().__init__(msg)


class WarehouseCascadeDeleteBlockedError(DomainError):
    def __init__(self, msg: str = "Каскадное удаление склада заблокировано"):
        super().__init__(msg)


class VehicleAlreadyInWarehouseError(DomainError):
    def __init__(self, vehicle_id: UUID, warehouse_id: UUID | None = None):
        if warehouse_id is not None:
            msg = (
                f"Автомобиль {vehicle_id} уже привязан к складу {warehouse_id}"
            )
        else:
            msg = f"Автомобиль {vehicle_id} уже привязан к складу"
        super().__init__(msg)
        self.vehicle_id = vehicle_id
        self.warehouse_id = warehouse_id


class VehicleNotInWarehouseError(DomainError):
    def __init__(self, vehicle_id: UUID | None = None):
        msg = (
            f"Автомобиль {vehicle_id} не привязан к этому складу"
            if vehicle_id is not None
            else "Привязка не найдена"
        )
        super().__init__(msg)


class MarkNotFoundError(DomainError):
    def __init__(self, mark_id: str | None = None):
        msg = (
            f"Марка {mark_id} не найдена"
            if mark_id is not None
            else "Марка не найдена"
        )
        super().__init__(msg)


class DealerOptionNotFoundError(DomainError):
    def __init__(self, option_id: UUID | None = None):
        msg = (
            f"Опция {option_id} не найдена"
            if option_id is not None
            else "Опция не найдена"
        )
        super().__init__(msg)


class DealerOptionAlreadyExistsError(DomainError):
    def __init__(self, name: str):
        super().__init__(f"Опция с названием '{name}' уже существует")
        self.name = name


class InvalidDealerOptionError(DomainError):
    """Domain validation failed for a dealer option."""


# ---------------------------------------------------------------------------
# Client profile / favorites / saved calculations domain (A2)
# ---------------------------------------------------------------------------


class ClientProfileNotFoundError(DomainError):
    def __init__(self, msg: str = "Профиль клиента не найден"):
        super().__init__(msg)


class FavoriteAlreadyExistsError(DomainError):
    def __init__(self, vehicle_id: UUID | None = None):
        msg = (
            f"Автомобиль {vehicle_id} уже в избранном"
            if vehicle_id is not None
            else "Автомобиль уже в избранном"
        )
        super().__init__(msg)
        self.vehicle_id = vehicle_id


class FavoriteNotFoundError(DomainError):
    def __init__(self, vehicle_id: UUID | None = None):
        msg = (
            f"Автомобиль {vehicle_id} не найден в избранном"
            if vehicle_id is not None
            else "Автомобиль не найден в избранном"
        )
        super().__init__(msg)
        self.vehicle_id = vehicle_id


class SavedCalculationNotFoundError(DomainError):
    def __init__(self, calculation_id: UUID | None = None):
        msg = (
            f"Расчёт {calculation_id} не найден"
            if calculation_id is not None
            else "Расчёт не найден"
        )
        super().__init__(msg)
        self.calculation_id = calculation_id


class InvalidPhoneChangeError(DomainError):
    """SMS verification code for phone change is invalid or expired."""

    def __init__(self, msg: str = "Неверный код или код истёк"):
        super().__init__(msg)


class PhoneAlreadyInUseError(DomainError):
    def __init__(
        self,
        msg: str = "Этот номер телефона уже используется другим пользователем",
    ):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Vehicles admin domain (B1)
# ---------------------------------------------------------------------------


class InvalidVehicleError(DomainError):
    """Domain validation failed for a vehicle."""


class VinAlreadyAssignedError(DomainError):
    def __init__(self, vin: str | None = None):
        msg = (
            f"VIN '{vin}' уже назначен другому автомобилю"
            if vin
            else "VIN уже назначен другому автомобилю"
        )
        super().__init__(msg)
        self.vin = vin


class NoAvailableVinsError(DomainError):
    def __init__(self) -> None:
        super().__init__("Нет доступных VIN для этой комплектации")


class ModelNotFoundError(DomainError):
    def __init__(self, model_id: str | None = None):
        msg = (
            f"Модель {model_id} не найдена"
            if model_id is not None
            else "Модель не найдена"
        )
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Featured vehicles admin domain (B1)
# ---------------------------------------------------------------------------


class FeaturedAlreadyExistsError(DomainError):
    def __init__(self, model_id: str | None = None):
        msg = (
            f"Модель {model_id} уже добавлена в избранное"
            if model_id is not None
            else "Модель уже добавлена в избранное"
        )
        super().__init__(msg)
        self.model_id = model_id


class FeaturedNotFoundError(DomainError):
    def __init__(self, featured_id: UUID | None = None):
        msg = (
            f"Запись избранного {featured_id} не найдена"
            if featured_id is not None
            else "Запись избранного не найдена"
        )
        super().__init__(msg)


class InvalidFeaturedReorderError(DomainError):
    """Reorder payload failed domain validation (empty / duplicates / unknown ids)."""


# ---------------------------------------------------------------------------
# Application-vehicles admin domain (B1)
# ---------------------------------------------------------------------------


class ApplicationVehicleNotFoundError(DomainError):
    def __init__(self, application_vehicle_id: UUID | None = None):
        msg = (
            f"Автомобиль заявки {application_vehicle_id} не найден"
            if application_vehicle_id is not None
            else "Автомобиль заявки не найден"
        )
        super().__init__(msg)
        self.application_vehicle_id = application_vehicle_id


class ApplicationVehicleFulfillmentRequiredError(DomainError):
    """Physical reservation requires an explicit stock selection."""

    def __init__(self) -> None:
        super().__init__("Подберите автомобили со склада и сохраните подбор")


class ApplicationVehicleAssignmentError(DomainError):
    """Application vehicle assignment failed a precondition (e.g. no VIN, no vehicle ref)."""


# ---------------------------------------------------------------------------
# Distributor admin domain (B3)
# ---------------------------------------------------------------------------


class DistributorAccessDeniedError(DomainError):
    """Actor is not a distributor (or not the owning distributor) and may
    not access the requested distributor-scoped resource."""

    def __init__(
        self,
        msg: str = "Доступ к ресурсу распределителя запрещён",
    ):
        super().__init__(msg)


class ExcelFormatError(DomainError):
    """Uploaded xlsx file is malformed, empty, or has the wrong shape."""

    def __init__(self, msg: str = "Некорректный формат Excel-файла"):
        super().__init__(msg)


class BulkImportValidationError(DomainError):
    """Pre-flight validation of the bulk import request failed (e.g. file
    too big or too many rows for the synchronous code path)."""

    def __init__(self, msg: str = "Файл превышает допустимый размер"):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Leasing applications domain (Phase 3)
# ---------------------------------------------------------------------------


class ApplicationNotFoundError(DomainError):
    def __init__(self, application_id: uuid.UUID | str | None = None):
        msg = (
            f"Заявка {application_id} не найдена"
            if application_id is not None
            else "Заявка не найдена"
        )
        super().__init__(msg)
        self.application_id = application_id


class InvalidStatusTransitionError(DomainError):
    """Application status transition is not legitimate from current state."""

    def __init__(self, current: str, target: str):
        super().__init__(
            f"Недопустимый переход статуса заявки: {current} → {target}"
        )
        self.current = current
        self.target = target


class ApplicationNotOwnedError(DomainError):
    """Authenticated user does not own / cannot access this application."""

    def __init__(self, msg: str = "Доступ к заявке запрещён"):
        super().__init__(msg)


class ApplicationNotSubmittableError(DomainError):
    """Application cannot transition to submission for a domain reason
    (missing fields, no leasing companies, etc)."""


class DealerAssignmentNotAllowedError(DomainError):
    """A dealer assignment candidate violates an application invariant."""

    def __init__(self, msg: str = "Дилер не может быть назначен на эту заявку"):
        super().__init__(msg)


class EmployeeAssignmentNotAllowedError(DomainError):
    """An employee selection violates an application invariant."""

    def __init__(
        self,
        msg: str = "Сотрудник не может быть назначен на эту заявку",
    ):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Documents domain (Phase 4 — D1)
# ---------------------------------------------------------------------------


class DocumentNotFoundError(DomainError):
    def __init__(self, document_id: UUID | None = None):
        msg = (
            f"Документ {document_id} не найден"
            if document_id is not None
            else "Документ не найден"
        )
        super().__init__(msg)
        self.document_id = document_id


class DocumentAccessDeniedError(DomainError):
    def __init__(self, msg: str = "Нет доступа к документу"):
        super().__init__(msg)


class InvalidDocumentStatusError(DomainError):
    """Document status transition is not legitimate from current state."""

    def __init__(self, current: str, target: str):
        super().__init__(
            f"Недопустимый переход статуса документа: {current} → {target}"
        )
        self.current = current
        self.target = target


class DocumentVersionConflictError(DomainError):
    """Attempted to create a new version while the parent lookup is ambiguous."""

    def __init__(
        self, msg: str = "Конфликт версий документа"
    ):
        super().__init__(msg)


class UnsupportedFileTypeError(DomainError):
    """Uploaded file's content-type is not allowed for this document type."""

    def __init__(
        self,
        content_type: str | None = None,
        allowed: list[str] | None = None,
    ):
        if content_type and allowed:
            msg = (
                f"Тип файла '{content_type}' не разрешён. "
                f"Допустимые: {', '.join(allowed)}"
            )
        else:
            msg = "Недопустимый тип файла"
        super().__init__(msg)
        self.content_type = content_type
        self.allowed = allowed


class FileTooLargeError(DomainError):
    """File size exceeds the limit configured on the document type."""

    def __init__(
        self, size_bytes: int | None = None, max_mb: int | None = None
    ):
        if size_bytes and max_mb:
            msg = (
                f"Размер файла {size_bytes} байт превышает лимит {max_mb} МБ"
            )
        elif max_mb:
            msg = f"Размер файла превышает лимит {max_mb} МБ"
        else:
            msg = "Размер файла превышает допустимый лимит"
        super().__init__(msg)
        self.size_bytes = size_bytes
        self.max_mb = max_mb


class DocumentRecognitionFailedError(DomainError):
    """Recognition provider failed to extract data from the file.

    Only raised when recognition is a hard requirement for the flow; most
    call-sites treat a failed recognition as soft (log, mark status) and
    do not propagate this error — it exists mainly for future use-cases
    that want to abort the upload on failure.
    """

    def __init__(self, msg: str = "Не удалось распознать документ"):
        super().__init__(msg)


class DocumentTypeNotFoundError(DomainError):
    def __init__(self, document_type: str | None = None):
        msg = (
            f"Тип документа '{document_type}' не найден"
            if document_type
            else "Тип документа не найден"
        )
        super().__init__(msg)
        self.document_type = document_type


class SopdTemplateNotFoundError(DomainError):
    def __init__(self) -> None:
        super().__init__("Файл СОПД не найден на сервере")


# ---------------------------------------------------------------------------
# Application documents domain (Phase 4 — D2)
# ---------------------------------------------------------------------------


class ApplicationDocumentNotFoundError(DomainError):
    def __init__(self, application_document_id: UUID | None = None):
        msg = (
            f"Документ заявки {application_document_id} не найден"
            if application_document_id is not None
            else "Документ заявки не найден"
        )
        super().__init__(msg)
        self.application_document_id = application_document_id


class DocumentRequestNotFoundError(DomainError):
    def __init__(self, request_id: UUID | None = None):
        msg = (
            f"Запрос документа {request_id} не найден"
            if request_id is not None
            else "Запрос документа не найден"
        )
        super().__init__(msg)
        self.request_id = request_id


class DocumentRequestAlreadyExistsError(DomainError):
    """Document already requested for (application, LC, document_type)."""

    def __init__(self, document_type: str | None = None):
        msg = (
            f"Запрос документа типа '{document_type}' уже существует"
            if document_type
            else "Запрос документа уже существует"
        )
        super().__init__(msg)
        self.document_type = document_type


class RequirementsUpdateAccessDeniedError(DomainError):
    """Actor cannot update requirements for another LC."""

    def __init__(
        self,
        msg: str = "Обновлять требования можно только для своей ЛК",
    ):
        super().__init__(msg)


class InvalidDocumentReviewError(DomainError):
    """Review payload violates a domain invariant (bad status, etc)."""

    def __init__(self, msg: str = "Некорректные данные ревью документа"):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Leasing LC workflow / status-management domain (Phase 4 — D3)
# ---------------------------------------------------------------------------


class LeasingCompanyAccessDeniedError(DomainError):
    """Authenticated LC user attempted to act on a leasing_company_applications
    row that does not belong to their company."""

    def __init__(self, msg: str = "Заявка не была отправлена в вашу компанию"):
        super().__init__(msg)


class LeasingCompanyApplicationNotFoundError(DomainError):
    def __init__(self, application_id: uuid.UUID | str | None = None):
        msg = (
            f"Связь заявки {application_id} с лизинговой компанией не найдена"
            if application_id is not None
            else "Связь заявки с лизинговой компанией не найдена"
        )
        super().__init__(msg)
        self.application_id = application_id


class InvalidLeasingCompanyApplicationStatusError(DomainError):
    """Per-LC status transition is not legitimate from the current state."""

    def __init__(self, current: str, target: str):
        super().__init__(
            f"Недопустимый переход статуса ЛК: {current} → {target}"
        )
        self.current = current
        self.target = target


class LeasingCompanyBindingNotConfiguredError(DomainError):
    """Authenticated user has role=leasing_company but isn't attached to any
    ``leasing_companies`` row (no ``LeasingCompanyUser``/``company_id`` match)."""

    def __init__(
        self,
        msg: str = "Пользователь не привязан к лизинговой компании",
    ):
        super().__init__(msg)


class RejectReasonRequiredError(DomainError):
    """LC reject must carry a human-readable reason (mirrors Express)."""

    def __init__(self, msg: str = "Причина отклонения обязательна"):
        super().__init__(msg)


class RequestedDocumentsRequiredError(DomainError):
    """LC request-documents must carry a non-empty list of document types."""

    def __init__(
        self,
        msg: str = "Необходимо указать список запрашиваемых документов",
    ):
        super().__init__(msg)


class StatusHistoryNotFoundError(DomainError):
    def __init__(
        self, msg: str = "История изменений статуса не найдена"
    ):
        super().__init__(msg)


class LeasingProposalNotFoundError(DomainError):
    def __init__(self, proposal_id: UUID | None = None):
        msg = (
            f"КП {proposal_id} не найдено"
            if proposal_id is not None
            else "КП не найдено"
        )
        super().__init__(msg)
        self.proposal_id = proposal_id


class IncompleteProposalError(DomainError):
    """Approve requires at least one fully-filled commercial proposal."""

    def __init__(
        self,
        msg: str = "Одобрение возможно только при наличии заполненного КП",
    ):
        super().__init__(msg)


class LeasingProposalNotSubmittedError(DomainError):
    """Client tried to act on a КП the LC hasn't actually issued yet."""

    def __init__(
        self,
        msg: str = "КП ещё не отправлено клиенту",
    ):
        super().__init__(msg)


class LeasingProposalAlreadyDecidedError(DomainError):
    """Client tried to accept/reject a КП that already has a decision."""

    def __init__(
        self,
        msg: str = "Решение по КП уже принято",
    ):
        super().__init__(msg)


class ResponseAlreadySubmittedError(DomainError):
    """LC tried to mutate a response that has already been finalised."""

    def __init__(
        self,
        msg: str = "Ответ уже отправлен клиенту и не может быть изменён",
    ):
        super().__init__(msg)


class ResponsePdfMissingError(DomainError):
    """Tried to download/remove a response PDF that wasn't uploaded."""

    def __init__(self, msg: str = "PDF-ответ не загружен"):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Shopping cart domain (Phase 5 — E1)
# ---------------------------------------------------------------------------


class CartItemNotFoundError(DomainError):
    def __init__(self, vehicle_id: UUID | None = None):
        msg = (
            f"Автомобиль {vehicle_id} не найден в корзине"
            if vehicle_id is not None
            else "Автомобиль не найден в корзине"
        )
        super().__init__(msg)
        self.vehicle_id = vehicle_id


class InvalidCartQuantityError(DomainError):
    def __init__(
        self, msg: str = "Количество должно быть минимум 1"
    ):
        super().__init__(msg)


class CartCustomPriceDeniedError(DomainError):
    def __init__(
        self,
        msg: str = "Изменение цены доступно только дилерам и сотрудникам",
    ):
        super().__init__(msg)


class GuestCartTransferConflictError(DomainError):
    def __init__(self, transfer_id: UUID):
        super().__init__(
            f"Операция переноса корзины {transfer_id} уже использована "
            "с другим содержимым"
        )
        self.transfer_id = transfer_id


# ---------------------------------------------------------------------------
# Exchange domain (Phase 5 — E2)
# ---------------------------------------------------------------------------


class ExchangeRequestNotFoundError(DomainError):
    def __init__(self, request_id: UUID | None = None):
        msg = (
            f"Заявка биржи {request_id} не найдена"
            if request_id is not None
            else "Заявка биржи не найдена"
        )
        super().__init__(msg)
        self.request_id = request_id


class ExchangeRequestAccessDeniedError(DomainError):
    def __init__(self, msg: str = "Нет доступа к заявке биржи"):
        super().__init__(msg)


class InvalidExchangeRequestStatusError(DomainError):
    """Exchange request status does not allow the requested operation."""

    def __init__(self, msg: str = "Недопустимый статус заявки биржи"):
        super().__init__(msg)


class ExchangeBidNotFoundError(DomainError):
    def __init__(self, bid_id: UUID | None = None):
        msg = (
            f"Ставка биржи {bid_id} не найдена"
            if bid_id is not None
            else "Ставка биржи не найдена"
        )
        super().__init__(msg)
        self.bid_id = bid_id


class ExchangeBidAccessDeniedError(DomainError):
    def __init__(self, msg: str = "Нет доступа к ставке биржи"):
        super().__init__(msg)


class InvalidBidStatusError(DomainError):
    """Bid KP status does not allow the requested operation."""

    def __init__(self, msg: str = "Недопустимый статус ставки"):
        super().__init__(msg)


class BidAlreadyAcceptedError(DomainError):
    def __init__(self) -> None:
        super().__init__("По заявке биржи уже принята другая ставка")


class BidAlreadyExistsError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "Вы уже сделали ставку на эту заявку. Используйте обновление."
        )


class ExchangeCartItemNotFoundError(DomainError):
    def __init__(self, item_id: uuid.UUID | None = None):
        msg = (
            f"Элемент корзины биржи {item_id} не найден"
            if item_id is not None
            else "Элемент корзины биржи не найден"
        )
        super().__init__(msg)
        self.item_id = item_id


class ExchangeCartEmptyError(DomainError):
    def __init__(self) -> None:
        super().__init__("Корзина биржи пуста")


# ---------------------------------------------------------------------------
# Dealer invite / LC-side application editing (Phase 5 — E3)
# ---------------------------------------------------------------------------


class DealerInviteError(DomainError):
    """Dealer invite flow failed a domain precondition (bad phone, etc.)."""

    def __init__(self, msg: str = "Не удалось отправить приглашение клиенту"):
        super().__init__(msg)


class ApplicationNotEditableError(DomainError):
    """Attempted to update a leasing application that is not in ``draft`` state."""

    def __init__(
        self,
        msg: str = "Можно редактировать только черновики заявок",
    ):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Reports domain (Phase 6 — F1)
# ---------------------------------------------------------------------------


class ReportsAccessDeniedError(DomainError):
    """Authenticated user may not access the requested report."""

    def __init__(self, msg: str = "Доступ к отчёту запрещён"):
        super().__init__(msg)


class InvalidReportTypeError(DomainError):
    """Unknown / unsupported report type."""

    def __init__(self, report_type: str | None = None):
        msg = (
            f"Неизвестный тип отчёта: {report_type}"
            if report_type
            else "Неизвестный тип отчёта"
        )
        super().__init__(msg)
        self.report_type = report_type


class InvalidExportFormatError(DomainError):
    """Unknown / unsupported export format."""

    def __init__(self, export_format: str | None = None):
        msg = (
            f"Неизвестный формат экспорта: {export_format}"
            if export_format
            else "Неизвестный формат экспорта"
        )
        super().__init__(msg)
        self.export_format = export_format


class InvalidDateRangeError(DomainError):
    """Date range payload failed validation (from > to, non-tz-aware, etc)."""

    def __init__(self, msg: str = "Некорректный период"):
        super().__init__(msg)


class DistributorScopeMissingError(DomainError):
    """Authenticated user has role=distributor but no distributor binding."""

    def __init__(
        self,
        msg: str = "Пользователь не привязан к дистрибьютору",
    ):
        super().__init__(msg)


class DealerAlreadyLinkedError(DomainError):
    """Dealer company is already linked to a distributor."""

    def __init__(self, msg: str = "Дилер уже привязан к другому дистрибьютору"):
        super().__init__(msg)


class DistributorDealerLinkNotFoundError(DomainError):
    """Distributor-dealer relationship does not exist."""

    def __init__(self, msg: str = "Связь дистрибьютор–дилер не найдена"):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Admin residual domain (Phase 6 — F2)
# ---------------------------------------------------------------------------


class InvalidRoleError(DomainError):
    """Requested user role is not one of the supported values."""

    def __init__(self, role: str | None = None):
        msg = (
            f"Недопустимая роль пользователя: {role}"
            if role
            else "Недопустимая роль пользователя"
        )
        super().__init__(msg)
        self.role = role


class UserEmailAlreadyExistsError(DomainError):
    """Another user already owns this email address."""

    def __init__(self, email: str | None = None):
        msg = (
            f"Пользователь с email '{email}' уже существует"
            if email
            else "Пользователь с таким email уже существует"
        )
        super().__init__(msg)
        self.email = email


class CompanyAlreadyExistsError(DomainError):
    """Another company already owns this INN."""

    def __init__(self, inn: str | None = None):
        msg = (
            f"Компания с ИНН '{inn}' уже существует"
            if inn
            else "Компания с таким ИНН уже существует"
        )
        super().__init__(msg)
        self.inn = inn


class InvalidCompanyTypeError(DomainError):
    """Requested company_type is not one of the supported values."""

    def __init__(self, company_type: str | None = None):
        msg = (
            f"Недопустимый тип компании: {company_type}"
            if company_type
            else "Недопустимый тип компании"
        )
        super().__init__(msg)
        self.company_type = company_type


class ApplicationCreateIdempotencyConflictError(DomainError):
    """A create key is busy or already identifies a different request."""


class InvalidInnError(DomainError):
    """INN failed syntactic validation (wrong length / non-digits)."""

    def __init__(self, inn: str | None = None):
        msg = (
            f"Некорректный ИНН: {inn}"
            if inn
            else "Некорректный ИНН"
        )
        super().__init__(msg)
        self.inn = inn


class ApplicationLcAssignmentNotAllowedError(DomainError):
    """Current application status does not allow LC assignment."""

    def __init__(self, status: str | None = None):
        msg = (
            f"Нельзя назначить ЛК на заявку в статусе '{status}'"
            if status
            else "Нельзя назначить ЛК на заявку"
        )
        super().__init__(msg)
        self.status = status


# ---------------------------------------------------------------------------
# Companies self-service + carcraft_employee writes (Phase 7a — G4)
# ---------------------------------------------------------------------------


class CompanyHasNoInnError(DomainError):
    """Company has no INN and cannot be enriched or used for profile export."""

    def __init__(self, msg: str = "ИНН компании не указан"):
        super().__init__(msg)


class InvalidCompanyPayloadError(DomainError):
    """Company update / create payload failed a domain invariant."""

    def __init__(
        self, msg: str = "Некорректные данные компании"
    ):
        super().__init__(msg)


class CompanyAlreadyDeactivatedError(DomainError):
    def __init__(self, msg: str = "Компания уже деактивирована"):
        super().__init__(msg)


class CompanySpecialEquipmentConflictError(DomainError):
    """An active special-equipment seller cannot be deactivated."""

    def __init__(
        self,
        msg: str = (
            "Нельзя деактивировать компанию-продавца: есть опубликованная "
            "или участвующая в активных операциях спецтехника"
        ),
    ) -> None:
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Dealer self-service profile + inventory (Phase 7a — G4)
# ---------------------------------------------------------------------------


class DealerRoleRequiredError(DomainError):
    def __init__(self, msg: str = "Доступ разрешён только дилерам"):
        super().__init__(msg)


class InvalidDealerProfilePayloadError(DomainError):
    """Dealer profile update payload failed a domain invariant."""

    def __init__(self, msg: str = "Некорректные данные профиля дилера"):
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Client 2FA shim (Phase 7a — G4)
# ---------------------------------------------------------------------------


class Invalid2FAActionError(DomainError):
    """Client 2FA action is not one of the supported values."""

    def __init__(self, action: str | None = None):
        msg = (
            f"Недопустимое действие 2FA: {action}"
            if action
            else "Недопустимое действие 2FA"
        )
        super().__init__(msg)
        self.action = action
