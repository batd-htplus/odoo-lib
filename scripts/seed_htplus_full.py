from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError

CODE = 'HTPLUS-DEMO'
PASSWORD = 'htplus123'
today = fields.Date.today()
company = env.company

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_or_create(model, domain, vals):
    rec = env[model].search(domain, limit=1)
    if not rec:
        rec = env[model].create(vals)
    return rec


def _cleanup():
    """Remove the transactional records from a previous DEMO run."""
    notes_like = [('notes', 'like', 'HTPLUS-DEMO%')]
    Demand = env['htplus.demand.plan']
    ProductionPlan = env['htplus.production.plan']
    templates = env['htplus.shift.template'].search([('code', 'like', CODE + '%')])
    lines = env['htplus.line'].search([('code', 'like', CODE + '%')])
    wcs = env['mrp.workcenter'].search([('code', 'like', CODE + '%')])

    demands = Demand.search(notes_like)
    plans = ProductionPlan.search(notes_like) | demands.mapped('production_plan_ids')
    for plan in plans:
        for run in plan.schedule_run_ids:
            run.workorder_ids.write({'schedule_run_id': False})
            try:
                run.unlink()
            except Exception:
                pass
        for production in plan.production_ids:
            try:
                production.action_cancel()
            except Exception:
                pass
            try:
                production.unlink()
            except Exception:
                pass
        try:
            plan.unlink()
        except Exception:
            pass
    demands.unlink()

    demo_shifts = env['htplus.production.shift'].search( 
        [('template_id', 'in', templates.ids)])
    demo_wos = env['mrp.workorder'].search([('workcenter_id', 'in', wcs.ids)]) 
    env['htplus.shift.completion'].search([ 
        ('shift_id', 'in', demo_shifts.ids)]).unlink()
    env['htplus.shift.actual'].search([ 
        ('shift_id', 'in', demo_shifts.ids)]).unlink()
    env['htplus.workorder.actual'].search([ 
        ('workorder_id', 'in', demo_wos.ids)]).unlink()
    env['htplus.workforce.assignment'].search([ 
        ('shift_id', 'in', demo_shifts.ids)]).unlink()
    demo_shifts.unlink()


print('[cleanup] done')

# ---------------------------------------------------------------------------
# 1. Factory structure
# ---------------------------------------------------------------------------
Factory = env['htplus.factory'] 
Plant = env['htplus.plant'] 
Line = env['htplus.line'] 
Machine = env['htplus.machine'] 
WC = env['mrp.workcenter'] 

factory = get_or_create('htplus.factory', [('code', '=', CODE)], {
    'name': 'HTPlus Manufacturing VN', 'code': CODE,
})
p1 = get_or_create('htplus.plant', [('code', '=', CODE + '-P1')], {
    'name': 'Plant A — HCMC', 'code': CODE + '-P1', 'factory_id': factory.id,
})
p2 = get_or_create('htplus.plant', [('code', '=', CODE + '-P2')], {
    'name': 'Plant B — Binh Duong', 'code': CODE + '-P2', 'factory_id': factory.id,
})

lines_spec = [
    ('L1', 'Line 1 — SMT / Assembly', p1.id),
    ('L2', 'Line 2 — CNC / Metal', p1.id),
    ('L3', 'Line 3 — Molding', p2.id),
    ('L4', 'Line 4 — Packaging', p2.id),
]
demo_lines = {}
for code, name, plant_id in lines_spec:
    demo_lines[code] = get_or_create('htplus.line', [('code', '=', CODE + '-' + code)], {
        'name': name, 'code': CODE + '-' + code, 'plant_id': plant_id,
    })
demo_line_set = Line.browse([v.id for v in demo_lines.values()])

wc_spec = [
    ('WC-ASM', 'Assembly Workcenter', 'L1', 'Assembly Line'),
    ('WC-CNC', 'CNC Workcenter', 'L2', 'CNC Line'),
    ('WC-MLD', 'Molding Workcenter', 'L3', 'Molding Line'),
    ('WC-PKG', 'Packaging Workcenter', 'L4', 'Packaging Line'),
]
demo_wcs = {}
for code, name, line_code, machine_name in wc_spec:
    line = demo_lines[line_code]
    demo_wcs[code] = get_or_create('mrp.workcenter', [('code', '=', CODE + '-' + code)], {
        'name': name, 'code': CODE + '-' + code,
        'factory_id': factory.id, 'plant_id': line.plant_id.id, 'line_id': line.id,
    })
    get_or_create('htplus.machine', [('code', '=', CODE + '-' + code + '-M1')], {
        'name': '%s Machine' % machine_name, 'code': CODE + '-' + code + '-M1',
        'workcenter_id': demo_wcs[code].id, 'line_id': line.id,
    })
