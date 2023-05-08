def get_data():
	return {
		"fieldname": "loan",
		"non_standard_fieldnames": {
			"Loan Disbursement": "against_loan",
			"Loan Repayment": "against_loan",
		},
		"transactions": [
			{
				"items": [
					"Loan Repayment Schedule",
					"Loan Security Pledge",
					"Loan Security Shortfall",
					"Loan Disbursement",
				]
			},
			{
				"items": [
					"Loan Repayment",
					"Loan Interest Accrual",
					"Loan Write Off",
				]
			},
			{"items": ["Loan Security Unpledge", "Days Past Due Log"]},
		],
	}
