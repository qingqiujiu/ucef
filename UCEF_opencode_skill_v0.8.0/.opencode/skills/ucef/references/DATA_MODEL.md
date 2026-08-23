# UCEF Data Model Provider

Database/system metadata is authoritative input and is stored separately from AI-discovered business facts.

## Import

```bash
python .opencode/skills/ucef/scripts/ucef.py metadata import --file .ucef/metadata/system-db.json
```

Supported JSON/YAML collections:

```yaml
systems:
  - system_id: SYS-FLIGHT
    name: 机票系统

modules:
  - module_id: MOD-ORDER
    system_id: SYS-FLIGHT
    name: 订单模块

tables:
  - table_id: TABLE-flight_order
    system_id: SYS-FLIGHT
    module_id: MOD-ORDER
    name: flight_order
    comment: 机票订单主表
    columns:
      - name: order_no
        data_type: varchar(64)
        nullable: false
        comment: 订单号
    indexes:
      - name: uk_order_no
        unique: true
        columns: [order_no]

relations:
  - relation_id: REL-order-payment
    kind: FK_OR_LOGICAL
    from: table:TABLE-flight_order
    to: table:TABLE-payment_record

assignments:
  - entity_key: node:NODE-ORDER-SAVE
    system_id: SYS-FLIGHT
    module_id: MOD-ORDER
```

Nested columns/indexes are expanded into first-class catalog entities.

`assignments` can bind an existing Java UCEF entity to a System/Module without changing the technical Fact.

## Truth boundary

Physical metadata such as table name, type, nullability, index columns and uniqueness is not editable as a display override. Re-import corrected authoritative metadata instead.

Business display names, descriptions and entity/module/system classification can be manually overridden in the HTML workbench.