factory.action_apply_calendar_to_workcenters()

# ---------------------------------------------------------------------------
# 2. Shift templates (Day synced to the factory calendar; Evening/Night are UI)
# ---------------------------------------------------------------------------
Template = env['htplus.shift.template'] 
day_tpl = get_or_create('htplus.shift.template', [('code', '=', CODE + '-DAY')], {
    'name': 'Day Shift', 'code': CODE + '-DAY', 'shift_type': 'day',
    'start_time': 8.0, 'end_time': 17.0, 'break_minutes': 60,
    'default_manpower': 4, 'factory_id': factory.id, 'plant_id': p1.id,
    'day_of_week_start': '0', 'day_of_week_end': '6', 'color': 1,
})
evening_tpl = get_or_create('htplus.shift.template', [('code', '=', CODE + '-EVE')], {
    'name': 'Evening Shift', 'code': CODE + '-EVE', 'shift_type': 'evening',
    'start_time': 14.0, 'end_time': 22.0, 'break_minutes': 30,
    'default_manpower': 2, 'day_of_week_start': '0', 'day_of_week_end': '5', 'color': 3,
})
night_tpl = get_or_create('htplus.shift.template', [('code', '=', CODE + '-NIGHT')], {
    'name': 'Night Shift', 'code': CODE + '-NIGHT', 'shift_type': 'night',
    'start_time': 22.0, 'end_time': 6.0, 'break_minutes': 30,
    'default_manpower': 2, 'day_of_week_start': '6', 'day_of_week_end': '3', 'color': 4,
})
if not day_tpl.resource_calendar_id:
    day_tpl.action_sync_to_calendar()

# ---------------------------------------------------------------------------
# 3. Employees, users, skills, shift members
# ---------------------------------------------------------------------------
Employee = env['hr.employee'] 
User = env['res.users'] 
Member = env['htplus.shift.member'] 
Skill = env['hr.skill'] 
EmpSkill = env['hr.employee.skill'] 

prod_type = env.ref('htplus_workforce_skills.hr_skill_type_production', raise_if_not_found=False)
qa_type = env.ref('htplus_workforce_skills.hr_skill_type_quality', raise_if_not_found=False)
L = {
    'leader': env.ref('htplus_workforce_skills.hr_skill_level_prod_leader', raise_if_not_found=False),
    'senior': env.ref('htplus_workforce_skills.hr_skill_level_prod_senior', raise_if_not_found=False),
    'operator': env.ref('htplus_workforce_skills.hr_skill_level_prod_operator', raise_if_not_found=False),
    'trainee': env.ref('htplus_workforce_skills.hr_skill_level_prod_trainee', raise_if_not_found=False),
    'inspector': env.ref('htplus_workforce_skills.hr_skill_level_qa_inspector', raise_if_not_found=False),
    'basic': env.ref('htplus_workforce_skills.hr_skill_level_qa_basic', raise_if_not_found=False),
}

def skill_by(name):
    rec = Skill.search([('name', '=', name)], limit=1)
    if not rec:
        rec = Skill.create({'name': name, 'skill_type_id': prod_type.id})
    return rec


