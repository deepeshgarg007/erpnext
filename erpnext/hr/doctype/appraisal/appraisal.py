# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

from __future__ import unicode_literals
import frappe

from frappe.utils import flt, getdate

from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.model.document import Document
from erpnext.hr.utils import set_employee_name
from six import iteritems

class Appraisal(Document):
	def validate(self):
		if not self.status:
			self.status = "Draft"

		# if not self.goals:
		# 	frappe.throw(_("Goals cannot be empty"))

		set_employee_name(self)
		self.validate_dates()
		self.validate_existing_appraisal()
		# self.calculate_total()
		self.calculate_hi_po()
		self.update_managers_rating()

	def on_update_after_submit(self):
		self.update_based_on_managers_rating()

	def get_employee_name(self):
		self.employee_name = frappe.db.get_value("Employee", self.employee, "employee_name")
		return self.employee_name

	def calculate_hi_po(self, after_submit=0):

		result_map = {
			'A': 3,
			'B': 2,
			'C': 1
		}

		leadership_map = {
			'+': 3,
			'/': 2,
			'-': 1
		}

		inv_result_map = {v: k for k, v in iteritems(result_map)}
		inv_leadership_map = {v: k for k, v in iteritems(leadership_map)}

		rating_list = []
		leadership_list= []

		for rate in self.get('personal_rating'):
			rating_list.append(result_map.get(rate.result))
			leadership_list.append(leadership_map.get(rate.leadership))

		self.results = inv_result_map.get(sum(rating_list)//len(rating_list))
		self.leadership = inv_leadership_map.get(sum(leadership_list)//len(leadership_list))

		if self.results in ('A', 'B') and self.leadership in ('/', '+'):
			self.hi_po = 'Yes'
		else:
			self.hi_po = 'No'

	def update_managers_rating(self):
		self.set('managers_rating', [])
		for rate in self.get('personal_rating'):
				self.append('managers_rating', {
					'kra': rate.kra
				})

	def update_based_on_managers_rating(self):
		rating_list = []
		leadership_list= []

		result_map = {
			'A': 3,
			'B': 2,
			'C': 1
		}

		leadership_map = {
			'+': 3,
			'/': 2,
			'-': 1
		}

		inv_result_map = {v: k for k, v in iteritems(result_map)}
		inv_leadership_map = {v: k for k, v in iteritems(leadership_map)}

		for rate in self.get('managers_rating'):
			if rate.result:
				rating_list.append(result_map.get(rate.result))
			if rate.leadership:
				leadership_list.append(leadership_map.get(rate.leadership))

		if rating_list:
			results = inv_result_map.get(sum(rating_list)//len(rating_list))

		if leadership_list:
			leadership = inv_leadership_map.get(sum(leadership_list)//len(leadership_list))

		if results in ('A', 'B') and leadership in ('/', '+'):
			hi_po = 'Yes'
		else:
			hi_po = 'No'

		frappe.db.set_value("Appraisal", self.name, {
			'results': results,
			'leadership': leadership,
			'hi_po': hi_po
		})

		self.reload()

	def validate_dates(self):
		if getdate(self.start_date) > getdate(self.end_date):
			frappe.throw(_("End Date can not be less than Start Date"))

	def validate_existing_appraisal(self):
		chk = frappe.db.sql("""select name from `tabAppraisal` where employee=%s
			and (status='Submitted' or status='Completed')
			and ((start_date>=%s and start_date<=%s)
			or (end_date>=%s and end_date<=%s))""",
			(self.employee,self.start_date,self.end_date,self.start_date,self.end_date))
		if chk:
			frappe.throw(_("Appraisal {0} created for Employee {1} in the given date range").format(chk[0][0], self.employee_name))

	def calculate_total(self):
		total, total_w  = 0, 0
		for d in self.get('goals'):
			if d.score:
				d.score_earned = flt(d.score) * flt(d.per_weightage) / 100
				total = total + d.score_earned
			total_w += flt(d.per_weightage)

		if int(total_w) != 100:
			frappe.throw(_("Total weightage assigned should be 100%. It is {0}").format(str(total_w) + "%"))

		if frappe.db.get_value("Employee", self.employee, "user_id") != \
				frappe.session.user and total == 0:
			frappe.throw(_("Total cannot be zero"))

		self.total_score = total

	def on_submit(self):
		frappe.db.set(self, 'status', 'Submitted')

	def on_cancel(self):
		frappe.db.set(self, 'status', 'Cancelled')

@frappe.whitelist()
def fetch_appraisal_template(source_name, target_doc=None):
	target_doc = get_mapped_doc("Appraisal Template", source_name, {
		"Appraisal Template": {
			"doctype": "Appraisal",
		},
		"Appraisal Template Goal": {
			"doctype": "Appraisal Goal",
		}
	}, target_doc)

	return target_doc
