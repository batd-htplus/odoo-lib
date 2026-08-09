from odoo import http
from odoo.http import request

class HtplusApiController(http.Controller):

    @http.route('/htplus/api/schedule', type='json', auth='user', methods=['GET'])
    def schedule_runs(self, **kwargs):
        runs = request.env['htplus.schedule.run'].search_read(
            [], ['id', 'name', 'version', 'state', 'algorithm', 'conflict_count'])
        return {'success': True, 'data': runs}

    @http.route('/htplus/api/workorder', type='json', auth='user', methods=['GET'])
    def workorders(self, schedule_run_id=None, **kwargs):
        domain = []
        if schedule_run_id:
            domain.append(('schedule_run_id', '=', int(schedule_run_id)))
        fields = ['id', 'display_name', 'workcenter_id', 'machine_id', 'date_start',
                  'date_finished', 'schedule_state', 'priority', 'locked']
        workorders = request.env['mrp.workorder'].search_read(domain, fields)
        return {'success': True, 'data': workorders}

    @http.route('/htplus/api/demand', type='json', auth='user', methods=['POST'])
    def create_demand(self, **kwargs):
        payload = request.jsonrequest or {}
        lines = payload.get('lines', [])
        plan = request.env['htplus.demand.plan'].create({
            'date_start': payload.get('date_start'),
            'date_end': payload.get('date_end'),
            'source': payload.get('source', 'manual'),
        })
        for line in lines:
            product = request.env['product.product'].browse(int(line.get('product_id')))
            plan.line_ids = [(0, 0, {
                'product_id': product.id,
                'date': line.get('date'),
                'qty': line.get('qty', 0.0),
                'uom_id': line.get('uom_id') or product.uom_id.id,
            })]
        return {'success': True, 'data': {'plan_id': plan.id, 'name': plan.name}}

    @http.route('/htplus/api/schedule/<int:schedule_run_id>/lock', type='json', auth='user', methods=['POST'])
    def lock_schedule(self, schedule_run_id, **kwargs):
        run = request.env['htplus.schedule.run'].browse(schedule_run_id)
        run.action_lock()
        return {'success': True, 'data': {'id': run.id, 'state': run.state}}