employees_spec = [
    # name, line code (or None), is_leader, login, [(skill_name, level_key)]
    ('Tran Minh Khoa', 'L1', True, 'op1@htplus.demo',
     [('Machine Operation', 'leader'), ('Assembly', 'senior')]),
    ('Le Thi Hoa', 'L1', False, 'op1@htplus.demo',
     [('Assembly', 'operator'), ('Packaging', 'trainee')]),
    ('Pham Quoc Bao', 'L2', True, 'op2@htplus.demo',
     [('CNC Operation', 'leader'), ('Machine Operation', 'operator')]),
    ('Nguyen Huu Dat', 'L2', False, 'op2@htplus.demo',
     [('Welding', 'operator'), ('Setup / Changeover', 'trainee')]),
    ('Vo Thi Lan', 'L3', True, 'op3@htplus.demo',
     [('Molding / Injection', 'leader'), ('Machine Operation', 'operator')]),
    ('Bui Minh Tam', 'L4', True, 'op3@htplus.demo',
     [('Packaging', 'operator'), ('Material Handling', 'operator')]),
    ('Do Van Hung', 'L3', False, None,
     [('Forklift', 'operator'), ('Material Handling', 'senior')]),
    ('Tran Ngoc Anh', 'L1', False, None,
     [('In-Process Inspection', 'inspector'), ('Measuring Instruments', 'basic')]),
    ('Ly Quoc Dung', None, False, 'manager@htplus.demo', []),
    ('Phan Minh Chau', None, False, 'planner@htplus.demo', []),
]
G = {
    'manager': env.ref('htplus_factory.group_aps_manager').id,
    'planner': env.ref('htplus_factory.group_aps_planner').id,
    'operator': env.ref('htplus_factory.group_mes_operator').id,
}
employees = {}
for name, line_code, is_leader, login, skills in employees_spec:
    employee = Employee.search([('name', '=', name)], limit=1)
    if not employee:
        employee = Employee.create({'name': name, 'company_id': company.id})
    employees[name] = employee
    if login:
        existing = User.search([('login', '=', login)], limit=1)
        if not existing:
            group_id = G['manager'] if login.startswith('manager') \
                else G['planner'] if login.startswith('planner') else G['operator']
            User.create({
                'name': name, 'login': login, 'password': PASSWORD,
                'partner_id': employee.work_contact_id.id,
                'company_id': company.id, 'company_ids': [company.id],
                'groups_id': [(6, 0, [group_id])],
            })
    for skill_name, level_key in skills:
        skill = skill_by(skill_name)
        if EmpSkill.search([('employee_id', '=', employee.id),
                            ('skill_id', '=', skill.id)], limit=1):
            continue
        vals = {
            'employee_id': employee.id,
            'skill_id': skill.id,
            'skill_type_id': skill.skill_type_id.id,
        }
        if L.get(level_key) and L[level_key].skill_type_id.id == skill.skill_type_id.id:
            vals['skill_level_id'] = L[level_key].id
        else:
            vals['skill_level_id'] = skill.skill_type_id.skill_level_ids[:1].id
        EmpSkill.create(vals)

for name, line_code, is_leader, _login, _skills in employees_spec:
    if not line_code:
        continue
    line = demo_lines[line_code]
    member = Member.search([('employee_id', '=', employees[name].id)], limit=1)
    if not member:
        Member.create({
            'employee_id': employees[name].id,
            'factory_id': factory.id,
            'plant_id': line.plant_id.id,
            'line_id': line.id,
            'is_leader': is_leader,
            'start_date': today,
        })

leader_of = {code: employees[name] for name, code, is_leader, *_ in employees_spec
             if code and is_leader}

# ---------------------------------------------------------------------------
# 4. Products, BOMs and raw material stock
# ---------------------------------------------------------------------------
Product = env['product.product'] 
Bom = env['mrp.bom'] 
Quants = env['stock.quant'] 
location = env.ref('stock.stock_location_stock') 


def product(code, name, qty=False):
    rec = Product.search([('default_code', '=', code)], limit=1)
    if not rec:
        rec = Product.create({
            'name': name, 'default_code': code, 'type': 'consu', 'is_storable': True,
        })
    if qty and Quants._get_available_quantity(rec, location) < qty:
        Quants._update_available_quantity(
            rec, location, qty - Quants._get_available_quantity(rec, location))
    return rec


fg01 = product('HTPLUS-DEMO-FG01', 'Smart Controller', 0)
fg02 = product('HTPLUS-DEMO-FG02', 'Control Panel', 0)
semi01 = product('HTPLUS-DEMO-SEMI01', 'Main Board Assembly', 200)
semi02 = product('HTPLUS-DEMO-SEMI02', 'Metal Chassis', 200)
rm = {
    'pcb': product('HTPLUS-DEMO-RM01', 'PCB Board', 400),
    'conn': product('HTPLUS-DEMO-RM02', 'Connector Kit', 600),
    'sheet': product('HTPLUS-DEMO-RM03', 'Sheet Metal', 400),
    'cable': product('HTPLUS-DEMO-RM04', 'Cable Harness', 300),
    'plastic': product('HTPLUS-DEMO-RM05', 'Molded Plastic Part', 600),
    'fast': product('HTPLUS-DEMO-RM06', 'Fastener Kit', 600),
}
wc_asm = demo_wcs['WC-ASM']
wc_cnc = demo_wcs['WC-CNC']
wc_mld = demo_wcs['WC-MLD']
wc_pkg = demo_wcs['WC-PKG']


