# Data dictionary

`companies` — корень компании.  
`documents` — импортированные документы и SHA-256.  
`value_sources`, `value_refs` — происхождение значений.  
`reference_rates` — датированные ставки.  
`contracts`, `objects` — договор и объект.  
`work_items` — версионируемые позиции ВОР.  
`schedule_tasks`, `schedule_notes` — календарный график и предпосылки.  
`value_confirmations` — append-only журнал подтверждений и замен.

Все tenant-domain таблицы имеют индексированный `company_id`. `companies` — корень, а `reference_rates` —
глобальный справочник согласно заданной схеме.
