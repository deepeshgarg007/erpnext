// Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Loan Restructure", {
	refresh: function (frm) {
		frm.trigger("toggle_fields");
		frm.ignore_doctypes_on_cancel_all = ['Loan Balance Adjustment'];
	},

	new_repayment_method: function (frm) {
		frm.trigger("toggle_fields");
	},

	toggle_fields: function (frm) {
		frm.toggle_enable("new_monthly_repayment_amount", frm.doc.new_repayment_method == "Repay Fixed Amount per Period");
		frm.toggle_enable("new_repayment_period_in_months", frm.doc.new_repayment_method == "Repay Over Number of Periods");
	}
});
