import json

from odoo import http
from odoo.http import request


def _json_response(data, status=200):
    return http.Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        mimetype='application/json',
    )


class HtplusApiController(http.Controller):

    @http.route('/htplus/api/schedule', type='http', auth='user', methods=['GET'])
    def schedule_runs(self, **kwargs):
        """List schedule runs for the external UI."""
        runs = request.env['htplus.schedule.run'].search_read(
            [], ['id', 'name', 'version', 'state', 'algorithm', 'conflict_count'])
        return _json_response({'success': True, 'data': runs})

    @http.route('/htplus/api/workorder', type='http', auth='user', methods=['GET'])
    def workorders(self, schedule_run_id=None, **kwargs):
        """List work orders, optionally filtered by schedule run.

        Args:
            schedule_run_id: Restrict results to this schedule run.
        """
        domain = []
        if schedule_run_id:
            domain.append(('schedule_run_id', '=', int(schedule_run_id)))
        fields = ['id', 'display_name', 'workcenter_id', 'machine_id', 'date_start',
                  'date_finished', 'schedule_state', 'priority', 'locked']
        workorders = request.env['mrp.workorder'].search_read(domain, fields)
        return _json_response({'success': True, 'data': workorders})

    @http.route('/htplus/api/demand', type='json', auth='user', methods=['POST'])
    def create_demand(self, **kwargs):
        """Create a demand plan from the submitted JSON lines."""
        payload = request.get_json_data() or {}
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
        """Lock the schedule run so work orders can no longer be rescheduled."""
        run = request.env['htplus.schedule.run'].browse(schedule_run_id)
        run.action_lock()
        return {'success': True, 'data': {'id': run.id, 'state': run.state}}
