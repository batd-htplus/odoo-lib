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

ENTITY_COLUMNS = {
    'factory': ['name', 'code'],
    'plant': ['name', 'code', 'factory_code'],
    'line': ['name', 'code', 'plant_code'],
    'workcenter': ['name', 'code', 'line_code', 'factory_code'],
    'machine': ['name', 'code', 'line_code', 'workcenter_code', 'status'],
    'employee': ['name', 'code'],
    'bom': ['product_code', 'component_code', 'component_qty'],
    'skill': ['name', 'type_name'],
}


class HtplusMasterDataImportWizard(models.TransientModel):
    _name = 'htplus.master.data.import.wizard'
    _description = 'Import Master Data'

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    entity = fields.Selection([
        ('factory', 'Factories'),
        ('plant', 'Plants'),
        ('line', 'Production Lines'),
        ('workcenter', 'Work Centers'),
        ('machine', 'Machines'),
        ('employee', 'Employees'),
        ('bom', 'BOMs'),
        ('skill', 'Skills'),
    ], string='Entity', required=True)
    file = fields.Binary(string='File', required=True)
    filename = fields.Char(string='Filename')
    preview = fields.Text(string='Preview', readonly=True)
    import_summary = fields.Text(string='Import Summary', readonly=True)

    def _parse_file(self):
        """Parse the uploaded file into raw rows of string cells."""
        if not self.file:
            raise UserError(_('Please select a file to import.'))
        data = base64.b64decode(self.file)
        name = (self.filename or '').lower()
        rows = []
        if name.endswith('.csv'):
            reader = csv.reader(io.StringIO(data.decode('utf-8-sig')))
            for row in reader:
                if any(cell.strip() for cell in row):
                    rows.append(row)
        elif name.endswith('.xls'):
            if not xlrd:
                raise UserError(_('xlrd is not installed; cannot read .xls files.'))
            book = xlrd.open_workbook(file_contents=data)
            sheet = book.sheet_by_index(0)
            for i in range(sheet.nrows):
                row = [str(sheet.cell_value(i, c)).strip() for c in range(sheet.ncols)]
                if any(cell for cell in row):
                    rows.append(row)
        elif name.endswith('.xlsx'):
            if not openpyxl:
                raise UserError(_('openpyxl is not installed; cannot read .xlsx files.'))
            book = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
            sheet = book.active
            for row in sheet.iter_rows(values_only=True):
                cells = [str(c).strip() if c is not None else '' for c in row]
                if any(cells):
                    rows.append(cells)
        else:
            raise UserError(_('Unsupported file format. Use CSV, XLS or XLSX.'))
        return rows

    def action_preview(self):
        """Fill the preview field with the expected columns and the first rows."""
        self.ensure_one()
        rows = self._parse_file()
        columns = ENTITY_COLUMNS[self.entity]
        lines = [' | '.join(columns)]
        lines.extend([' | '.join((row + [''] * len(columns))[:len(columns)]) for row in rows[:20]])
        self.preview = '\n'.join(lines)
        return True

    def _find(self, model, key_field, value):
        """Look up a record by an exact key field, or False."""
        if not value:
            return self.env[model]
        return self.env[model].search([(key_field, '=', value)], limit=1)

    def _cell(self, row, index):
        """Return the cell value at the given column index, stripped."""
        if index >= len(row):
            return ''
        return (row[index] or '').strip()

    def _counts(self, created, skipped):
        """Return a human-readable summary line of the import result."""
        return _('Created: %(created)s  |  Skipped (already present): %(skipped)s') % {
            'created': created, 'skipped': skipped,
        }

    def action_import(self):
        """Import the parsed rows into the selected entity."""
        self.ensure_one()
        rows = self._parse_file()
        if not rows:
            raise UserError(_('The file is empty.'))
        handler = getattr(self, '_import_%s' % self.entity)
        self.import_summary = handler(rows)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------
    def _import_factory(self, rows):
        created = skipped = 0
        Factory = self.env['htplus.factory']
        for row in rows:
            name, code = self._cell(row, 0), self._cell(row, 1)
            if not code:
                raise UserError(_('Factory row missing code: %s') % (name or row))
            if self._find('htplus.factory', 'code', code):
                skipped += 1
                continue
            Factory.create({'name': name or code, 'code': code})
            created += 1
        return self._counts(created, skipped)

    # ------------------------------------------------------------------
    # Plants
    # ------------------------------------------------------------------
    def _import_plant(self, rows):
        created = skipped = 0
        for row in rows:
            name, code, factory_code = self._cell(row, 0), self._cell(row, 1), self._cell(row, 2)
            if not code:
                raise UserError(_('Plant row missing code: %s') % (name or row))
            factory = self._find('htplus.factory', 'code', factory_code)
            if not factory:
                factory = self.env['htplus.factory'].create({
                    'name': factory_code or 'Factory', 'code': factory_code,
                })
            if self._find('htplus.plant', 'code', code):
                skipped += 1
                continue
            self.env['htplus.plant'].create({
                'name': name or code, 'code': code, 'factory_id': factory.id,
            })
            created += 1
        return self._counts(created, skipped)

    # ------------------------------------------------------------------
    # Production lines
    # ------------------------------------------------------------------
    def _import_line(self, rows):
        created = skipped = 0
        for row in rows:
            name, code, plant_code = self._cell(row, 0), self._cell(row, 1), self._cell(row, 2)
            if not code:
                raise UserError(_('Line row missing code: %s') % (name or row))
            plant = self._find('htplus.plant', 'code', plant_code)
            if not plant:
                raise UserError(_('Plant not found for line %s: %s') % (code, plant_code))
            if self._find('htplus.line', 'code', code):
                skipped += 1
                continue
            self.env['htplus.line'].create({
                'name': name or code, 'code': code, 'plant_id': plant.id,
            })
            created += 1
        return self._counts(created, skipped)

    # ------------------------------------------------------------------
    # Work centers
    # ------------------------------------------------------------------
    def _import_workcenter(self, rows):
        created = skipped = 0
        Workcenter = self.env['mrp.workcenter']
        for row in rows:
            name, code, line_code, factory_code = (
                self._cell(row, 0), self._cell(row, 1), self._cell(row, 2), self._cell(row, 3))
            if not code:
                raise UserError(_('Work center row missing code: %s') % (name or row))
            existing = self._find('mrp.workcenter', 'code', code)
            if existing:
                skipped += 1
                continue
            vals = {'name': name or code, 'code': code}
            if line_code:
                line = self._find('htplus.line', 'code', line_code)
                if not line:
                    raise UserError(_('Line not found for work center %s: %s') % (code, line_code))
                vals['line_id'] = line.id
                vals['factory_id'] = line.factory_id.id
            elif factory_code:
                factory = self._find('htplus.factory', 'code', factory_code)
                if not factory:
                    raise UserError(_('Factory not found for work center %s: %s')
                                    % (code, factory_code))
                vals['factory_id'] = factory.id
            Workcenter.create(vals)
            created += 1
        return self._counts(created, skipped)

    # ------------------------------------------------------------------
    # Machines
    # ------------------------------------------------------------------
    def _import_machine(self, rows):
        created = skipped = 0
        Machine = self.env['htplus.machine']
        for row in rows:
            name, code, line_code, wc_code, status = (
                self._cell(row, 0), self._cell(row, 1), self._cell(row, 2),
                self._cell(row, 3), self._cell(row, 4))
            if not code:
                raise UserError(_('Machine row missing code: %s') % (name or row))
            if self._find('htplus.machine', 'code', code):
                skipped += 1
                continue
            vals = {'name': name or code, 'code': code}
            if wc_code:
                wc = self._find('mrp.workcenter', 'code', wc_code)
                if not wc:
                    raise UserError(_('Work center not found for machine %s: %s')
                                    % (code, wc_code))
                vals['workcenter_id'] = wc.id
                vals['factory_id'] = wc.factory_id.id
            if line_code:
                line = self._find('htplus.line', 'code', line_code)
                if not line:
                    raise UserError(_('Line not found for machine %s: %s') % (code, line_code))
                vals['line_id'] = line.id
                vals['factory_id'] = vals.get('factory_id') or line.factory_id.id
            if status:
                vals['status'] = status
            Machine.create(vals)
            created += 1
        return self._counts(created, skipped)

    # ------------------------------------------------------------------
    # Employees
    # ------------------------------------------------------------------
    def _import_employee(self, rows):
        created = skipped = 0
        Employee = self.env['hr.employee']
        for row in rows:
            name, code = self._cell(row, 0), self._cell(row, 1)
            if not name:
                raise UserError(_('Employee row missing name: %s') % row)
            domain = [('name', '=', name)]
            if code:
                domain = ['|', ('barcode', '=', code), ('name', '=', name)]
            if Employee.search(domain, limit=1):
                skipped += 1
                continue
            vals = {'name': name}
            if code:
                vals['barcode'] = code
            Employee.create(vals)
            created += 1
        return self._counts(created, skipped)

    # ------------------------------------------------------------------
    # BOMs (product / component / qty per row)
    # ------------------------------------------------------------------
    def _import_bom(self, rows):
        created = skipped = 0
        Bom = self.env['mrp.bom']
        for row in rows:
            product_code, component_code, qty_str = (
                self._cell(row, 0), self._cell(row, 1), self._cell(row, 2))
            if not product_code or not component_code or not qty_str:
                raise UserError(_('BOM row needs product_code, component_code and '
                                  'component_qty: %s') % row)
            product = self._find('product.product', 'default_code', product_code)
            if not product:
                raise UserError(_('Product not found for BOM: %s') % product_code)
            component = self._find('product.product', 'default_code', component_code)
            if not component:
                raise UserError(_('Component not found for BOM: %s') % component_code)
            bom = Bom.search([
                ('product_tmpl_id', '=', product.product_tmpl_id.id),
                ('type', '=', 'normal'),
            ], limit=1)
            if not bom:
                bom = Bom.create({
                    'product_tmpl_id': product.product_tmpl_id.id,
                    'product_qty': 1.0,
                    'type': 'normal',
                })
                created += 1
            bom.bom_line_ids = [(0, 0, {
                'product_id': component.id,
                'product_qty': float(qty_str),
            })]
        return self._counts(created, skipped)

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------
    def _import_skill(self, rows):
        created = skipped = 0
        Skill = self.env['hr.skill']
        SkillType = self.env['hr.skill.type']
        for row in rows:
            name, type_name = self._cell(row, 0), self._cell(row, 1)
            if not name:
                raise UserError(_('Skill row missing name: %s') % row)
            if self._find('hr.skill', 'name', name):
                skipped += 1
                continue
            skill_type = self._find('hr.skill.type', 'name', type_name) if type_name else SkillType
            if not skill_type:
                skill_type = SkillType.create({'name': type_name or _('Production')})
            Skill.create({'name': name, 'skill_type_id': skill_type.id})
            created += 1
        return self._counts(created, skipped)
