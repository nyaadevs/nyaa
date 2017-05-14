import sys
from nyaa import app, db, models

# Create tables

db.create_all()

# Insert categories and insert if it doesn't eixst
existing_cats = models.MainCategory.query.all()
if not existing_cats:
    if app.config['SITE_FLAVOR'] == 'nyaa':
        CATEGORIES = [
            ('Anime', ['Anime Music Video', 'English-translated', 'Non-English-translated', 'Raw']),
            ('Audio', ['Lossless', 'Lossy']),
            ('Literature', ['English-translated', 'Non-English-translated', 'Raw']),
            ('Live Action', ['English-translated', 'Idol/Promotional Video', 'Non-English-translated', 'Raw']),
            ('Pictures', ['Graphics', 'Photos']),
            ('Software', ['Applications', 'Games']),
        ]
    elif app.config['SITE_FLAVOR'] == 'sukebei':
        CATEGORIES = [
            ('Art', ['Anime', 'Doujinshi', 'Games', 'Manga', 'Pictures']),
            ('Real Life', ['Photobooks / Pictures', 'Videos']),
        ]
    else:
        CATEGORIES = []

    for main_cat_name, sub_cat_names in CATEGORIES:
        main_cat = models.MainCategory(name=main_cat_name)
        for i, sub_cat_name in enumerate(sub_cat_names):
            # Composite keys can't autoincrement, set sub_cat id manually (1-index)
            sub_cat = models.SubCategory(id=i+1, name=sub_cat_name, main_category=main_cat)
        db.session.add(main_cat)

    db.session.commit()

# Create fulltext index

if app.config['USE_MYSQL']:
    db.engine.execute('ALTER TABLE ' + app.config['TABLE_PREFIX'] + 'torrents ADD FULLTEXT KEY (display_name)')

