"""Unit tests for special equipment catalog cascade delete pure domain logic."""

import uuid

import pytest

from domain.special_equipment_cascade_delete import (
    CASCADE_CONFIRMATION_INVALID,
    CASCADE_TOO_LARGE,
    CONFIRMATION_WORD,
    CascadeConfirmationInvalidError,
    CascadeGraphSnapshot,
    CascadeTooLargeError,
    DistributorBlocker,
    EntityRef,
    ProductBlockerDocument,
    SupportProgramBlocker,
    SupportProgramBlockerReference,
    build_cascade_plan,
    compute_preview_token,
    ensure_confirmation,
    validate_confirmation,
)


def test_validate_confirmation() -> None:
    assert validate_confirmation(CONFIRMATION_WORD) is True
    assert validate_confirmation("  УДАЛИТЬ  ") is True
    assert validate_confirmation("удалить") is False
    assert validate_confirmation("DELETE") is False
    assert validate_confirmation("УДАЛИТЬ ") is True
    assert validate_confirmation("УДАЛИТЬ_") is False

    ensure_confirmation(CONFIRMATION_WORD)
    with pytest.raises(CascadeConfirmationInvalidError) as exc_info:
        ensure_confirmation("wrong")
    assert exc_info.value.code == CASCADE_CONFIRMATION_INVALID


def test_preview_token_determinism_and_change_detection() -> None:
    root = EntityRef(type="mark", id=uuid.uuid4(), name="Test Mark")
    graph = CascadeGraphSnapshot()
    graph.marks[root.id] = root

    plan1 = build_cascade_plan(root, graph)
    plan2 = build_cascade_plan(root, graph)

    token1 = compute_preview_token(plan1, catalog_revision=1)
    token2 = compute_preview_token(plan2, catalog_revision=1)
    assert token1 == token2
    assert len(token1) == 64

    # Revision change modifies token
    token_rev2 = compute_preview_token(plan1, catalog_revision=2)
    assert token_rev2 != token1

    # Adding a model modifies token
    model_id = uuid.uuid4()
    graph.add_model(model_id, mark_id=root.id, name="Model 1")
    plan3 = build_cascade_plan(root, graph)
    token3 = compute_preview_token(plan3, catalog_revision=1)
    assert token3 != token1


def test_mark_cascade_complete_hierarchy() -> None:
    graph = CascadeGraphSnapshot()
    mark_id = uuid.uuid4()
    mark_ref = graph.add_mark(mark_id, code="mark_1", name="Mark 1")

    model_id = uuid.uuid4()
    graph.add_model(model_id, mark_id=mark_id, code="model_1", name="Model 1")

    mod_id = uuid.uuid4()
    graph.add_modification(mod_id, model_id=model_id, code="mod_1", name="Mod 1")
    graph.modification_attribute_values[mod_id] = {uuid.uuid4(): uuid.uuid4()}

    trim_id = uuid.uuid4()
    graph.add_trim(trim_id, modification_id=mod_id, code="trim_1", name="Trim 1")
    graph.trim_attribute_values[trim_id] = {uuid.uuid4(): uuid.uuid4()}

    prod_id = uuid.uuid4()
    graph.add_product(prod_id, modification_id=mod_id, trim_id=trim_id, code="prod_1")

    # Clear references on warehouses
    graph.warehouse_mark_counts[mark_id] = 2
    graph.warehouse_access_rule_mark_counts[mark_id] = 1

    # Blockers
    distributor_company = {"id": uuid.uuid4(), "name": "Distributor LLC", "inn": "7700000000"}
    graph.distributor_blockers_by_mark[mark_id] = [DistributorBlocker(company=distributor_company)]

    sp_ref = SupportProgramBlockerReference(type="mark", id=mark_id, name="Mark 1")
    graph.support_program_blockers.append(
        SupportProgramBlocker(program={"id": uuid.uuid4(), "name": "Subsidy 2026"}, references=[sp_ref])
    )

    doc = ProductBlockerDocument(type="application", id=uuid.uuid4(), number="APP-001", status="active")
    graph.product_blockers_by_product[prod_id] = [doc]

    # User impact
    graph.product_cart_counts[prod_id] = 3
    graph.product_favorite_counts[prod_id] = 5

    plan = build_cascade_plan(mark_ref, graph)

    assert plan.counts["marks"] == 1
    assert plan.counts["models"] == 1
    assert plan.counts["modifications"] == 1
    assert plan.counts["trims"] == 1
    assert plan.counts["products"] == 1
    assert plan.attribute_values_to_delete_count == 2  # 1 mod val + 1 trim val

    # Verify clears
    clear_fields = {(c.type, c.field): c.count for c in plan.clear}
    assert clear_fields[("warehouse", "mark_id")] == 2
    assert clear_fields[("warehouse_access_rule", "mark_id")] == 1

    # Verify user impact
    assert plan.user_impact.cart_items == 3
    assert plan.user_impact.favorites == 5

    # Verify blockers
    assert len(plan.blockers.distributors) == 1
    assert plan.blockers.distributors[0].company["inn"] == "7700000000"
    assert len(plan.blockers.support_programs) == 1
    assert len(plan.blockers.products) == 1
    assert plan.blockers.products[0].documents[0].number == "APP-001"


