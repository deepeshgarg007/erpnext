# Copyright (c) 2013, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import frappe
from frappe.utils import date_diff, getdate, cstr
from six import iteritems
from frappe import _

def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)
	return columns, data

def get_data(filters):
	data = []
	conditions = ''
	employee_detail_map = {}
	employee_appraisal_map = {}

	if filters.get('designation'):
		conditions += 'AND e.designation = %s' % frappe.db.escape(filters.get('designation'))

	employee_data = frappe.db.sql(
		""" SELECT
				e.employee_name, e.date_of_joining, e.department as current_department, e.designation as current_designation,
				ew.company_name, ew.designation, ew.total_experience, ed.school_univ, ed.qualification,
				iw.designation as previous_designation, iw.department as previous_department,
				iw.from_date, iw.to_date
			FROM `tabEmployee` e, `tabEmployee Education` ed, `tabEmployee External Work History` ew,
				`tabEmployee Internal Work History` iw
			WHERE ed.parent = e.name
			AND ew.parent = e.name
			AND iw.parent = e.name
			AND e.company = %s
			{conditions}
			ORDER BY e.employee, to_date DESC
		""".format(conditions=conditions), (filters.get('company')), as_dict=1)

	query_filters = {'docstatus': 1}

	if filters.get('designation'):
		query_filters.update({'designation': filters.get('designation')})

	if filters.get('date_range'):
		query_filters.update({'start_date': (">=", filters.get('date_range')[0])})
		query_filters.update({'end_date': ("<=", filters.get('date_range')[1])})

	appraisal_data = frappe.db.get_all('Appraisal', fields=['employee_name', 'results', 'leadership',
		'hi_po', 'strengths', 'considerations'], filters=query_filters, order_by='results, leadership')

	for d in appraisal_data:

		if not d.results or not d.leadership:
			continue

		employee_appraisal_map.setdefault(d.employee_name, {
			'rating': [],
			'strengths': [],
			'considerations': [],
			'hi_po': []
		})

		employee_appraisal_map[d.employee_name]['rating'].append(d.results + d.leadership)
		employee_appraisal_map[d.employee_name]['strengths'].append(cstr(d.strengths))
		employee_appraisal_map[d.employee_name]['considerations'].append(cstr(d.considerations))
		employee_appraisal_map[d.employee_name]['hi_po'].append(d.hi_po)


	for d in employee_data:
		employee_detail_map.setdefault(d.employee_name, {
			'name_title': '',
			'department': '',
			'company_history': [],
			'previous_experience': [],
			'education': [],
			'ratings': []
		})

		if not employee_detail_map[d.employee_name]['name_title']:
			name_title = frappe.bold(d.employee_name) + '<br>'
			name_title += cstr(d.current_designation) + ', ' + cstr(d.current_department) + '<br>'
			name_title += cstr(getdate(d.to_date or d.date_of_joining).year)
			employee_detail_map[d.employee_name]['name_title'] = name_title

		if not employee_detail_map[d.employee_name]['department']:
			employee_detail_map[d.employee_name]['department'] = d.current_department

		company_history = cstr(d.previous_designation) + ', (' + cstr(date_diff(d.to_date, d.from_date) // 365) + ')'

		if company_history not in employee_detail_map[d.employee_name]['company_history']:
			employee_detail_map[d.employee_name]['company_history'].append(company_history)

		previous_experience = cstr(d.company_name) + ' (' + cstr(d.total_experience) + ')' + '<br>' + cstr(d.designation)

		if previous_experience not in employee_detail_map[d.employee_name]['previous_experience']:
			employee_detail_map[d.employee_name]['previous_experience'].append(previous_experience)

		education = cstr(d.qualification) + ', ' + cstr(d.school_univ) + '<br>'

		if education not in employee_detail_map[d.employee_name]['education']:
			employee_detail_map[d.employee_name]['education'].append(education)

	for employee, value in iteritems(employee_detail_map):
		row = {}
		for key, value in iteritems(value):
			if isinstance(value, list):
				row[key] = '<br>'.join(value)
			else:
				row[key] = value

		row['rating'] = '<br>'.join(employee_appraisal_map.get(employee, {}).get('rating') or [])
		row['strengths'] = '<br>'.join(employee_appraisal_map.get(employee, {}).get('strengths') or [])
		row['considerations'] = '<br>'.join(employee_appraisal_map.get(employee, {}).get('considerations') or [])

		row['hi_po'] = 'Yes' if employee_appraisal_map.get(employee, {}).get('hi_po', []).count('Yes') \
			> employee_appraisal_map.get(employee, {}).get('hi_po', []).count('No') else 'No'

		data.append(row)

	return data


def get_columns(filters):
	columns = [
		{
			"label": _("Name/Title"),
			"fieldtype": "Data",
			"fieldname": "name_title",
			"width": 150
		},
		{
			"label": _("Department"),
			"fieldtype": "Link",
			"fieldname": "department",
			"options": "Department",
			"width": 150
		},
		{
			"label": _("Company History"),
			"fieldtype": "Data",
			"fieldname": "company_history",
			"width": 150
		},
		{
			"label": _("Previous Experience"),
			"fieldtype": "Data",
			"fieldname": "previous_experience",
			"width": 150
		},
		{
			"label": _("Education"),
			"fieldtype": "Data",
			"fieldname": "education",
			"width": 150
		},
		{
			"label": _("Rating"),
			"fieldtype": "Data",
			"fieldname": "rating",
			"width": 60
		},
		{
			"label": _("Strengths"),
			"fieldtype": "Data",
			"fieldname": "strengths",
			"width": 150
		},
		{
			"label": _("Considerations"),
			"fieldtype": "Data",
			"fieldname": "considerations",
			"width": 150
		},
		{
			"label": _("Hi-Po"),
			"fieldtype": "Data",
			"fieldname": "hi_po",
			"width": 150
		}
	]

	return columns
