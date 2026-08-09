from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HtplusFactoryHoliday(models.Model):
    """Plant/factory shutdown day — syncs to resource.calendar.leaves (MRP capacity)."""

    _name = 'htplus.factory.holiday'
    _description = 'Factory Holiday'
    _order = 'date_from desc'

    name = fields.Char(required=True)
    factory_id = fields.Many2one('htplus.factory', required=True, ondelete='cascade')
    date_from = fields.Datetime(required=True, string='Start')
    date_to = fields.Datetime(required=True, string='End')
    resource_leave_id = fields.Many2one(
        'resource.calendar.leaves', string='Calendar Leave', copy=False, readonly=True)
    company_id = fields.Many2one(
        related='factory_id.company_id', store=True, readonly=True)
    active = fields.Boolean(default=True)

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        """Validate that the holiday end is not before its start."""
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_to < rec.date_from:
                raise ValidationError(_('Holiday end must be on or after the start.'))

    def _sync_resource_leave(self):
        """Create or update the matching resource calendar leave for each holiday."""
        Leave = self.env['resource.calendar.leaves']
        for rec in self:
            calendar = rec.factory_id._ensure_resource_calendar()
            vals = {
                'name': rec.name,
                'calendar_id': calendar.id,
                'date_from': rec.date_from,
                'date_to': rec.date_to,
                'time_type': 'leave',
                'company_id': rec.company_id.id,
                'htplus_factory_holiday_id': rec.id,
            }
            if rec.resource_leave_id:
                rec.resource_leave_id.write(vals)
            else:
                leave = Leave.create(vals)
                rec.with_context(htplus_skip_leave_sync=True).write({
                    'resource_leave_id': leave.id,
                })

    @api.model_create_multi
    def create(self, vals_list):
        """Create the holidays and sync their resource calendar leaves."""
        records = super().create(vals_list)
        records._sync_resource_leave()
        return records

    def write(self, vals):
        """Re-sync the resource calendar leaves when holiday details change."""
        res = super().write(vals)
        if not self.env.context.get('htplus_skip_leave_sync'):
            if any(k in vals for k in ('name', 'factory_id', 'date_from', 'date_to', 'active')):
                self.filtered('active')._sync_resource_leave()
        return res

    def unlink(self):
        """Delete the linked calendar leaves when the holidays are removed."""
        leaves = self.mapped('resource_leave_id')
        res = super().unlink()
        leaves.unlink()
        return res
