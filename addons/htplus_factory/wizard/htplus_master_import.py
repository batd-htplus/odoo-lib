import base64
import csv
import io

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:  # pragma: no cover - optional dependency
    openpyxl = None

# One row of the sheet describes one path down the hierarchy. Blank cells to the
# right simply stop the walk, so a sheet may mix "factory + plant" rows with
# full "factory .. machine" rows.
COLUMNS = (
    'factory_code', 'factory_name',
    'plant_code', 'plant_name',
    'line_code', 'line_name',
    'workcenter_code', 'workcenter_name',
    'machine_code', 'machine_name',
)


class HtplusMasterImportWizard(models.TransientModel):
    """Load a whole factory hierarchy from one spreadsheet.

    Odoo already imports any model from CSV or XLSX, and this does not try to
    replace that. What it adds is the thing a rollout actually struggles with:
    the *hierarchy*. Loading a site through the standard importer means five
    files in dependency order, each referencing the previous one by external ID,
    with no way to re-run a corrected file without hand-cleaning first.

    Here one sheet carries the whole path - factory, plant, line, work center,
    machine - and every row is resolved by business code. Re-importing a
    corrected sheet updates in place instead of duplicating, which is what makes
    it usable during the back-and-forth of a real rollout.
    """

    _name = 'htplus.master.import.wizard'
    _description = 'Import Factory Master Data'

    file = fields.Binary(string='File', required=True)
    filename = fields.Char(string='Filename')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company)
    dry_run = fields.Boolean(
        string='Preview only', default=True,
        help='Report what would change without writing anything. Turn off to import.')
    result = fields.Text(string='Result', readonly=True)

    def _htplus_rows(self):
        """Parse the upload into dicts keyed by COLUMNS.

        Accepts CSV or XLSX. The first row is treated as a header and is matched
        against COLUMNS by name, so column order does not matter and unknown
        columns are ignored rather than shifting everything sideways.

        Returns:
            List of dicts, one per non-empty data row.

        Raises:
            UserError: The file cannot be read, or no known column is present.
        """
        if not self.file:
            raise UserError(_('Please select a file to import.'))
        raw = base64.b64decode(self.file)
        name = (self.filename or '').lower()
        if name.endswith(('.xlsx', '.xlsm')):
            if not openpyxl:
                raise UserError(_('openpyxl is not installed; save the sheet as CSV instead.'))
            book = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
            table = [[cell if cell is not None else '' for cell in row]
                     for row in book.active.iter_rows(values_only=True)]
        else:
            text = raw.decode('utf-8-sig', errors='replace')
            table = list(csv.reader(io.StringIO(text)))
        if not table:
            raise UserError(_('The file is empty.'))
        header = [str(cell or '').strip().lower().replace(' ', '_') for cell in table[0]]
        known = {index: key for index, key in enumerate(header) if key in COLUMNS}
        if not known:
            raise UserError(_(
                'No recognised column. Expected any of: %s', ', '.join(COLUMNS)))
        rows = []
        for line in table[1:]:
            row = {key: str(line[index]).strip() if index < len(line) and line[index] is not None else ''
                   for index, key in known.items()}
            if any(row.values()):
                rows.append(row)
        return rows

    def _htplus_upsert(self, model, code, vals, cache, report):
        """Create or update one record, keyed by its business code.

        Args:
            model: Model name to write to.
            code: Business code identifying the record.
            vals: Values to create with, or to correct an existing record from.
            cache: Per-model dict of already-resolved codes.
            report: Counter dict to record the outcome in.

        Returns:
            The record, or an empty recordset when code is blank.
        """
        Model = self.env[model]
        if not code:
            return Model.browse()
        key = (model, code)
        if key in cache:
            return cache[key]
        record = Model.search([('code', '=', code)], limit=1)
        if record:
            changed = {field: value for field, value in vals.items()
                       if value and record[field] != value
                       and not hasattr(record[field], 'ids')}
            if changed and not self.dry_run:
                record.write(changed)
            report['updated' if changed else 'unchanged'] += 1
        else:
            if self.dry_run:
                # Nothing to write yet, but later rows still need something to
                # hang off, so hand back an empty recordset and keep counting.
                report['created'] += 1
                cache[key] = Model.browse()
                return cache[key]
            record = Model.create(dict(vals, code=code))
            report['created'] += 1
        cache[key] = record
        return record

    def action_import(self):
        """Walk every row and upsert the hierarchy it describes."""
        self.ensure_one()
        rows = self._htplus_rows()
        cache = {}
        report = {'created': 0, 'updated': 0, 'unchanged': 0}
        for number, row in enumerate(rows, start=2):
            factory = self._htplus_upsert(
                'htplus.factory', row.get('factory_code'),
                {'name': row.get('factory_name') or row.get('factory_code'),
                 'company_id': self.company_id.id},
                cache, report)
            if not row.get('factory_code'):
                raise UserError(_('Row %s has no factory code.', number))
            plant = self._htplus_upsert(
                'htplus.plant', row.get('plant_code'),
                {'name': row.get('plant_name') or row.get('plant_code'),
                 'factory_id': factory.id},
                cache, report)
            line = self._htplus_upsert(
                'htplus.line', row.get('line_code'),
                {'name': row.get('line_name') or row.get('line_code'),
                 'plant_id': plant.id},
                cache, report)
            workcenter = self._htplus_upsert(
                'mrp.workcenter', row.get('workcenter_code'),
                {'name': row.get('workcenter_name') or row.get('workcenter_code'),
                 'factory_id': factory.id, 'plant_id': plant.id, 'line_id': line.id,
                 'company_id': self.company_id.id},
                cache, report)
            self._htplus_upsert(
                'htplus.machine', row.get('machine_code'),
                {'name': row.get('machine_name') or row.get('machine_code'),
                 'workcenter_id': workcenter.id, 'line_id': line.id, 'plant_id': plant.id,
                 'company_id': self.company_id.id},
                cache, report)
        self.result = _(
            '%(rows)s row(s) read.\nCreated: %(created)s\nUpdated: %(updated)s\n'
            'Unchanged: %(unchanged)s%(dry)s',
            rows=len(rows), created=report['created'], updated=report['updated'],
            unchanged=report['unchanged'],
            dry=_('\n\nPreview only - nothing was written.') if self.dry_run else '',
        )
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