def test_model_cascade() -> None:
    graph = CascadeGraphSnapshot()
    mark_id = uuid.uuid4()
    graph.add_mark(mark_id, name="Mark")
    model_id = uuid.uuid4()
    model_ref = graph.add_model(model_id, mark_id=mark_id, name="Model")

    mod_id = uuid.uuid4()
    graph.add_modification(mod_id, model_id=model_id, name="Mod")
    prod_id = uuid.uuid4()
    graph.add_product(prod_id, modification_id=mod_id, name="Product")

    plan = build_cascade_plan(model_ref, graph)

    assert plan.counts["marks"] == 0
    assert plan.counts["models"] == 1
    assert plan.counts["modifications"] == 1
    assert plan.counts["products"] == 1


def test_modification_cascade() -> None:
    graph = CascadeGraphSnapshot()
    mod_id = uuid.uuid4()
    mod_ref = graph.add_modification(mod_id, model_id=uuid.uuid4(), name="Mod")
    trim_id = uuid.uuid4()
    graph.add_trim(trim_id, modification_id=mod_id, name="Trim")
    prod_id = uuid.uuid4()
    graph.add_product(prod_id, modification_id=mod_id, name="Product")

    plan = build_cascade_plan(mod_ref, graph)

    assert plan.counts["models"] == 0
    assert plan.counts["modifications"] == 1
    assert plan.counts["trims"] == 1
    assert plan.counts["products"] == 1


def test_trim_cascade_does_not_delete_product() -> None:
    graph = CascadeGraphSnapshot()
    trim_id = uuid.uuid4()
    trim_ref = graph.add_trim(trim_id, modification_id=uuid.uuid4(), name="Trim")
    prod_id = uuid.uuid4()
    graph.add_product(prod_id, trim_id=trim_id, name="Product")

    # Add attribute value on trim
    attr_id = uuid.uuid4()
    graph.trim_attribute_values[trim_id] = {attr_id: uuid.uuid4()}

    plan = build_cascade_plan(trim_ref, graph)

    assert plan.counts["trims"] == 1
    assert plan.counts["products"] == 0  # Products are NOT deleted
    assert plan.attribute_values_to_delete_count == 1

    assert len(plan.clear) == 1
    assert plan.clear[0].type == "product"
    assert plan.clear[0].field == "trim_id"
    assert plan.clear[0].count == 1


def test_color_cascade_clears_fields() -> None:
    graph = CascadeGraphSnapshot()
    color_id = uuid.uuid4()
    color_ref = graph.add_color(color_id, code="c_red", name="Red")

    p1 = uuid.uuid4()
    p2 = uuid.uuid4()
    graph.add_product(p1, body_color_id=color_id)
    graph.add_product(p2, interior_color_id=color_id)

    plan = build_cascade_plan(color_ref, graph)

    assert plan.counts["colors"] == 1
    assert plan.counts["products"] == 0

    clear_fields = {(c.type, c.field): c.count for c in plan.clear}
    assert clear_fields[("product", "body_color_id")] == 1
    assert clear_fields[("product", "interior_color_id")] == 1


