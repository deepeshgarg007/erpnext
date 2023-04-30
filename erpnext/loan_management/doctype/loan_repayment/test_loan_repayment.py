# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import unittest

import frappe
from frappe.utils import flt

from erpnext.loan_management.doctype.loan.loan import update_days_past_due_in_loans
from erpnext.loan_management.doctype.loan.test_loan import (
	create_loan,
	create_loan_accounts,
	create_loan_type,
	create_repayment_entry,
	make_loan_disbursement_entry,
)
from erpnext.loan_management.doctype.process_loan_interest_accrual.process_loan_interest_accrual import (
	process_loan_interest_accrual_for_term_loans,
)


class TestLoanRepayment(unittest.TestCase):
	def setUp(self):
		create_loan_accounts()

		create_loan_type(
			loan_name="Term Loan With Cyclic Date",
			maximum_loan_amount=2000000,
			rate_of_interest=26,
			penalty_interest_rate=25,
			is_term_loan=1,
			grace_period_in_days=5,
			mode_of_payment="Cash",
			disbursement_account="Disbursement Account - _TC",
			payment_account="Payment Account - _TC",
			loan_account="Loan Account - _TC",
			interest_income_account="Interest Income Account - _TC",
			penalty_income_account="Penalty Income Account - _TC",
			repayment_method="Repay Over Number of Periods",
			repayment_periods=12,
			repayment_schedule_type="Monthly as per cycle date",
			days_past_due_threshold_for_npa=90,
		)

		self.applicant = frappe.db.get_value("Customer", {"name": "_Test Loan Customer"}, "name")

	def test_loan_repayment_as_per_npa_mark(self):
		loan = create_loan(
			applicant=self.applicant,
			loan_type="Term Loan With Cyclic Date",
			loan_amount=100000,
			repayment_method="Repay Over Number of Periods",
			repayment_periods=12,
			applicant_type="Customer",
			repayment_start_date="2023-01-05",
			posting_date="2023-01-01",
		)
		loan.submit()

		make_loan_disbursement_entry(loan.name, loan.loan_amount, disbursement_date="2023-02-01")
		process_loan_interest_accrual_for_term_loans(posting_date="2023-04-06")

		re = create_repayment_entry(loan.name, self.applicant, "2023-01-06", 1000, offset_based_on_npa=1)
		re.submit()

		lia_values = frappe.get_all(
			"Loan Interest Accrual",
			{"loan": loan.name},
			["paid_interest_amount", "paid_principal_amount"],
			order_by="due_date",
			limit=1,
		)[0]

		self.assertEqual(lia_values.paid_interest_amount, 1000.0)
		self.assertEqual(lia_values.paid_principal_amount, 0.0)

		update_days_past_due_in_loans(posting_date="2023-04-07")

		re = create_repayment_entry(
			loan.name, self.applicant, "2023-04-08", 20000, offset_based_on_npa=1
		)
		re.submit()

		lia_values = frappe.get_all(
			"Loan Interest Accrual",
			{"loan": loan.name},
			["paid_interest_amount", "paid_principal_amount", "payable_principal_amount"],
			order_by="due_date",
			limit=3,
		)

		paid_amount = 20000
		self.assertEqual(
			lia_values[0].paid_principal_amount, flt(lia_values[0].payable_principal_amount, 2)
		)
		self.assertEqual(lia_values[0].paid_interest_amount, 1000)
		paid_amount -= flt(lia_values[0].paid_principal_amount, 2)

		self.assertEqual(
			lia_values[1].paid_principal_amount, flt(lia_values[1].payable_principal_amount, 2)
		)
		paid_amount -= flt(lia_values[1].paid_principal_amount, 2)
		self.assertEqual(lia_values[1].paid_interest_amount, 0)

		self.assertEqual(flt(lia_values[2].paid_principal_amount, 2), flt(paid_amount, 2))
