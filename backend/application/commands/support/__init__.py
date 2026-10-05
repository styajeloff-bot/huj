"""Support-program admin commands."""
from application.commands.support.create_dealer_group import (
    CreateDealerGroupCommand,
    DeleteDealerGroupCommand,
    UpdateDealerGroupCommand,
    handle_create_dealer_group,
    handle_delete_dealer_group,
    handle_distributor_can_manage_dealer_groups,
    handle_update_dealer_group,
)
from application.commands.support.create_support_program import (
    CreateSupportProgramCommand,
    handle_create_support_program,
)
from application.commands.support.delete_support_program import (
    DeleteBillOfLadingCommand,
    DeleteSupportProgramCommand,
    handle_delete_bill_of_lading,
    handle_delete_support_program,
)
from application.commands.support.patch_support_program import (
    PatchSupportProgramCommand,
    handle_patch_support_program,
)
from application.commands.support.update_support_program import (
    UpdateSupportProgramCommand,
    handle_update_support_program,
)
from application.commands.support.upload_bill_of_lading import (
    UploadBillOfLadingCommand,
    UploadedBillOfLadingFile,
    handle_upload_bill_of_lading,
)
from application.commands.support.upsert_dealer_group import (
    UpsertDealerGroupCommand,
    UpsertDealerGroupResult,
    handle_upsert_dealer_group,
)

__all__ = [
    "CreateDealerGroupCommand",
    "CreateSupportProgramCommand",
    "DeleteBillOfLadingCommand",
    "DeleteDealerGroupCommand",
    "DeleteSupportProgramCommand",
    "PatchSupportProgramCommand",
    "UpdateDealerGroupCommand",
    "UpdateSupportProgramCommand",
    "UploadBillOfLadingCommand",
    "UploadedBillOfLadingFile",
    "UpsertDealerGroupCommand",
    "UpsertDealerGroupResult",
    "handle_create_dealer_group",
    "handle_create_support_program",
    "handle_delete_bill_of_lading",
    "handle_delete_dealer_group",
    "handle_delete_support_program",
    "handle_distributor_can_manage_dealer_groups",
    "handle_patch_support_program",
    "handle_update_dealer_group",
    "handle_update_support_program",
    "handle_upload_bill_of_lading",
    "handle_upsert_dealer_group",
]
