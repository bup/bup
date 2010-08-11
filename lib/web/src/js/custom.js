var Bup = {
	templates : {
		file :
			'<div id="{{path}}" class="file_wrapper">'
			+ '<table cellspacing="0">'
			+ '<thead><tr><th colspan="2">{{name}}</th></tr></thead>' 
			+ '<tbody>'

			+ '{{#size}}'
			+ 	'<tr><th>Size</th><td>{{size}}</td></tr>'
			+ '{{/size}}'

			+ '{{#permissions}}'
			+ 	'<tr><th>Permissions</th><td>{{permissions}}</td></tr>'
			+ '{{/permissions}}'

			+ '{{#filetype}}'
			+ 	'<tr><th>Filetype</th><td>{{filetype}}</td></tr>'
			+ '{{/filetype}}'

			+ '<tr><td colspan="2"><a href="{{path}}">Open file</a></tr>'
			+ '</tbody></table></div>',

		//TODO make this use a parital
		directory :
			'<div id="{{path}}" class="directory_wrapper">'
			+ '<table cellspacing="0">'
			+ '<thead><tr><th>Filetype</th><th>Size</th></tr></thead>'
			+ '<tbody>'

			+ '{{#rows}}'
			+	'{{{.}}}'
			+ '{{/rows}}'

			+ '</tbody>'
			+ '</table></div>',

		//TODO make this use a parital
		directory_row_directory :
			'<tr class="directory"><td>'
			+ '<a href="#" data-path="{{path}}">'
			+ '{{name}}'
			+ '</a>'
			+ '</td>'
			+ '<td>&nbsp;</td>',

		//TODO make this use a parital
		directory_row_file :
			'<tr class="file"><td>'
			+ '<a href="#" data-path="{{path}}">'
			+ '{{name}}'
			+ '</a>'
			+ '</td>'
			+ '<td>{{size}}</td>'
	},

	renderDirectory: function (directory_data) {
		var directory_path = directory_data.path;

		var directory_rows = [];

		$(directory_data.items).each(function() {
			if (this.name.match('\/$') || this.name.match('@$')) {
				// this is a directory
				directory_rows.push(
					Mustache.to_html(Bup.templates.directory_row_directory, this)
				);
			} else {
				// this is a file
				directory_rows.push(
					Mustache.to_html(Bup.templates.directory_row_file, this)
				);
			}
		});

		var directory_data = {
			'path' : directory_path,
			'rows' : directory_rows
		}
		//TODO make this use a parital
		var html = Mustache.to_html(this.templates.directory, directory_data);
		$('#directories #clearing').before($(html));
		this.resizeDirectories();
		$('#directories_wrapper').scrollLeft($('#directories_wrapper').width());
	},

	renderFile: function (file_data) {
		html = Mustache.to_html(this.templates.file, file_data);
		$('#directories #clearing').before($(html));

		this.resizeDirectories();
		this.highlightPath(file_data.path);
	},

	showDirectory: function (directory_path) {
		$('#directories').children().each(function () {
			var id = $(this).attr('id');
			if (id != 'clearing') {
				if (!directory_path.match('^' + id) || directory_path == id) {
					$(this).remove();
				}
			}
		});

		//$('#directories #clearing').before(this.renderDirectory_testing(directory_path));
		$.getJSON(directory_path + '?json=1', function (data) { Bup.renderDirectory(data); })

		$('#breadcrumb').html(this.renderBreadcrumb(directory_path));
		this.highlightPath(directory_path);
	},

	resizeDirectories: function () {
		var max_height = 0;
		var directories = $('#directories');
		directories.children().each(function () {
			if ($(this).height() > max_height) {
				max_height = $(this).height();
			}
		});
		directories.children().each(function () {
			if ($(this).attr('id') != 'clearing') {
				$(this).height(max_height);
			}
		});
		directories.height(max_height);
		directories.width((directories.children().length - 1) * 301);
	},

	showFile: function (file_path) {
		var path_array = file_path.split('/');
		path_array.pop();
		$.getJSON(file_path + '?json=1', function (data) { Bup.renderFile(data); })
	},

	renderBreadcrumb: function (path) {
		var path_array = path.split('/');
		var html = '<a href="#" data-path="/">[root]</a>';
		for (var i=1; i<path_array.length-1; i++) {
			var subpath = '';
			for (var j=1; j<=i; j++) {
				subpath += '/' + path_array[j];
			}
			html += ' / <a href="#" data-path="' + subpath + '">' + path_array[i] + '</a>';
		}
		html += ' / <strong>' + path_array[path_array.length-1] + '</strong>';
		return html;
	},

	highlightPath: function (path) {
		$('#directories').children().each(function () {
			var id = $(this).attr('id');
			if (id != 'clearing') {
				$(this).find('tbody tr').each(function () {
					var currentpath = $(this).find('a').attr('data-path');
					if (path.match('^' + currentpath)) {
						$(this).addClass('active');
					} else {
						$(this).removeClass('active');
					}
				});
			}
		});
	}
}

$(function () {
	Bup.showDirectory('/');

	$('#directories .directory a').live('click', function() {
		var path = $(this).attr('data-path');
		Bup.showDirectory(path);
		return false;
	});

	$('#directories .file a').live('click', function() {
		var path = $(this).attr('data-path');
		Bup.showFile(path);
		return false;
	});

	$('#breadcrumb a').live('click', function() {
		var path = $(this).attr('data-path');
		Bup.showDirectory(path);
	});
});
