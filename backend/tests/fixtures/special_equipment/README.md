# Special-equipment XLSX fixtures

`special_equipment_demo_v1.xlsx` is the upload-ready happy-path fixture for
Bitrix task 21808. It uses import mode `APPEND`, policy `ATOMIC`, source code
`demo_special_equipment`, and the seller INN `9718036458` seeded by migration
`001_init`.

Expected preview on a clean Alembic-built database:

| Sheet | Rows |
|---|---:|
| categories | 10 |
| manufacturers | 5 |
| attributes | 9 |
| category_attributes | 18 |
| products | 7 |
| product_categories | 7 |
| product_attribute_values | 63 |
| product_images | 0 |

The preview must contain 119 accepted rows, no issues, 56 `ADD` operations and
63 `SET` operations. Applying it creates seven published special-equipment
products and a five-level category branch. Re-uploading the same fixture with a
new import job is intentionally rejected by `APPEND`; use a `PATCH` or
`FULL_SNAPSHOT` fixture for subsequent synchronization scenarios.
