from urllib.parse import urlparse

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ALLOWED_URL_SCHEMES = ('http', 'https')


class MenuBookmark(models.Model):
    _name = 'menu.bookmark'
    _description = 'Menu Bookmark'
    _order = 'sequence, name, id'

    name = fields.Char(required=True, translate=False)
    url = fields.Char(
        string='URL',
        required=True,
        help="Absolute http(s) URL, or a path relative to this Odoo instance "
             "such as /odoo/sales.",
    )
    target = fields.Selection(
        [('_self', 'Current Tab'), ('_blank', 'New Tab')],
        default='_self',
        required=True,
    )

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        index=True,
        ondelete='cascade',
        default=lambda self: self.env.user,
    )
    sequence = fields.Integer(default=10)

    _sql_constraints = [
        (
            'name_url_user_uniq',
            'unique(user_id, name, url)',
            'You already have a bookmark with this name and URL.',
        ),
    ]

    @api.constrains('url')
    def _check_url(self):
        """Validate that bookmark URLs use an allowed http(s) scheme or a same-instance relative path."""
        for bookmark in self:
            url = (bookmark.url or '').strip()
            # A relative path stays inside this instance and is always safe.
            if url.startswith('/') and not url.startswith('//'):
                continue
            scheme = urlparse(url).scheme.lower()
            if scheme not in ALLOWED_URL_SCHEMES:
                raise ValidationError(_(
                    "A bookmark URL must start with http://, https:// or / "
                    "(got: %(url)s).",
                    url=bookmark.url,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        """Strip surrounding whitespace from new bookmark URLs."""
        for vals in vals_list:
            if 'url' in vals and vals['url']:
                vals['url'] = vals['url'].strip()
        return super().create(vals_list)

    def write(self, vals):
        """Strip surrounding whitespace from bookmark URLs when they are updated."""
        if vals.get('url'):
            vals['url'] = vals['url'].strip()
        return super().write(vals)
