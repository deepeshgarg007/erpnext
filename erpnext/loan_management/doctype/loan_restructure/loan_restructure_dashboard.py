def get_data():
	return {
		"fieldname": "loan_restructure",
		"non_standard_fieldnames": {
			"Loan Balance Adjustment": "reference_name",
		},
		"transactions": [
			{"items": ["Loan Balance Adjustment", "Loan Repayment Schedule"]},
		],
	}
