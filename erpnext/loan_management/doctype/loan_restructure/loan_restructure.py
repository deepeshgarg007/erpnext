# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, add_months, date_diff, flt, get_last_day, getdate

from erpnext.controllers.accounts_controller import AccountsController
from erpnext.loan_management.doctype.loan_repayment.loan_repayment import get_amounts
from erpnext.loan_management.doctype.loan_repayment_schedule.loan_repayment_schedule import (
	add_single_month,
	get_monthly_repayment_amount,
)


class LoanRestructure(AccountsController):
	def validate(self):
		self.update_overdue_amounts()
		self.validate_branch_limit()
		self.validate_waiver_amount()
		self.calculate_new_loan_amount()
		self.validate_new_loan_amount()
		self.update_restructured_loan_details()
		self.make_repayment_schedule()

	def on_submit(self):
		self.restructure_loan()
		self.make_loan_adjustment_for_waiver()
		self.make_loan_adjustment_for_capitalization()
		self.mark_loan_as_npa()
		self.update_totals()

	def on_cancel(self):
		self.cancel_loan_adjustments()

	def update_overdue_amounts(self):
		amounts = {
			"penalty_amount": 0.0,
			"interest_amount": 0.0,
			"pending_principal_amount": 0.0,
			"payable_principal_amount": 0.0,
			"payable_amount": 0.0,
			"unaccrued_interest": 0.0,
			"due_date": "",
		}

		amounts = get_amounts(amounts, self.loan, self.restructure_date)

		self.pending_principal_amount = amounts.get("pending_principal_amount")
		self.total_overdue_amount = amounts.get("payable_amount")
		self.principal_overdue = amounts.get("payable_principal_amount")
		self.interest_overdue = amounts.get("interest_amount")
		self.penalty_overdue = amounts.get("penalty_amount")
		self.charges_overdue = amounts.get("charges_amount")

	def validate_branch_limit(self):
		if self.branch:
			branch_limit = frappe.db.get_value(
				"Loan Restructure Limit",
				{
					"branch": self.branch,
					"from_date": ["<=", self.restructure_date],
					"to_date": [">=", self.restructure_date],
				},
				"limit_percent",
			)

			outstanding_pos = frappe.db.get_all(
				"Loan",
				{"branch": self.branch, "docstatus": 1, "status": "Disbursed"},
				["sum(total_payment_amount) - sum(total_principal_paid) - sum(total_interest_payable)"],
			)

			if branch_limit:
				limit_amount = outstanding_pos * flt(branch_limit) / 100
				utilized_limit = frappe.db.get_value(
					"Loan Restructure", {"branch": self.branch, "docstatus": 1}, ["sum(pending_principal_amount)"]
				)

				if self.pending_principal_amount > (limit_amount - utilized_limit):
					frappe.throw(_("Branch Restructure Limit is exceeded"))

	def validate_waiver_amount(self):
		if flt(self.principal_waiver_amount) > flt(self.principal_overdue):
			frappe.throw(_("Principal Waiver Amount cannot be greater than overdue principal"))

		if flt(self.interest_waiver_amount) > flt(self.interest_overdue):
			frappe.throw(_("Interest Waiver Amount cannot be greater than overdue interest"))

		if flt(self.other_charges_waiver) > flt(self.charges_overdue):
			frappe.throw(_("Other Charges Waiver cannot be greater than overdue charges"))

	def calculate_new_loan_amount(self):
		self.new_loan_amount = (
			flt(self.pending_principal_amount)
			- flt(self.principal_waiver_amount)
			- flt(self.interest_waiver_amount)
			- flt(self.other_charges_waiver)
		)

		if self.capitalize_other_charges:
			self.new_loan_amount += self.charges_overdue

		if self.capitalize_penal_interest:
			self.new_loan_amount += self.penalty_overdue

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

	def make_repayment_schedule(self):
		if not self.repayment_start_date:
			self.repayment_start_date = self.restructure_date

		schedule_type_details = frappe.db.get_value(
			"Loan Type", self.loan_type, ["repayment_schedule_type", "repayment_date_on"], as_dict=1
		)

		self.repayment_schedule = []
		payment_date = self.repayment_start_date
		balance_amount = self.new_loan_amount

		while balance_amount > 0:
			(
				interest_amount,
				principal_amount,
				balance_amount,
				total_payment,
				days,
			) = self.get_schedule_amounts(
				payment_date,
				balance_amount,
				schedule_type_details.repayment_schedule_type,
				schedule_type_details.repayment_date_on,
			)

			if schedule_type_details.repayment_schedule_type == "Pro-rated calendar months":
				next_payment_date = get_last_day(payment_date)
				if schedule_type_details.repayment_date_on == "Start of the next month":
					next_payment_date = add_days(next_payment_date, 1)

				payment_date = next_payment_date

			self.add_repayment_schedule_row(
				payment_date, principal_amount, interest_amount, total_payment, balance_amount, days
			)

			if (
				self.repayment_method == "Repay Over Number of Periods"
				and len(self.get("repayment_schedule")) >= self.new_repayment_period_in_months
			):
				self.get("repayment_schedule")[-1].principal_amount += balance_amount
				self.get("repayment_schedule")[-1].balance_loan_amount = 0
				self.get("repayment_schedule")[-1].total_payment = (
					self.get("repayment_schedule")[-1].interest_amount
					+ self.get("repayment_schedule")[-1].principal_amount
				)
				balance_amount = 0

			if (
				schedule_type_details.repayment_schedule_type
				in ["Monthly as per repayment start date", "Monthly as per cycle date"]
				or schedule_type_details.repayment_date_on == "End of the current month"
			):
				next_payment_date = add_single_month(payment_date)
				payment_date = next_payment_date

	def get_schedule_amounts(self, payment_date, balance_amount, schedule_type, repayment_date_on):
		if schedule_type == "Monthly as per repayment start date":
			days = 1
			months = 12
		else:
			expected_payment_date = get_last_day(payment_date)
			if repayment_date_on == "Start of the next month":
				expected_payment_date = add_days(expected_payment_date, 1)

			if schedule_type == "Monthly as per cycle date":
				days = date_diff(add_months(payment_date, 1), payment_date)
				months = 365
			elif expected_payment_date == payment_date:
				# using 30 days for calculating interest for all full months
				days = 30
				months = 365
			else:
				days = date_diff(get_last_day(payment_date), payment_date)
				months = 365

		interest_amount = flt(balance_amount * flt(self.new_rate_of_interest) * days / (months * 100))
		principal_amount = self.new_monthly_repayment_amount - interest_amount
		balance_amount = flt(balance_amount + interest_amount - self.new_monthly_repayment_amount)
		if balance_amount < 0:
			principal_amount += balance_amount
			balance_amount = 0.0

		total_payment = principal_amount + interest_amount

		return interest_amount, principal_amount, balance_amount, total_payment, days

	def add_repayment_schedule_row(
		self, payment_date, principal_amount, interest_amount, total_payment, balance_loan_amount, days
	):
		self.append(
			"repayment_schedule",
			{
				"number_of_days": days,
				"payment_date": payment_date,
				"principal_amount": principal_amount,
				"interest_amount": interest_amount,
				"total_payment": total_payment,
				"balance_loan_amount": balance_loan_amount,
			},
		)

	def mark_loan_as_npa(self):
		frappe.db.set_value("Loan", self.loan, "is_npa", 1)

	def restructure_loan(self):
		# Mark Loan as NPA
		frappe.db.set_value("Loan", self.loan, {"is_npa": 1, "manual_npa": 1})

		# Mark Old Repayment Schedule as Restructured
		frappe.db.set_value(
			"Loan Repayment Schedule",
			{"loan": self.loan, "status": ("!=", "Restructured")},
			"status",
			"Restructured",
		)

		self.make_repayment_new_loan_repayment_schedule()

	def make_repayment_new_loan_repayment_schedule(self):
		schedule = frappe.get_doc(
			{
				"doctype": "Loan Repayment Schedule",
				"loan": self.loan,
				"repayment_method": self.new_repayment_method,
				"repayment_start_date": self.repayment_start_date,
				"repayment_periods": self.new_repayment_period_in_months,
				"loan_amount": self.new_loan_amount,
				"loan_type": self.loan_type,
				"rate_of_interest": self.new_rate_of_interest,
			}
		).insert()

		schedule.submit()

	def update_totals(self):
		total_payment = 0
		total_interest_payable = 0

		schedule = frappe.get_doc(
			"Loan Repayment Schedule", {"loan": self.name, "docstatus": 1, "status": "Disbursed"}
		)
		for data in schedule.repayment_schedule:
			total_payment += data.total_payment
			total_interest_payable += data.interest_amount
		else:
			total_payment = self.loan_amount

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
		principal_waiver_account = frappe.db.get_value(
			"Loan Type", self.loan_type, "principal_waiver_account"
		)
		make_loan_balance_entry(
			self.loan,
			self.principal_waiver_amount,
			principal_waiver_account,
			"Credit Adjustment",
			posting_date=self.restructure_date,
			reference_name=self.name,
			reference_doctype="Loan Restructure",
		)

		interest_waiver_account = frappe.db.get_value(
			"Loan Type", self.loan_type, "interest_waiver_account"
		)
		make_loan_balance_entry(
			self.loan,
			self.interest_waiver_amount,
			interest_waiver_account,
			"Credit Adjustment",
			posting_date=self.restructure_date,
			reference_name=self.name,
			reference_doctype="Loan Restructure",
		)

		penalty_waiver_account = frappe.db.get_value(
			"Loan Type", self.loan_type, "principal_waiver_account"
		)
		make_loan_balance_entry(
			self.loan,
			self.other_charges_waiver,
			penalty_waiver_account,
			"Credit Adjustment",
			posting_date=self.restructure_date,
			reference_name=self.name,
			reference_doctype="Loan Restructure",
		)

	def cancel_loan_adjustments(self):
		for d in frappe.get_all(
			"Loan Balance Adjustment",
			{"reference_document_type": "Loan Restructure", "reference_name": self.name},
		):
			doc = frappe.get_doc("Loan Balance Adjustment", d.name)
			doc.cancel()

	def make_loan_adjustment_for_capitalization(self):
		if self.capitalize_normal_interest:
			interest_capitalization_account = frappe.db.get_value(
				"Loan Type", self.loan_type, "interest_capitalization_account"
			)
			make_loan_balance_entry(
				self.loan,
				self.interest_overdue,
				interest_capitalization_account,
				"Debit Adjustment",
				posting_date=self.restructure_date,
				reference_name=self.name,
				reference_doctype="Loan Restructure",
			)

		if self.capitalize_penal_interest:
			penalty_capitalization_account = frappe.db.get_value(
				"Loan Type", self.loan_type, "penalty_capitalization_account"
			)
			make_loan_balance_entry(
				self.loan,
				self.interest_overdue,
				penalty_capitalization_account,
				"Debit Adjustment",
				posting_date=self.restructure_date,
				reference_name=self.name,
				reference_doctype="Loan Restructure",
			)

		if self.capitalize_other_charges:
			other_charges_capitalization_account = frappe.db.get_value(
				"Loan Type", self.loan_type, "other_charges_capitalization_account"
			)
			make_loan_balance_entry(
				self.loan,
				self.interest_overdue,
				other_charges_capitalization_account,
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
	la.insert()
	la.submit()
