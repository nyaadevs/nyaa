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
	$(':file').on('fileselect', function(event, numFiles, label) {

		var input = $(this).parent().prev().find(':text'),
			log = numFiles > 1 ? numFiles + ' files selected' : label;

		if (input.length) {
			input.val(log);
		} else {
			if (log) alert(log);
		}
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
function _format_date(date) {
	var pad = function (n) { return ("00" + n).slice(-2); }
	var ymd = date.getFullYear() + "-" + pad(date.getMonth()+1) + "-" + pad(date.getDate());
	var hm = pad(date.getHours()) + ":" + pad(date.getMinutes());
	return ymd + " " + hm;
}

// Add title text to elements with data-timestamp attribute
document.addEventListener("DOMContentLoaded", function(event) {
	var now_timestamp = (Date.now() / 1000) | 0; // UTC timestamp in seconds

	var timestamp_targets = document.querySelectorAll('[data-timestamp]');
	for (var i = 0; i < timestamp_targets.length; i++) {
		var target = timestamp_targets[i];
		var torrent_timestamp = parseInt(target.getAttribute('data-timestamp'));
		if (torrent_timestamp) {
			var timedelta = now_timestamp - torrent_timestamp;
			target.setAttribute('title', _format_time_difference(timedelta));

			target.innerText = _format_date(new Date(torrent_timestamp*1000));
		}
	};

	var header_date = document.querySelector('.hdr-date');
	if (header_date) {
		header_date.setAttribute('title', 'In local time');
	}
});

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
      targetEl.innerHTML = marked(sourceSelector.value.trim(), { sanitize: true, breaks:true });
    });
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
