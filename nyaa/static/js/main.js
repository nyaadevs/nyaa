document.addEventListener("DOMContentLoaded", function(event) { // wait for content to load because this script is above the link
	document.getElementById('themeToggle').addEventListener('click', function(e) { // listen for click event
		e.preventDefault(); // keep link from default action, which going to top of the page
		toggleDarkMode();   // toggle theme
	});
});


// Credit: https://www.abeautifulsite.net/whipping-file-inputs-into-shape-with-bootstrap-3
// We can attach the `fileselect` event to all file inputs on the page
$(document).on('change', ':file', function() {
	var input = $(this),
		numFiles = input.get(0).files ? input.get(0).files.length : 1,
		label = input.val().replace(/\\/g, '/').replace(/.*\//, '');
	input.trigger('fileselect', [numFiles, label]);
});


// We can watch for our custom `fileselect` event like this
$(document).ready(function() {
	var dropZone = $('#upload-drop-zone'),
		fileWarning = $('<div/>').html('Invalid file selected. Please select a torrent file.')
			.css({  id: 'file-warning', class: 'alert alert-warning text-center',
					role: 'alert', width: $('.form-group:first').width() + 'px' })
			.hide().insertAfter(dropZone);

	$(':file').on('fileselect', function(event, numFiles, label) {
		var input = $(this).parent().prev().find(':text'),
			log = numFiles > 1 ? numFiles + ' files selected' : label;

		if (label.endsWith('.torrent')) {
			fileWarning.fadeOut('fast');
		} else {
			fileWarning.fadeIn('fast');
			input.val('');
			return false;
		}

		if (input.length) {
			input.val(log);
		} else {
			if (log) alert(log);
		}
	});

	// Drag & Drop zone for upload page
	$('body').on('dragenter', function(event) {
		event.preventDefault();
		dropZone.css({ 'visibility': 'visible', 'opacity': 1 });
	});

	dropZone.on('dragleave', function(event) {
		event.preventDefault();
		$(this).css({ 'visibility': 'hidden', 'opacity': 0 });
	});

	dropZone.on('dragover', function(event) {
		event.preventDefault();
	});

	dropZone.on('drop dragdrop', function(event) {
		event.preventDefault();
		var files = event.originalEvent.dataTransfer.files;
		$('#torrent_file')[0].files = files;
		$(this).css({ 'visibility': 'hidden', 'opacity': 0 });
	});
	
	// Collapsible file lists
	$('.torrent-file-list a.folder').click(function(e) {
		e.preventDefault();
		$(this).blur().children('i').toggleClass('fa-folder-open fa-folder');
		$(this).next().stop().slideToggle(250);
	});
});

function _format_time_difference(seconds) {
	var units = [
		["year", 365*24*60*60],
		["month", 30*24*60*60],
		["week", 7*24*60*60],
		["day", 24*60*60],
		["hour", 60*60],
		["minute", 60],
		["second", 1]
	];
	var suffix = " ago";
	var prefix = "";
	if (seconds < 0) {
		suffix = "";
		prefix = "After ";
	} else if (seconds == 0) {
		return "Just now"
	}

	var parts = [];
	for (var i = 0; i < units.length; i++) {
		var scale = units[i];

		var m = (seconds / scale[1]) | 0;

		if (m > 0) {
			// N unit(s)
			parts.push( m.toString() + " " + scale[0] + (m == 1 ? "" : "s") );
			seconds -= m*scale[1];
		}
	}
	return prefix + parts.join(" ") + suffix;
}
function _format_date(date, show_seconds) {
	var pad = function (n) { return ("00" + n).slice(-2); }
	var ymd = date.getFullYear() + "-" + pad(date.getMonth()+1) + "-" + pad(date.getDate());
	var hm = pad(date.getHours()) + ":" + pad(date.getMinutes());
	var s = show_seconds ? ":" + pad(date.getSeconds()) : ""
	return ymd + " " + hm + s;
}

// Add title text to elements with data-timestamp attribute
document.addEventListener("DOMContentLoaded", function(event) {
	var now_timestamp = (Date.now() / 1000) | 0; // UTC timestamp in seconds

	var timestamp_targets = document.querySelectorAll('[data-timestamp]');
	for (var i = 0; i < timestamp_targets.length; i++) {
		var target = timestamp_targets[i];
		var torrent_timestamp = parseInt(target.getAttribute('data-timestamp'));
		var swap_flag = target.getAttribute('data-timestamp-swap') != null;

		if (torrent_timestamp) {
			var timedelta = now_timestamp - torrent_timestamp;

			var formatted_date = _format_date(new Date(torrent_timestamp*1000), swap_flag);
			var formatted_timedelta = _format_time_difference(timedelta);
			if (swap_flag) {
				target.setAttribute('title', formatted_date);
				target.innerText = formatted_timedelta;
			} else {
				target.setAttribute('title', formatted_timedelta);
				target.innerText = formatted_date;
			}
		}
	};

	var header_date = document.querySelector('.hdr-date');
	if (header_date) {
		header_date.setAttribute('title', 'In local time');
	}
});

var markdownOptions = {
	html : false,
	breaks : true,
	linkify: true,
	typographer:  true
}
var markdown = window.markdownit(markdownOptions);
markdown.renderer.rules.table_open = function (tokens, idx) {
	// Format tables nicer (bootstrap). Force auto-width (default is 100%)
	return '<table class="table table-striped table-bordered" style="width: auto;">';
}

// Initialise markdown editors on page
document.addEventListener("DOMContentLoaded", function() {
	var markdownEditors = Array.prototype.slice.call(document.querySelectorAll('.markdown-editor'));

	markdownEditors.forEach(function (markdownEditor) {
		var fieldName = markdownEditor.getAttribute('data-field-name');

		var previewTabSelector = '#' + fieldName + '-preview-tab';
		var targetSelector = '#' + fieldName + '-markdown-target';
		var sourceSelector = markdownEditor.querySelector('.markdown-source');

		var previewTabEl = markdownEditor.querySelector(previewTabSelector);
		var targetEl = markdownEditor.querySelector(targetSelector);

		previewTabEl.addEventListener('click', function () {
			var rendered = markdown.render(sourceSelector.value.trim());
			targetEl.innerHTML = rendered;
		});
	});
});

// Render markdown from elements with "markdown-text" attribute
document.addEventListener("DOMContentLoaded", function() {
	var markdownTargets = document.querySelectorAll('[markdown-text]');
	for (var i = 0; i < markdownTargets.length; i++) {
		var target = markdownTargets[i];
		var rendered = markdown.render(target.innerHTML);
		target.innerHTML = rendered;
	}
});

// Adds torrent mass action functionality when user is permitted to do so.
document.addEventListener('DOMContentLoaded', function () {
	var form = document.querySelector('#torrent-mass-action-form');
	if (!form) {
		return;
	}

	var state = {};
	var allSelected = false;

	var torrentActionSelectEl = form.querySelector('#action');
	var categorySelectEl = form.querySelector('.category-select');
	var selectAllBtn = form.querySelector('#select-all');
	var torrentTable = document.querySelector('.torrent-list');

	Object.defineProperty(state, 'allSelected', {
		get: function () { return allSelected; },
		set: function (value) {
			var checkboxes = Array.prototype.slice.call(torrentTable.querySelectorAll('input[type="checkbox"]'));
			checkboxes.forEach(function (chkBox) {
				chkBox.checked = value;
			});

			allSelected = value;
		}
	});

	torrentActionSelectEl.addEventListener('change', function (event) {
		if (event.target.value === 'move_category') {
			categorySelectEl.classList.remove('hidden');
		} else {
			categorySelectEl.classList.add('hidden');
		}
	});

	selectAllBtn.addEventListener('click', function () {
		event.preventDefault();
		state.allSelected = !state.allSelected;
	});
});

// 
// This is the unminified version of the theme changer script in the layout.html @ line: 21
// ===========================================================
// if (typeof(Storage) !== 'undefined') {
// 	var bsThemeLink = document.getElementById('bsThemeLink');

// 	if (localStorage.getItem('theme') === 'dark') {
// 		setThemeDark();
// 	}

// 	function toggleDarkMode() {
// 		if (localStorage.getItem('theme') === 'dark') {
// 			setThemeLight();
// 		} else {
// 			setThemeDark();
// 		}
// 	}

// 	function setThemeDark() {
// 		bsThemeLink.href = '/static/css/bootstrap-dark.min.css';
// 		localStorage.setItem('theme', 'dark');
// 	}

// 	function setThemeLight() {
// 		bsThemeLink.href = '/static/css/bootstrap.min.css';
// 		localStorage.setItem('theme', 'light');
// 	}
// }
