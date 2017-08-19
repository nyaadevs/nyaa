#!/usr/bin/env python3
import sqlalchemy

from nyaa import create_app, models
from nyaa.extensions import db

app = create_app('config')

NYAA_CATEGORIES = [
    {
        'name': 'Anime',
        'subcats': [
            {'name': 'Anime Music Video', 'title': 'AMV'},
            {'name': 'English-translated', 'title': 'English'},
            {'name': 'Non-English-translated', 'title': 'Non-English'},
            {'name': 'Raw'},
        ]
    },
    {
        'name': 'Audio',
        'subcats': [
            {'name': 'Lossless'},
            {'name': 'Lossy'}
        ]
    },
    {
        'name': 'Literature',
        'subcats': [
            {'name': 'English-translated', 'title': 'English'},
            {'name': 'Non-English-translated', 'title': 'Non-English'},
            {'name': 'Raw'},
        ]
    },
    {
        'name': 'Live Action',
        'subcats': [
            {'name': 'English-translated', 'title': 'English'},
            {'name': 'Idol/Promotional Video', 'title': 'Idol/PV'},
            {'name': 'Non-English-translated', 'title': 'Non-English'},
            {'name': 'Raw'},
        ]
    },
    {
        'name': 'Pictures',
        'subcats': [
            {'name': 'Graphics'},
            {'name': 'Photos'}
        ]
    },
    {
        'name': 'Software',
        'subcats': [
            {'name': 'Applications', 'title': 'Apps'},
            {'name': 'Games'}
        ]
    },
]

SUKEBEI_CATEGORIES = [
    {
        'name': 'Art',
        'subcats': [
            {'name': 'Anime'},
            {'name': 'Doujinshi'},
            {'name': 'Games'},
            {'name': 'Manga'},
            {'name': 'Pictures'},
            {'name': 'Audio'},
        ]
    },
    {
        'name': 'Real Life',
        'subcats': [
            {'name': 'Photobooks and Pictures', 'title': 'Pictures'},
            {'name': 'Videos'},
        ]
    },
]


def add_categories(categories, main_class, sub_class):
    for main_cat in categories:
        sub_categories = main_cat.get('subcats', [])
        main_cat = main_class(name=main_cat['name'],
                              title=main_cat.get('title', main_cat['name']))
        for i, sub_cat in enumerate(sub_categories):
            # Composite keys can't autoincrement, set sub_cat id manually (index+1)
            sub_cat = sub_class(id=i+1, name=sub_cat['name'],
                                title=sub_cat.get('title', sub_cat['name']),
                                main_category=main_cat)
        db.session.add(main_cat)


if __name__ == '__main__':
    with app.app_context():
        # Test for the user table, assume db is empty if it's not created
        database_empty = False
        try:
            models.User.query.first()
        except (sqlalchemy.exc.ProgrammingError, sqlalchemy.exc.OperationalError):
            database_empty = True

        print('Creating all tables...')
        db.create_all()

        nyaa_category_test = models.NyaaMainCategory.query.first()
        if not nyaa_category_test:
            print('Adding Nyaa categories...')
            add_categories(NYAA_CATEGORIES, models.NyaaMainCategory, models.NyaaSubCategory)

        sukebei_category_test = models.SukebeiMainCategory.query.first()
        if not sukebei_category_test:
            print('Adding Sukebei categories...')
            add_categories(SUKEBEI_CATEGORIES, models.SukebeiMainCategory, models.SukebeiSubCategory)

        db.session.commit()

        if database_empty:
            print('Remember to run the following to mark the database up-to-date for Alembic:')
            print('./db_migrate.py stamp head')
            # Technically we should be able to do this here, but when you have
            # Flask-Migrate and Flask-SQA and everything... I didn't get it working.
