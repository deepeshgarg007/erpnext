// Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on('Loan Security Unpledge', {
	refresh: function(frm) {
		if (frm.doc.docstatus == 1 && frm.doc.unpledge_status == "Requested") {
			frm.add_custom_button("Approve", function(){
				frappe.call({
					method: "erpnext.loan_management.doctype.loan_security_unpledge.loan_security_unpledge.approve_unpledge_request",
					args: {
						loan: frm.doc.loan,
						unpledge_request: frm.doc.name
					},
					callback: function(r) {
						frm.reload_doc();
					}
				})
			});
		}
	}
});
