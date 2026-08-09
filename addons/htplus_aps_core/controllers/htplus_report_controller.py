import io

from odoo import http
from odoo.http import request

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class HtplusApsReportController(http.Controller):

    @http.route('/htplus/aps/report/shift/export', type='http', auth='user')
    def export_shift_report(self, date_from=None, date_to=None, wizard_id=None, **kwargs):
        """Export the shift report for the selected period as an XLSX download.

        Args:
            date_from: Start of the reporting period.
            date_to: End of the reporting period.
            wizard_id: Existing report wizard to reuse, if any.

        Returns:
            HTTP response carrying the XLSX file.
        """
        if not xlsxwriter:
            return request.not_found()
        wizard = request.env['htplus.shift.report.wizard'].browse(int(wizard_id or 0))
        if not wizard.exists():
            wizard = request.env['htplus.shift.report.wizard'].create({
                'date_from': date_from,
                'date_to': date_to,
            })
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Shift Report')
        bold = workbook.add_format({'bold': True})
        headers = ['Shift', 'Date', 'Line', 'Leader', 'Target', 'Done', 'Good',
                   'NG', 'Downtime (min)', 'Overtime (min)', 'Manpower',
                   'Achievement %', 'Yield %']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)
        for row, line in enumerate(wizard._get_lines(), start=1):
            sheet.write(row, 0, line['name'])
            sheet.write(row, 1, line['date'].isoformat() if line['date'] else '')
            sheet.write(row, 2, line['line'])
            sheet.write(row, 3, line['leader'])
            sheet.write(row, 4, line['qty_target'])
            sheet.write(row, 5, line['qty_done'])
            sheet.write(row, 6, line['qty_good'])
            sheet.write(row, 7, line['qty_ng'])
            sheet.write(row, 8, line['downtime_minutes'])
            sheet.write(row, 9, line['overtime_minutes'])
            sheet.write(row, 10, line['manpower_used'])
            sheet.write(row, 11, line['achievement_rate'])
            sheet.write(row, 12, line['yield_rate'])
        totals = wizard._get_totals()
        row += 1
        sheet.write(row, 0, 'Total (%d shifts)' % totals['count'], bold)
        sheet.write(row, 4, totals['qty_target'], bold)
        sheet.write(row, 5, totals['qty_done'], bold)
        sheet.write(row, 6, totals['qty_good'], bold)
        sheet.write(row, 7, totals['qty_ng'], bold)
        sheet.write(row, 8, totals['downtime_minutes'], bold)
        sheet.write(row, 9, totals['overtime_minutes'], bold)
        workbook.close()
        content = output.getvalue()
        filename = 'shift_report_%s_%s.xlsx' % (wizard.date_from, wizard.date_to)
        return request.make_response(
            content,
            headers=[('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                     ('Content-Disposition', 'attachment; filename=%s' % filename)],
        )
