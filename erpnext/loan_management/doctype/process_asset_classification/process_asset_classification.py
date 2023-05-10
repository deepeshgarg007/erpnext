# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class ProcessAssetClassification(Document):
	def on_submit(self):
		from erpnext.loan_management.doctype.loan.loan import update_days_past_due_in_loans

		update_days_past_due_in_loans(
			posting_date=self.posting_date,
			loan_type=self.loan_type,
			loan_name=self.loan,
			event_type=self.event_type,
		)


def create_process_asset_classification(
	posting_date=None, loan_type=None, loan=None, event_type=None
):
	posting_date = posting_date or getdate()
	asset_classification = frappe.new_doc("Process Asset Classification")
	asset_classification.posting_date = posting_date
	asset_classification.loan_type = loan_type
	asset_classification.event_type = event_type or "Scheduled Job"
	asset_classification.loan = loan
	asset_classification.submit()
