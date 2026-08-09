from datetime import timedelta

from odoo import fields  # noqa: F821 — provided by odoo shell

CODE = 'HTPLUS-E2E'
today = fields.Date.today()

Factory = env['htplus.factory']  # noqa: F821
Plant = env['htplus.plant']
Line = env['htplus.line']
Machine = env['htplus.machine']
WC = env['mrp.workcenter']
Product = env['product.product']
Bom = env['mrp.bom']
Template = env['htplus.shift.template']
Employee = env['hr.employee']
Demand = env['htplus.demand.plan']

factory = Factory.search([('code', '=', CODE)], limit=1)
if not factory:
    factory = Factory.create({'name': 'HTPlus E2E Factory', 'code': CODE})
plant = Plant.search([('code', '=', CODE + '-P1')], limit=1) or Plant.create({
    'name': 'Plant 1', 'code': CODE + '-P1', 'factory_id': factory.id,
})
line = Line.search([('code', '=', CODE + '-L1')], limit=1) or Line.create({
    'name': 'Line 1', 'code': CODE + '-L1', 'plant_id': plant.id,
})
wc = WC.search([('code', '=', CODE + '-WC1')], limit=1) or WC.create({
    'name': 'E2E Workcenter', 'code': CODE + '-WC1',
    'factory_id': factory.id, 'plant_id': plant.id, 'line_id': line.id,
})
machine = Machine.search([('code', '=', CODE + '-M1')], limit=1) or Machine.create({
    'name': 'E2E Machine', 'code': CODE + '-M1', 'workcenter_id': wc.id, 'line_id': line.id,
})
factory.action_apply_calendar_to_workcenters()

template = Template.search([('code', '=', CODE + '-DAY')], limit=1) or Template.create({
    'name': 'E2E Day', 'code': CODE + '-DAY', 'shift_type': 'day',
    'start_time': 8.0, 'end_time': 17.0, 'break_minutes': 60,
    'default_manpower': 1, 'factory_id': factory.id, 'plant_id': plant.id, 'line_id': line.id,
})
template.action_sync_to_calendar()

employee = Employee.search([('name', '=', 'HTPlus E2E Operator')], limit=1) or Employee.create({
    'name': 'HTPlus E2E Operator',
})
# Production skill so assignment confirm → MES actual is not blocked
skill_type = env.ref('htplus_planning_base.hr_skill_type_production', raise_if_not_found=False)
skill = env['hr.skill']
if skill_type:
    skill = env['hr.skill'].search([('skill_type_id', '=', skill_type.id)], limit=1)
    if not skill:
        skill = env['hr.skill'].create({
            'name': 'E2E Operator',
            'skill_type_id': skill_type.id,
        })
    level = env['hr.skill.level'].search([('skill_type_id', '=', skill_type.id)], limit=1)
    if not env['hr.employee.skill'].search([
        ('employee_id', '=', employee.id),
        ('skill_id', '=', skill.id),
    ], limit=1):
        vals = {
            'employee_id': employee.id,
            'skill_id': skill.id,
            'skill_type_id': skill_type.id,
        }
        if level:
            vals['skill_level_id'] = level.id
        env['hr.employee.skill'].create(vals)

# Semi + FG products with BOMs (multi-level)
semi = Product.search([('default_code', '=', CODE + '-SEMI')], limit=1)
if not semi:
    semi = Product.create({
        'name': 'E2E Semi', 'default_code': CODE + '-SEMI',
        'type': 'consu', 'is_storable': True,
    })
fg = Product.search([('default_code', '=', CODE + '-FG')], limit=1)
if not fg:
    fg = Product.create({
        'name': 'E2E Finished', 'default_code': CODE + '-FG',
        'type': 'consu', 'is_storable': True,
    })

semi_bom = Bom.search([('product_tmpl_id', '=', semi.product_tmpl_id.id)], limit=1)
if not semi_bom:
    semi_bom = Bom.create({
        'product_tmpl_id': semi.product_tmpl_id.id,
        'product_qty': 1.0,
        'type': 'normal',
        'operation_ids': [(0, 0, {
            'name': 'Semi Op', 'workcenter_id': wc.id, 'time_cycle_manual': 60, 'sequence': 10,
        })],
    })
fg_bom = Bom.search([('product_tmpl_id', '=', fg.product_tmpl_id.id)], limit=1)
if not fg_bom:
    fg_bom = Bom.create({
        'product_tmpl_id': fg.product_tmpl_id.id,
        'product_qty': 1.0,
        'type': 'normal',
        'bom_line_ids': [(0, 0, {'product_id': semi.id, 'product_qty': 2.0})],
        'operation_ids': [(0, 0, {
            'name': 'FG Op', 'workcenter_id': wc.id, 'time_cycle_manual': 90, 'sequence': 10,
        })],
    })

Quants = env['stock.quant']
location = env.ref('stock.stock_location_stock')
Quants._update_available_quantity(semi, location, 100.0)

demand = Demand.create({
    'date_start': today,
    'date_end': today + timedelta(days=7),
    'source': 'manual',
    'line_ids': [(0, 0, {
        'product_id': fg.id,
        'date': today + timedelta(days=5),
        'qty': 10.0,
        'uom_id': fg.uom_id.id,
    })],
})
demand.action_confirm()
demand.action_approve()
action = demand.action_generate_plan()
plan = env['htplus.production.plan'].browse(action['res_id'])
plan.action_confirm()
plan.action_approve()
plan.action_check_materials()
try:
    plan.action_create_productions()
except Exception as err:  # noqa: BLE001
    print('[seed] create_productions warning:', err)
    for line in plan.line_ids.filtered(lambda l: l.state == 'draft'):
        line.material_ok = True
        line.material_note = 'forced for e2e seed'
    plan.action_create_productions()

sched_action = plan.action_create_schedule()
run = env['htplus.schedule.run'].browse(sched_action['res_id'])

env['htplus.production.shift'].search([
    ('line_id', '=', line.id),
    ('state', 'in', ('draft', 'confirmed')),
]).write({'leader_id': employee.id})

try:
    wf_action = run.action_propose_workforce()
    assign_ids = wf_action.get('domain', [[]])[0][2] if wf_action else []
    print('[seed] workforce assignments:', len(assign_ids))
    assignments = env['htplus.workforce.assignment'].browse(assign_ids)
    assignments.write({'employee_id': employee.id})
    assignments.action_confirm()
    print('[seed] mes actuals from assignments:', len(assignments.mapped('actual_id')))
except Exception as err:  # noqa: BLE001
    print('[seed] workforce/mes:', err)

env.cr.commit()
print('[seed] OK factory=%s plan=%s mos=%s schedule=%s wos=%s conflicts=%s' % (
    factory.name, plan.name, len(plan.production_ids), run.name,
    len(run.workorder_ids), run.conflict_count,
))
print('[seed] plan lines (incl. exploded):', plan.line_ids.mapped(lambda l: '%s x %s' % (l.product_id.default_code, l.qty)))
print('[seed] shop floor actuals:', env['htplus.workorder.actual'].search_count([]))
