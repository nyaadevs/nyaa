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