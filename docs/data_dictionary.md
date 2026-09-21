# Словарь данных

## companies
Корневая организация. `id UUID` — PK, обязателен, пример `...`; `name TEXT` — уникальное имя, обязательно, пример «Подрядчик»; `inn TEXT` — ИНН, необязательно.

## documents
Импортированный документ. `id UUID` PK; `company_id UUID` обязателен, FK и индекс; `kind TEXT` — `vor|schedule`; `original_filename TEXT` — исходное имя; `stored_path TEXT` — путь источника; `sha256 CHAR(64)` — контрольная сумма; `uploaded_at TIMESTAMP` — время импорта; `meta JSON` — дополнительные метаданные. Уникальность `(company_id, sha256)`.

## value_sources
Источник значения. `id UUID` PK; `company_id UUID` обязателен/индекс; `source_type TEXT` — тип источника; `document_id UUID` — документ; `sheet TEXT` — лист; `cell_or_range TEXT` — ячейка/диапазон, пример `D11`; `row_no INT` — строка; `confidence TEXT` — статус достоверности; `note TEXT` — пояснение.

## value_refs
Связь значения сущности с источником. `id UUID` PK; `company_id UUID` обязателен/индекс; `entity_name TEXT` — таблица/сущность; `entity_id UUID` — идентификатор; `field_name TEXT` — поле, пример `quantity`; `source_id UUID` — FK на `value_sources`.

## reference_rates
Глобальные датированные ставки. `id UUID` PK; `rate_type TEXT` — тип; `value NUMERIC(12,6)` — ставка; `valid_from DATE` — начало действия; `valid_to DATE` — конец или NULL; `document_number TEXT` и `document_date DATE` — нормативный источник. Уникальность `(rate_type, valid_from)`.

## contracts
Контракт. `id UUID` PK; `company_id UUID` обязателен/индекс; `contract_type TEXT`; `number TEXT`; `price_is_final BOOL`; `advance_pct NUMERIC`; `payment_delay_days INT`; `security_amount NUMERIC`; `warranty_retention_pct NUMERIC`; `treasury_account BOOL`; `currency CHAR(3)`, пример `RUB`; `vat_rate_id UUID` — ссылка на ставку. Неизвестные условия остаются NULL.

## objects
Объект строительства. `id UUID` PK; `company_id UUID` обязателен/индекс; `contract_id UUID`; `name TEXT` — техническое или подтверждённое имя; `object_type TEXT`; `location_text TEXT`. Уникальность `(company_id, name)`.

## work_items
Позиция ведомости. `id UUID` PK; `company_id UUID` обязателен/индекс; `object_id UUID`; `contract_id UUID`; `position_no INT`; `name TEXT`; `unit TEXT`; `quantity NUMERIC(18,4)`; `price_gross NUMERIC(18,4)`; `amount_gross NUMERIC(18,2)`; `vat_rate NUMERIC(9,6)`; `document_id UUID`; `source_id UUID`; `valid_from DATE`; `valid_to DATE`; `superseded_by UUID`; `replace_reason TEXT`. Текущая версия имеет `valid_to IS NULL`.

## schedule_tasks
Строка календарного графика. `id UUID` PK; `company_id UUID` обязателен/индекс; `object_id UUID`; `position_no INT`; `name TEXT`; `front TEXT`; `unit TEXT`; `quantity NUMERIC(18,4)`; `start_on/end_on DATE`; `days INT`; `crew_size NUMERIC(9,2)`; `amount NUMERIC(18,2)`; `period_volumes JSON`; `source_id UUID`.

## schedule_notes
Текстовая предпосылка графика. `id UUID` PK; `company_id UUID` обязателен/индекс; `object_id UUID`; `note_type TEXT`; `text TEXT`; `parsed JSON`; `cell TEXT`; `source_id UUID`.

## value_confirmations
Неизменяемый журнал подтверждений. `id UUID` PK; `company_id UUID` обязателен/индекс; `entity_name TEXT`; `entity_id UUID`; `field_name TEXT`; `action TEXT`, пример `imported|replaced`; `old_value/new_value TEXT`; `reason TEXT`; `actor TEXT`; `acted_at TIMESTAMP`.
