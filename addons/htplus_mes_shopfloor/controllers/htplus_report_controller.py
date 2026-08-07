import io

from odoo import http
from odoo.http import request
from odoo.tools.misc import str2bool

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HtplusReportController(http.Controller):

    @http.route('/htplus/mes/report/production/export', type='http', auth='user')
    def export_production_report(self, date_from=None, date_to=None, wizard_id=None, **kwargs):
        if not xlsxwriter:
            return request.not_found()
        wizard = request.env['htplus.report.production.daily'].browse(int(wizard_id or 0))
        if not wizard.exists():
            wizard = request.env['htplus.report.production.daily'].create({
                'date_from': date_from,
                'date_to': date_to,
            })
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Production')
        bold = workbook.add_format({'bold': True})
        headers = ['Work Order', 'Work Center', 'Machine', 'Qty Good', 'Qty NG', 'Downtime (min)']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)
        for row, line in enumerate(wizard._get_lines(), start=1):
            sheet.write(row, 0, line['workorder'])
            sheet.write(row, 1, line['workcenter'])
            sheet.write(row, 2, line['machine'])
            sheet.write(row, 3, line['qty_good'])
            sheet.write(row, 4, line['qty_ng'])
            sheet.write(row, 5, line['downtime_minutes'])
        totals = wizard._get_totals()
        row += 1
        sheet.write(row, 0, 'Total', bold)
        sheet.write(row, 3, totals['qty_good'], bold)
        sheet.write(row, 4, totals['qty_ng'], bold)
        sheet.write(row, 5, totals['downtime_minutes'], bold)
        workbook.close()
        content = output.getvalue()
        filename = 'production_report_%s_%s.xlsx' % (wizard.date_from, wizard.date_to)
        return request.make_response(
            content,
            headers=[('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                     ('Content-Disposition', 'attachment; filename=%s' % filename)],
        )
