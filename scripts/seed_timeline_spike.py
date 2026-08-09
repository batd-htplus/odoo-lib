from datetime import datetime, timedelta

DEMO_CODE = "HTPLUS-SPIKE-DEMO"
WORKCENTER_NAMES = ["Spike Line A", "Spike Line B", "Spike Line C", "Spike Line D"]
TARGET_ORDER_COUNT = 8

env.cr.execute("SELECT 1")  # noqa: F821 - fail fast if the shell session is dead

Workcenter = env["mrp.workcenter"]  # noqa: F821
Product = env["product.product"]  # noqa: F821
Bom = env["mrp.bom"]  # noqa: F821
Production = env["mrp.production"]  # noqa: F821
Workorder = env["mrp.workorder"]  # noqa: F821

# --- 1. Work centers ---------------------------------------------------------
workcenters = Workcenter.browse()
for name in WORKCENTER_NAMES:
    wc = Workcenter.search([("name", "=", name)], limit=1)
    if not wc:
        wc = Workcenter.create({"name": name, "capacity_per_hour": 10.0})
    workcenters |= wc
print(f"[seed] work centers: {workcenters.mapped('name')}")

# --- 2. Demo product + BOM ----------------------------------------------------
product = Product.search([("default_code", "=", DEMO_CODE)], limit=1)
if not product:
    product = Product.create({
        "name": "HTPlus Timeline Spike Demo Product",
        "default_code": DEMO_CODE,
        "type": "consu",
        "is_storable": True,
    })
    print(f"[seed] created product {product.display_name}")
else:
    print(f"[seed] reusing product {product.display_name}")

bom = Bom.search([("product_tmpl_id", "=", product.product_tmpl_id.id)], limit=1)
if not bom:
    bom = Bom.create({
        "product_tmpl_id": product.product_tmpl_id.id,
        "product_id": product.id,
        "product_qty": 1.0,
        "type": "normal",
        "operation_ids": [
            (0, 0, {
                "name": f"Op {i + 1} - {wc.name}",
                "workcenter_id": wc.id,
                "time_cycle_manual": 90,  # minutes
                "sequence": (i + 1) * 10,
            })
            for i, wc in enumerate(workcenters)
        ],
    })
    print(f"[seed] created BOM with {len(bom.operation_ids)} operations")
else:
    print(f"[seed] reusing BOM {bom.id} ({len(bom.operation_ids)} operations)")

# --- 3. Production orders + workorders ----------------------------------------
existing = Production.search_count([("product_id", "=", product.id)])
if existing >= TARGET_ORDER_COUNT:
    print(f"[seed] {existing} production orders already exist, skipping creation")
else:
    to_create = TARGET_ORDER_COUNT - existing
    base = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    states_cycle = ["unscheduled", "scheduled", "confirmed", "locked"]

    created = Production.browse()
    for i in range(to_create):
        start = base + timedelta(days=i % 5, hours=(i % 3) * 3)
        production = Production.create({
            "product_id": product.id,
            "product_qty": 10.0,
            "product_uom_id": product.uom_id.id,
            "bom_id": bom.id,
            "date_start": start,
        })
        production.action_confirm()
        created |= production

        cursor = start
        for j, wo in enumerate(production.workorder_ids.sorted("sequence")):
            duration = timedelta(hours=1, minutes=30)
            wo.write({
                "date_start": cursor,
                "date_finished": cursor + duration,
                "schedule_state": states_cycle[(i + j) % len(states_cycle)],
                "line_id": False,
            })
            cursor += duration

    print(f"[seed] created {len(created)} production orders "
          f"({sum(len(p.workorder_ids) for p in created)} work orders)")

env.cr.commit()  # noqa: F821 - odoo shell does not auto-commit
print("[seed] done. Open 'Work Order Timeline (Spike)' to view the result.")
