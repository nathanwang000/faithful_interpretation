// local storage used for tracking
function track_add(e) { // this has really bad complexity though O(nlogn)
    // e is the element to add
    var set = new Set(JSON.parse(localStorage.track))
    set.add(e)
    localStorage.track = JSON.stringify(Array.from(set))
}

function track_delete(e) {
    // e is the element to delete
    var set = new Set(JSON.parse(localStorage.track))
    set.delete(e)
    localStorage.track = JSON.stringify(Array.from(set))
}

function track_has(e) {
    // e is the element to query
    var set = new Set(JSON.parse(localStorage.track))
    return set.has(e)
}

function track_basis() {
    var index = parseInt($('#track_index').text())
    // add the index name to the set
    if (this.checked) {
	track_add(index)
    } else {
	track_delete(index)
    }
}

/* for image editing */
function basis_edit() {
    $('img:not(.edit):not(.basis):not(.basis_demo)').click(function(){
	var $this = $(this)
	var src=$this.attr('src')
	if (src[0] == '/') {
	    src = src.slice(1)
	}
	window.location = '/basis/' + src.split('/').join('^')
    })

    $('img.basis').click(function(){
	var $this = $(this)
	var src=$this.attr('src')
	if (src[0] == '/') {
	    src = src.slice(1)
	}
	window.location = '/concepts/' + src.split('/').join('^')
    })

    function basename(path) {
	return path.split('/').reverse()[0];
    }

    $('img.basis_demo').click(function(){
	var $this = $(this)
	var cururl = $(location).attr('href');
	var src = basename(cururl)
	if (src[0] == '/') {
	    src = src.slice(1)
	}
	window.location = '/basis/' + src.split('/').join('^')
    })
}

/* resorting javascript */
function resort(mode='positive') {
    sort_funcs = {
	'positive': function(a, b) {return b[0] - a[0]},
	'negative': function(a, b) {return a[0] - b[0]},
	'abs': function(a, b) {return Math.abs(b[0]) - Math.abs(a[0])},
    }
    return function() {
	var top = $("input#top").val()
	if (top === undefined) {
	    console.log('no top')
	    return
	}
	var images = JSON.parse(document.getElementById('images_to_sort').innerHTML);
	var names = JSON.parse(document.getElementById('images_name').innerHTML);	
	// go through id [(theta, image_path)] pairs
	for (cat_id in images) {
	    if (mode == 'mix') {
		let p = images[cat_id].concat().sort(sort_funcs['positive'])
		let n = images[cat_id].concat().sort(sort_funcs['negative'])
		let halfp = Math.floor(top/2)
		let halfn = Math.ceil(top/2)		
		images[cat_id] = p.slice(0,halfp).concat(n.slice(0,halfn))
	    } else if (mode == 'track') {
		// sort all images
		images[cat_id].sort(sort_funcs['abs'])
		// append the original sorted order to each image
		images[cat_id] = images[cat_id].map(function(e, i) {
		    return [e[0],e[1],e[2],i]
		})
		// get all tracked images, and untracked images
		var tracked = images[cat_id].filter(function(a) {
		    return track_has(a[2]) })
		var untracked = images[cat_id].filter(function(a) {
		    return !track_has(a[2]) })
		// sort tracked images, and untracked images
		tracked.sort(sort_funcs['abs'])		
		untracked.sort(sort_funcs['abs'])

		if (tracked.length >= top) {
		    images[cat_id] = tracked
		} else {
		    // if tracked images has less than top, kickout top - #track
		    // from not tracked images and resort the top few
		    images[cat_id] = untracked.slice(0,top-tracked.length).
			concat(tracked)
		    images[cat_id].sort(sort_funcs['abs'])
		}
	    }else {
		images[cat_id].sort(sort_funcs[mode])
	    }
	}
	// update page content
	content = []
	for (cat_id in images) {
	    content.push('<div class="row" style="background-color:rgb(224,224,224)">')
	    content.push('<div>')
	    content.push(cat_id.toString() + ': ' + names[cat_id])
	    content.push('</div>')
	    content.push('</div>')
	    content.push('<div class="row text-center text-lg-left">')
	    for (ind in images[cat_id].slice(0,top)) {
		var theta = images[cat_id][ind][0]
		var image = images[cat_id][ind][1]
		var index = images[cat_id][ind][2]
		content.push('<div class="col-lg-1 col-md-4 col-xs-6">')
		if (theta > 0) {
		    content.push('<p style="color:green">' + theta.toFixed(3) + '</p>')	
		} else {
		    content.push('<p style="color:red">' + theta.toFixed(3) + '</p>')
		}

		content.push('<a class="d-block mb-4 h-100">')
		content.push('<img class="img-fluid"')  // img-thumbnail
		content.push('src='+ image + ' alt=""/>')

		// tracked box
		content.push('<div class="input-color">')
		if (track_has(index) && mode === 'track') {
		    var rank = images[cat_id][ind][3]
		    content.push('<p>' + (ind - rank) + '</p>')
		    content.push('<div class="color-box" style="background-color:#FF850A;"></div>')		    
		} else{
		    content.push('<p style="display:None">Inv</p>')
		}

		content.push('</div>')
		
		/content.push('</a>')
		content.push('</div>')
	    }
	    content.push('</div>')	
	}
	$('#main_board').html(content.join('\n'))
	basis_edit()
    }
}

// select basis
$('#select_basis').click(function() {
    var impath = $(this).children('#impath').text()
    var index = parseInt($(this).children('#index').text())    
    
    $.ajax({
    	type: "POST",
    	url: "/basis/",
    	data: {
    	    impath: impath,
	    index: index
    	}
    }).done(function(){
    	console.log('data url sent');
	$('img#display_img').attr("src", '/' + impath)
    });
})

//***************************** main
// sorting
$('a.pos').click(resort('positive'))
$('a.neg').click(resort('negative'))
$('a.abs').click(resort('abs'))
$('a.track').click(resort('track'))
$('a.mix').click(resort('mix'))
$('#main_board').ready(resort('track'))
// basis editing
basis_edit()
$('input#track_checkbox').ready(function() {
    var index = parseInt($('#track_index').text())    
    if (localStorage.track===undefined) {
	// should really be set, but since
	// localStorage only stores string, this is a 
	localStorage.track = JSON.stringify(new Array())
    }
    $('input#track_checkbox').prop('checked', track_has(index))
})
$('input#track_checkbox').click(track_basis)

$("#calc_Ainv").click(function() {
    console.log('calc Ainv clicked')
    $.ajax({
	type: "POST",
	url: '/update_Ainv'
    }).done(function(){
	//console.log('add_task_done')
    })
})

