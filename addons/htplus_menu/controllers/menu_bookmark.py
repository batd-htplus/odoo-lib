import logging

from odoo import http
from odoo.exceptions import ValidationError
from odoo.http import request, route

_logger = logging.getLogger(__name__)

BOOKMARK_FIELDS = ['id', 'name', 'url', 'target', 'sequence']
BOOKMARK_LIMIT = 200


class MenuBookmarkController(http.Controller):
    """Routes live under /htplus_menu/ rather than /web/, which belongs to core
    Odoo and could collide with a future upstream endpoint.

    `type='json'` is correct for Odoo 18 - the `jsonrpc` routing type only
    exists from Odoo 19 onwards.
    """

    @route(
        '/htplus_menu/bookmark/data',
        methods=['POST'],
        type='json',
        auth='user',
        readonly=True,
    )
    def bookmark_data(self):
        """Return the bookmarks visible to the calling user for the sidebar.

        Returns:
            list of dict: bookmark fields for the menu.
        """
        return request.env['menu.bookmark'].search_read(
            domain=[],
            fields=BOOKMARK_FIELDS,
            limit=BOOKMARK_LIMIT,
        )

    @route(
        '/htplus_menu/bookmark/add',
        methods=['POST'],
        type='json',
        auth='user',
    )
    def bookmark_add(self, name=None, url=None, target='_self'):
        """Create a bookmark for the calling user.

        Returns:
            dict: success flag with bookmark data, or an error for the client.
        """
        name = (name or '').strip()
        url = (url or '').strip()
        if not name or not url:
            return {'success': False, 'error': 'missing_values'}
        if target not in ('_self', '_blank'):
            target = '_self'

        Bookmark = request.env['menu.bookmark']
        name = name[:128]

        existing = Bookmark.search([('name', '=', name), ('url', '=', url)], limit=1)
        if existing:
            return {
                'success': True,
                'existing': True,
                'bookmark': existing.read(BOOKMARK_FIELDS)[0],
            }

        try:
            bookmark = Bookmark.create({
                'name': name,
                'url': url,
                'target': target,
                # Never trust a client-supplied user_id; bind to the session.
                'user_id': request.env.uid,
            })
        except ValidationError as error:
            return {'success': False, 'error': str(error)}

        return {
            'success': True,
            'bookmark': bookmark.read(BOOKMARK_FIELDS)[0],
        }
