CLI-скрипт scripts/leasing_seed_workbook.py, у него два режима:

- template — создаёт .xlsx шаблон;
- sql — читает заполненный .xlsx и генерирует .sql для companies, users, leasing_companies, leasing_applications, leasing_company_applications, application_vehicles, application_groups,
  leasing_applications_groups.

Готовый шаблон уже сгенерирован здесь: scripts/leasing_seed_template.xlsx. В нём листы clients, leasing_companies, groups, applications, vehicles и README с пояснениями по колонкам.

Как запускать:

.venv/bin/python scripts/leasing_seed_workbook.py template --output scripts/leasing_seed_template.xlsx
.venv/bin/python scripts/leasing_seed_workbook.py sql --input scripts/leasing_seed_template.xlsx --output /tmp/leasing_seed.sql

CLI-скрипт scripts/dadata_inn_export.py:

- читает `.txt` файл со списком ИНН, по одному на строку;
- делает запрос в DaData по каждому ИНН;
- сохраняет `.tsv` файл с колонками `ИНН`, `Название компании`, `ФИО генерального директора`.

Как запускать:

.venv/bin/python scripts/dadata_inn_export.py --input /tmp/inn.txt --output /tmp/companies.tsv
