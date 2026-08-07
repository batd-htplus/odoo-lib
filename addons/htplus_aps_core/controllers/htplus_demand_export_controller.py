import io

from odoo import http
from odoo.http import request

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HtplusDemandExportController(http.Controller):

    @http.route('/htplus/aps/demand/export', type='http', auth='user')
    def export_demand_plan(self, plan_id=None, **kwargs):
        if not xlsxwriter:
            return request.not_found()
        plan = request.env['htplus.demand.plan'].browse(int(plan_id or 0))
        if not plan.exists():
            return request.not_found()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Demand')
        bold = workbook.add_format({'bold': True})
        headers = ['Product', 'Code', 'Date', 'Qty', 'UoM', 'Confidence', 'Status']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)
        for row, line in enumerate(plan.line_ids, start=1):
            sheet.write(row, 0, line.product_id.name)
            sheet.write(row, 1, line.product_id.default_code or '')
            sheet.write(row, 2, str(line.date))
            sheet.write(row, 3, line.qty)
            sheet.write(row, 4, line.uom_id.name)
            sheet.write(row, 5, line.forecast_confidence or 0.0)
            sheet.write(row, 6, line.state)
        workbook.close()
        filename = 'demand_plan_%s.xlsx' % plan.name.replace('/', '_')
        return request.make_response(
            output.getvalue(),
            headers=[('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                     ('Content-Disposition', 'attachment; filename=%s' % filename)],
        )
