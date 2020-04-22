// Copyright (c) 2016, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt
/* eslint-disable */

frappe.query_reports["Bench Chart"] = {
	"filters": [
		{
			"fieldname":"company",
			"label": __("Company"),
			"fieldtype": "Link",
			"default": frappe.defaults.get_default('company'),
			"options": "Company",
			"reqd": 1
		},
		{
			"fieldname":"designation",
			"label": __("Designation"),
			"fieldtype": "Link",
			"options": "Designation"
		},
		{
			"fieldname":"date_range",
			"label": __("Date Range"),
			"fieldtype": "DateRange"
		}
	],

	get_datatable_options(options) {
		return Object.assign(options, {
			inlineFilters: false,
			cellHeight: 100
		})
	},
};
