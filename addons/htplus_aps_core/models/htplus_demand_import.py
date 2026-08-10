import base64
import csv
import io

from odoo import fields, models, _
from odoo.exceptions import UserError

try:
    import xlrd
except ImportError:
    xlrd = None

try:
    import openpyxl
except ImportError:
    openpyxl = None


class HtplusDemandPlanImportWizard(models.TransientModel):
    _name = 'htplus.demand.plan.import.wizard'
    _description = 'Import Demand Plan'

    date_start = fields.Date(required=True, default=fields.Date.context_today)
    date_end = fields.Date(required=True)
    file = fields.Binary(string='File', required=True)
    filename = fields.Char(string='Filename')
    preview = fields.Text(string='Preview', readonly=True)
    source = fields.Selection([
        ('manual', 'Manual'),
        ('import', 'Import'),
    ], default='import')

    def _parse_file(self):
        """Parse the uploaded file into raw rows of product code, date and qty.

        Returns:
            list of row tuples extracted from the first three columns.
        """
        if not self.file:
            raise UserError(_('Please select a file to import.'))
        data = base64.b64decode(self.file)
        name = (self.filename or '').lower()
        rows = []
        if name.endswith('.csv'):
            reader = csv.reader(io.StringIO(data.decode('utf-8-sig')))
            for row in reader:
                if len(row) >= 3:
                    rows.append(row[:3])
        elif name.endswith('.xls'):
            if not xlrd:
                raise UserError(_('xlrd is not installed; cannot read .xls files.'))
            book = xlrd.open_workbook(file_contents=data)
            sheet = book.sheet_by_index(0)
            for i in range(sheet.nrows):
                row = [str(sheet.cell_value(i, c)) for c in range(sheet.ncols)]
                if len(row) >= 3:
                    rows.append(row[:3])
        elif name.endswith('.xlsx'):
            if not openpyxl:
                raise UserError(_('openpyxl is not installed; cannot read .xlsx files.'))
            book = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
            sheet = book.active
            for row in sheet.iter_rows(values_only=True):
                if row and len(row) >= 3:
                    rows.append([str(c) if c is not None else '' for c in row[:3]])
        else:
            raise UserError(_('Unsupported file format. Use CSV, XLS or XLSX.'))
        return rows

    def action_preview(self):
        """Fill the preview field with the first rows of the parsed file."""
        self.ensure_one()
        rows = self._parse_file()
        lines = ['product_code | date | qty']
        lines.extend(['%s | %s | %s' % tuple(r) for r in rows[:20]])
        self.preview = '\n'.join(lines)
        return True

    def _load_product_map(self, rows):
        """Load every referenced product once, keyed by internal reference and name.

        Args:
            rows: Raw rows from the parsed file.

        Returns:
            (by_code, by_name) dicts mapping product keys to products.
        """
        codes = {row[0].strip() for row in rows if row[0] and row[0].strip()}
        products = self.env['product.product'].search([
            '|', ('default_code', 'in', list(codes)), ('name', 'in', list(codes)),
        ])
        by_code = {}
        by_name = {}
        for product in products:
            if product.default_code and product.default_code not in by_code:
                by_code[product.default_code] = product
            if product.name and product.name not in by_name:
                by_name[product.name] = product
        return by_code, by_name

    def _convert_row(self, row, by_code, by_name):
        """Resolve a raw row to a product, date and quantity using preloaded maps.

        Args:
            row: (product_code, date, qty) tuple from the parsed file.
            by_code: Products keyed by internal reference.
            by_name: Products keyed by name.

        Returns:
            (product, date, qty) ready to create a demand plan line.
        """
        product_code, date_str, qty_str = row
        key = product_code.strip()
        product = by_code.get(key) or by_name.get(key)
        if not product:
            raise UserError(_('Product not found: %s') % product_code)
        date = fields.Date.from_string(date_str.strip())
        qty = float(qty_str)
        return product, date, qty

    def action_import(self):
        """Import the parsed rows into a new demand plan and open it."""
        self.ensure_one()
        rows = self._parse_file()
        if not rows:
            raise UserError(_('The file is empty.'))
        by_code, by_name = self._load_product_map(rows)
        plan = self.env['htplus.demand.plan'].create({
            'date_start': self.date_start,
            'date_end': self.date_end,
            'source': self.source,
        })
        line_vals = []
        for row in rows:
            product, date, qty = self._convert_row(row, by_code, by_name)
            line_vals.append((0, 0, {
                'product_id': product.id,
                'date': date,
                'qty': qty,
                'uom_id': product.uom_id.id,
            }))
        if line_vals:
            plan.write({'line_ids': line_vals})
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'htplus.demand.plan',
            'res_id': plan.id,
            'view_mode': 'form',
        }