def get_or_create_bom(product_rec, lines, ops):
    bom = Bom.search([('product_tmpl_id', '=', product_rec.product_tmpl_id.id)], limit=1)
    if bom:
        return bom
    return Bom.create({
        'product_tmpl_id': product_rec.product_tmpl_id.id,
        'product_qty': 1.0,
        'type': 'normal',
        'bom_line_ids': [(0, 0, {'product_id': pid.id, 'product_qty': qty})
                         for pid, qty in lines],
        'operation_ids': [(0, 0, {'name': op_name, 'workcenter_id': wc.id,
                                  'time_cycle_manual': minutes, 'sequence': seq})
                          for seq, (op_name, wc, minutes) in enumerate(ops, start=10)],
    })


get_or_create_bom(semi01,
                  [(rm['pcb'], 1.0), (rm['conn'], 2.0), (rm['plastic'], 2.0)],
                  [('SMT Assembly', wc_asm, 20), ('Functional Test', wc_asm, 15)])
get_or_create_bom(semi02,
                  [(rm['sheet'], 1.0), (rm['fast'], 4.0)],
                  [('CNC Machining', wc_cnc, 45)])
get_or_create_bom(fg01,
                  [(semi01, 1.0), (semi02, 1.0), (rm['cable'], 1.0)],
                  [('Final Assembly', wc_asm, 30), ('Packaging', wc_pkg, 10)])
get_or_create_bom(fg02,
                  [(semi01, 1.0), (rm['sheet'], 1.0)],
                  [('Injection Molding', wc_mld, 20), ('Final Assembly', wc_asm, 25)])

# ---------------------------------------------------------------------------
# 5. Demand plan
# ---------------------------------------------------------------------------
Demand = env['htplus.demand.plan'] 
ProductionPlan = env['htplus.production.plan'] 
demand = Demand.create({
    'date_start': today,
    'date_end': today + timedelta(days=7),
    'source': 'manual',
    'factory_id': factory.id,
    'notes': 'HTPLUS-DEMO seeded demand',
    'line_ids': [(0, 0, {
        'product_id': fg01.id, 'date': today + timedelta(days=3), 'qty': 60.0,
        'uom_id': fg01.uom_id.id,
    }), (0, 0, {
        'product_id': fg01.id, 'date': today + timedelta(days=6), 'qty': 40.0,
        'uom_id': fg01.uom_id.id,
    }), (0, 0, {
        'product_id': fg02.id, 'date': today + timedelta(days=4), 'qty': 50.0,
        'uom_id': fg02.uom_id.id,
    }), (0, 0, {
        'product_id': fg02.id, 'date': today + timedelta(days=7), 'qty': 30.0,
        'uom_id': fg02.uom_id.id,
    })],
})
demand.action_confirm()
demand.action_approve()
plan = ProductionPlan.browse(demand.action_generate_plan()['res_id'])
plan.notes = 'HTPLUS-DEMO seeded plan'
plan.action_confirm()
plan.action_approve()
plan.action_check_materials()
try:
    plan.action_create_productions()
except Exception as err:  # force material flag like the e2e seed
    print('[seed] create_productions warning:', err)
    for line in plan.line_ids.filtered(lambda l: l.state == 'draft'):
        line.material_ok = True
        line.material_note = 'forced for demo seed'
    plan.action_create_productions()

# ---------------------------------------------------------------------------
# 6. Schedule run
# ---------------------------------------------------------------------------
run = plan.action_create_schedule()
run = env['htplus.schedule.run'].browse(run['res_id']) 
try:
    run.action_confirm()
    run_state = run.state
except Exception as err:
    run_state = 'calculated (%s)' % err

# ---------------------------------------------------------------------------
# 7. Workforce assignments (redistribute employees, confirm non-conflicting)
# ---------------------------------------------------------------------------
Assignment = env['htplus.workforce.assignment'] 
wf_action = run.action_propose_workforce()
assign_ids = wf_action.get('domain', [[]])[0][2] if wf_action else []
assignments = Assignment.browse(assign_ids)
line_staff = [employees[name] for name, code, *_ in employees_spec
              if code and name in employees]
for index, assignment in enumerate(assignments.sorted('date_start')):
    assignment.employee_id = line_staff[index % len(line_staff)]
