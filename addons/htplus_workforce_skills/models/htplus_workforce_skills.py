from odoo import models


class HtplusWorkforceAssignment(models.Model):
    """Skill matching for workforce assignment.

    Only meaningful once hr_skills is installed, so the check lives here rather
    than in htplus_workforce, which qualifies everybody by default.
    """

    _inherit = 'htplus.workforce.assignment'

    def _htplus_skill_ok_employee_ids(self, employees):
        """Return the employees holding at least one production skill.

        Args:
            employees: hr.employee recordset to evaluate.

        Returns:
            Set of qualified employee ids, or None when the production skill
            taxonomy is absent - an assignment must not be blocked by a missing
            configuration.
        """
        production_type = self.env.ref(
            'htplus_workforce_skills.hr_skill_type_production', raise_if_not_found=False,
        )
        if not production_type:
            return None
        return set(
            self.env['hr.employee.skill'].search([
                ('employee_id', 'in', employees.ids),
                ('skill_id.skill_type_id', '=', production_type.id),
            ]).mapped('employee_id').ids
        )
