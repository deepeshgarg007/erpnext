# -*- coding: utf-8 -*-
# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe, math
from frappe import _
from frappe.utils import flt, rounded
from frappe.model.mapper import get_mapped_doc
from frappe.model.document import Document

from erpnext.loan_management.doctype.loan.loan import get_monthly_repayment_amount, validate_repayment_method

class LoanApplication(Document):
	def validate(self):
		validate_repayment_method(self.repayment_method, self.loan_amount, self.repayment_amount, self.repayment_periods)
		self.set_loan_amount()
		self.validate_loan_amount()
		self.get_repayment_details()

	def on_submit(self):
		self.pledge_loan_securities()

	def on_cancel(self):
		self.unpledge_loan_securities()
	def validate_loan_amount(self):
		maximum_loan_limit = frappe.db.get_value('Loan Type', self.loan_type, 'maximum_loan_amount')
		if maximum_loan_limit and self.loan_amount > maximum_loan_limit:
			frappe.throw(_("Loan Amount cannot exceed Maximum Loan Amount of {0}").format(maximum_loan_limit))

	def get_repayment_details(self):
		if self.repayment_method == "Repay Over Number of Periods":
			self.repayment_amount = get_monthly_repayment_amount(self.repayment_method, self.loan_amount, self.rate_of_interest, self.repayment_periods)

		if self.repayment_method == "Repay Fixed Amount per Period":
			monthly_interest_rate = flt(self.rate_of_interest) / (12 *100)
			if monthly_interest_rate:
				min_repayment_amount = self.loan_amount*monthly_interest_rate
				if self.repayment_amount - min_repayment_amount <= 0:
					frappe.throw(_("Repayment Amount must be greater than " \
						+ str(flt(min_repayment_amount, 2))))
				self.repayment_periods = math.ceil((math.log(self.repayment_amount) -
					math.log(self.repayment_amount - min_repayment_amount)) /(math.log(1 + monthly_interest_rate)))
			else:
				self.repayment_periods = self.loan_amount / self.repayment_amount

		self.calculate_payable_amount()

	def calculate_payable_amount(self):
		balance_amount = self.loan_amount
		self.total_payable_amount = 0
		self.total_payable_interest = 0

		while(balance_amount > 0):
			interest_amount = rounded(balance_amount * flt(self.rate_of_interest) / (12*100))
			balance_amount = rounded(balance_amount + interest_amount - self.repayment_amount)

			self.total_payable_interest += interest_amount

		self.total_payable_amount = self.loan_amount + self.total_payable_interest

	def set_loan_amount(self):

		self.pledge_list = []
		if not self.loan_amount and self.is_secured_loan and self.loan_security_pledges:
			for security in self.loan_security_pledges:
				self.loan_amount += security.amount - (security.amount * security.haircut/100)
			self.pledge_list.append(security.loan_security)


	def pledge_loan_securities(self):
		frappe.db.sql("""UPDATE `tabLoan Security`
			set is_pledged = 1, loan_application = %s where
			name in (%s) """  % ('%s', ", ".join(['%s']*len(self.pledge_list))), tuple([self.name] + self.pledge_list))

	def unpledge_loan_securities(self):
		pledge_list = self.get_pledges()

		frappe.db.sql("""UPDATE `tabLoan Security`
			set is_pledged = 0 , loan_application = '' where
			name in (%s) """  % ", ".join(['%s']*len(pledge_list)), tuple(pledge_list))

	def get_pledges(self):
		return [ d.loan_security for d in self.loan_security_pledges]

@frappe.whitelist()
def make_loan(source_name, target_doc = None):
	doclist = get_mapped_doc("Loan Application", source_name, {
		"Loan Application": {
			"doctype": "Loan",
			"validation": {
				"docstatus": ["=", 1]
			}
		}
	}, target_doc)

	return doclist