assignments.action_validate()
conflicted = assignments.filtered(lambda a: a.conflict)
confirmed = Assignment.browse()
for assignment in assignments.filtered(lambda a: a.skill_ok and not a.conflict).sorted('date_start'):
    try:
        assignment.action_confirm()
        confirmed |= assignment
    except ValidationError as err:  # skip conflicts raised mid-loop
        print('[seed] skip assignment %s (%s): %s' % (
            assignment.name, assignment.employee_id.name, err))
print('[seed] assignments total=%s confirmed=%s conflicts=%s' % (
    len(assignments), len(confirmed), len(conflicted)))

# ---------------------------------------------------------------------------
# 8. Production shifts: set leaders on the shifts proposed by the run
# ---------------------------------------------------------------------------
Shift = env['htplus.production.shift'] 
demo_shifts = Shift.search([
    ('template_id', 'in', (day_tpl | evening_tpl | night_tpl).ids),
    ('date', '>=', today), ('date', '<=', today + timedelta(days=7)),
]).filtered(lambda s: s.line_id in demo_line_set)
for shift in demo_shifts:
    line_key = next((k for k, v in demo_lines.items() if v.id == shift.line_id.id), None)
    if line_key and line_key in leader_of and not shift.leader_id:
        shift.leader_id = leader_of[line_key].id
    shift.qty_target = max(shift.qty_target, 100)
    if shift.state == 'draft':
        shift.action_confirm()
print('[seed] production shifts:', len(demo_shifts), 'lines=',
      sorted(set(demo_shifts.mapped('line_id.code'))))

# ---------------------------------------------------------------------------
# 9. MES actuals: finish a few with real quantities
# ---------------------------------------------------------------------------
Actual = env['htplus.workorder.actual'] 
actuals = Actual.search([
    ('workorder_id', 'in', run.workorder_ids.ids),
    ('state', 'in', ('running', 'paused')),
])
finished = 0
for actual in actuals[:4]:
    actual.write({
        'qty_done': actual.workorder_id.production_id.product_qty or 10.0,
        'qty_good': (actual.workorder_id.production_id.product_qty or 10.0) * 0.95,
        'qty_ng': (actual.workorder_id.production_id.product_qty or 10.0) * 0.05,
        'date_finished': fields.Datetime.now(),
    })
    actual.action_finish()
    finished += 1
print('[seed] mes actuals total=%s finished=%s' % (len(actuals), finished))

# ---------------------------------------------------------------------------
# 10. Shift actuals + completions
# ---------------------------------------------------------------------------
ShiftActual = env['htplus.shift.actual'] 
Completion = env['htplus.shift.completion'] 
for shift in demo_shifts.filtered(
        lambda s: s.assignment_ids.filtered(lambda a: a.state == 'confirmed'))[:2]:
    actual = ShiftActual.create({'shift_id': shift.id})
    actual.action_generate_from_shift()
    if actual.line_ids:
        for line in actual.line_ids:
            line.qty_done = line.qty_target * 0.9
            line.qty_good = line.qty_target * 0.85
            line.qty_ng = line.qty_target * 0.05
            line.downtime_minutes = 20
        actual.action_confirm()
        actual.action_done()
    for wo in shift.assignment_ids.mapped('workorder_id')[:1]:
        Completion.create({
            'shift_id': shift.id, 'workorder_id': wo.id, 'date': shift.date,
            'qty_target': 100.0, 'qty_done': 92.0, 'qty_good': 88.0,
            'qty_ng': 4.0, 'downtime_minutes': 25, 'overtime_minutes': 30,
        })
print('[seed] shift actuals:', ShiftActual.search_count([('line_id', 'in', demo_line_set.ids)]))
print('[seed] shift completions:', Completion.search_count([('shift_id', 'in', demo_shifts.ids)]))

# ---------------------------------------------------------------------------
# 11. Working plan on the dashboard
# ---------------------------------------------------------------------------
plan.action_use_on_dashboard()

env.cr.commit()
print('[seed] OK factory=%s plan=%s mos=%s run=%s wos=%s conflicts=%s' % (
    factory.name, plan.name, len(plan.production_ids), run.name,
    len(run.workorder_ids), run.conflict_count,
))
print('[seed] plan lines (incl. exploded):', plan.line_ids.mapped(
    lambda l: '%s x %s' % (l.product_id.default_code, l.qty)))
print('[seed] users:',
      User.search([('login', 'in', ('manager@htplus.demo', 'planner@htplus.demo',
                                    'op1@htplus.demo', 'op2@htplus.demo', 'op3@htplus.demo'))]
                  ).mapped('login'))
print('[seed] password for all demo users: %s' % PASSWORD)
