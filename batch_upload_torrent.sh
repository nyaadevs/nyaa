up_t() { curl -F "category=1_2" -F "torrent_file=@$1" 'http://localhost:5500/upload'; }
for x in test_torrent_batch/*; do up_t "$x"; done