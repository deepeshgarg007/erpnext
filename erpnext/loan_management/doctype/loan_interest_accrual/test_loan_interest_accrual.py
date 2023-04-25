# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import unittest

import frappe
from frappe.utils import add_to_date, date_diff, flt, get_datetime, get_first_day, nowdate

from erpnext.loan_management.doctype.loan.loan import update_days_past_due_in_loans
from erpnext.loan_management.doctype.loan.test_loan import (
	create_demand_loan,
	create_loan,
	create_loan_accounts,
	create_loan_application,
	create_loan_security,
	create_loan_security_price,
	create_loan_security_type,
	create_loan_type,
	make_loan_disbursement_entry,
)
from erpnext.loan_management.doctype.loan_application.loan_application import create_pledge
from erpnext.loan_management.doctype.loan_interest_accrual.loan_interest_accrual import (
	days_in_year,
)
from erpnext.loan_management.doctype.process_loan_interest_accrual.process_loan_interest_accrual import (
	process_loan_interest_accrual_for_demand_loans,
	process_loan_interest_accrual_for_term_loans,
)
from erpnext.selling.doctype.customer.test_customer import get_customer_dict


class TestLoanInterestAccrual(unittest.TestCase):
	def setUp(self):
		create_loan_accounts()

		create_loan_type(
			"Demand Loan",
			2000000,
			13.5,
			25,
			0,
			5,
			"Cash",
			"Disbursement Account - _TC",
			"Payment Account - _TC",
			"Loan Account - _TC",
			"Interest Income Account - _TC",
			"Penalty Income Account - _TC",
		)

		create_loan_type(
			loan_name="Term Loan With DPD",
			maximum_loan_amount=2000000,
			rate_of_interest=10,
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
			repayment_schedule_type="Monthly as per repayment start date",
			days_past_due_threshold_for_npa=90,
		)

		create_loan_security_type()
		create_loan_security()

		create_loan_security_price(
			"Test Security 1", 500, "Nos", get_datetime(), get_datetime(add_to_date(nowdate(), hours=24))
		)

		if not frappe.db.exists("Customer", "_Test Loan Customer"):
			frappe.get_doc(get_customer_dict("_Test Loan Customer")).insert(ignore_permissions=True)

		self.applicant = frappe.db.get_value("Customer", {"name": "_Test Loan Customer"}, "name")

	def test_loan_interest_accural(self):
		pledge = [{"loan_security": "Test Security 1", "qty": 4000.00}]

		loan_application = create_loan_application(
			"_Test Company", self.applicant, "Demand Loan", pledge
		)
		create_pledge(loan_application)
		loan = create_demand_loan(
			self.applicant, "Demand Loan", loan_application, posting_date=get_first_day(nowdate())
		)
		loan.submit()

		first_date = "2019-10-01"
		last_date = "2019-10-30"

		no_of_days = date_diff(last_date, first_date) + 1

		accrued_interest_amount = (loan.loan_amount * loan.rate_of_interest * no_of_days) / (
			days_in_year(get_datetime(first_date).year) * 100
		)
		make_loan_disbursement_entry(loan.name, loan.loan_amount, disbursement_date=first_date)
		process_loan_interest_accrual_for_demand_loans(posting_date=last_date)
		loan_interest_accural = frappe.get_doc("Loan Interest Accrual", {"loan": loan.name})

		self.assertEqual(flt(loan_interest_accural.interest_amount, 0), flt(accrued_interest_amount, 0))

	def test_dpd_calculation(self):
		loan = create_loan(
			applicant=self.applicant,
			loan_type="Term Loan With DPD",
			loan_amount=1200000,
			repayment_method="Repay Over Number of Periods",
			repayment_periods=12,
			applicant_type="Customer",
			repayment_start_date="2023-01-31",
			posting_date="2023-01-01",
		)
		loan.submit()

		make_loan_disbursement_entry(loan.name, loan.loan_amount, disbursement_date="2023-02-01")
		process_loan_interest_accrual_for_term_loans(posting_date="2023-02-01")
		update_days_past_due_in_loans(posting_date="2023-02-02")

		self.assertEqual(frappe.db.get_value("Loan", loan.name, "days_past_due"), 2)

		update_days_past_due_in_loans(posting_date="2023-02-05")
		self.assertEqual(frappe.db.get_value("Loan", loan.name, "days_past_due"), 5)

	def test_accumulated_amounts(self):
		pledge = [{"loan_security": "Test Security 1", "qty": 4000.00}]

		loan_application = create_loan_application(
			"_Test Company", self.applicant, "Demand Loan", pledge
		)
		create_pledge(loan_application)
		loan = create_demand_loan(
			self.applicant, "Demand Loan", loan_application, posting_date=get_first_day(nowdate())
		)
		loan.submit()

		first_date = "2019-10-01"
		last_date = "2019-10-30"

		no_of_days = date_diff(last_date, first_date) + 1
		accrued_interest_amount = (loan.loan_amount * loan.rate_of_interest * no_of_days) / (
			days_in_year(get_datetime(first_date).year) * 100
		)
		make_loan_disbursement_entry(loan.name, loan.loan_amount, disbursement_date=first_date)
		process_loan_interest_accrual_for_demand_loans(posting_date=last_date)
		loan_interest_accrual = frappe.get_doc("Loan Interest Accrual", {"loan": loan.name})

		self.assertEqual(flt(loan_interest_accrual.interest_amount, 0), flt(accrued_interest_amount, 0))

		next_start_date = "2019-10-31"
		next_end_date = "2019-11-29"

		no_of_days = date_diff(next_end_date, next_start_date) + 1
		process = process_loan_interest_accrual_for_demand_loans(posting_date=next_end_date)
		new_accrued_interest_amount = (loan.loan_amount * loan.rate_of_interest * no_of_days) / (
			days_in_year(get_datetime(first_date).year) * 100
		)

		total_pending_interest_amount = flt(accrued_interest_amount + new_accrued_interest_amount, 0)

		loan_interest_accrual = frappe.get_doc(
			"Loan Interest Accrual", {"loan": loan.name, "process_loan_interest_accrual": process}
		)
		self.assertEqual(
			flt(loan_interest_accrual.total_pending_interest_amount, 0), total_pending_interest_amount
		)
