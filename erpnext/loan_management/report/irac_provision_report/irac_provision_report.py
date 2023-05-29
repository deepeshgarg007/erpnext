# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cstr


def execute(filters=None):
	columns = get_columns(filters)
	data = get_data(filters)

	return columns, data


def get_columns(filters):
	columns = [
		{
			"fieldname": "loan",
			"label": "Loan",
			"fieldtype": "Link",
			"options": "Loan",
			"width": 150,
		},
		{
			"fieldname": "partner",
			"label": "Partner",
			"fieldtype": "Link",
			"options": "Company",
			"width": 150,
		},
		{
			"fieldname": "share",
			"label": "Company's Share",
			"fieldtype": "Percent",
			"width": 150,
		},
		{
			"fieldname": "pos",
			"label": "Principal Outstanding",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"fieldname": "own_pos",
			"label": "Own Principal Outstanding",
			"fieldtype": "Currency",
			"width": 150,
		},
		{
			"fieldname": "par_bucket",
			"label": "PAR Bucket",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"fieldname": "asset_classification",
			"label": "Asset Classification",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"fieldname": "asset_type",
			"label": "Asset Type",
			"fieldtype": "Data",
			"width": 150,
		},
		{
			"fieldname": "irac_provision_rate",
			"label": "IRAC Provision Rate",
			"fieldtype": "Percent",
			"width": 150,
		},
		{
			"fieldname": "irac_provision_amount",
			"label": "IRAC Provision Amount",
			"fieldtype": "Currency",
			"width": 150,
		},
	]

	return columns


def get_data(filters):
	data = []

	loan_details = frappe.db.get_all(
		"Loan",
		filters={
			"docstatus": 1,
			"status": ("in", ["Disbursed", "Partially Disbursed"]),
			"company": filters.get("company"),
		},
		fields=[
			"name",
			"total_payment",
			"total_principal_paid",
			"total_interest_payable",
			"company",
			"days_past_due",
			"asset_classification_code",
			"is_secured_loan",
		],
	)

	par_details = frappe.db.get_all(
		"Loan IRAC Provision Rate",
		filters={"parent": filters.get("company")},
		fields=["asset_classification_code", "asset_type", "provision_rate"],
	)

	print(par_details)

	par_details_map = {}
	for _range in par_details:
		par_details_map[_range.asset_classification_code] = _range

	for loan in loan_details:
		pos = loan.total_payment - loan.total_principal_paid - loan.total_interest_payable
		own_pos = pos * 100 / 100
		range_details = par_details_map.get(loan.asset_classification_code or "Standard")

		par_bucket = cstr(range_details.get("min_range")) + " to " + cstr(range_details.get("max_range"))
		row = {
			"loan": loan.name,
			"partner": loan.company,
			"share": 100,
			"pos": pos,
			"own_pos": own_pos,
			"par_bucket": "0" if not range_details.get("min_range") else par_bucket,
			"asset_classification": loan.asset_classification_code or "Standard",
			"asset_type": "Secured" if loan.is_secured else "Unsecured",
			"irac_provision_rate": range_details.get("provision_rate"),
			"irac_provision_amount": own_pos * range_details.get("provision_rate") / 100,
		}

		data.append(row)

	return data
