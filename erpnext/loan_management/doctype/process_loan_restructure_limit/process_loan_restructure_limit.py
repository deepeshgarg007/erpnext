# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document

from erpnext.loan_management.doctype.loan_restructure.loan_restructure import (
	calculate_monthly_restructure_limit,
)


class ProcessLoanRestructureLimit(Document):
	def on_submit(self):
		calculate_monthly_restructure_limit(posting_date=self.posting_date)
