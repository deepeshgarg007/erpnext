# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate

from erpnext.controllers.accounts_controller import AccountsController
from erpnext.loan_management.doctype.loan_repayment.loan_repayment import calculate_amounts
from erpnext.loan_management.doctype.loan_repayment_schedule.loan_repayment_schedule import (
	get_monthly_repayment_amount,
)


class LoanRestructure(AccountsController):
	def validate(self):
		self.validate_restructure_date()
		self.set_completed_tenure()
		self.update_overdue_amounts()
		self.validate_branch_limit()
		self.allocate_security_deposit()
		self.validate_waiver_amount()
		self.calculate_balance_amounts()
		self.set_missing_values()
		self.validate_repayment_start_date()
		self.calculate_new_loan_amount()
		self.validate_new_loan_amount()
		self.add_restructure_charges()
		self.update_restructured_loan_details()
		if not self.is_new():
			self.make_update_draft_loan_repayment_schedule()

	def validate_restructure_date(self):
		max_due_date = frappe.db.get_value("Loan Interest Accrual", {"loan": self.loan}, "max(due_date)")
		if getdate(self.restructure_date) < getdate(max_due_date):
			frappe.throw(_("Restructure Date cannot be before last due date"))

	def after_insert(self):
		self.make_update_draft_loan_repayment_schedule()

	def set_status(self, status=None):
		if self.docstatus == 1 and not status:
			self.db_set("status", "Initiated")
		else:
			self.db_set("status", status)

	def allocate_security_deposit(self):
		deposit_amount = flt(self.available_security_deposit)
		self.principal_adjusted = 0
		self.adjusted_interest_amount = 0
		self.adjusted_other_charges = 0

		if deposit_amount > 0:
			# Adjust Principal
			deposit_amount = self.adjust_component(
				deposit_amount, "principal_overdue", "principal_adjusted"
			)

		if deposit_amount > 0:
			# Adjust Interest
			deposit_amount = self.adjust_component(
				deposit_amount, "interest_overdue", "adjusted_interest_amount"
			)

		if deposit_amount > 0:
			# Adjust Unaccrued Interest
			deposit_amount = self.adjust_component(
				deposit_amount, "unaccrued_interest", "adjusted_unaccrued_interest"
			)

		if deposit_amount > 0:
			# Adjust Penalty
			deposit_amount = self.adjust_component(
				deposit_amount, "penalty_overdue", "adjusted_penalty_amount"
			)

	def calculate_balance_amounts(self):
		self.balance_principal = flt(self.principal_overdue) - flt(self.principal_adjusted)
		self.balance_interest_amount = (
			flt(self.interest_overdue)
			- flt(self.adjusted_interest_amount)
			- flt(self.interest_waiver_amount)
		)

		self.balance_unaccrued_interest = (
			flt(self.unaccrued_interest)
			- flt(self.adjusted_unaccrued_interest)
			- flt(self.unaccrued_interest_waiver)
		)

		self.balance_penalty_amount = flt(self.penalty_overdue) - flt(self.penal_interest_waiver)
		self.balance_charges = flt(self.charges_overdue) - flt(self.other_charges_waiver)

	def validate_repayment_start_date(self):
		if getdate(self.repayment_start_date) < getdate(self.restructure_date):
			frappe.throw(_("Restructure Date cannot be after Repayment Start Date"))

	def set_missing_values(self):
		if not self.repayment_start_date:
			self.repayment_start_date = self.restructure_date

		if not self.new_rate_of_interest:
			self.new_rate_of_interest = self.old_rate_of_interest

		if not self.new_repayment_method:
			self.new_repayment_method = self.repayment_method

		if not self.new_repayment_period_in_months:
			self.new_repayment_period_in_months = self.old_tenure

	def set_completed_tenure(self):
		previous_repayment_schedule = frappe.db.get_value(
			"Loan Repayment Schedule", {"loan": self.loan, "docstatus": 1, "status": "Disbursed"}, "name"
		)

		self.completed_tenure = frappe.db.count(
			"Repayment Schedule", filters={"parent": previous_repayment_schedule, "is_accrued": 1}
		)

	def add_restructure_charges(self):
		self.restructure_charges = 0

		for charge in frappe.get_all(
			"Loan Charges",
			filters={"parent": self.loan_type, "event": "Restructure"},
			fields=["charge_type", "charge_based_on", "amount", "percentage"],
		):
			if charge.charge_based_on == "Percentage":
				amount = flt(self.new_loan_amount) * flt(charge.percentage) / 100
			else:
				amount = flt(charge.amount)

			self.restructure_charges += amount

	def calculate_new_loan_amount(self):
		self.new_loan_amount = flt(self.pending_principal_amount) - flt(self.principal_adjusted)

		if self.treatment_of_normal_interest == "Add To First EMI":
			self.new_loan_amount += flt(self.balance_interest_amount)

		if self.treatment_of_normal_interest == "Add To First EMI":
			self.new_loan_amount += flt(self.balance_unaccrued_interest)

		if self.treatment_of_penal_interest == "Capitalize":
			self.new_loan_amount += flt(self.balance_penalty_amount)

		if self.treatment_of_other_charges == "Capitalize":
			self.new_loan_amount += flt(self.balance_charges)

	def adjust_component(self, amount_to_adjust, component, update_field):
		if amount_to_adjust > 0:
			if amount_to_adjust >= self.get(component):
				old_value = flt(self.get(update_field))
				self.set(update_field, flt(self.get(component)) + old_value)
				amount_to_adjust -= flt(self.get(component))
			else:
				old_value = flt(self.get(update_field))
				self.set(update_field, amount_to_adjust + old_value)
				amount_to_adjust = 0

		return amount_to_adjust

	def on_update_after_submit(self):
		if self.status == "Approved":
			self.restructure_loan()
			self.make_loan_adjustment_for_waiver()
			# self.make_interest_waiver()
			# self.make_loan_adjustment_for_capitalization()
			self.update_totals()
			self.update_repayment_schedule_status(status="Disbursed")
			self.update_security_deposit_amount()
			self.update_branch_limit()
			self.update_restructure_count()
			self.make_restructure_charges_invoice()
		elif self.status == "Rejected":
			self.update_repayment_schedule_status(status="Rejected")
			# self.update_branch_limit(cancel=1)

	def update_security_deposit_amount(self, cancel=0):
		allocated_amount_details = frappe.db.get_value(
			"Loan Security Deposit",
			{
				"loan": self.loan,
			},
			["name", "allocated_amount"],
			as_dict=1,
		)

		current_allocated_amount = (
			flt(self.principal_adjusted)
			+ flt(self.adjusted_interest_amount)
			+ flt(self.adjusted_unaccrued_interest)
		)

		if cancel:
			current_allocated_amount = -1 * current_allocated_amount

		final_allocated_amount = current_allocated_amount + flt(
			allocated_amount_details.allocated_amount
		)
		frappe.db.set_value(
			"Loan Security Deposit",
			allocated_amount_details.name,
			"allocated_amount",
			final_allocated_amount,
		)

	def update_branch_limit(self, cancel=1):
		if self.branch:
			# Get Latest Limit Log
			available_limit = frappe.db.get_all(
				"Loan Restructure Limit Log",
				{
					"branch": self.branch,
					"company": self.company,
				},
				["name", "available_limit"],
				order_by="date desc",
				limit=1,
			)[0]

			loan_amount = self.new_loan_amount
			if cancel:
				loan_amount = -1 * loan_amount

			# Update Limit Log
			if self.status == "Initiated":
				frappe.db.set_value(
					"Loan Restructure Limit Log",
					available_limit.name,
					{
						"in_process_limit": flt(available_limit.available_limit) + loan_amount,
						"available_limit": flt(available_limit.available_limit) - loan_amount,
					},
				)
			elif self.status == "Approved":
				frappe.db.set_value(
					"Loan Restructure Limit Log",
					available_limit.name,
					{
						"in_process_limit": flt(available_limit.available_limit) - loan_amount,
						"utilized_limit": flt(available_limit.utilized_limit) + loan_amount,
					},
				)

	def update_restructure_count(self, cancel=0):
		increment_count = 1
		if cancel:
			increment_count = 0

		frappe.db.set_value(
			"Loan", self.loan, "loan_restructure_count", self.current_restructure_count + increment_count
		)

	def make_restructure_charges_invoice(self):
		if self.applicant_type == "Customer":

			si = frappe.new_doc("Sales Invoice")
			si.customer = self.applicant

			for charge in frappe.get_all(
				"Loan Charges",
				filters={"parent": self.loan_type, "event": "Restructure"},
				fields=["charge_type", "charge_based_on", "amount", "percentage"],
			):

				si.append(
					"items",
					{
						"item_code": charge.charge_type,
						"qty": 1,
						"rate": charge.amount
						if charge.charge_based_on == "Fixed Amount"
						else flt(self.new_loan_amount) * flt(charge.percentage) / 100,
					},
				)

			si.loan = self.loan
			self.due_date = self.restructure_date
			si.save()
			si.submit()

	def update_repayment_schedule_status(self, status):
		if status == "Initiated":
			draft_schedule = frappe.db.get_value(
				"Loan Repayment Schedule", {"loan_restructure": self.name, "docstatus": 0}, "name"
			)
			schedule = frappe.get_doc("Loan Repayment Schedule", draft_schedule)
			schedule.status = "Initiated"
			schedule.save()
			schedule.submit()
		else:
			frappe.db.set_value(
				"Loan Repayment Schedule", {"loan_restructure": self.name}, "status", status
			)

	def on_submit(self):
		self.set_status()
		self.update_repayment_schedule_status(status="Initiated")
		self.update_branch_limit()

	def on_cancel(self):
		self.cancel_loan_adjustments()
		self.update_branch_limit(cancel=1)
		self.update_restructure_count(cancel=1)
		self.update_security_deposit_amount(cancel=1)

	def update_overdue_amounts(self):
		amounts = calculate_amounts(self.loan, self.restructure_date)

		self.pending_principal_amount = amounts.get("pending_principal_amount")
		self.total_overdue_amount = amounts.get("payable_amount")
		self.principal_overdue = amounts.get("payable_principal_amount")
		self.interest_overdue = amounts.get("interest_amount")
		self.penalty_overdue = amounts.get("penalty_amount")
		self.charges_overdue = amounts.get("total_charges_payable")
		self.unaccrued_interest = amounts.get("unaccrued_interest")
		self.available_security_deposit = amounts.get("available_security_deposit")

	def validate_branch_limit(self):
		if self.branch:
			# Get Latest Limit Log
			limit_details = frappe.db.get_all(
				"Loan Restructure Limit Log",
				{
					"branch": self.branch,
					"company": self.company,
				},
				["available_limit", "delinquent_available_limit"],
				order_by="date desc",
				limit=1,
			)

			if limit_details:
				available_limit = limit_details[0].get("available_limit")
				delinquent_available_limit = limit_details[0].get("delinquent_available_limit")

			if self.pending_principal_amount > available_limit:
				frappe.throw(_("Branch Limit Exceeded"))

			if self.pre_restructure_dpd > 0 and self.pending_principal_amount > delinquent_available_limit:
				frappe.throw(_("Delinquent Branch Limit Exceeded"))

	def validate_waiver_amount(self):
		if flt(self.interest_waiver_amount) > flt(self.interest_overdue) - flt(
			self.adjusted_interest_amount
		):
			frappe.throw(_("Interest Waiver Amount cannot be greater than overdue interest"))

		if flt(self.other_charges_waiver) > flt(self.charges_overdue) - flt(self.adjusted_other_charges):
			frappe.throw(_("Other Charges Waiver cannot be greater than overdue charges"))

	def update_restructured_loan_details(self):
		if not self.new_rate_of_interest:
			self.new_rate_of_interest = self.old_rate_of_interest

		if not self.new_repayment_method:
			self.new_repayment_method = frappe.db.get_value("Loan", self.loan, "repayment_method")

		if not self.new_repayment_period_in_months:
			self.new_repayment_period_in_months = frappe.db.get_value(
				"Loan", self.loan, "repayment_periods"
			)

		if self.new_repayment_method == "Repay Over Number of Periods":
			self.new_monthly_repayment_amount = get_monthly_repayment_amount(
				self.new_loan_amount, self.new_rate_of_interest, self.new_repayment_period_in_months
			)

	def validate_new_loan_amount(self):
		if self.new_loan_amount > self.disbursed_amount:
			frappe.throw(frappe._("New Loan Amount cannot be greater than original disbursed amount"))

	def restructure_loan(self):
		# Mark Loan as NPA
		frappe.db.set_value("Loan", self.loan, {"is_npa": 1, "manual_npa": 1})

		# Mark Old Repayment Schedule as Restructured
		loan_schedule = frappe.qb.DocType("Loan Repayment Schedule")

		frappe.qb.update(loan_schedule).set(loan_schedule.status, "Restructured").where(
			(loan_schedule.docstatus == 1)
			& (loan_schedule.loan == self.loan)
			& (loan_schedule.status == "Disbursed")
			& (
				(loan_schedule.loan_restructure.isnull())
				| (loan_schedule.loan_restructure == "")
				| (loan_schedule.loan_restructure != self.name)
			)
		).run()

	def make_update_draft_loan_repayment_schedule(self):
		adjusted_interest = 0

		if self.treatment_of_normal_interest == "Add To First EMI":
			adjusted_interest += self.balance_interest_amount

		if self.unaccrued_interest_treatment == "Add To First EMI":
			adjusted_interest += self.balance_unaccrued_interest

		draft_schedule = frappe.db.get_value(
			"Loan Repayment Schedule", {"loan_restructure": self.name, "docstatus": 0}, "name"
		)
		if draft_schedule:
			schedule = frappe.get_doc("Loan Repayment Schedule", draft_schedule)
			schedule.update(
				{
					"loan": self.loan,
					"repayment_periods": self.new_repayment_period_in_months,
					"repayment_method": self.new_repayment_method,
					"repayment_start_date": self.repayment_start_date,
					"posting_date": self.restructure_date,
					"loan_amount": self.new_loan_amount,
					"loan_type": self.loan_type,
					"rate_of_interest": self.new_rate_of_interest,
					"adjusted_interest": adjusted_interest,
				}
			)
			schedule.save()
		else:
			schedule = frappe.new_doc("Loan Repayment Schedule")
			schedule.loan = self.loan
			schedule.loan_restructure = self.name
			schedule.repayment_method = self.new_repayment_method
			schedule.repayment_start_date = self.repayment_start_date
			schedule.repayment_periods = self.new_repayment_period_in_months
			schedule.loan_amount = self.new_loan_amount
			schedule.loan_type = self.loan_type
			schedule.rate_of_interest = self.new_rate_of_interest
			schedule.posting_date = self.restructure_date
			schedule.adjusted_interest = adjusted_interest
			schedule.insert()

	def update_totals(self):
		total_payment = 0
		total_interest_payable = 0

		schedule = frappe.get_doc(
			"Loan Repayment Schedule",
			{"loan_restructure": self.name, "docstatus": 1, "status": "Initiated"},
		)
		for data in schedule.repayment_schedule:
			total_payment += data.total_payment
			total_interest_payable += data.interest_amount
		else:
			total_payment = self.new_loan_amount

		frappe.db.set_value(
			"Loan",
			self.loan,
			{
				"total_payment": total_payment,
				"total_interest_payable": total_interest_payable,
				"total_principal_paid": 0,
				"total_amount_paid": 0,
			},
		)

	def make_loan_adjustment_for_waiver(self):
		account_details = frappe.db.get_value(
			"Loan Type",
			self.loan_type,
			[
				"interest_waiver_account",
				"penalty_waiver_account",
				"charges_receivable_account",
				"charges_waiver_account",
				"interest_receivable_account",
				"penalty_receivable_account",
			],
			as_dict=1,
		)

		make_loan_balance_entry(
			self.loan,
			self.interest_waiver_amount,
			account_details.interest_waiver_account,
			"Credit Adjustment",
			posting_date=self.restructure_date,
			reference_name=self.name,
			reference_doctype="Loan Restructure",
			adjustment_receivable_account=account_details.interest_receivable_account,
		)

		make_loan_balance_entry(
			self.loan,
			self.penal_interest_waiver,
			account_details.penalty_waiver_account,
			"Credit Adjustment",
			posting_date=self.restructure_date,
			reference_name=self.name,
			reference_doctype="Loan Restructure",
			adjustment_receivable_account=account_details.penalty_receivable_account,
		)

		make_loan_balance_entry(
			self.loan,
			self.other_charges_waiver,
			account_details.charges_waiver_account,
			"Credit Adjustment",
			posting_date=self.restructure_date,
			reference_name=self.name,
			reference_doctype="Loan Restructure",
			adjustment_receivable_account=account_details.charges_receivable_account,
		)

	def make_interest_waiver(self):
		if self.interest_waiver_amount:
			interest_waived = self.interest_waived

			lia = frappe.qb.DocType("Loan Interest Accrual")
			accruals = (
				frappe.qb.from_(lia)
				.select(lia.name, lia.interest_amount, lia.paid_interest_amount)
				.where(lia.interest_amount - lia.paid_interest_amount > 0)
				.orderby(lia.due_date)
				.run(as_dict=1)
			)

			for accrual in accruals:
				if interest_waived > 0:
					if interest_waived > (accrual.interest_amount - accrual.paid_interest_amount):
						interest_waived -= accrual.interest_amount - accrual.paid_interest_amount
						frappe.db.set_value(
							"Loan Interest Accrual", accrual.name, "paid_interest_amount", accrual.interest_amount
						)

	def cancel_loan_adjustments(self):
		for d in frappe.get_all(
			"Loan Balance Adjustment",
			{"reference_document_type": "Loan Restructure", "reference_name": self.name},
		):
			doc = frappe.get_doc("Loan Balance Adjustment", d.name)
			doc.cancel()

	def make_loan_adjustment_for_capitalization(self):
		account_details = frappe.db.get_value(
			"Loan Type", self.loan_type, ["penalty_receivable_account", "charges_receivable_account", ""]
		)
		if self.treatment_of_penal_interest == "Capitalize":
			make_loan_balance_entry(
				self.loan,
				self.interest_overdue,
				account_details.penalty_receivable_account,
				"Debit Adjustment",
				posting_date=self.restructure_date,
				reference_name=self.name,
				reference_doctype="Loan Restructure",
			)

		if self.treatment_of_other_charges == "Capitalize":
			make_loan_balance_entry(
				self.loan,
				self.interest_overdue,
				account_details.other_charges_receivable_account,
				"Debit Adjustment",
				posting_date=self.restructure_date,
				reference_name=self.name,
				reference_doctype="Loan Restructure",
			)


def make_loan_balance_entry(
	loan,
	amount,
	account,
	adjustment_type,
	posting_date=None,
	reference_doctype=None,
	reference_name=None,
	adjustment_receivable_account=None,
):
	if not amount:
		return

	la = frappe.new_doc("Loan Balance Adjustment")
	la.loan = loan
	la.posting_date = posting_date or getdate()
	la.amount = amount
	la.adjustment_type = adjustment_type
	la.adjustment_account = account
	la.reference_document_type = reference_doctype
	la.reference_name = reference_name
	la.adjustment_receivable_account = adjustment_receivable_account
	la.insert()
	la.submit()
