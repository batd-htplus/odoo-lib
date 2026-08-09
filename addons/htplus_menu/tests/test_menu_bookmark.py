from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestMenuBookmark(TransactionCase):

    @classmethod
    def setUpClass(cls):
        """Create Alice and Bob plus a bookmark owned by Alice."""
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        group_user = cls.env.ref('base.group_user')
        cls.alice = Users.create({
            'name': 'Alice',
            'login': 'htplus_menu_alice',
            'groups_id': [(6, 0, [group_user.id])],
        })
        cls.bob = Users.create({
            'name': 'Bob',
            'login': 'htplus_menu_bob',
            'groups_id': [(6, 0, [group_user.id])],
        })
        cls.alice_bookmark = cls.env['menu.bookmark'].create({
            'name': 'Alice dashboard',
            'url': '/odoo/sales',
            'user_id': cls.alice.id,
        })

    # --- Record rule ---------------------------------------------------------

    def test_owner_sees_own_bookmark(self):
        """A user always sees their own bookmarks."""
        found = self.env['menu.bookmark'].with_user(self.alice).search([])
        self.assertIn(self.alice_bookmark, found)

    def test_other_user_cannot_read_bookmark(self):
        """Regression: with no record rule the ACL let Bob read and edit
        Alice's bookmarks."""
        found = self.env['menu.bookmark'].with_user(self.bob).search([])
        self.assertNotIn(self.alice_bookmark, found)

    def test_other_user_cannot_write_bookmark(self):
        """Bob cannot edit Alice's bookmark."""
        with self.assertRaises(AccessError):
            self.alice_bookmark.with_user(self.bob).write({'name': 'hijacked'})

    def test_other_user_cannot_unlink_bookmark(self):
        """Bob cannot delete Alice's bookmark."""
        with self.assertRaises(AccessError):
            self.alice_bookmark.with_user(self.bob).unlink()

    def test_admin_sees_every_bookmark(self):
        """Admins bypass the owner-only rule and see every bookmark."""
        found = self.env['menu.bookmark'].search([])
        self.assertIn(self.alice_bookmark, found)

    # --- URL validation ------------------------------------------------------

    def test_javascript_url_rejected(self):
        """Stored XSS vector: the URL ends up in window.open()."""
        for bad_url in (
            'javascript:alert(document.cookie)',
            'JavaScript:alert(1)',
            '  javascript:alert(1)  ',
            'data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==',
            'vbscript:msgbox(1)',
            'file:///etc/passwd',
        ):
            with self.subTest(url=bad_url), self.assertRaises(ValidationError):
                self.env['menu.bookmark'].create({
                    'name': 'Bad',
                    'url': bad_url,
                    'user_id': self.alice.id,
                })

    def test_valid_urls_accepted(self):
        """http(s) URLs and same-instance relative paths are accepted."""
        for good_url in (
            'https://example.com/report',
            'http://example.com',
            '/odoo/inventory',
        ):
            with self.subTest(url=good_url):
                bookmark = self.env['menu.bookmark'].create({
                    'name': f'ok {good_url}',
                    'url': good_url,
                    'user_id': self.alice.id,
                })
                self.assertTrue(bookmark.id)

    def test_protocol_relative_url_rejected(self):
        """`//evil.com` looks relative but leaves the origin."""
        with self.assertRaises(ValidationError):
            self.env['menu.bookmark'].create({
                'name': 'Protocol relative',
                'url': '//evil.example.com',
                'user_id': self.alice.id,
            })

    def test_url_is_stripped_on_write(self):
        """Whitespace is stripped from URLs when a bookmark is updated."""
        self.alice_bookmark.write({'url': '  /odoo/purchase  '})
        self.assertEqual(self.alice_bookmark.url, '/odoo/purchase')

    # --- Model behaviour -----------------------------------------------------

    def test_deleting_user_cascades(self):
        """Deleting a user cascades to their bookmarks (user_id defaults to ondelete='restrict')."""
        bookmark_id = self.alice_bookmark.id
        self.alice.unlink()
        self.assertFalse(self.env['menu.bookmark'].browse(bookmark_id).exists())

    def test_default_user_is_current_user(self):
        """A bookmark created without user_id binds to the session user."""
        bookmark = self.env['menu.bookmark'].with_user(self.bob).create({
            'name': 'Bob bookmark',
            'url': '/odoo/settings',
        })
        self.assertEqual(bookmark.user_id, self.bob)
