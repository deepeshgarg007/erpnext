// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.provide("erpnext.performance_9_box");

frappe.ui.form.on('Performance 9 BOX', {
	refresh: function(frm) {
		frm.disable_save();
		frm.set_value('from_date', frappe.datetime.add_months(frappe.datetime.nowdate(), -12));
		frm.set_value('to_date', frappe.datetime.nowdate());
	},

	from_date: function(frm) {
		frm.trigger('designation');
	},

	to_date: function(frm) {
		frm.trigger('designation');
	},

	designation: function(frm) {

		if (!frm.doc.designation) {
			return;
		}

		if (!frm.doc.from_date || !frm.doc.to_date) {
			frappe.throw(__('Please enter From Date and To Date'));
		}

		if (frm.doc.to_date < frm.doc.from_date) {
			frappe.throw(__('From Date cannot be before To Date'));
		}

		frappe.call({
			method: 'erpnext.hr.doctype.performance_9_box.performance_9_box.get_employees',
			args: {
				'designation': frm.doc.designation,
				'from_date': frm.doc.from_date,
				'to_date': frm.doc.to_date
			},
			callback: function(r) {
				console.log(r);
				frm.set_df_property('9_box_section', 'hidden', 0);
				let employee_map = r.message;
				let results = ['A', 'B', 'C'];
				let leaderships = ['-', '/', '+'];

				let template = '';

				template = template + `<table style="text-align:center;
					margin-top: 50px; margin-left: -50px"><tbody>`;

				$.each(results, function(i, result) {
					template = template + `<tr>`;
					$.each(leaderships, function(j, leadership) {

						if (j == 0) {
							template = template + `<td height="200px" >${results[i]}</td>`;
						}

						let names = ''
						if (employee_map[result+leadership]) {
							names = employee_map[result+leadership].join('<br>');
						}
						template = template + `<td width="30%" height="200px" style="border: 1px solid">${names}</td>`;
					});
					template = template + `</tr>`
				});

				template = template + erpnext.performance_9_box.get_leadership_section();
				template = template + `</tbody></table>`;

				template = template + erpnext.performance_9_box.add_legends();
				$(frm.fields_dict.box.wrapper).empty().html(template);
				frm.refresh_fields();
			}
		});
	},
});

erpnext.performance_9_box.get_leadership_section = function() {
	let template = '';

	template = template + `<tr>`;
	let leaderships = ['', '-', '/', '+'];

	$.each(leaderships, function(j, leadership) {
		template = template + `<td width="359px">${leadership}</td>`;
	});
	template = template + `</tr>`;

	return template
}

erpnext.performance_9_box.add_legends = function() {

	let template =`<table class="table table-bordered" margin-top: 50px">
		<tr>
			<th style="border:none">Results</th>
			<th style="border:none">Leadership</th>
		</tr>
		<tr>
			<td style="border:none"><b>A</b> = Exceeds Expectations</td>
			<td style="border:none"><b>+</b> = Consistently demonstrates the leadership principles at high level of effectiveness</td>
		</tr>
		<tr>
			<td style="border:none"><b>B</b> = Meets Expectations</td>
			<td style="border:none"><b>/</b> = Demonstrates the leadership principles at an  appropriate level for the role</td>
		</tr>
		<tr>
			<td style="border:none"><b>C</b> = Does Not Meet Expectations</tds>
			<td style="border:none"><b>-</b> = Does not demonstrates the leadership principles or needs improvement</td>
		</tr>
		</table>`;

	return template
}