def test_attribute_group_cascade_clears_group_ids() -> None:
    graph = CascadeGraphSnapshot()
    group_id = uuid.uuid4()
    group_ref = graph.add_attribute_group(group_id, name="Engine specs")

    a1 = uuid.uuid4()
    graph.add_attribute(a1, group_id=group_id, name="Horsepower")

    cat_id = uuid.uuid4()
    graph.category_attribute_group_ids[(cat_id, a1)] = group_id
    trim_id = uuid.uuid4()
    graph.trim_attribute_group_ids[(trim_id, a1)] = group_id

    plan = build_cascade_plan(group_ref, graph)

    assert plan.counts["attribute_groups"] == 1
    assert plan.counts["attributes"] == 0  # Attributes NOT deleted

    clear_types = {(c.type, c.field): c.count for c in plan.clear}
    assert clear_types[("attribute", "attribute_group_id")] == 1
    assert clear_types[("category_attribute", "group_id")] == 1
    assert clear_types[("trim_attribute", "group_id")] == 1


def test_attribute_and_option_cascade() -> None:
    graph = CascadeGraphSnapshot()
    attr_id = uuid.uuid4()
    attr_ref = graph.add_attribute(attr_id, name="Transmission")
    opt1 = uuid.uuid4()
    opt2 = uuid.uuid4()
    graph.add_option(opt1, attribute_id=attr_id, name="Manual")
    graph.add_option(opt2, attribute_id=attr_id, name="Automatic")

    mod_id = uuid.uuid4()
    graph.modification_attribute_values[mod_id] = {attr_id: opt1}
    trim_id = uuid.uuid4()
    graph.trim_attribute_values[trim_id] = {attr_id: opt2}

    # Cascade attribute -> deletes options and attribute values
    plan_attr = build_cascade_plan(attr_ref, graph)
    assert plan_attr.counts["attributes"] == 1
    assert plan_attr.counts["options"] == 2
    assert plan_attr.attribute_values_to_delete_count == 2

    # Cascade option -> deletes only values where option is selected; attribute stays
    opt1_ref = graph.options[opt1]
    plan_opt = build_cascade_plan(opt1_ref, graph)
    assert plan_opt.counts["attributes"] == 0
    assert plan_opt.counts["options"] == 1
    assert plan_opt.attribute_values_to_delete_count == 1  # only mod_id has opt1


def test_category_orphan_diamond_graph() -> None:
    r"""Diamond graph:

         Root
        /    \
      Cat1   Cat2
        \    /
        ChildK
    """
    graph = CascadeGraphSnapshot()
    root_id = uuid.uuid4()
    graph.add_category(root_id, name="Root")
    c1_id = uuid.uuid4()
    graph.add_category(c1_id, parent_ids=[root_id], name="Cat1")
    c2_id = uuid.uuid4()
    graph.add_category(c2_id, parent_ids=[root_id], name="Cat2")
    child_k_id = uuid.uuid4()
    graph.add_category(child_k_id, parent_ids=[c1_id, c2_id], name="ChildK")

    # 1. Delete C1: C2 is still a parent of ChildK -> ChildK stays
    plan_c1 = build_cascade_plan(graph.categories[c1_id], graph)
    assert plan_c1.counts["categories"] == 1
    assert [c.id for c in plan_c1.delete["categories"]] == [c1_id]

    # 2. Delete Root: C1 and C2 both become orphans, then ChildK has ALL parents in D -> ChildK deleted too!
    plan_root = build_cascade_plan(graph.categories[root_id], graph)
    assert plan_root.counts["categories"] == 4
    deleted_cat_ids = {c.id for c in plan_root.delete["categories"]}
    assert deleted_cat_ids == {root_id, c1_id, c2_id, child_k_id}


def test_category_orphan_three_level_chain() -> None:
    """Chain: R -> P -> K."""
    graph = CascadeGraphSnapshot()
    r_id = uuid.uuid4()
    graph.add_category(r_id, name="R")
    p_id = uuid.uuid4()
    graph.add_category(p_id, parent_ids=[r_id], name="P")
    k_id = uuid.uuid4()
    graph.add_category(k_id, parent_ids=[p_id], name="K")

    # Deleting P cascades to K
    plan_p = build_cascade_plan(graph.categories[p_id], graph)
    assert plan_p.counts["categories"] == 2
    assert {c.id for c in plan_p.delete["categories"]} == {p_id, k_id}


