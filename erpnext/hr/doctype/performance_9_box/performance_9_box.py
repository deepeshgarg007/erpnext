# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.model.document import Document

class Performance9BOX(Document):
	pass

@frappe.whitelist()
def get_employees(designation, from_date, to_date, employee=None):
	result_wise_map = {}

	query_filters = {
		'designation': designation,
		'docstatus': 1,
		'start_date': ('>=', from_date),
		'end_date': ('<=', to_date),
	}

	if employee:
		query_filters.update({
			'employee': employee
		})

	employee_list = frappe.db.get_all('Appraisal', fields=['name', 'employee_name', 'results', 'leadership'],
		filters=query_filters, order_by='results, leadership')

	for d in employee_list:
		result_wise_map.setdefault(d.results + d.leadership, [])
		result_wise_map[d.results + d.leadership].append(d.employee_name)

	return result_wise_map