def test_category_orphan_modifications_and_attribute_consistency() -> None:
    graph = CascadeGraphSnapshot()
    c1_id = uuid.uuid4()
    c2_id = uuid.uuid4()
    attr_c1 = uuid.uuid4()
    attr_c2 = uuid.uuid4()

    graph.add_category(c1_id, attribute_ids=[attr_c1], name="Cat1")
    graph.add_category(c2_id, attribute_ids=[attr_c2], name="Cat2")

    # Modification M1 belongs ONLY to Cat1 -> orphan when Cat1 is deleted -> M1 deleted
    m1_id = uuid.uuid4()
    graph.add_modification(m1_id, model_id=uuid.uuid4(), category_ids=[c1_id], name="M1")
    graph.modification_attribute_values[m1_id] = {attr_c1: uuid.uuid4()}

    # Modification M2 belongs to BOTH Cat1 and Cat2 -> stays when Cat1 is deleted, but unlinked
    m2_id = uuid.uuid4()
    graph.add_modification(m2_id, model_id=uuid.uuid4(), category_ids=[c1_id, c2_id], name="M2")
    # M2 has value for attr_c1 (from Cat1) and attr_c2 (from Cat2)
    graph.modification_attribute_values[m2_id] = {
        attr_c1: uuid.uuid4(),
        attr_c2: uuid.uuid4(),
    }

    plan = build_cascade_plan(graph.categories[c1_id], graph)

    # M1 deleted
    assert plan.counts["modifications"] == 1
    assert plan.delete["modifications"][0].id == m1_id

    # M2 stayed, unlinked from Cat1
    assert any(u.type == "modification_category" for u in plan.unlink)

    # In M2, attr_c1 is outside remaining effective set {attr_c2} -> pruned!
    # Attribute values deleted: 1 from M1 (deleted mod) + 1 pruned from M2 = 2
    assert plan.attribute_values_to_delete_count == 2


def test_composite_product_cascade() -> None:
    graph = CascadeGraphSnapshot()
    component_id = uuid.uuid4()
    composite_id = uuid.uuid4()
    super_composite_id = uuid.uuid4()

    c_ref = graph.add_product(component_id, name="Bucket attachment")
    graph.add_product(composite_id, name="Excavator with bucket")
    graph.add_product(super_composite_id, name="Fleet set")

    graph.add_composite(composite_id, component_ids=[component_id])
    graph.add_composite(super_composite_id, component_ids=[composite_id])

    # 1. Component deleted -> recursively composite and super_composite are deleted!
    plan_comp = build_cascade_plan(c_ref, graph)
    assert plan_comp.counts["products"] == 3
    deleted_pids = {p.id for p in plan_comp.delete["products"]}
    assert deleted_pids == {component_id, composite_id, super_composite_id}

    # 2. Composite deleted directly -> component stays!
    comp_ref = graph.products[composite_id]
    plan_composite_direct = build_cascade_plan(comp_ref, graph)
    assert plan_composite_direct.counts["products"] == 2  # composite and super_composite
    assert component_id not in {p.id for p in plan_composite_direct.delete["products"]}
    assert any(u.type == "product_component" for u in plan_composite_direct.unlink)


def test_cascade_too_large_flag_and_raise() -> None:
    graph = CascadeGraphSnapshot()
    root = graph.add_mark(uuid.uuid4(), name="Big Mark")
    # Add 10 models
    for _ in range(10):
        graph.add_model(uuid.uuid4(), mark_id=root.id)

    # With max_rows = 5, total affected = 11 > 5
    plan = build_cascade_plan(root, graph, max_rows=5)
    assert plan.is_too_large is True
    assert plan.total_affected == 11

    with pytest.raises(CascadeTooLargeError) as exc_info:
        build_cascade_plan(root, graph, max_rows=5, raise_on_too_large=True)
    assert exc_info.value.code == CASCADE_TOO_LARGE
    assert exc_info.value.total == 11
    assert exc_info.value.max_rows == 5
